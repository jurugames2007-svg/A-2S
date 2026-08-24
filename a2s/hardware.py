"""Diagnóstico de hardware de solo lectura y listas BIOS. Sin flashear."""

from __future__ import annotations

import os
import platform
from typing import Any, Optional

from .control import StopToken
from .finder import fold
from .models import now_iso


def diagnose(workspace: str, topic: str = "",
             stop: Optional[StopToken] = None) -> dict[str, Any]:
    if stop:
        stop.raise_if_set()
    text = fold(topic)
    if any(w in text for w in ("flash", "flashear", "overclock", "undervolt",
                               "modificar bios", "actualizar bios")):
        note = _refuse_write()
        status = "refused_hardware_write"
    else:
        note = _playbook()
        status = "hardware_brief"
    snap = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "(no expuesto)",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    md = (
        "# Diagnóstico de hardware (solo lectura)\n\n"
        f"Generado: {now_iso()}\n\n"
        "> A²S no flashea BIOS, no overclockea GPU/CPU y no escribe en firmware.\n"
        "> Un error ahí puede ladrillar el equipo. Eso lo hace el fabricante "
        "o un técnico con el binario oficial.\n\n"
        "## Snapshot del proceso\n\n"
        + "\n".join(f"- **{k}**: `{v}`" for k, v in snap.items())
        + "\n\n" + note
    )
    folder = os.path.join(os.path.abspath(workspace), "hardware")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "brief.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    return {"status": status, "title": "Diagnóstico hardware",
            "snapshot": snap, "artifacts": ["hardware/brief.md"],
            "writes_firmware": False}


def _refuse_write() -> str:
    return (
        "## Pedido rechazado\n\n"
        "Flashear BIOS u overclockear desde un agente autónomo no es seguro. "
        "Pasos legítimos:\n\n"
        "1. Identifica marca y modelo exactos (etiqueta, `dmidecode` en Linux "
        "o Información del sistema en Windows).\n"
        "2. Descarga el firmware **solo** del fabricante.\n"
        "3. Verifica checksum. Usa su utilidad oficial.\n"
        "4. Energía estable. No apagues a mitad.\n"
        "5. Si no estás seguro, no lo hagas: lleva el equipo a servicio.\n"
        "\nA²S puede ayudarte a **preparar la lista**, no a pulsar el flash.\n"
    )


def _playbook() -> str:
    return (
        "## Optimización segura (sin tocar voltajes)\n\n"
        "- Cierra procesos que no uses; mide con el monitor del SO.\n"
        "- Actualiza el driver de GPU desde el fabricante (NVIDIA/AMD/Intel), "
        "no desde un empaquetador desconocido.\n"
        "- En portátiles: perfil equilibrado, no 'rendimiento máximo' 24/7.\n"
        "- Limpia polvo y comprueba temperaturas. El thermal throttle no se "
        "arregla con un flag mágico.\n"
        "- BIOS: entra con la tecla del fabricante (Del/F2/F10). Anota "
        "valores por defecto **antes** de cambiar boot order o virtualización.\n"
        "- No desactives Secure Boot para 'ir más rápido'.\n"
    )
