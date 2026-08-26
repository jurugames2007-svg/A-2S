"""SecOps asistido (v1.27): alcance criptográfico + ejecución defensiva.

Traduce el diseño de "authorization as technical control" a lo que se puede
construir con honestidad:

* **Vocabulario CERRADO**: ``recon`` | ``scan`` | ``analizar``. No existe ruta
  de código para explotación, volcado de datos, exfiltración ni evasión; un
  token que pida esas acciones se rechaza al crearlo.
* ``workspace/.a2s/scope.jwt``: payload base64url + firma HMAC-SHA256 con clave
  del workspace (``scope.key``, 32 bytes aleatorios). No hay CA externa: aviso
  honesto — el "seguro técnico" real es que el motor no contiene munición, no
  el formulario firmado.
* **simulación**: plan de ejecución completo sin tocar red ni lanzar procesos.
* **asistido**: solo adaptadores defensivos sobre el alcance verificado, con
  confirmación explícita para pasos de red; cada intento (incluidos los
  denegados) se registra en el ledger con hash chain.

Uso: ``a2s secops scope-create ...``, ``a2s secops scope-status``,
``a2s secops ejecutar OBJETIVO --modo simulacion|asistido``,
``GET /api/secops``, ``POST /api/secops/plan`` (solo simulación).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .ledger import Ledger
from .models import now_iso
from .pcb import _atomic_write

SAFE_ACTIONS: tuple[str, ...] = ("recon", "scan", "analizar")
ACCION_NOMBRE: dict[str, str] = {
    "recon": "reconocimiento HTTP/TLS de un activo propio",
    "scan": "escaneo de vulnerabilidades con escáner local instalado",
    "analizar": "análisis estático de un archivo del workspace",
}
UA = "A2S-SecOps/1.27 (autorizado; un GET por objetivo)"


# ---------------------------------------------------------------------------
# Alcance firmado (HMAC, vocabulario cerrado)
# ---------------------------------------------------------------------------

def _scope_dir(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace or "."), ".a2s")


def _key_path(workspace: str) -> str:
    return os.path.join(_scope_dir(workspace), "scope.key")


def _token_path(workspace: str) -> str:
    return os.path.join(_scope_dir(workspace), "scope.jwt")


def _clave(workspace: str) -> bytes:
    """Clave del workspace (se crea una vez, 32 bytes; nunca se exporta)."""
    path = _key_path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.isfile(path):
        with open(path, "wb") as fh:
            fh.write(os.urandom(32))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    with open(path, "rb") as fh:
        return fh.read()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _firma(key: bytes, body: str) -> str:
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def _valida_target(target: str) -> str:
    target = (target or "").strip().lower()
    if not target:
        raise ValueError("target vacío")
    if target == "*":
        return target
    try:
        ipaddress.ip_network(target, strict=False)
        return target
    except ValueError:
        pass
    if re.match(r"^[a-z0-9*][a-z0-9.\-*]*$", target) and "." in target:
        return target
    raise ValueError(f"objetivo inválido «{target}» (host, CIDR o '*')")


def crear_scope(workspace: str, targets: list[str], acciones: list[str],
                expires: str = "", firma: str = "") -> dict[str, Any]:
    """Crea/renueva el alcance firmado. Rechaza acciones fuera del cerrado."""
    firma = (firma or "").strip()
    if not firma:
        raise ValueError("falta la identidad del firmante (--firma)")
    targets_norm = [_valida_target(t) for t in (targets or [])]
    if not targets_norm:
        raise ValueError("falta al menos un target (--targets)")
    acciones_norm = [a.strip().lower() for a in (acciones or []) if a.strip()]
    if not acciones_norm:
        raise ValueError("falta al menos una acción (--acciones)")
    illegales = [a for a in acciones_norm if a not in SAFE_ACTIONS]
    if illegales:
        raise ValueError(
            f"acciones no soportadas por el motor (vocabulario cerrado): "
            f"{', '.join(illegales)}; acciones permitidas: "
            f"{', '.join(SAFE_ACTIONS)}")
    if not expires:
        expires = (datetime.now(timezone.utc) + timedelta(days=30)
                   ).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("expires debe ser YYYY-MM-DDTHH:MM:SSZ") from exc
    payload = {"version": 1, "targets": targets_norm,
               "acciones": sorted(set(acciones_norm)),
               "expires": expires, "signed_by": firma[:120],
               "iat": now_iso()}
    body = _b64(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    token = {"payload": body, "sig": _firma(_clave(workspace), body)}
    _atomic_write(_token_path(workspace), token)
    return dict(payload)


def _leer_token(workspace: str) -> Optional[dict[str, Any]]:
    path = _token_path(workspace)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    body = str(data.get("payload") or "")
    sig = str(data.get("sig") or "")
    if not body or not sig:
        return None
    if not hmac.compare_digest(sig, _firma(_clave(workspace), body)):
        return None
    try:
        payload = json.loads(_b64d(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return {"payload": payload if isinstance(payload, dict) else {},
            "sig": sig, "path": _token_path(workspace)}


def estado_scope(workspace: str) -> dict[str, Any]:
    """Estado del alcance firmado (o por qué no es válido)."""
    base = {"existe": False, "valido": False, "motivo": "",
            "targets": [], "acciones": [], "expires": "", "signed_by": "",
            "iat": "", "path": _token_path(workspace)}
    token = _leer_token(workspace)
    if token is None:
        base["motivo"] = "sin scope.jwt válido"
        return base
    payload = token["payload"]
    vencido = False
    try:
        vencido = datetime.strptime(str(payload.get("expires") or ""),
                                    "%Y-%m-%dT%H:%M:%SZ") < datetime.utcnow()
    except ValueError:
        return {**base, "existe": True,
                "motivo": "expiración ilegible o ausente"}
    if vencido:
        return {**base, "existe": True, "motivo": "alcance vencido",
                "targets": payload.get("targets", []),
                "acciones": payload.get("acciones", []),
                "expires": str(payload.get("expires", "")),
                "signed_by": str(payload.get("signed_by", "")),
                "iat": str(payload.get("iat", ""))}
    return {**base, "existe": True, "valido": True,
            "targets": payload.get("targets", []),
            "acciones": payload.get("acciones", []),
            "expires": str(payload.get("expires", "")),
            "signed_by": str(payload.get("signed_by", "")),
            "iat": str(payload.get("iat", ""))}


def _host_de(target: str) -> str:
    """Extrae el host de un objetivo (quita esquema, puerto, ruta)."""
    text = (target or "").strip().lower()
    text = re.sub(r"^[a-z]+://", "", text)
    text = text.split("/", 1)[0]
    if ":" in text and text.rsplit(":", 1)[1].isdigit():
        text = text.rsplit(":", 1)[0]
    return text


def _match(autorizado: str, actual: str) -> bool:
    if autorizado == "*":
        return True
    host = _host_de(actual)
    try:
        red = ipaddress.ip_network(autorizado, strict=False)
        ip = ipaddress.ip_address(host)
        return ip in red
    except ValueError:
        pass
    if autorizado == host:
        return True
    if autorizado.startswith("*.") and host.endswith(autorizado[1:]):
        return True
    return False


def verificar_scope(workspace: str, target: str, accion: str) -> dict[str, Any]:
    """Verificación técnica de alcance para un objetivo y una acción."""
    accion = (accion or "").strip().lower()
    estado = estado_scope(workspace)
    base = {k: v for k, v in estado.items() if k != "motivo"}
    if not estado["existe"]:
        return {"ok": False, **base, "motivo": "sin scope.jwt — crea uno con "
                "`a2s secops scope-create`"}
    if not estado["valido"]:
        return {"ok": False, **base, "motivo": estado.get("motivo",
                                                          "alcance inválido")}
    if accion not in estado["acciones"]:
        return {"ok": False, **base, "motivo": f"acción «{accion}» fuera del "
                "alcance (permitidas: "
                f"{', '.join(estado['acciones'])})"}
    if not target:
        return {"ok": False, **base, "motivo": "falta el objetivo para la acción"}
    if not any(_match(a, target) for a in estado["targets"]):
        return {"ok": False, **base, "motivo": f"«{_host_de(target)}» fuera "
                f"del alcance (targets: {', '.join(estado['targets'])})"}
    return {"ok": True, **base, "motivo": ""}


def _denegar(workspace: str, motivo: str, datos: dict[str, Any]) -> None:
    try:
        Ledger(_scope_dir(workspace)).append("secops.denegado",
                                             {"motivo": motivo[:200], **datos})
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Adaptadores defensivos (recon / scan / analizar)
# ---------------------------------------------------------------------------

def _tls_info(host: str, port: int = 443) -> dict[str, Any]:
    """Certificado TLS presentado por el host (best-effort, un handshake)."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=6) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
        subject = dict(x[0] for x in cert.get("subject", ()))
        return {"ok": True, "cn": subject.get("commonName", ""),
                "not_after": cert.get("notAfter", "")[:24],
                "valido": True}
    except Exception as exc:  # noqa: BLE001 — diagnóstico por host
        return {"ok": False, "error": type(exc).__name__}


