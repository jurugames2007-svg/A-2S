"""Horizonte largo: oportunidades públicas. No suplanta al usuario."""

from __future__ import annotations

import os
from typing import Any, Optional

from .control import StopToken
from .models import now_iso


def brief(workspace: str, topic: str,
          stop: Optional[StopToken] = None) -> dict[str, Any]:
    if stop:
        stop.raise_if_set()
    folder = os.path.join(os.path.abspath(workspace), "opportunities")
    os.makedirs(folder, exist_ok=True)
    md = (
        f"# Brief de oportunidades\n\nGenerado: {now_iso()}\n\n"
        f"Encargo: {topic}\n\n"
        "## Lo que A²S sí hace\n\n"
        "- Redacta un perfil y un plan de búsqueda de varios días.\n"
        "- Prepara consultas públicas (portales de empleo, licitaciones, "
        "becas) para que **tú** las ejecutes o las revises.\n"
        "- Borradores de carta y seguimiento. No envía nada en tu nombre.\n\n"
        "## Lo que no hace\n\n"
        "- No crea cuentas en portales ajenos.\n"
        "- No se hace pasar por ti.\n"
        "- No opera dinero ni wallets.\n"
        "- Un ciclo de horas/días es una **cola de briefs**, no un empleado "
        "invisible con tu identidad.\n\n"
        "## Plan de 7 días\n\n"
        "1. Escribe 8 líneas de perfil (oficio, zona, restricción de sueldo).\n"
        "2. Elige 2 portales oficiales de tu país y 1 de oficio.\n"
        "3. Postula a 3 avisos reales. Guarda capturas en `opportunities/`.\n"
        "4. Pídeme que critique tu CV o la carta (artefacto, no envío).\n"
        "5. Repite. El horizonte se mide en postulaciones hechas, no en promesas.\n\n"
        "## Consultas sugeridas\n\n"
        f"- `{topic}` + ciudad + 'empleo' / 'job'\n"
        "- sitio oficial de empleo de tu gobierno\n"
        "- cooperativas / pymes del oficio, no solo marketplaces\n"
    )
    path = os.path.join(folder, "brief.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    plan = os.path.join(folder, "plan7d.md")
    with open(plan, "w", encoding="utf-8") as fh:
        fh.write("# Plan 7 días\n\n" + "\n".join(
            f"- Día {i}: revisar brief y anotar 1 evidencia." for i in range(1, 8)))
    return {"status": "horizon_brief", "title": "Oportunidades (públicas)",
            "artifacts": ["opportunities/brief.md", "opportunities/plan7d.md"],
            "impersonates": False}
