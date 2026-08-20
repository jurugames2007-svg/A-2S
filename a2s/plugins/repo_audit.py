"""Plugin: auditoría defensiva de repositorios, plugins y skills.

Inspirado en la parte DEFENSIVA de la lista de referencia (repo-forensics):
escanea código local en busca de patrones de riesgo ANTES de cargarlo o
ejecutarlo. Protege al usuario de agentes/plugins maliciosos.

Honestidad técnica: es un escáner heurístico — detecta patrones sospechosos
convencionales (y los reporta con archivo/línea/severidad), pero no es un
análisis estático completo ni detecta ofuscación deliberada sofisticada.
"""

import hashlib
import os
import re

PLUGIN = {
    "name": "repo_audit",
    "version": "1.0.0",
    "description": "Escáner de seguridad de repositorios/plugins locales (patrones de riesgo)",
    "tags": ["auditoria", "audit", "seguridad", "scan", "escaner", "repositorio",
            "plugin", "malware", "revision", "forense"],
    "tools": [
        {"name": "audit_path", "description": "Escanea un directorio del workspace en busca de patrones de riesgo.",
         "params": {"path": "str (relativo al workspace)", "max_files": "int opcional"}},
        {"name": "audit_plugins", "description": "Audita los directorios de plugins de A²S (integrados y externos).",
         "params": {}},
    ],
}

_PATTERNS = [
    (re.compile(r"subprocess[^)]*shell\s*=\s*True"), "alta",
     "ejecución de shell sin control"),
    (re.compile(r"\bexec\s*\(|\beval\s*\(|compile\([^)]*,\s*['\"]exec"), "alta",
     "ejecución dinámica de código"),
    (re.compile(r"pickle\.loads?|marshal\.loads?"), "alta",
     "deserialización no segura"),
    (re.compile(r"os\.environ(\.get)?\([^)]*(SECRET|TOKEN|KEY|PASS|CRED)"), "alta",
     "lectura de secretos/credenciales"),
    (re.compile(r"base64\.b64decode|b64decode"), "media",
     "posible ofuscación (base64)"),
    (re.compile(r"os\.system\(|os\.popen\("), "media",
     "invocación directa al sistema"),
    (re.compile(r"ctypes\.|\bCDLL\("), "media",
     "acceso de bajo nivel (ctypes)"),
    (re.compile(r"socket\.(create_connection|connect)\("), "media",
     "conexión de red directa"),
    (re.compile(r"requests\.(post|get)\(|urlopen\(|HTTPSConnection\("), "baja",
     "tráfico de red"),
    (re.compile(r"[A-Za-z0-9+/]{80,}={0,2}"), "media",
     "blob largo (posible payload codificado)"),
]

_CODE_EXTS = {".py", ".sh", ".bash", ".js", ".ts", ".json", ".yaml", ".yml",
              ".md", ".toml", ".cfg", ".txt", ".log", ".csv", ".ini"}
_MAX_FILE = 2 * 1024 * 1024


def _scan_dir(root: str, max_files: int = 200) -> tuple[list[dict], list[dict]]:
    findings, hashes = [], []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".a2s", "__pycache__")]
        for name in sorted(filenames):
            if count >= max_files:
                break
            ext = os.path.splitext(name)[1].lower()
            full = os.path.join(dirpath, name)
            if ext not in _CODE_EXTS:
                continue
            count += 1
            try:
                size = os.path.getsize(full)
                if size > _MAX_FILE:
                    continue
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            try:
                with open(full, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                digest = "?"
            hashes.append({"file": os.path.relpath(full, root), "sha256": digest})
            for lineno, line in enumerate(text.splitlines(), 1):
                for rx, severity, why in _PATTERNS:
                    if rx.search(line):
                        findings.append({"file": os.path.relpath(full, root),
                                         "line": lineno, "severity": severity,
                                         "why": why,
                                         "code": line.strip()[:160]})
        if count >= max_files:
            break
    return findings, hashes


def _render(root: str, findings: list[dict], hashes: list[dict], label: str) -> str:
    lines = [f"Auditoría de {label} ({len(hashes)} archivos, "
             f"{len(findings)} hallazgos)", "=" * 60]
    if not findings:
        lines.append("Sin patrones de riesgo detectados en los archivos escaneados.")
    for f in findings:
        lines.append(f"[{f['severity'].upper()}] {f['file']}:{f['line']} — {f['why']}")
        lines.append(f"    {f['code']}")
    if hashes:
        lines.append("")
        lines.append(f"Hashes SHA-256 ({len(hashes)} archivos):")
        lines += [f"  {h['sha256']}  {h['file']}" for h in hashes[:60]]
    return "\n".join(lines)


def audit_path(registry, path=".", max_files=200):
    full = registry._resolve(path)
    if not registry._inside_workspace(full) or not os.path.isdir(full):
        raise PermissionError("directorio fuera del workspace o inexistente")
    findings, hashes = _scan_dir(full, max_files=int(max_files))
    return _render(full, findings, hashes, os.path.relpath(full, registry.workspace))


def audit_plugins(registry):
    import a2s.plugins as _pkg
    dirs = [os.path.dirname(_pkg.__file__)]
    dirs += [os.path.abspath(d) for d in
             (os.environ.get("A2S_PLUGIN_DIRS") or "").split(os.pathsep) if d.strip()]
    parts = []
    for d in dirs:
        if os.path.isdir(d):
            findings, hashes = _scan_dir(d, max_files=100)
            parts.append(_render(d, findings, hashes, f"plugins en {d}"))
    return "\n\n".join(parts) or "(sin directorios de plugins que auditar)"


def register(registry, ctx):
    from a2s.tools import Tool

    def f_path(path=".", max_files=200):
        return audit_path(registry, path, max_files)

    registry.register(Tool("audit_path", PLUGIN["tools"][0]["description"],
                           PLUGIN["tools"][0]["params"], f_path))
    registry.register(Tool("audit_plugins", PLUGIN["tools"][1]["description"],
                           PLUGIN["tools"][1]["params"],
                           lambda: audit_plugins(registry)))