def recon_http(target: str, timeout: float = 6.0) -> dict[str, Any]:
    """Un GET benigno al activo propio: estado, cabeceras y TLS."""
    url = target if "://" in target else f"https://{target}"
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    t0 = time.monotonic()
    out: dict[str, Any] = {"url": url, "ms": None}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            headers = dict(resp.headers or {})
        out["status"] = status
        out["server"] = str(headers.get("Server", ""))[:80]
        out["content_type"] = str(headers.get("Content-Type", ""))[:80]
        out["redirect"] = str(headers.get("Location", ""))[:120]
        out["security_headers"] = {
            name: bool(headers.get(name))
            for name in ("Content-Security-Policy", "X-Frame-Options",
                         "Strict-Transport-Security", "X-Content-Type-Options",
                         "Referrer-Policy")}
        out["tls"] = _tls_info(_host_de(url))
    except urllib.error.HTTPError as exc:
        out["status"] = exc.code
        out["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — diagnóstico por host
        out["error"] = type(exc).__name__
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


def _parse_nuclei(texto: str) -> list[dict[str, Any]]:
    """Parse de la salida ``-jsonl`` de Nuclei a hallazgos planos."""
    out = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            item = json.loads(linea)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        info = item.get("info") or {}
        out.append({
            "template_id": str(item.get("template-id", "")),
            "name": str(info.get("name", "")),
            "severity": str(info.get("severity", "")),
            "tags": str(info.get("tags", "")),
            "matched_at": str(item.get("matched-at", "")),
            "matcher_name": str(item.get("matcher-name", "")),
            "extracted": [str(x) for x in (item.get("extracted-results") or [])][:5],
        })
    return out


def _parse_trivy(texto: str) -> list[dict[str, Any]]:
    """Parse del JSON de Trivy a vulnerabilidades planas."""
    try:
        data = json.loads(texto)
    except ValueError:
        return []
    out = []
    for result in data.get("Results", []) or []:
        for v in result.get("Vulnerabilities", []) or []:
            out.append({
                "cve": str(v.get("VulnerabilityID", "")),
                "severity": str(v.get("Severity", "")),
                "pkg": str(v.get("PkgName", "")),
                "installed": str(v.get("InstalledVersion", "")),
                "fixed": str(v.get("FixedVersion", "")),
                "title": str(v.get("Title", ""))[:140],
            })
    return out


def ejecutar_nuclei(targets: list[str], templates: str = "",
                    timeout: float = 120.0) -> dict[str, Any]:
    """Ejecuta el escáner local (si está instalado) sobre los targets dados."""
    binary = shutil.which("nuclei")
    if not binary:
        return {"ok": False, "motivo": "nuclei no instalado (binario no hallado)"}
    findings: list[dict[str, Any]] = []
    errores = []
    for target in targets:
        argv = [binary, "-jsonl", "-silent", "-no-color", "-u", target]
        if templates:
            argv += ["-t", templates]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
            findings.extend(_parse_nuclei(proc.stdout))
            if proc.returncode != 0 and proc.stderr.strip():
                errores.append(f"{target}: {proc.stderr.strip()[:200]}")
        except subprocess.TimeoutExpired:
            errores.append(f"{target}: timeout {timeout:.0f}s")
        except OSError as exc:
            errores.append(f"{target}: {exc}")
    return {"ok": not errores or bool(findings), "findings": findings,
            "errores": errores, "total": len(findings), "scanner": "nuclei"}


def ejecutar_trivy(objetivo: str, workspace: str = "",
                   timeout: float = 180.0) -> dict[str, Any]:
    """Escanea con Trivy: ruta local (fs) o imagen (image)."""
    binary = shutil.which("trivy")
    if not binary:
        return {"ok": False, "motivo": "trivy no instalado (binario no hallado)"}
    full = os.path.abspath(os.path.join(os.path.abspath(workspace or "."),
                                        objetivo))
    if os.path.isfile(full) or os.path.isdir(full):
        kind, target = "fs", full
    else:
        kind, target = "image", objetivo
    argv = [binary, kind, "--format", "json", "--quiet", target]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "motivo": f"timeout {timeout:.0f}s", "scanner": "trivy"}
    except OSError as exc:
        return {"ok": False, "motivo": str(exc), "scanner": "trivy"}
    vulns = _parse_trivy(proc.stdout)
    return {"ok": proc.returncode == 0 or bool(vulns), "scanner": "trivy",
            "kind": kind, "target": target, "vulnerabilities": vulns,
            "total": len(vulns),
            "stderr": (proc.stderr or "").strip()[:200]}


