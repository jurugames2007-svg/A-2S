"""Proveedores de razonamiento ("runtime técnico" del núcleo).

* ``HeuristicProvider``: núcleo heurístico determinista. Funciona sin red y sin
  claves — garantiza que el loop siempre pueda operar ("auto-recursos").
* ``OpenAICompatProvider``: LLM vía API externa compatible con OpenAI
  (``OPENAI_API_KEY``, ``A2S_LLM_BASE_URL`` opcional). Si la API falla,
  degrada automáticamente al núcleo heurístico y continúa (el objetivo se
  persigue igualmente).

Ambos exponen la misma interfaz de planificación/evaluación, por lo que el
núcleo de metaprendizaje puede cambiar de motor sin tocar el resto.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from .models import ToolCall


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Extrae el primer objeto JSON de un texto (tolerante a prosa sobrante)."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Buscar bloque delimitado
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


SYSTEM_PROMPT = (
    "Eres el planificador de A²S, un agente autónomo forense. Responde SIEMPRE "
    "solo con un objeto JSON válido, sin prosa adicional, siguiendo el esquema "
    "solicitado. Persigue el objetivo hasta lograrlo: si un enfoque falla, "
    "propón uno distinto (reparametrización)."
)


class BaseProvider:
    name = "base"

    def plan(self, goal: str, context: str, tools: str, variant: int = 0) -> dict[str, Any]:
        raise NotImplementedError

    def reparameterize(self, goal: str, failed: str, history: str, tools: str) -> dict[str, Any]:
        raise NotImplementedError

    def evaluate(self, step_goal: str, observation: str, criteria: str) -> dict[str, Any]:
        raise NotImplementedError

    def goal_check(self, goal: str, summary: str) -> tuple[bool, str]:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Núcleo heurístico determinista
# --------------------------------------------------------------------------

# Código de los pasos de recopilación de la plantilla forense. 100% stdlib
# (os.walk/hashlib/os.stat): el núcleo heurístico no depende de herramientas
# POSIX (find/stat/sha256sum) ni de shell alguno — funciona igual en Windows
# sin Git-Bash/MSYS2/WSL y dentro del sandbox.
_INV_CODE = """\
import os
lineas = []
for root, dirs, files in os.walk("."):
    dirs[:] = sorted(d for d in dirs if d not in (".git", ".a2s"))
    for fn in sorted(files):
        lineas.append(os.path.relpath(os.path.join(root, fn), ".").replace(os.sep, "/"))
print("\\n".join(lineas[:200]) or "(workspace vacío)")
"""

_META_CODE = """\
import os, time
for root, dirs, files in os.walk("."):
    dirs[:] = sorted(d for d in dirs if d not in (".git", ".a2s"))
    for fn in sorted(files):
        full = os.path.join(root, fn)
        try:
            st = os.stat(full)
        except OSError:
            continue
        rel = os.path.relpath(full, ".").replace(os.sep, "/")
        mt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))
        print(f"{rel} | {st.st_size} bytes | mtime {mt}")
"""

_HASH_CODE = """\
import hashlib, os
for root, dirs, files in os.walk("."):
    dirs[:] = sorted(d for d in dirs if d not in (".git", ".a2s"))
    for fn in sorted(files):
        full = os.path.join(root, fn)
        if not os.path.isfile(full):
            continue
        try:
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
        except OSError:
            continue
        print(h.hexdigest() + "  " + os.path.relpath(full, ".").replace(os.sep, "/"))
"""

_CUSTODIA_CODE = """\
import subprocess
try:
    p = subprocess.run(["git", "log", "--oneline", "-20"], capture_output=True,
                       text=True, timeout=10, stdin=subprocess.DEVNULL)
    out = (p.stdout or "").strip()
except Exception:
    out = ""
