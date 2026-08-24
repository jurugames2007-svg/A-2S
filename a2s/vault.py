"""Bóveda honesta: etiquetas, no semillas. Nunca genera wallets reales."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .control import StopToken
from .models import now_iso


def handle(workspace: str, topic: str,
           stop: Optional[StopToken] = None) -> dict[str, Any]:
    if stop:
        stop.raise_if_set()
    folder = os.path.join(os.path.abspath(workspace), "vault")
    os.makedirs(folder, exist_ok=True)
    md = (
        "# Política de bóveda A²S\n\n"
        f"{now_iso()}\n\n"
        "## Rechazo explícito\n\n"
        "No genero wallets de criptomonedas, seed phrases, claves privadas "
        "ni cuentas en terceros. Un agente que escribe una semilla en un "
        "workspace o un chat está regalándola. Si la pierdes, el dinero "
        "no se recupera. Si alguien la lee, te la roban.\n\n"
        "## Qué sí puedes hacer\n\n"
        "1. Crea la wallet **tú** en el dispositivo oficial (hardware o app "
        "del proyecto). Anota la semilla en papel, offline.\n"
        "2. Aquí solo guardo **etiquetas públicas**: nombre de la cuenta, "
        "red, dirección pública que **tú** pegues.\n"
        "3. No pidas que A²S 'cree la cuenta de banco/correo/exchange'. "
        "Eso viola términos y suele ser fraude si no eres tú.\n\n"
        f"Pedido original: {topic}\n"
    )
    path = os.path.join(folder, "policy.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    labels = os.path.join(folder, "labels.json")
    if not os.path.isfile(labels):
        with open(labels, "w", encoding="utf-8") as fh:
            json.dump({"labels": [], "secrets": "never"}, fh, indent=2)
    return {"status": "wallet_refused", "title": "Bóveda (sin secretos)",
            "generated_keys": False,
            "artifacts": ["vault/policy.md", "vault/labels.json"]}
