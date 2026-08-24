"""A²S Control Plane: GUI industrial local, SSE y API stdlib.

La interfaz usa URLs relativas, activos empaquetados y cero CDN/dependencias.
Expone operación de misiones, topología SORL, preview explicable, radar OSS,
conocimiento y auditoría reproducible. Las acciones mutables conservan el
modelo de autenticación del dashboard y validan origen cuando el navegador lo
envía.
"""

from __future__ import annotations

import json
import os
import platform
import queue
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Optional

from . import __version__
from .artifacts import get_artifact, list_artifacts, read_artifact_bytes
from .chat import ChatManager
from .config import Config
from .goals import (DEMO_GOAL, build_demo_step_verifiers,
                    forensic_report_goal_verifier, prepare_demo_workspace)
from .loop import AgentLoop
from .models import now_iso

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


def _asset(name: str) -> bytes:
    return resources.files("a2s.ui").joinpath(name).read_bytes()


class EventHub:
    """Pub/sub acotado para telemetría SSE."""

    def __init__(self, history: int = 500):
        self.subs: set[queue.Queue] = set()
        self.history: list[dict[str, Any]] = []
        self.history_max = history
        self._lock = threading.Lock()

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.history.append(event)
            if len(self.history) > self.history_max:
                self.history = self.history[-self.history_max:]
            for subscriber in list(self.subs):
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    pass

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=600)
        with self._lock:
            self.subs.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self.subs.discard(subscriber)