def _dentro(workspace: str, path: str) -> str:
    full = os.path.abspath(os.path.join(os.path.abspath(workspace or "."), path))
    root = os.path.abspath(workspace or ".")
    if not (full == root or full.startswith(root + os.sep)):
        raise PermissionError("ruta fuera del workspace")
    return full


def analizar_local(workspace: str, path: str,
                   ghidra: bool = True) -> dict[str, Any]:
    """Análisis estático local: magia, strings, EXIF/PDF, SHA-256 (+Ghidra)."""
    full = _dentro(workspace, path)
    if not os.path.isfile(full):
        raise FileNotFoundError(path)
    from .plugins.forensics_extra import extract_strings, file_magic
    out: dict[str, Any] = {"path": path, "size": os.path.getsize(full)}
    with open(full, "rb") as fh:
        out["sha256"] = hashlib.sha256(fh.read()).hexdigest()
    try:
        out["magic"] = file_magic(full)
    except OSError as exc:
        out["magic"] = f"error: {exc}"
    try:
        strings = extract_strings(full, min_len=6)
        out["strings"] = strings[:40]
        out["strings_total"] = len(strings)
    except OSError:
        out["strings"] = []
        out["strings_total"] = 0
    if full.lower().endswith((".jpg", ".jpeg", ".tif", ".tiff")):
        try:
            from .plugins.forensics_extra import exif_basic
            out["exif"] = exif_basic(full)
        except OSError:
            out["exif"] = {}
    if full.lower().endswith(".pdf"):
        try:
            from .plugins.forensics_extra import pdf_metadata
            out["pdf"] = pdf_metadata(full)
        except OSError:
            out["pdf"] = {}
    out["ghidra"] = _ghidra_si_disponible(full, ghidra)
    return out


