"""Macros deterministas: secuencias de pasos seguros del estudio."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .control import StopToken
from .models import now_iso

DEFAULTS = {
    "ordenar_workspace": [
        {"op": "steward", "topic": "ordena el workspace"},
    ],
    "escritorio_virtual": [
        {"op": "steward", "topic": "personaliza y anima el escritorio virtual"},
    ],
    "limpieza_segura": [
        {"op": "steward", "topic": "limpia basura temporal"},
    ],
    "brief_oportunidades": [
        {"op": "horizon", "topic": "busca oportunidades de trabajo públicas"},
    ],
}


def _path(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), ".a2s", "macros.json")


def list_macros(workspace: str) -> dict[str, Any]:
    custom = {}
    path = _path(workspace)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                custom = json.load(fh)
        except (OSError, ValueError):
            custom = {}
    names = sorted(set(DEFAULTS) | set(custom))
    return {"macros": names, "builtin": list(DEFAULTS), "custom": list(custom)}


def save_macro(workspace: str, name: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")
    if not slug:
        raise ValueError("nombre de macro vacío")
    path = _path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
    data[slug] = {"steps": steps, "updated": now_iso()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return {"status": "saved", "name": slug}


def run_macro(workspace: str, name: str,
              stop: Optional[StopToken] = None) -> dict[str, Any]:
    catalog = {**{k: {"steps": v} for k, v in DEFAULTS.items()}}
    path = _path(workspace)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                catalog.update(json.load(fh))
        except (OSError, ValueError):
            pass
    rec = catalog.get(name)
    if rec is None:
        return {"status": "unknown_macro", "name": name,
                "available": sorted(catalog)}
    results = []
    for step in rec.get("steps") or []:
        if stop:
            stop.raise_if_set()
        op = str(step.get("op") or "")
        topic = str(step.get("topic") or name)
        from .studio import produce
        results.append(produce(workspace, topic, {"kind": op or "steward"},
                               stop=stop))
    return {"status": "macro_done", "name": name, "steps": len(results),
            "results": results, "title": f"Macro {name}",
            "artifacts": [a for r in results for a in r.get("artifacts") or []]}
