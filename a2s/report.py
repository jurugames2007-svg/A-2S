"""Generación del informe forense de ejecución (texto, Markdown, JSON)."""

from __future__ import annotations

import json
import os
from typing import Any

from .models import RunReport


def render_text(report: RunReport) -> str:
    lines = [
        "=" * 72,
        " INFORME DE EJECUCIÓN A²S",
        "=" * 72,
        f" Run:          {report.run_id}",
        f" Objetivo:     {report.goal}",
        f" Resultado:    {'✔ CUMPLIDO' if report.success else '◐ PARCIAL (reanudable)'}",
        f" Iteraciones:  {report.iterations}",
        f" Pasos:        {report.steps}",
        f" Tiempo:       {report.wall_seconds}s",
        f" Estancamientos superados: {report.stagnation_events}",
        "",
        " Protocolo adaptativo:",
        f"   Necesidad: {', '.join(report.capability_protocol.get('need_types', [])) or 'no registrada'}",
        "   Capacidades: " + (", ".join(
            capability.get("label", capability.get("id", ""))
            for capability in report.capability_protocol.get("capabilities", []))
            or "no registradas"),
        "",
        " Estrategias (metaprendizaje):",
    ]
    for s in report.strategies:
        lines.append(f"   - {s['name']:24} usos={s['used']:3} "
                     f"ganadas={s['wins']:3} tasa={s['win_rate']}")
    lines.append("")
    lines.append(" Artefactos registrados (cadena de custodia):")
    if report.artifacts:
        for a in report.artifacts:
            lines.append(f"   - {a}")
    else:
        lines.append("   (ninguno)")
    lines.append("")
    lines.append(" Cronología:")
    for e in report.timeline:
        detail = ", ".join(f"{k}={str(v)[:60]}" for k, v in e.items()
                           if k not in ("at", "event"))
        lines.append(f"   {e['at']}  {e['event']:<16} {detail}")
    lines += ["", " Nota final:"]
    lines += [f"   {line}" for line in report.final_note.split(" | ")]
    lines.append("=" * 72)
    return "\n".join(lines)


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# Informe de ejecución A²S — {report.run_id}",
        "",
        f"- **Objetivo:** {report.goal}",
        f"- **Resultado:** {'✔ CUMPLIDO' if report.success else '◐ PARCIAL (reanudable)'}",
        f"- **Iteraciones:** {report.iterations} · **Pasos:** {report.steps} · "
        f"**Tiempo:** {report.wall_seconds}s",
        f"- **Estancamientos superados:** {report.stagnation_events}",
        f"- **Rango:** {report.started_at} → {report.ended_at}",
        "",
        "## Protocolo adaptativo Aegis",
        "",
        f"- **Necesidad:** {', '.join(report.capability_protocol.get('need_types', [])) or 'no registrada'}",
        "- **Capacidades:** " + (", ".join(
            capability.get("label", capability.get("id", ""))
            for capability in report.capability_protocol.get("capabilities", []))
            or "no registradas"),
        "- **Criterios:** " + ("; ".join(
            report.capability_protocol.get("acceptance_criteria", []))
            or "no registrados"),
        "",
        "## Metaprendizaje (estrategias)",
        "",
        "| Estrategia | Usos | Ganadas | Tasa |",
        "|---|---|---|---|",
    ]
    for s in report.strategies:
        lines.append(f"| {s['name']} | {s['used']} | {s['wins']} | {s['win_rate']} |")
    lines += ["", "## Artefactos (cadena de custodia)", ""]
    lines += [f"- `{a}`" for a in report.artifacts] or ["(ninguno)"]
    lines += ["", "## Cronología", "", "| Hora | Evento | Detalle |", "|---|---|---|"]
    for e in report.timeline:
        detail = ", ".join(f"{k}={str(v)[:50]}" for k, v in e.items()
                           if k not in ("at", "event"))
        lines.append(f"| {e['at']} | {e['event']} | {detail} |")
    lines += ["", "## Nota final", "", report.final_note]
    return "\n".join(lines)


def save_report(report: RunReport, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    with open(path + ".json", "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, ensure_ascii=False, indent=2)
    return path
