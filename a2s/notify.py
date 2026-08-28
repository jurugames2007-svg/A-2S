"""Notificaciones salientes (criterios 49/151 del roadmap).

Backends declarados como URL-esquema, repetibles con --notify:

* ``webhook:https://...``  → POST JSON (eventos de misión/escalado/pool)
* ``file:ruta``            → append JSONL (audit-friendly)
* ``print:``               → stdout (testing/composición)

Fronteras: el envío NUNCA rompe la misión (best-effort, errores al log), no
se envían secretos (solo asunto/cuerpo/estado) y el webhook respeta un
timeout corto. SMTP/email queda en roadmap (requiere credenciales y cuidado
que escapan al stdlib honesto); ntfy.sh funciona HOY vía webhook:.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

from .models import now_iso


def _post_webhook(url: str, payload: dict, timeout: int = 8) -> str:
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "A2S-notify/1.7 (honesto)"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return f"HTTP {resp.status}"


def notify(targets: list[str], asunto: str, cuerpo: str,
           nivel: str = "info", extra: Optional[dict] = None) -> list[str]:
    """Envía una notificación a cada destino. Best-effort: devuelve el
    resultado por destino; nunca lanza (la misión sigue)."""
    resultados = []
    payload = {"at": now_iso(), "asunto": asunto, "cuerpo": cuerpo[:4000],
               "nivel": nivel, **(extra or {})}
    for target in targets or []:
        target = (target or "").strip()
        try:
            if target.startswith("webhook:"):
                resultados.append(f"{target[:48]}… → {_post_webhook(target[8:], payload)}")
            elif target.startswith("file:"):
                path = target[5:]
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                resultados.append(f"file:{path} → ok")
            elif target.startswith("print:"):
                print(f"[notify:{nivel}] {asunto}: {cuerpo[:200]}", flush=True)
                resultados.append("print → ok")
            else:
                resultados.append(f"{target[:32]}… → esquema no soportado "
                                  "(webhook:|file:|print:)")
        except Exception as exc:  # noqa: BLE001 — notificar nunca rompe la misión
            resultados.append(f"{target[:48]}… → ERROR {type(exc).__name__}")
    return resultados
