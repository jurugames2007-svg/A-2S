#!/usr/bin/env python3
"""Servidor LLM simulado (API OpenAI-compatible, solo stdlib) para probar el
SORL **sin claves externas ni coste**.

Un solo proceso simula tres proveedores con carácter distinto:

  ruta        latencia  límite real   carácter
  /fast/v1    ~20 ms    5 rpm         gratis y veloz, pero satura enseguida
                                       (sirve para VER el failover y el
                                       aprendizaje de cuota en acción)
  /mid/v1     ~80 ms    30 rpm        gratis, término medio: absorbe la carga
  /pro/v1    ~250 ms    sin límite    el "de pago": el scheduler solo lo usa
                                       si no queda otra (cost_first evita)

Los 429 se devuelven con cabecera ``Retry-After: 30`` — el pool los respeta
(cuarentena + migración), nunca los evita.

Uso::

    python3 examples/mock_llm_server.py [--port 8765]
    curl http://127.0.0.1:8765/stats     # contadores en vivo por ruta
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTES = {
    "/fast/v1": {"latency": 0.02, "rpm": 5, "model": "mock-fast-8b"},
    "/mid/v1": {"latency": 0.08, "rpm": 30, "model": "mock-mid-70b"},
    "/pro/v1": {"latency": 0.25, "rpm": 0, "model": "mock-pro-max"},
}

_lock = threading.Lock()
_hits: dict[str, deque] = {r: deque() for r in ROUTES}   # ventana 60s por ruta
_stats = {r: {"ok": 0, "rate_limited": 0} for r in ROUTES}


def _over_limit(route: str) -> bool:
    cfg = ROUTES[route]
    if cfg["rpm"] <= 0:
        return False
    now = time.monotonic()
    with _lock:
        q = _hits[route]
        while q and q[0] <= now - 60.0:
            q.popleft()
        if len(q) >= cfg["rpm"]:
            return True
        q.append(now)
        return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silencio (ver /stats)
        pass

    def _json(self, code: int, obj: dict, headers: dict | None = None) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/stats":
            with _lock:
                out = {r: {**s, "window_used": len(_hits[r])} for r, s in _stats.items()}
            self._json(200, out)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        route = next((r for r in ROUTES if self.path.startswith(r)), None)
        if route is None:
            self._json(404, {"error": f"ruta desconocida: {self.path}"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "json inválido"})
            return
        if not self.path.endswith("/chat/completions"):
            self._json(404, {"error": "solo /chat/completions"})
            return
        if _over_limit(route):
            with _lock:
                _stats[route]["rate_limited"] += 1
            self._json(429, {"error": {"message": "Rate limit exceeded",
                                       "type": "rate_limit_error"}},
                       headers={"Retry-After": "30"})
            return
        cfg = ROUTES[route]
        time.sleep(cfg["latency"])
        user_full = ""
        for msg in reversed(payload.get("messages", [])):
            if msg.get("role") == "user":
                user_full = str(msg.get("content", ""))
                break
        user = user_full[:60]
        model = payload.get("model") or cfg["model"]
        content = f"[{route.split('/')[1]}] eco: {user}"
        # Solo el modelo "pro" sabe seguir esquemas JSON estructurados
        # (los eco gratuitos devuelven prosa — así se VE la medición de
        # capacidades del SORL: el pool aprende quién planifica de verdad).
        # La detección usa el texto COMPLETO: "Devuelve JSON" aparece al
        # final del prompt, más allá de los 60 chars que muestra el eco.
        if route == "/pro/v1" and "Devuelve JSON" in user_full:
            content = ('{"strategy": "mock-pro", "steps": [{"id": "s1", '
                       '"goal": "inventariar", "approach": "listado ordenado", '
                       '"tool": "shell", "params": {"command": "ls"}, '
                       '"success_criteria": ["listado obtenido"], "depends_on": []}]}')
        with _lock:
            _stats[route]["ok"] += 1
        self._json(200, {
            "id": f"chatcmpl-mock-{int(time.time()*1000)}",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 25},
        })


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[mock-llm] escuchando en http://{args.host}:{args.port}")
    for r, cfg in ROUTES.items():
        rpm = f"{cfg['rpm']} rpm" if cfg["rpm"] else "sin límite"
        print(f"[mock-llm]   {r:<9} {cfg['model']:<14} {cfg['latency']*1000:>4.0f} ms  {rpm}")
    print("[mock-llm] GET /stats para contadores")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
