"""Biblioteca de objetivos con verificadores de cumplimiento.

Los verificadores son la "validación de objetivo": el loop consulta al
verificador después de cada ronda y solo declara éxito si éste da el visto
bueno. La misión demo está diseñada para que el primer enfoque FALLE y el
loop tenga que superar el estancamiento (reparametrización + división
fractal) hasta lograrlo — demostración real de la escalera de recuperación.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import Any, Callable, Optional

from .memory import MemoryHub

GoalVerifier = Callable[[MemoryHub], tuple[bool, str]]
StepVerifier = Callable[[Any], tuple[bool, str]]

_SHA_RE = re.compile(r"\b[0-9a-f]{64}\b")


def _read_workspace_file(memory: MemoryHub, relpath: str) -> Optional[str]:
    full = os.path.join(memory.workspace, relpath)
    if not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _informe_es_valido(text: str) -> tuple[bool, str]:
    required = ("## Inventario", "## Hashes", "## Cadena de custodia", "## Conclusiones")
    missing = [sec for sec in required if sec not in text]
    hashes = _SHA_RE.findall(text)
    if missing:
        return False, f"secciones faltantes: {missing}"
    if len(hashes) < 1:
        return False, "el informe no contiene hashes SHA-256 reales"
    if "(hashes de la fase 3)" in text or "(evidencia de la fase 4)" in text:
        return False, "el informe aún contiene marcadores de posición (datos no reales)"
    if "Total de evidencias con hash: 0" in text:
        return False, "cero evidencias con hash"
    return True, f"informe completo con {len(hashes)} hashes verificados"


def forensic_report_goal_verifier(memory: MemoryHub) -> tuple[bool, str]:
    text = _read_workspace_file(memory, "informe_forense.md")
    if text is None:
        return False, "informe_forense.md no existe todavía"
    return _informe_es_valido(text)


def build_demo_step_verifiers(memory: MemoryHub) -> dict[str, StepVerifier]:
    """Verificadores de paso cerrados sobre el workspace de la misión."""
    def redactar(obs: Any) -> tuple[bool, str]:
        text = _read_workspace_file(memory, "informe_forense.md")
        if text is None:
            return False, "el archivo del informe no existe tras el intento de escritura"
        return _informe_es_valido(text)

    def verificar_informe(obs: Any) -> tuple[bool, str]:
        out = (obs.output or "")[:4000]
        if "## Cadena de custodia" not in out:
            return False, "lectura sin sección de cadena de custodia"
        return _informe_es_valido(out)

    def recopilar(obs: Any) -> tuple[bool, str]:
        out = obs.output or ""
        if "PERMISO DENEGADO" in out or not out.strip():
            return False, "recopilación sin salida"
        if not _SHA_RE.search(out):
            return False, "la recopilación no produjo hashes SHA-256"
        return True, "datos reales recopilados"

    def componer(obs: Any) -> tuple[bool, str]:
        out = obs.output or ""
        m = re.search(r"con (\d+) hashes", out)
        if m and int(m.group(1)) > 0:
            text = _read_workspace_file(memory, "informe_forense.md")
            if text:
                return _informe_es_valido(text)
            return False, "el documento no existe pese al aviso de éxito"
        return False, "composición sin hashes reales"

    return {
        "redactar_informe": redactar,
        "verificar_informe": verificar_informe,
        # Sufijos: aplican a cualquier profundidad de división fractal.
        "__suffix__ (parte 1/2: recopilar datos)": recopilar,
        "__suffix__ (parte 2/2: componer documento)": componer,
    }


def prepare_demo_workspace(memory: MemoryHub, n_evidence: int = 3) -> None:
    """Siembra evidencias de ejemplo para que el informe forense tenga contenido."""
    ev_dir = os.path.join(memory.workspace, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    for i in range(n_evidence):
        path = os.path.join(ev_dir, f"evidence_{i+1}.txt")
        if not os.path.exists(path):
            blob = (f"EV-{uuid.uuid4().hex}\nartefacto de prueba {i+1}\n"
                    f"registrado {__import__('time').strftime('%Y-%m-%dT%H:%M:%SZ', __import__('time').gmtime())}\n")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(blob)
    # El informe previo se elimina para que el loop parta de cero (re-intento limpio).
    informe = os.path.join(memory.workspace, "informe_forense.md")
    if os.path.exists(informe):
        os.remove(informe)


DEMO_GOAL = (
    "Produce un informe forense completo del workspace en 'informe_forense.md' que incluya "
    "inventario de evidencias, hashes SHA-256 de cada archivo, sección de cadena de custodia "
    "y conclusiones. El informe debe contener datos REALES, no marcadores de posición."
)