def _ghidra_si_disponible(full: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"ok": False, "motivo": "desactivado"}
    binary = shutil.which("analyzeHeadless")
    if not binary:
        return {"ok": False, "motivo": "analyzeHeadless no instalado"}
    proj = os.path.join(os.path.dirname(full), ".ghidra_a2s")
    try:
        proc = subprocess.run(
            [binary, proj, "A2S", "-import", full, "-overwrite"],
            capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "motivo": f"{type(exc).__name__}"}
    return {"ok": proc.returncode == 0,
            "motivo": (proc.stdout + proc.stderr)[-300:] or "sin salida"}


# ---------------------------------------------------------------------------
# Plan y ejecución
# ---------------------------------------------------------------------------

_TIPO_PASO: dict[str, tuple[str, str]] = {
    "web-check": ("recon", "web-check"),
    "osint4all": ("recon", "osint4all"),
    "nuclei": ("scan", "nuclei"),
    "trivy": ("scan", "trivy"),
    "ghidra": ("analizar", "ghidra"),
    "imhex": ("analizar", "imhex"),
    "cyberchef": ("analizar", "cyberchef"),
}
_OPERADOR: tuple[str, ...] = ("metasploit", "sqlmap", "hashcat", "hackingtool",
                              "payloads-all-things", "grayhat-warfare",
                              "gmail-account-creator")


