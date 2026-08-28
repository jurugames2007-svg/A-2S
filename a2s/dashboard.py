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
from .control import JobSupervisor, StopToken, acquire
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
        self.stop_token = StopToken()
        self.jobs = JobSupervisor(publish=self.hub.publish)

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
        if not acquire(self._lock, 1.5):
            return False, "no pude tomar el candado de misión (evito deadlock)"
        try:
            if self.running:
                return False, "ya hay una misión en curso"
            self.running = True
            self.report = None
            self.current = None
            self.iterations = 0
            self.started_at = now_iso()
            self.stop_token = StopToken()
            self.options = {
                "provider": config.provider, "max_time": config.max_wall_seconds,
                "max_iterations": config.max_iterations, "max_rounds": config.max_rounds,
                "speculative": config.speculative_candidates,
                "allow_network": config.allow_network, "allow_shell": config.allow_shell,
                "pool_strategy": config.pool_strategy,
            }
        finally:
            self._lock.release()

        def worker() -> None:
            mission_goal = DEMO_GOAL if demo else goal
            try:
                if self.stop_token.is_set():
                    self.hub.publish({"event": "operator_stop", "at": now_iso(),
                                      "note": "parada antes de arrancar el loop"})
                    return
                if demo or "informe forense" in mission_goal.lower():
                    loop = AgentLoop.create(
                        mission_goal, config=config,
                        goal_verifier=forensic_report_goal_verifier)
                    prepare_demo_workspace(loop.memory)
                    loop.step_verifiers = build_demo_step_verifiers(loop.memory)
                else:
                    loop = AgentLoop.create(mission_goal, config=config)
                loop.stop_token = self.stop_token
                loop.registry.stop_token = self.stop_token
                if self.stop_token.is_set():
                    loop.request_stop(self.stop_token.reason or "operator")
                loop.on_event = self.hub.publish
                if acquire(self._lock, 1.0):
                    try:
                        self.current = loop
                    finally:
                        self._lock.release()
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
        """Corta el token, los trabajos laterales y el plazo de la misión."""
        cancelled = self.jobs.cancel_all("operator")
        with self._lock:
            running = self.running
            current = self.current
            self.stop_token.set("operator")
            if current is not None:
                current.request_stop("operator")
        if not running and not cancelled:
            return False, "no hay una misión en curso"
        self.hub.publish({"event": "operator_stop", "at": now_iso(),
                          "note": "parada cooperativa: token, jobs y plazo cortados"})
        return True, "parada solicitada"

    def snapshot(self) -> dict[str, Any]:
        if not acquire(self._lock, 1.0):
            return {"running": self.running, "iterations": self.iterations,
                    "started_at": self.started_at, "options": {},
                    "report": None, "events": [], "jobs": self.jobs.snapshot()}
        try:
            report = self.report.to_dict() if self.report else None
            return {"running": self.running, "iterations": self.iterations,
                    "started_at": self.started_at, "options": dict(self.options),
                    "report": report, "events": list(self.hub.history),
                    "jobs": self.jobs.snapshot()}
        finally:
            self._lock.release()

    def provider_for_chat(self):
        """Proveedor AISLADO: nunca se reutiliza el de la misión (anti-deadlock)."""
        from .providers import HeuristicProvider, get_provider
        try:
            cfg = Config(workspace=self.workspace, quiet=True,
                         provider=os.environ.get("A2S_CHAT_PROVIDER", "heuristic"))
            # heuristic por defecto en chat: no comparte pool ni candados
            # con la misión. Si el operador pide auto, se crea OTRA instancia.
            kind = cfg.provider if cfg.provider in ("heuristic", "auto") else "heuristic"
            if kind == "auto":
                return get_provider("auto", config=cfg)
            return HeuristicProvider()
        except Exception:
            return HeuristicProvider()

    def run_search(self, query: str) -> dict[str, Any]:
        from .finder import RepoFinder
        return RepoFinder(self.workspace).search(query, limit=8, allow_network=True)

    def run_create(self, topic: str, options: Optional[dict[str, Any]] = None
                   ) -> tuple[bool, str]:
        options = options or {}

        def job(token: StopToken) -> dict[str, Any]:
            from .studio import produce

            def progress(percent: int, note: str, extra=None) -> None:
                payload = {"event": "studio_progress", "at": now_iso(),
                           "percent": percent, "note": note,
                           "title": topic}
                if extra:
                    payload.update(extra)
                self.hub.publish(payload)

            result = produce(self.workspace, topic, options, stop=token,
                             progress=progress)
            self.hub.publish({"event": "artifact_ready", "at": now_iso(),
                              "artifacts": result.get("artifacts", []),
                              "title": result.get("title", topic),
                              "kind": result.get("status")})
            return result

        kind = "slides" if options.get("slides") else "create"
        return self.jobs.submit(kind, job, {"topic": topic})

    def run_action(self, action_id: str, topic: str = "") -> dict[str, Any]:
        from .actions import run_local
        local = run_local(self.workspace, action_id, topic)
        if not local.get("ok"):
            return local
        mode = local.get("mode")
        if mode == "stop":
            ok, message = self.stop()
            local["message"] = message
            local["ok"] = ok
            return local
        if mode == "search":
            query = local.get("topic") or "agentes autónomos"
            report = self.run_search(query)
            local["result"] = report
            local["view"] = "results"
            local["queued"] = False
            local["message"] = f"Búsqueda lista: {query}"
            return local
        if mode == "mission":
            ok, message = self.start_in_background(local.get("topic") or topic)
            local["queued"] = ok
            local["message"] = message
            return local
        if mode == "studio":
            options = {}
            if local.get("kind"):
                options["kind"] = local["kind"]
            ok, message = self.run_create(local.get("topic") or topic, options)
            local["queued"] = ok
            local["message"] = message
            local["view"] = "results"
            return local
        return local

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
            get_state=self.missions.snapshot,
            stop_all=self.missions.stop,
            run_search=self.missions.run_search,
            run_create=self.missions.run_create)
        if os.environ.get("A2S_PUBLIC", "").strip() in {"1", "true", "yes"}:
            self.public = True
            self.host = "0.0.0.0"
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
        origin_host = urllib.parse.urlsplit(origin).netloc.lower()
        host = (self.headers.get("Host") or "").lower()
        if origin_host == host:
            return True
        if self.control_plane.public:
            return True
        # Previews / proxies: el Host interno no coincide con el origen público.
        for suffix in (".e2b.app", ".arena.ai", ".localhost", "localhost"):
            if origin_host.endswith(suffix) or origin_host == suffix:
                return True
        return False

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
            from .kernel import Kernel
            pcb = Kernel.open(self.control_plane.workspace).snapshot()
            self._json({**self.control_plane.missions.snapshot(),
                        "system": self.control_plane._system_snapshot(),
                        "growth": growth.snapshot() if growth
                        else {"active": False},
                        "pcb": pcb})
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
        elif path == "/api/recursos":
            from .recursos import api_snapshot
            self._json(api_snapshot(
                consulta=(query.get("q") or [""])[0][:200],
                cat=(query.get("cat") or [""])[0][:40],
                workspace=self.control_plane.workspace))
        elif path == "/api/secops":
            from .secops import resumen_secops
            self._json(resumen_secops(self.control_plane.workspace))
        elif path == "/api/capacidades":
            from .capacidades import resumen, seleccionar
            objetivo = (query.get("objetivo") or [""])[0][:200]
            if objetivo:
                perfil = (query.get("perfil") or [""])[0][:32]
                self._json(seleccionar(
                    objetivo,
                    contexto=(query.get("ctx") or [""])[0][:300],
                    workspace=self.control_plane.workspace,
                    perfil=perfil))
            else:
                self._json(resumen(self.control_plane.workspace))
        elif path == "/api/audit":
            from .audit import run_audit
            self._json(run_audit())
        elif path == "/api/chat":
            self._json(self.control_plane.chat.snapshot())
        elif path == "/api/pcb":
            from .kernel import Kernel
            self._json(Kernel.open(self.control_plane.workspace).snapshot())
        elif path == "/api/actions":
            from .actions import catalog
            self._json({"actions": catalog()})
        elif path == "/api/jobs":
            self._json({"jobs": self.control_plane.missions.jobs.snapshot()})
        elif path == "/api/find":
            query = (query.get("q") or query.get("query") or [""])[0]
            self._json(self.control_plane.missions.run_search(query))
        elif path == "/api/artifacts":
            self._json({"artifacts": list_artifacts(
                self.control_plane.workspace)})
        elif path == "/api/artifact":
            self._serve_artifact(query)
        else:
            self._json({"error": "endpoint no encontrado"}, 404)

    def _serve_artifact(self, query: dict[str, list[str]]) -> None:
        """Sirve un archivo del workspace.

        * ``?path=...`` → metadata JSON (el visor necesita ``raw_url``).
        * ``?path=...&raw=1`` → bytes en línea (``<img>``, ``<iframe>``, PDF).
        * ``?path=...&download=1`` → bytes con ``Content-Disposition: attachment``.
        """
        rel = (query.get("path") or [""])[0]
        if not rel:
            self._json({"error": "falta 'path'"}, 400)
            return
        download = (query.get("download") or ["0"])[0] == "1"
        raw = (query.get("raw") or ["0"])[0] == "1"

        meta = get_artifact(self.control_plane.workspace, rel)
        if meta is None:
            self._json({"error": "archivo no encontrado"}, 404)
            return

        inline_kinds = {"image", "audio", "video", "pdf", "html"}
        if download or (raw and meta["kind"] in inline_kinds):
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
            self._post_scout(payload)
        elif path == "/api/chat":
            self._post_chat(payload)
        elif path == "/api/chat/clear":
            self.control_plane.chat.clear()
            self._json({"status": "conversación reiniciada"})
        elif path == "/api/find":
            query = str(payload.get("query") or payload.get("q") or "")
            self._json(self.control_plane.missions.run_search(query))
        elif path == "/api/pcb/resume":
            from .kernel import Kernel
            kernel = Kernel.open(self.control_plane.workspace)
            restored = kernel.resume_all()
            self.control_plane.hub.publish(
                {"event": "pcb_resume", "at": now_iso(),
                 "restored": len(restored)})
            self._json({"status": "ok", "restored": len(restored),
                        "pcb": kernel.snapshot()})
        elif path == "/api/studio":
            topic = str(payload.get("topic") or payload.get("goal") or "")
            options = payload.get("options") if isinstance(
                payload.get("options"), dict) else {}
            ok, message = self.control_plane.missions.run_create(topic, options)
            self._json({"status": message}, 202 if ok else 409)
        elif path == "/api/action":
            action_id = str(payload.get("id") or payload.get("action") or "")
            topic = str(payload.get("topic") or "")
            result = self.control_plane.missions.run_action(action_id, topic)
            code = 200 if result.get("ok") else 400
            if result.get("ok") and result.get("queued"):
                code = 202
            self._json(result, code)
        elif path == "/api/recursos":
            self._post_recursos(payload)
        elif path == "/api/secops/plan":
            self._post_secops_plan(payload)
        else:
            self._json({"error": "endpoint no encontrado"}, 404)

    def _post_scout(self, payload: dict[str, Any]) -> None:
        from .ecosystem import EcosystemRadar
        query = str(payload.get("query", ""))[:160]
        limit = MissionManager._bounded(payload.get("limit"), 6, 1, 12)
        radar = EcosystemRadar(self.control_plane.workspace)
        if query.strip():
            report = radar.keyword_search(query, limit=limit)
        else:
            report = radar.scan(query=query, limit_per_query=limit)
        self.control_plane.hub.publish({"event": "ecosystem_scan",
                                        "at": now_iso(),
                                        "added": len(report["added"]),
                                        "total": report["total"]})
        self._json({"scan": report, **radar.snapshot()}, 200)

    def _post_chat(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message", "")).strip()
        ok, msg = self.control_plane.chat.send(message)
        if not ok:
            code = 409 if "curso" in msg or "respondiendo" in msg else 400
            self._json({"error": msg}, code)
        else:
            self._json({"status": msg}, 202)

    def _post_secops_plan(self, payload: dict[str, Any]) -> None:
        """Plan de simulación desde la UI (nunca ejecución asistida)."""
        from .secops import ejecutar
        objetivo = str(payload.get("objetivo") or "")[:200]
        targets = [str(t)[:120] for t in (payload.get("targets") or [])
                   if str(t).strip()]
        archivo = str(payload.get("archivo") or "")[:200]
        try:
            self._json(ejecutar(objetivo, modo="simulacion",
                                workspace=self.control_plane.workspace,
                                targets=targets or None, archivo=archivo))
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)

    def _post_recursos(self, payload: dict[str, Any]) -> None:
        from .recursos import extra_add
        tags_raw = payload.get("tags")
        tags = [str(t)[:32] for t in tags_raw][:8] \
            if isinstance(tags_raw, list) else []
        try:
            entry = extra_add(
                self.control_plane.workspace,
                str(payload.get("nombre") or "")[:120],
                str(payload.get("url") or "")[:300],
                str(payload.get("cat") or "ia")[:40],
                desc=str(payload.get("desc") or "")[:300], tags=tags)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        self.control_plane.hub.publish(
            {"event": "recursos_add", "at": now_iso(),
             "id": entry["id"], "nombre": entry["nombre"]})
        self._json({"status": "recurso añadido", "recurso": entry}, 201)

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