print(out or "sin repositorio git")
print("(fin del registro de custodia)")
"""

_HEURISTIC_PLANS: list[tuple[tuple[str, ...], str, list[tuple[str, str, dict[str, Any], list[str]]]]] = [
    # (palabras clave, nombre de plantilla, pasos (nombre, tool, params, criterios))
    (("ppt", "pptx", "powerpoint", "presentación", "presentacion",
      "diapositiva", "slides"), "verified_deck", [
        ("disenar_presentacion", "create_slides",
         {"topic": "{goal}"},
         ["slides/deck.pptx, HTML, PDF y process.json creados"]),
        ("verificar_deck", "read_file", {"path": "slides/quality.json"},
         ["calidad y número de láminas disponibles"]),
    ]),
    (("libro", "ebook", "manual", "capítulos", "capitulos"), "verified_book", [
        ("investigar_y_crear_libro", "create_book",
         {"topic": "{goal}", "chapters": 12, "target_words": 5000},
         ["book/book.md, HTML, PDF y quality.json creados"]),
        ("verificar_manuscrito", "read_file", {"path": "book/quality.json"},
         ["quality gate y limitaciones disponibles"]),
    ]),
    (("github.com", "search_repos", "palabra clave"), "repo_keyword_search", [
        ("buscar_repositorios", "search_repos",
         {"query": "{goal}", "limit": 8},
         ["resultados de repositorios guardados"]),
        ("guardar_busqueda", "read_file", {"path": "research/search.md"},
         ["informe de búsqueda disponible"]),
    ]),
    (("pdf", "papers", "recientes",
      "reciente", "actual", "noticias", "precio", "destacables"), "verified_research", [
        ("investigar_fuentes_y_repositorio", "research_topic",
         {"topic": "{goal}", "repo_limit": 8, "pdf_limit": 8},
         ["repositorios y PDF OA documentados con procedencia"]),
        ("verificar_fuentes", "read_file", {"path": "research/sources.json"},
         ["manifiesto de fuentes disponible"]),
    ]),
    (("forense", "informe", "auditor", "analiza", "análisis", "evidence", "evidencia"),
     "forensic_report", [
         ("inventariar_evidencia", "python_exec",
          {"code": _INV_CODE},
          ["lista de archivos obtenida"]),
         ("extraer_metadatos", "python_exec",
          {"code": _META_CODE},
          ["metadatos de archivos obtenidos"]),
         ("calcular_hashes", "python_exec",
          {"code": _HASH_CODE},
          ["hashes SHA-256 calculados"]),
         ("registrar_cadena_custodia", "python_exec",
          {"code": _CUSTODIA_CODE},
          ["historial o estado del repositorio registrado"]),
         ("redactar_informe", "write_file",
          {"path": "informe_forense.md",
           "content": "# Informe Forense A²S\n\n## Inventario\n\n(inventario de la fase 1)\n\n## Metadatos\n\n(metadatos de la fase 2)\n\n## Hashes\n\n(hashes de la fase 3)\n\n## Cadena de custodia\n\n(evidencia de la fase 4)\n\n## Conclusiones\n\nAnálisis completado por el agente A²S.\n"},
          ["archivo informe_forense.md creado"]),
         ("verificar_informe", "read_file",
          {"path": "informe_forense.md"},
          ["el informe existe y contiene las secciones requeridas"]),
     ]),
    (("busca", "buscar", "investig", "research", "web"), "web_research", [
        ("busqueda_web", "web_search", {"query": "{goal}"}, ["resultados de búsqueda obtenidos"]),
        ("guardar_hallazgos", "save_artifact",
         {"name": "hallazgos", "content": "resultados de la búsqueda"},
         ["hallazgos guardados"]),
        ("redactar_resumen", "write_file",
         {"path": "resumen_investigacion.md", "content": "# Resumen de investigación\n\n{goal}\n"},
         ["resumen creado"]),
    ]),
    (("api", "descarg", "download", "endpoint", "http"), "api_call", [
        ("consultar_api", "fetch_url", {"url": "{goal}"}, ["respuesta de la API obtenida"]),
        ("guardar_respuesta", "write_file",
         {"path": "respuesta_api.txt", "content": "respuesta de la API"},
         ["respuesta guardada"]),
    ]),
    ((), "generic_explore", [
        ("explorar_entorno", "list_dir", {"path": "."}, ["entorno explorado"]),
        ("analizar_archivos", "read_file", {"path": "README.md"}, ["archivos analizados"]),
        ("documentar", "write_file",
         {"path": "resultado.md", "content": "# Resultado\n\n{goal}\n"},
         ["resultado documentado"]),
    ]),
]


class HeuristicProvider(BaseProvider):
    name = "heuristic"

    def __init__(self) -> None:
        self.plan_hits: dict[str, int] = {}

    def _match_plan(self, goal: str, variant: int = 0
                    ) -> tuple[str, list[tuple[str, str, dict[str, Any], list[str]]]]:
        gl = goal.lower()
        scored = []
        for keywords, name, steps in _HEURISTIC_PLANS:
            score = sum(1 for k in keywords if k in gl)
            if score > 0:
                scored.append((score, name, steps))
        if not scored:
            name, steps = _HEURISTIC_PLANS[-1][1], _HEURISTIC_PLANS[-1][2]
            return name, steps
        # Rotación por variante: cada ronda de plan puede elegir otra plantilla
        # con el mismo puntaje → diversidad de enfoques ante estancamiento.
        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[0][0]
        pool = [t for t in scored if t[0] == top]
        _, name, steps = pool[variant % len(pool)]
        return name, steps

    def plan(self, goal: str, context: str, tools: str, variant: int = 0) -> dict[str, Any]:
        _, steps = self._match_plan(goal, variant)
        step_ids = [f"step-{variant}-{i+1}" for i in range(len(steps))]
        out_steps = []
        for i, (name, tool, params, criteria) in enumerate(steps):
            params = {k: (v.replace("{goal}", goal) if isinstance(v, str) else v)
                      for k, v in params.items()}
            if variant > 0 and "command" in params:
                params["command"] = f"{params['command']} 2>&1 | head -300"
            out_steps.append({
                "id": step_ids[i], "goal": name,
                "approach": f"plantilla heurística {name} (variante {variant})",
                "tool": tool, "params": params,
                "success_criteria": criteria,
                "depends_on": [step_ids[i - 1]] if i > 0 else [],
            })
        return {"strategy": "núcleo heurístico", "steps": out_steps,
                "note": "plan determinista generado sin LLM"}

    def reparameterize(self, goal: str, failed: str, history: str, tools: str) -> dict[str, Any]:
        """Reparametrización: variar parámetros, cambiar herramienta, dividir el paso."""
        return {
            "strategy": "reparametrización heurística",
            "change": ("cambiar parámetros o herramienta; si el fallo persiste, "
                       "dividir el paso en sub-pasos más simples y reintentar"),
            "failed_note": failed[-400:],
        }

    def evaluate(self, step_goal: str, observation: str, criteria: str) -> dict[str, Any]:
        text = (observation or "")
        if not text.strip() or "PERMISO DENEGADO" in text:
            return {"score": 0.0, "verdict": "blocked",
                    "reason": "sin salida útil o acción denegada por permisos"}
        if any(bad in text for bad in ("Error", "error:", "Traceback", "denegada",
                                       "ERROR(", "(exit=", "find:", "usage:")):
            return {"score": 0.2, "verdict": "failed", "reason": "la observación contiene errores"}
        if len(text) < 3:
            return {"score": 0.2, "verdict": "failed", "reason": "salida demasiado breve"}
        return {"score": 0.8, "verdict": "success",
                "reason": "observación no vacía y sin errores aparentes"}

    def goal_check(self, goal: str, summary: str) -> tuple[bool, str]:
        ok = bool(summary.strip()) and not any(b in summary for b in
                                               ("PERMISO DENEGADO", "Traceback"))
        return ok, ("evidencia de progreso presente" if ok else "sin evidencia de progreso")


# --------------------------------------------------------------------------
# LLM vía API externa (compatible OpenAI)
# --------------------------------------------------------------------------

class OpenAICompatProvider(BaseProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: str = "gpt-4o-mini", temperature: float = 0.2,
                 fallback: Optional[BaseProvider] = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("A2S_LLM_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.model = model
        self.temperature = temperature
        self.fallback = fallback or HeuristicProvider()

    def _chat(self, prompt: str, max_tokens: int = 1500,
              system: str = SYSTEM_PROMPT) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY no definida")
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]

    def _structured(self, prompt: str, fallback_obj: dict[str, Any],
                    max_tokens: int = 1500) -> dict[str, Any]:
        """Llama al LLM; ante cualquier fallo degrada al núcleo heurístico."""
        try:
            raw = self._chat(prompt, max_tokens)
            obj = _extract_json(raw)
            if obj is not None:
                return obj
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError,
                KeyError, json.JSONDecodeError, OSError) as exc:
            fallback_obj["llm_fallback_reason"] = str(exc)
            return fallback_obj
        fallback_obj["llm_fallback_reason"] = "respuesta sin JSON válido"
        return fallback_obj

    def plan(self, goal: str, context: str, tools: str, variant: int = 0) -> dict[str, Any]:
        prompt = (
            f"OBJETIVO: {goal}\n\nCONTEXTO:\n{context}\n\nHERRAMIENTAS:\n{tools}\n\n"
            f"Ronda de planificación: {variant}. Si variante > 0, el enfoque anterior "
            "falló: propón un plan DISTINTO.\n"
            'Devuelve JSON: {"strategy": str, "steps": [{"id": str, "goal": str, '
            '"approach": str, "tool": str, "params": dict, "success_criteria": [str], '
            '"depends_on": [str]}]}. Planifica pasos ejecutables con las herramientas '
            "disponibles para lograr el objetivo."
        )
        fallback = self.fallback.plan(goal, context, tools, variant=variant)
        obj = self._structured(prompt, fallback)
        if not isinstance(obj.get("steps"), list) or not obj["steps"]:
            return fallback
        return obj

    def reparameterize(self, goal: str, failed: str, history: str, tools: str) -> dict[str, Any]:
        prompt = (
            f"Un paso del plan falló.\nOBJETIVO: {goal}\nFALLO:\n{failed}\n"
            f"HISTORIAL RECIENTE:\n{history}\nHERRAMIENTAS:\n{tools}\n"
            'Devuelve JSON: {"strategy": str, "change": str, "new_params_hint": str}. '
            "Propón un enfoque DIFERENTE (reparametrización), nunca el mismo."
        )
        fallback = self.fallback.reparameterize(goal, failed, history, tools)
        return self._structured(prompt, fallback)

    def evaluate(self, step_goal: str, observation: str, criteria: str) -> dict[str, Any]:
        prompt = (
            f"Evalúa si el paso logró su objetivo.\nPASO: {step_goal}\n"
            f"CRITERIOS: {criteria}\nOBSERVACIÓN:\n{observation[:3000]}\n"
            'Devuelve JSON: {"score": float(0..1), "verdict": "success|failed|blocked", '
            '"reason": str}. blocked = imposible con el enfoque actual; failed = '
            "intento fallido pero reparametrizable."
        )
        fallback = self.fallback.evaluate(step_goal, observation, criteria)
        obj = self._structured(prompt, fallback, max_tokens=400)
        if obj.get("verdict") not in ("success", "failed", "blocked"):
            return fallback
        return obj

    def goal_check(self, goal: str, summary: str) -> tuple[bool, str]:
        prompt = (
            f"OBJETIVO: {goal}\nEVIDENCIA RECOPILADA:\n{summary[:3000]}\n"
            'Devuelve JSON: {"achieved": bool, "reason": str}. Sé estricto: solo '
            "true si el objetivo está realmente cumplido."
        )
        try:
            obj = _extract_json(self._chat(prompt, max_tokens=200))
            if obj is not None and isinstance(obj.get("achieved"), bool):
                return obj["achieved"], str(obj.get("reason", ""))
        except Exception:  # noqa: BLE001
            pass
        return self.fallback.goal_check(goal, summary)


def get_provider(kind: str, fallback_ok: bool = True,
                 config: Any = None) -> BaseProvider:
    """Resuelve el motor sin obligar al operador a escoger un proveedor.

    ``auto`` y ``pool`` usan SORL: descubren OmniRoute y cualquier otro recurso
    legítimo disponible, y conservan el núcleo heurístico como último fallback.
    Así, la ruta por defecto del CLI y del agente es el OmniRoute incluido por
    la distribución npm cuando está vivo, sin ``--provider`` ni clave externa.
    ``heuristic`` y ``openai`` permanecen como overrides explícitos.
    """
    fallback = HeuristicProvider()
    if kind == "heuristic":
        return fallback
    if kind in ("auto", "pool"):
        from .provider_pool import build_pool_provider
        return build_pool_provider(config=config)
    if kind == "openai":
        return OpenAICompatProvider(fallback=fallback)
    # Una entrada desconocida nunca debe saltarse la degradación segura.
    return fallback