def plan_para(objetivo: str, workspace: str = "",
              targets: Optional[list[str]] = None,
              archivo: str = "") -> list[dict[str, Any]]:
    """Plan de pasos para el motor (auto = A²S; operador = lo ejecuta el dueño).

    Incluye los eslabones habilitados Y los que la puerta retiene (para que la
    simulación muestre la cadena completa y la asistida los deniegue con
    auditoría en lugar de ignorarlos en silencio).
    """
    from .capacidades import seleccionar
    plan = seleccionar(objetivo, workspace=workspace)
    pasos = []
    for paso in plan["pasos"] + plan["bloqueados"]:
        ident = paso["id"]
        tipo, fuente = _TIPO_PASO.get(ident, ("operador", ident))
        if paso.get("motivo") and tipo not in SAFE_ACTIONS:
            tipo = "operador"
        objetivo = ""
        if tipo == "recon":
            objetivo = (targets or [""])[0] if targets else ""
        elif tipo == "scan":
            objetivo = (targets or [""])[0] if targets else (
                archivo if "trivy" in fuente else "")
        elif tipo == "analizar":
            objetivo = archivo
        motivo_limite = paso.get("motivo") or (
            "La ejecuta el operador en su entorno autorizado; A²S no "
            "automatiza herramientas ofensivas" if ident in _OPERADOR else "")
        pasos.append({"id": ident, "nombre": paso["nombre"],
                      "fuente": fuente, "tipo": tipo,
                      "accion": tipo if tipo in SAFE_ACTIONS else None,
                      "objetivo": objetivo,
                      "por_que": paso.get("por_que", ""),
                      "requiere": paso.get("requiere", []),
                      "razon_limite": motivo_limite})
    return pasos


def _run_dir(workspace: str, run_id: str) -> str:
    return os.path.join(_scope_dir(workspace), "secops", run_id)


def _guardar_run(workspace: str, run_id: str, datos: dict[str, Any]) -> None:
    d = _run_dir(workspace, run_id)
    os.makedirs(d, exist_ok=True)
    _atomic_write(os.path.join(d, "resumen.json"), datos)
    lineas = ["# Informe SecOps asistido", "",
              f"Ejecución: {run_id} · {datos.get('at', '')}",
              f"Modo: {datos.get('modo', '')} · Objetivo: "
              f"{datos.get('objetivo', '')}", ""]
    for paso in datos.get("pasos", []):
        estado = paso.get("estado", paso.get("tipo", "?"))
        marca = {"ok": "✔", "denegado": "✗", "sin_objetivo": "•",
                 "omitido": "•", "error": "✗"}.get(estado, "•")
        lineas.append(f"## {marca} {paso.get('nombre', paso.get('id', '?'))}")
        lineas.append(f"- tipo: {paso.get('tipo')} · fuente: "
                      f"{paso.get('fuente')}")
        if paso.get("objetivo"):
            lineas.append(f"- objetivo: {paso['objetivo']}")
        if paso.get("motivo"):
            lineas.append(f"- motivo: {paso['motivo']}")
        reporte = paso.get("reporte")
        if reporte:
            lineas.append(f"- resultado: {json.dumps(reporte, ensure_ascii=False)[:400]}")
        lineas.append("")
    _atomic_write(os.path.join(d, "informe.md"), "\n".join(lineas) + "\n")


