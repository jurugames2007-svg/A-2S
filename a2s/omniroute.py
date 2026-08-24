"""Supervisión portable del sidecar OmniRoute incluido por npm.

El arranque real vive en ``npm/lib/omniroute.mjs`` para poder ejecutar el
bundle ``dist`` publicado sin importar ``src``/tsx. Este puente stdlib permite
que incluso ``python -m a2s dashboard`` aproveche ese runtime cuando existe el
checkout o paquete npm, y lo recupera si cae durante una sesión larga.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from typing import Any, Optional


def _gateway_script() -> Optional[str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "npm", "scripts", "gateway.mjs")
    return path if os.path.isfile(path) else None


def ensure_gateway(timeout: int = 90) -> dict[str, Any]:
    """Arranca/verifica OmniRoute mediante el runtime npm, sin lanzar errores."""
    if os.environ.get("A2S_OMNIROUTE", "").strip().lower() == "off":
        return {"state": "disabled", "usable": False}
    configured = os.environ.get("A2S_OMNIROUTE_URL", "").strip()
    if configured and os.environ.get("A2S_OMNIROUTE_MANAGED") != "1":
        return {"state": "configured", "usable": True, "url": configured}
    node = shutil.which("node")
    script = _gateway_script()
    if not node or not script:
        return {"state": "unavailable", "usable": False,
                "detail": "runtime npm/Node no disponible"}
    try:
        proc = subprocess.run(
            [node, script, "start"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            env=os.environ.copy(), stdin=subprocess.DEVNULL)
        data = json.loads((proc.stdout or "").strip() or "{}")
    except subprocess.TimeoutExpired:
        return {"state": "failed", "usable": False,
                "detail": "timeout iniciando OmniRoute"}
    except (OSError, json.JSONDecodeError) as exc:
        return {"state": "failed", "usable": False, "detail": str(exc)[:300]}
    if data.get("usable") and data.get("url"):
        os.environ["A2S_OMNIROUTE_URL"] = str(data["url"])
        if data.get("mode") == "direct-dist":
            os.environ["A2S_OMNIROUTE_MANAGED"] = "1"
    elif proc.returncode and not data.get("detail"):
        data["detail"] = (proc.stderr or f"exit {proc.returncode}")[-300:]
    return data


class OmniRouteWatchdog:
    """Comprueba el sidecar y lo relanza sin bloquear el dashboard."""

    def __init__(self, interval_seconds: int = 15) -> None:
        self.interval_seconds = max(5, int(interval_seconds))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last: dict[str, Any] = {}

    def ensure_now(self) -> dict[str, Any]:
        self.last = ensure_gateway()
        return self.last

    def start(self) -> None:
        if (os.environ.get("A2S_OMNIROUTE", "").strip().lower() == "off" or
                os.environ.get("A2S_OMNIROUTE_PARENT_WATCHDOG") == "1"):
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run,
                                        name="a2s-omniroute-watchdog", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.ensure_now()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