class MissionManager:
    """Ejecuta una misión a la vez y permite parada cooperativa."""

    PROVIDERS = frozenset({"auto", "heuristic", "openai", "pool"})
    POOL_STRATEGIES = frozenset({"round_robin", "cost_first", "speed_first",
                                 "multi_objective"})

    def __init__(self, hub: EventHub, workspace: str):
        self.hub = hub
        self.workspace = workspace
        self.running = False
        self.current: Optional[AgentLoop] = None
        self.report = None
        self.iterations = 0
        self.started_at = ""
        self.options: dict[str, Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _bounded(value: Any, default: int, low: int, high: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(low, min(high, number))

    def _config(self, raw: dict[str, Any]) -> Config:
        provider = str(raw.get("provider", "auto"))
        if provider not in self.PROVIDERS:
            raise ValueError("proveedor no permitido")
        strategy = str(raw.get("pool_strategy", "multi_objective"))
        if strategy not in self.POOL_STRATEGIES:
            raise ValueError("estrategia de pool no permitida")
        cfg = Config(
            workspace=self.workspace, provider=provider,
            max_wall_seconds=self._bounded(raw.get("max_time"), 600, 10, 3600),
            max_iterations=self._bounded(raw.get("max_iterations"), 60, 1, 500),
            max_rounds=self._bounded(raw.get("max_rounds"), 6, 1, 20),
            allow_network=bool(raw.get("allow_network", True)),
            allow_shell=bool(raw.get("allow_shell", True)),
            quiet=True, pool_strategy=strategy,
        )
        cfg.speculative_candidates = self._bounded(raw.get("speculative"), 0, 0, 8)
        return cfg

    def start(self, goal: Optional[str], demo: bool,
              options: Optional[dict[str, Any]] = None) -> tuple[bool, str]:
        goal = (goal or "").strip()
        if not demo and not goal:
            return False, "el objetivo es obligatorio"
        if len(goal) > 8_000:
            return False, "el objetivo supera 8000 caracteres"
        try:
            config = self._config(options or {})
        except ValueError as exc:
            return False, str(exc)
        with self._lock:
            if self.running:
                return False, "ya hay una misión en curso"
            self.running = True
            self.report = None
            self.current = None
            self.iterations = 0
            self.started_at = now_iso()
            self.options = {
                "provider": config.provider, "max_time": config.max_wall_seconds,
                "max_iterations": config.max_iterations, "max_rounds": config.max_rounds,
                "speculative": config.speculative_candidates,
                "allow_network": config.allow_network, "allow_shell": config.allow_shell,
                "pool_strategy": config.pool_strategy,
            }

        def worker() -> None:
            mission_goal = DEMO_GOAL if demo else goal
            try:
                if demo or "informe forense" in mission_goal.lower():
                    loop = AgentLoop.create(
                        mission_goal, config=config,
                        goal_verifier=forensic_report_goal_verifier)
                    prepare_demo_workspace(loop.memory)
                    loop.step_verifiers = build_demo_step_verifiers(loop.memory)
                else:
                    loop = AgentLoop.create(mission_goal, config=config)
                loop.on_event = self.hub.publish
                with self._lock:
                    self.current = loop
                self.report = loop.run(mission_goal)
            except Exception as exc:  # noqa: BLE001 — control plane informa y sigue vivo
                self.hub.publish({"event": "run_end", "at": now_iso(),
                                  "success": False,
                                  "note": f"excepción en la misión: {type(exc).__name__}: {exc}"})
                self.report = None
            finally:
                with self._lock:
                    self.running = False
                    self.iterations = (getattr(self.report, "iterations", 0)
                                       if self.report else 0)

        threading.Thread(target=worker, name="a2s-mission", daemon=True).start()
        return True, "misión iniciada"

    def stop(self) -> tuple[bool, str]:
        """Acorta el deadline; el paso activo termina dentro de su timeout."""
        with self._lock:
            if not self.running:
                return False, "no hay una misión en curso"
            if self.current is not None:
                self.current.config.max_wall_seconds = 0
        self.hub.publish({"event": "operator_stop", "at": now_iso(),
                          "note": "parada cooperativa solicitada; esperando el paso activo"})
        return True, "parada solicitada"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            report = self.report.to_dict() if self.report else None
            return {"running": self.running, "iterations": self.iterations,
                    "started_at": self.started_at, "options": dict(self.options),
                    "report": report, "events": list(self.hub.history)}

    def provider_for_chat(self):
        """Proveedor de razonamiento para el asistente conversacional.

        Reutiliza el pool SORL si está configurado (OmniRoute, OpenRouter,
        Groq, Gemini…) y, si no hay endpoints, cae al núcleo heurístico.
        El proveedor se construye por llamada para reflejar cambios de
        configuración sin reiniciar el servicio.
        """
        from .providers import get_provider
        # Si la misión activa ya tiene un provider vivo, lo reutilizamos
        # (comparte cuotas/telemetría aprendida).
        with self._lock:
            if self.current is not None:
                return self.current.provider
        cfg = Config(workspace=self.workspace, quiet=True,
                     provider=os.environ.get("A2S_CHAT_PROVIDER", "auto"))
        return get_provider(cfg.provider, config=cfg)

    def start_in_background(self, goal: str, options: Optional[dict[str, Any]] = None
                            ) -> tuple[bool, str]:
        """Lanzamiento desde el chat con opciones por defecto seguras."""
        defaults = {"provider": "auto", "pool_strategy": "multi_objective",
                    "max_time": 600, "max_rounds": 6, "speculative": 0,
                    "allow_network": True, "allow_shell": True}
        if options:
            defaults.update(options)
        return self.start(goal, False, defaults)


class _DashboardHTTPServer(ThreadingHTTPServer):
    """Servidor que no imprime trazas por desconexiones normales del navegador."""

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class DashboardServer:
    def __init__(self, port: int = 8000, workspace: str = "workspace",
                 auto_demo: bool = False, public: bool = False,
                 require_auth: bool = False):
        self.port = port
        self.workspace = os.path.abspath(workspace)
        self.public = public
        self.require_auth = require_auth
        self.host = "0.0.0.0" if public else "127.0.0.1"
        self.hub = EventHub()
        self.missions = MissionManager(self.hub, self.workspace)
        self.chat = ChatManager(
            self.hub, self.workspace,
            get_provider=self.missions.provider_for_chat,
            launch_mission=self.missions.start_in_background,
            get_state=self.missions.snapshot)
        self.auto_demo = auto_demo
        self.growth = None  # AutoLearner: lo arranca cmd_dashboard (si procede)
        self.token_manager = None
        if require_auth:
            from .auth import workspace_token_manager
            self.token_manager = workspace_token_manager(self.workspace)

    def make_http_server(self) -> ThreadingHTTPServer:
        return _DashboardHTTPServer((self.host, self.port), self._handler())

    def serve_forever(self) -> None:
        server = self.make_http_server()
        actual_port = server.server_address[1]
        print(f"[A²S] Control Plane: http://{self.host}:{actual_port}/")
        if self.require_auth:
            print("[A²S] 🔒 autenticación activa; genera token con: "
                  f"python -m a2s token --workspace {self.workspace}")
        elif self.public:
            print("[A²S] ⚠ exposición sin autenticación: añade --auth o limita la red")
        else:
            print("[A²S] solo localhost; --public requiere evaluación de riesgo")
        if self.auto_demo:
            self.missions.start(None, demo=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    def _system_snapshot(self) -> dict[str, Any]:
        return {"version": __version__, "python": platform.python_version(),
                "platform": platform.system(), "workspace": self.workspace,
                "auth_required": self.require_auth, "public": self.public,
                "stdlib_only": True, "at": now_iso()}

    def _pool_snapshot(self, kind: str) -> dict[str, Any]:
        from .provider_pool import build_pool_provider
        cfg = Config(workspace=self.workspace, quiet=True)
        pool = build_pool_provider(cfg)
        try:
            return {"status": pool.status(), "preview": pool.route_preview(kind)}
        finally:
            pool.close()

    def _knowledge_snapshot(self) -> dict[str, Any]:
        from dataclasses import asdict
        from .ecosystem import EcosystemRadar
        from .learner import load_cards
        cards = load_cards(self.workspace)
        return {"cards": [asdict(c) for c in cards[-40:]], "cards_total": len(cards),
                "ecosystem": EcosystemRadar(self.workspace).snapshot()}

    @staticmethod
    def _path(request_path: str) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlsplit(request_path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def _handler(self):
        return type("BoundControlPlaneHandler", (ControlPlaneHandler,),
                    {"control_plane": self})


class ControlPlaneHandler(BaseHTTPRequestHandler):
    """Handler reusable; cada servidor inyecta su control plane por clase."""

    protocol_version = "HTTP/1.1"
    server_version = "A2S-ControlPlane"

    def log_message(self, fmt, *args):
        pass

    def _token(self) -> str:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if part.strip().startswith("a2s_token="):
                return part.strip().split("=", 1)[1]
        auth = self.headers.get("Authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else ""

    def _auth_ok(self) -> bool:
        if not self.control_plane.require_auth:
            return True
        ok, _ = self.control_plane.token_manager.verify(self._token(), scope="dashboard")
        return ok

    def _headers(self, content_type: str, length: int,
                 cache: str = "no-store") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data: blob:; "
                         "media-src 'self' data: blob:; frame-src 'self'; "
                         "object-src 'self'; base-uri 'none'; frame-ancestors 'none'")

    def _json(self, obj: Any, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length > 65_536:
            raise ValueError("payload demasiado grande")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError("JSON inválido") from exc
        if not isinstance(data, dict):
            raise ValueError("se esperaba un objeto JSON")
        return data

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urllib.parse.urlsplit(origin).netloc == self.headers.get("Host", "")

    def _asset(self, name: str, content_type: str) -> None:
        try:
            body = _asset(name)
        except (OSError, FileNotFoundError):
            self._json({"error": "activo no disponible"}, 500)
            return
        self.send_response(200)
        # Los activos cambian junto al agente; revalidarlos evita que una UI
        # antigua siga mostrando «conecta un proveedor» tras actualizar.
        self._headers(content_type, len(body), cache="no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):  # noqa: N802
        path, _query = self.control_plane._path(self.path)
        if path in ASSETS:
            name, content_type = ASSETS[path]
            try:
                length = len(_asset(name))
            except (OSError, FileNotFoundError):
                self.send_error(500)
                return
            self.send_response(200)
            self._headers(content_type, length, cache="no-cache")
            self.end_headers()
        elif path == "/healthz":
            self.send_response(200)
            self._headers("application/json; charset=utf-8", 0)
            self.end_headers()
        else:
            self.send_error(404)

    def do_GET(self):  # noqa: N802
        path, query = self.control_plane._path(self.path)
        if path in ASSETS:
            name, content_type = ASSETS[path]
            self._asset(name, content_type)
            return
        if path == "/healthz":
            self._json({"status": "ok", "version": __version__, "at": now_iso()})
            return
        if path == "/api/login":
            self._json({"auth_required": self.control_plane.require_auth,
                        "authenticated": self._auth_ok()})
            return
        if not self._auth_ok():
            self._json({"error": "no autorizado"}, 401)
            return
        if path == "/api/events":
            self._events()
        elif path == "/api/state":
            growth = self.control_plane.growth
            self._json({**self.control_plane.missions.snapshot(),
                        "system": self.control_plane._system_snapshot(),
                        "growth": growth.snapshot() if growth
                        else {"active": False}})
        elif path == "/api/growth":
            growth = self.control_plane.growth
            self._json(growth.snapshot() if growth else {"active": False})
        elif path == "/api/system":
            self._json(self.control_plane._system_snapshot())
        elif path == "/api/pool":
            kind = query.get("kind", ["general"])[0][:32]
            self._json(self.control_plane._pool_snapshot(kind))
        elif path == "/api/knowledge":
            self._json(self.control_plane._knowledge_snapshot())
        elif path == "/api/audit":
            from .audit import run_audit
            self._json(run_audit())
        elif path == "/api/chat":
            self._json(self.control_plane.chat.snapshot())
        elif path == "/api/artifacts":
            self._json({"artifacts": list_artifacts(
                self.control_plane.workspace)})
        elif path == "/api/artifact":
            self._serve_artifact(query)
        else:
            self._json({"error": "endpoint no encontrado"}, 404)

    def _serve_artifact(self, query: dict[str, list[str]]) -> None:
        """Sirve un archivo del workspace.

        * ``?path=...&download=1`` → bytes con ``Content-Disposition: attachment``.
        * ``?path=...`` sobre medios/PDF → bytes en línea (para ``<img>``,
          ``<audio>``, ``<video>`` o ``<iframe>``).
        * Resto (texto, binario) → metadata JSON (el visor pinta el texto).
        """
        rel = (query.get("path") or [""])[0]
        if not rel:
            self._json({"error": "falta 'path'"}, 400)
            return
        download = (query.get("download") or ["0"])[0] == "1"

        meta = get_artifact(self.control_plane.workspace, rel)
        if meta is None:
            self._json({"error": "archivo no encontrado"}, 404)
            return

        # Los formatos previsualizables nativos del navegador se sirven como
        # bytes (in-line) para que el visor los pueda embeber; el resto va
        # como JSON (texto) o como descarga.
        inline_kinds = {"image", "audio", "video", "pdf"}
        if download or meta["kind"] in inline_kinds:
            result = read_artifact_bytes(self.control_plane.workspace, rel)
            if result is None:
                self._json({"error": "archivo no encontrado"}, 404)
                return
            blob, mime, name = result
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            disposition = "attachment" if download else "inline"
            self.send_header(
                "Content-Disposition",
                f"{disposition}; filename=\"{name}\"")
            self.end_headers()
            try:
                self.wfile.write(blob)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self._json(meta)

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        subscriber = self.control_plane.hub.subscribe()
        try:
            while True:
                try:
                    event = subscriber.get(timeout=15)
                    data = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(data.encode())
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.control_plane.hub.unsubscribe(subscriber)

    def do_POST(self):  # noqa: N802
        path, _query = self.control_plane._path(self.path)
        try:
            payload = self._body()
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        if path == "/api/login":
            self._login(payload)
            return
        if not self._auth_ok():
            self._json({"error": "no autorizado"}, 401)
            return
        if not self._same_origin():
            self._json({"error": "origen no permitido"}, 403)
            return
        if path == "/api/start":
            ok, message = self.control_plane.missions.start(
                payload.get("goal"), bool(payload.get("demo")),
                payload.get("options") if isinstance(payload.get("options"), dict) else {})
            self._json({"status": message}, 202 if ok else
                       (409 if "curso" in message else 400))
        elif path == "/api/stop":
            ok, message = self.control_plane.missions.stop()
            self._json({"status": message}, 202 if ok else 409)
        elif path == "/api/scout":
            from .ecosystem import EcosystemRadar
            query = str(payload.get("query", ""))[:160]
            limit = MissionManager._bounded(payload.get("limit"), 6, 1, 12)
            radar = EcosystemRadar(self.control_plane.workspace)
            report = radar.scan(query=query, limit_per_query=limit)
            self.control_plane.hub.publish({"event": "ecosystem_scan", "at": now_iso(),
                               "added": len(report["added"]),
                               "total": report["total"]})
            self._json({"scan": report, **radar.snapshot()}, 200)
        elif path == "/api/chat":
            message = str(payload.get("message", "")).strip()
            ok, msg = self.control_plane.chat.send(message)
            if not ok:
                self._json({"error": msg}, 409 if "curso" in msg or "respondiendo" in msg else 400)
            else:
                self._json({"status": msg}, 202)
        elif path == "/api/chat/clear":
            self.control_plane.chat.clear()
            self._json({"status": "conversación reiniciada"})
        else:
            self._json({"error": "endpoint no encontrado"}, 404)

    def _login(self, payload: dict[str, Any]) -> None:
        if not self.control_plane.require_auth:
            self._json({"status": "autenticación desactivada"})
            return
        token = str(payload.get("token", ""))
        ok, info = self.control_plane.token_manager.verify(token, scope="dashboard")
        if not ok:
            self._json({"error": f"token inválido: {info}"}, 401)
            return
        body = b'{"status":"autenticado"}'
        self.send_response(200)
        self.send_header("Set-Cookie",
                         f"a2s_token={token}; Path=/; HttpOnly; SameSite=Strict")
        self._headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)