def ejecutar(objetivo: str, modo: str = "simulacion", workspace: str = "",
             targets: Optional[list[str]] = None, archivo: str = "",
             templates: str = "", confirm: bool = False) -> dict[str, Any]:
    """Motor: simulación (sin red) o ejecución asistida defensiva con alcance."""
    modo = (modo or "simulacion").strip().lower()
    if modo not in ("simulacion", "asistido"):
        raise ValueError("modo debe ser simulacion o asistido")
    pasos_plan = plan_para(objetivo, workspace=workspace,
                           targets=targets, archivo=archivo)
    if modo == "simulacion":
        return {"modo": "simulacion", "objetivo": objetivo,
                "at": now_iso(), "ejecutado": False,
                "pasos": [{**p, "estado": "simulado"} for p in pasos_plan],
                "nota": "simulación: sin llamadas de red ni procesos; "
                        "los escáneres/exploradores reales se ejecutan con "
                        "--modo asistido sobre el alcance firmado"}
    run_id = f"secops-{int(time.time())}-{abs(hash(objetivo)) % 10000}"
    resultados = []
    ledger = Ledger(_scope_dir(workspace))
    for paso in pasos_plan:
        if paso["tipo"] not in SAFE_ACTIONS:
            resultados.append({**paso, "estado": "omitido"})
            continue
        accion = paso["accion"]
        objetivo_paso = paso["objetivo"]
        if not objetivo_paso:
            resultados.append({**paso, "estado": "sin_objetivo",
                               "motivo": ("--targets para recon/scan o "
                                          "--archivo para analizar")})
            continue
        if accion in ("recon", "scan") and not confirm:
            resultados.append({**paso, "estado": "omitido",
                               "motivo": "requiere --confirm (paso de red)"})
            continue
        if accion in ("recon", "scan"):
            verif = verificar_scope(workspace, objetivo_paso, accion)
            if not verif["ok"]:
                _denegar(workspace, verif["motivo"],
                         {"objetivo": objetivo, "paso": paso["id"],
                          "target": objetivo_paso, "accion": accion})
                ledger.append("secops.denegado",
                              {"motivo": verif["motivo"][:200],
                               "paso": paso["id"], "target": objetivo_paso,
                               "accion": accion})
                resultados.append({**paso, "estado": "denegado",
                                   "motivo": verif["motivo"]})
                continue
        try:
            if accion == "recon":
                reporte = recon_http(objetivo_paso)
            elif accion == "scan":
                if paso["fuente"] == "trivy":
                    reporte = ejecutar_trivy(objetivo_paso, workspace=workspace)
                else:
                    reporte = ejecutar_nuclei([objetivo_paso],
                                              templates=templates)
            else:
                reporte = analizar_local(workspace, objetivo_paso)
            resultados.append({**paso, "estado": "ok", "reporte": reporte})
            ledger.append("secops.ejecucion",
                          {"paso": paso["id"], "target": objetivo_paso,
                           "accion": accion,
                           "resumen": json.dumps(reporte, ensure_ascii=False)[:300]})
        except (PermissionError, FileNotFoundError, ValueError) as exc:
            resultados.append({**paso, "estado": "error", "motivo": str(exc)})
            ledger.append("secops.error", {"paso": paso["id"],
                                           "motivo": str(exc)[:200]})
    datos = {"modo": "asistido", "objetivo": objetivo, "at": now_iso(),
             "ejecutado": True, "pasos": resultados,
             "scope": {k: v for k, v in estado_scope(workspace).items()
                       if k != "path"}}
    _guardar_run(workspace, run_id, datos)
    return {**datos, "run_id": run_id}


def ultimo_run(workspace: str) -> dict[str, Any]:
    """Resumen del último run (o vacío) para la API/CLI."""
    d = _run_dir(workspace, "")
    if not os.path.isdir(d):
        return {"run_id": "", "at": "", "modo": "", "pasos": 0, "ok": 0}
    runs = sorted((os.path.join(d, n) for n in os.listdir(d)
                   if os.path.isdir(os.path.join(d, n))), key=os.path.getmtime)
    if not runs:
        return {"run_id": "", "at": "", "modo": "", "pasos": 0, "ok": 0}
    try:
        with open(os.path.join(runs[-1], "resumen.json"),
                  encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"run_id": "", "at": "", "modo": "", "pasos": 0, "ok": 0}
    return {"run_id": str(data.get("run_id", os.path.basename(runs[-1]))),
            "at": data.get("at", ""), "modo": data.get("modo", ""),
            "pasos": len(data.get("pasos", [])),
            "ok": sum(1 for p in data.get("pasos", [])
                      if p.get("estado") == "ok")}


def resumen_secops(workspace: str) -> dict[str, Any]:
    """Estado del alcance + último run (para CLI/API)."""
    return {"scope": estado_scope(workspace),
            "acciones_permitidas": list(SAFE_ACTIONS),
            "acciones_nombre": ACCION_NOMBRE,
            "ultimo_run": ultimo_run(workspace)}
