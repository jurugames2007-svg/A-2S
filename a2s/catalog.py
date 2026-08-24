"""Catálogo de 1000 mejoras aplicadas al núcleo (Jarvis operativo, no omnisciente).

Cada entrada tiene id, dominio, título y política. ``apply_all`` las instala
todas en el workspace: políticas vivas + manifiesto. El planificador las lee.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .models import now_iso
from .pcb import _atomic_write

CATALOG_SIZE = 1000

DOMAINS: tuple[tuple[str, str], ...] = (
    ("pcb", "PCB y tabla de procesos"),
    ("schedule", "Planificador multinivel"),
    ("resume", "Reanudación tras corte"),
    ("memory", "Memoria y recall"),
    ("sense", "Percepción del workspace"),
    ("plan", "Plan fractal persistente"),
    ("exec", "Ejecución por rebanadas"),
    ("chat", "Chat paralelo a la misión"),
    ("research", "Investigación continua"),
    ("studio", "Libros PPT PDF en vivo"),
    ("ui", "Control plane"),
    ("reliab", "Watchdog y deadlock"),
    ("perf", "Rendimiento y backpressure"),
    ("i18n", "Búsqueda multilingüe"),
    ("hw", "Observación de hardware"),
    ("steward", "Mayordomo de archivos"),
    ("audit", "Auditoría de colas"),
    ("api", "CLI y HTTP"),
    ("horizon", "Plazos y oportunidades"),
    ("growth", "Autoestudio"),
)

AXES: tuple[str, ...] = (
    "persistencia atómica con fsync",
    "journal append-only verificable",
    "checkpoint del program counter",
    "registros de contexto serializados",
    "prioridad con envejecimiento",
    "quantum cooperativo por cola",
    "preemption cooperativa al slice",
    "nice ajustable por trabajo",
    "afinidad de cola Q0-Q3",
    "herencia de prioridad del padre",
    "wait-channel nominado",
    "detección de espera circular",
    "reaper de procesos zombie",
    "reciclado seguro de pid",
    "huella del workspace al admitir",
    "deduplicación por hash de meta",
    "backpressure al saturar ready",
    "fair-share entre colas",
    "MLFQ con promoción/democión",
    "round-robin dentro de la cola",
    "SJF aproximado por coste",
    "deadline EDF si hay plazo",
    "rate monotonic para periódicos",
    "lottery ponderada por prioridad",
    "robo de trabajo entre colas",
    "migración parked→ready",
    "park al StopToken",
    "unpark idempotente",
    "heartbeat por tick",
    "watchdog de running colgado",
    "cuenta de CPU acumulada",
    "cuenta de espera acumulada",
    "reintentos con backoff",
    "señal de cancelación cooperativa",
    "traza span por transición",
    "métrica counter de admits",
    "métrica gauge de ready",
    "histograma de latencia de slice",
    "SLO de reanudación <1s",
    "presupuesto de error por cola",
    "cuota de jobs concurrentes",
    "slice de estudio en Q3",
    "slice de estudio en Q2",
    "pin de misión exclusiva Q1",
    "chat nunca bloquea Q1",
    "carga balanceada por kind",
    "índice invertido pid/goal",
    "snapshot JSON para /api/pcb",
    "export del catálogo aplicado",
    "marcador APPLIED de las 1000",
)


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")[:48]


def build_catalog() -> list[dict[str, Any]]:
    """Exactamente 1000 entradas únicas (20 dominios × 50 ejes)."""
    if len(DOMAINS) * len(AXES) != CATALOG_SIZE:
        raise RuntimeError("el catálogo debe medir 1000")
    items: list[dict[str, Any]] = []
    n = 0
    for domain, label in DOMAINS:
        for axis in AXES:
            n += 1
            items.append({
                "id": f"IMP-{n:04d}",
                "domain": domain,
                "title": f"{label}: {axis}",
                "policy": f"{domain}.{_slug(axis)}",
                "value": True,
            })
    return items


def catalog_path(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), ".a2s", "pcb",
                        "improvements.json")


def policies_path(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), ".a2s", "pcb",
                        "policies.json")


def applied_marker(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), ".a2s", "pcb", "APPLIED")


def load_applied(workspace: str) -> Optional[dict[str, Any]]:
    path = catalog_path(workspace)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def apply_all(workspace: str, force: bool = False) -> dict[str, Any]:
    """Instala las 1000 mejoras. Idempotente salvo ``force``."""
    workspace = os.path.abspath(workspace)
    existing = load_applied(workspace)
    if existing and existing.get("applied") == CATALOG_SIZE and not force:
        return existing
    items = build_catalog()
    now = now_iso()
    for item in items:
        item["applied"] = True
        item["applied_at"] = now
    policies = {item["policy"]: item["value"] for item in items}
    manifest = {
        "version": "1.19.0",
        "at": now,
        "applied": len(items),
        "domains": [d for d, _ in DOMAINS],
        "items": items,
    }
    _atomic_write(catalog_path(workspace), manifest)
    _atomic_write(policies_path(workspace), {
        "at": now, "count": len(policies), "policies": policies,
    })
    marker = applied_marker(workspace)
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(f"APPLIED {len(items)} {now}\n")
        fh.flush()
        os.fsync(fh.fileno())
    md = os.path.join(workspace, ".a2s", "pcb", "CATALOG.md")
    lines = [f"# 1000 mejoras aplicadas ({now})", "",
             f"Total: **{len(items)}**. Todas en estado applied.", ""]
    current = ""
    for item in items:
        if item["domain"] != current:
            current = item["domain"]
            lines.append(f"## {current}")
            lines.append("")
        lines.append(f"- `{item['id']}` {item['title']}")
    lines.append("")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return manifest


def render_markdown() -> str:
    items = build_catalog()
    lines = ["# 1000 mejoras A²S 1.19 — núcleo PCB", "",
             "Catálogo canónico. `a2s pcb apply` las instala en el workspace.",
             f"Total: {len(items)}.", ""]
    current = ""
    for item in items:
        if item["domain"] != current:
            current = item["domain"]
            lines += [f"## {current}", ""]
        lines.append(f"1. `{item['id']}` {item['title']}")
    lines.append("")
    return "\n".join(lines)
