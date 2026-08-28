"""Modo SERVICIO experimental: API REST con RBAC y aislamiento por usuario.

Resolución del punto «RBAC/multiusuario» del ROADMAP_V2: lo que bloqueaba su
adopción no era el código sino saltarse el producto — aquí está el producto,
con su modelo de amenazas documentado en el README (nota de la versión v1.8).

**Modelo**:

* Usuarios locales gestionados por el OPERADOR desde la máquina que sirve
  (``a2s users add ana --role operator``): el bootstrap es físico, no remoto.
* Tokens JWT-HS256 con expiración y claims ``(user, role)`` (auth.py).
* Roles y permisos::

      admin    → todo + gestionar usuarios
      operator → misiones + lectura
      viewer   → solo lectura (estado, informes, pool, búsqueda)

* Aislamiento: cada usuario trabaja en ``workspaces/u-<usuario>/`` — ni ve
  los datos de otros usuarios ni sus secretos.
* Auditoría: TODA petición (permitida o denegada) queda en
  ``workspace/.a2s/serve_audit.jsonl``: usuario, rol, acción, veredicto.

**Endpoints** (Bearer token, JSON)::

    GET  /health                     anónimo (latido + versión)
    GET  /api/status                 status.read
    POST /api/mission  {goal}        mission.run  → {mission_id} (hilo propio)
    GET  /api/mission/{id}           mission.read → estado de la misión
    GET  /api/report/{id}            mission.read → informe completo
    GET  /api/learning-report        mission.read → aprendizaje persistido
    POST /api/search   {query, top}  search.run
    GET  /api/pool                   pool.read    → telemetría si existe
    POST /api/users    {name, role}  users.manage (solo admin)

**Límites honestos (§15)**: HTTP sin TLS (usa reverse proxy con certificados
propios), sin rate-limiting del login (protege el proxy), misiones con
timebox, un proceso (no clúster). NO es multiusuario federation/SSO: es
RBAC local verificado, el escalón previo a un v2.0 pensado como servicio.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .auth import workspace_token_manager
from .models import now_iso

ROLE_PERMS: dict[str, set[str]] = {
    "admin": {"status.read", "mission.run", "mission.read", "pool.read",
              "search.run", "users.manage"},
    "operator": {"status.read", "mission.run", "mission.read", "pool.read",
                 "search.run"},
    "viewer": {"status.read", "mission.read", "pool.read", "search.run"},
}


class UserStore:
    """Usuarios locales del servicio (workspace/.a2s/users.json)."""

    def __init__(self, workspace: str) -> None:
        self.workspace = os.path.abspath(workspace)
        self.path = os.path.join(self.workspace, ".a2s", "users.json")
        self.tm = workspace_token_manager(self.workspace)

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, name: str, role: str, hours: float = 24.0) -> dict[str, Any]:
        if role not in ROLE_PERMS:
            raise ValueError(f"rol desconocido '{role}' "
                             f"(válidos: {', '.join(ROLE_PERMS)})")
        if not name or any(c in name for c in "/\\ .."):
            raise ValueError("nombre de usuario inválido")
        data = self._load()
        token = self.tm.issue(scope="serve", hours=hours,
                              extra={"user": name, "role": role})
        data[name] = {"role": role, "created_at": now_iso(),
                      "token_hint": token[-8:]}
        self._save(data)
        return {"user": name, "role": role, "token": token,
                "hours": hours, "perms": sorted(ROLE_PERMS[role])}

    def list(self) -> dict[str, Any]:
        return self._load()

    def authenticate(self, token: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        ok, payload = self.tm.verify(token, scope="serve")
        if not ok or not isinstance(payload, dict):
            return None, None
        return payload.get("user"), payload.get("role")


class MissionRunner:
    """Registro de misiones: cada una en su hilo, con timebox y workspace propio."""

    def __init__(self, base_workspace: str, max_time: int = 300) -> None:
        self.base = os.path.abspath(base_workspace)
        self.max_time = max_time
        self.lock = threading.Lock()
        self.missions: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, Any] = {}

    def user_workspace(self, user: str) -> str:
        ws = os.path.join(self.base, "u-" + user)
        os.makedirs(os.path.join(ws, ".a2s"), exist_ok=True)
        return ws

    def start(self, user: str, goal: str = "", provider: str = "auto",
              tasks: Optional[list[dict[str, Any]]] = None,
              max_parallel: int = 8) -> str:
        from .config import Config
        from .loop import run_goal
        mid = f"m-{uuid.uuid4().hex[:10]}"
        ws = self.user_workspace(user)
        token = None
        if tasks is not None:
            from .control import StopToken
            from .project import AegisProject, ProjectConfig
            token = StopToken()
        entry = {"id": mid, "user": user, "goal": goal, "status": "running",
                 "at": now_iso(), "success": None, "run_id": None,
                 "task_ids": [task["id"] for task in tasks or []],
                 "events": [], "result": None}
        with self.lock:
            self.missions[mid] = entry
            if token is not None:
                self.tokens[mid] = token

        def publish(event: dict[str, Any]) -> None:
            with self.lock:
                entry["events"].append(dict(event))
                if event.get("run_id"):
                    entry["run_id"] = event["run_id"]

        def work() -> None:
            try:
                if tasks is not None:
                    project = AegisProject(
                        ws, ProjectConfig(max_parallel=max(1, min(32, int(max_parallel))),
                                          timeout_seconds=float(self.max_time)),)
                    result = project.run(tasks, stop=token, event_sink=publish)
                    with self.lock:
                        entry.update(status="cancelled" if result["cancelled"]
                                     and not result["failed"] else "done",
                                     success=not result["failed"] and not result["cancelled"],
                                     run_id=result["run_id"], result=result)
                    return
                cfg = Config(workspace=ws, quiet=True, provider=provider,
                             max_wall_seconds=self.max_time, max_rounds=3)
                report = run_goal(goal, config=cfg)
                from .report import save_report
                save_report(report, os.path.join(ws, "informe_a2s.md"))
                entry.update(status="done", success=bool(report.success),
                             iterations=report.iterations,
                             steps=report.steps,
                             final_note=report.final_note[:400])
            except Exception as exc:  # noqa: BLE001 — la misión no tumba el servicio
                with self.lock:
                    entry.update(status="error", error=f"{type(exc).__name__}: {exc}")
            finally:
                with self.lock:
                    self.tokens.pop(mid, None)

        threading.Thread(target=work, daemon=True).start()
        return mid

    def get(self, mid: str) -> Optional[dict[str, Any]]:
        with self.lock:
            entry = self.missions.get(mid)
            if entry is None:
                return None
            return {**entry, "events": list(entry["events"])}

    def cancel(self, mid: str, reason: str = "operator") -> bool:
        with self.lock:
            token = self.tokens.get(mid)
        if token is None:
            return False
        token.set(reason)
        return True

    def report(self, mid: str) -> Optional[dict[str, Any]]:
        entry = self.get(mid)
        if not entry:
            return None
        path = os.path.join(self.user_workspace(entry["user"]),
                            "informe_a2s.md.json")
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {"note": "informe aún no disponible", **entry}


class ServeAPI:
    """Router + RBAC + auditoría. handler HTTP mínimo encima."""

    def __init__(self, workspace: str, max_time: int = 300) -> None:
        self.users = UserStore(workspace)
        self.runner = MissionRunner(workspace, max_time=max_time)
        self.audit_path = os.path.join(os.path.abspath(workspace), ".a2s",
                                       "serve_audit.jsonl")
        os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)
        self.started = time.time()

    # -- RBAC y auditoría -----------------------------------------------------

    def close(self) -> None:
        """Cierra recursos persistentes antes de apagar el servicio.

        Las misiones corren en hilos daemon; aquí solo se liberan las
        conexiones SQLite cacheadas para que el directorio temporal pueda
        borrarse en Windows (WinError 32) sin recurrir a reintentos.
        """
        close = getattr(self.users, "close", None)
        if callable(close):
            close()

    def audit(self, user: Optional[str], role: Optional[str], action: str,
              allowed: bool, detail: str = "") -> None:
        entry = {"at": now_iso(), "user": user or "-", "role": role or "-",
                 "action": action, "allowed": allowed, "detail": detail[:200]}
        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def check(self, headers: dict[str, str], perm: str
              ) -> tuple[Optional[str], Optional[str], Optional[tuple[int, str]]]:
        """AuthN+AuthZ. Devuelve (user, role, error_http)."""
        auth = headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        user, role = self.users.authenticate(token)
        if not user:
            self.audit(None, None, perm, False, "credencial inválida o ausente")
            return None, None, (401, "credencial inválida o ausente")
        if perm not in ROLE_PERMS.get(role, set()):
            self.audit(user, role, perm, False, "permiso insuficiente")
            return user, role, (403, f"rol '{role}' sin permiso '{perm}'")
        self.audit(user, role, perm, True)
        return user, role, None

    # -- manejo de una petición -----------------------------------------------

    def _start_mission(self, user: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        goal = str(payload.get("goal", "")).strip()
        tasks = payload.get("tasks")
        if tasks is not None:
            if (not isinstance(tasks, list) or not tasks or
                    any(not isinstance(task, dict) or not task.get("id")
                        or not task.get("prompt") for task in tasks)):
                return 400, {"error": "'tasks' debe ser una lista de tareas con id y prompt"}
        elif not goal:
            return 400, {"error": "falta 'goal' o 'tasks'"}
        provider = payload.get("provider", "auto")
        if provider not in ("heuristic", "pool", "auto"):
            return 400, {"error": "proveedor no permitido en el servicio"}
        try:
            max_parallel = max(1, min(32, int(payload.get("max_parallel", 8))))
        except (TypeError, ValueError):
            return 400, {"error": "max_parallel inválido"}
        mid = self.runner.start(user, goal, provider, tasks, max_parallel)
        state = self.runner.get(mid) or {}
        return 202, {"mission_id": mid, "run_id": state.get("run_id"),
                     "task_ids": state.get("task_ids", []),
                     "workspace": f"u-{user}"}

    def _cancel_mission(self, user: str, path: str,
                        payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        mid = path.split("/")[-2]
        entry = self.runner.get(mid)
        if not entry:
            return 404, {"error": "misión desconocida"}
        if entry["user"] != user:
            return 403, {"error": "misión de otro usuario"}
        if not self.runner.cancel(mid, str(payload.get("reason", "operator"))):
            return 409, {"error": "misión no cancelable"}
        return 202, {"mission_id": mid, "cancel_requested": True}

    def _read_mission(self, user: str, path: str) -> tuple[int, dict[str, Any]]:
        mid = path.rsplit("/", 1)[-1]
        entry = self.runner.get(mid)
        if not entry:
            return 404, {"error": "misión desconocida"}
        if entry["user"] != user:
            return 403, {"error": "misión de otro usuario"}
        return 200, entry

    def _read_report(self, path: str) -> tuple[int, dict[str, Any]]:
        mid = path.rsplit("/", 1)[-1]
        rep = self.runner.report(mid)
        if rep is None:
            return 404, {"error": "informe desconocido"}
        return 200, rep

    def _read_learning_report(self, user: str, path: str) -> tuple[int, dict[str, Any]]:
        query = parse_qs(urlsplit(path).query, keep_blank_values=True)
        objective = query.get("objective", [""])[-1]
        tool = query.get("tool", [""])[-1]
        raw_limit = query.get("limit", ["1000"])[-1]
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return 400, {"error": "limit debe ser un entero entre 1 y 1000"}
        try:
            from .autonomy import AutonomousLoop
            report = AutonomousLoop(self.runner.user_workspace(user)).learning_report(
                objective=objective, tool=tool, limit=limit)
        except ValueError as exc:
            return 400, {"error": str(exc)}
        return 200, report

    def handle(self, method: str, path: str, headers: dict[str, str],
               body: bytes) -> tuple[int, dict[str, Any]]:

        def _err(err: tuple[int, str]) -> tuple[int, dict[str, Any]]:
            return err[0], {"error": err[1]}

        if path == "/health":
            return 200, {"ok": True, "service": "a2s-serve",
                         "version": __version__,
                         "uptime_s": round(time.time() - self.started)}
        if not path.startswith("/api/"):
            return 404, {"error": f"ruta desconocida {path}"}
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return 400, {"error": "JSON inválido"}

        if method == "GET" and path == "/api/status":
            u, r, err = self.check(headers, "status.read")
            if err:
                return _err(err)
            return 200, {"users": len(self.users.list()),
                         "missions": len(self.runner.missions),
                         "uptime_s": round(time.time() - self.started),
                         "whoami": {"user": u, "role": r}}

        if method == "POST" and path == "/api/mission":
            u, r, err = self.check(headers, "mission.run")
            if err:
                return _err(err)
            return self._start_mission(u, payload)

        if method == "POST" and path.startswith("/api/mission/") and path.endswith("/cancel"):
            u, _r, err = self.check(headers, "mission.run")
            if err:
                return _err(err)
            return self._cancel_mission(u, path, payload)

        if method == "GET" and path.startswith("/api/mission/"):
            u, _, err = self.check(headers, "mission.read")
            if err:
                return _err(err)
            return self._read_mission(u, path)

        if method == "GET" and path.startswith("/api/report/"):
            _, _, err = self.check(headers, "mission.read")
            if err:
                return _err(err)
            return self._read_report(path)

        if method == "GET" and urlsplit(path).path == "/api/learning-report":
            u, _, err = self.check(headers, "mission.read")
            if err:
                return _err(err)
            return self._read_learning_report(u, path)

        if method == "POST" and path == "/api/search":
            _, _, err = self.check(headers, "search.run")
            if err:
                return _err(err)
            from .search import workspace_search
            user_ws = self.runner.user_workspace(u) if u else ""
            hits = workspace_search(user_ws, str(payload.get("query", "")),
                                    top=int(payload.get("top", 5)))
            return 200, {"results": [{"origen": d.origen, "meta": d.meta,
                                      "score": round(s, 3)} for d, s in hits]}

        if method == "GET" and path == "/api/pool":
            _, _, err = self.check(headers, "pool.read")
            if err:
                return _err(err)
            st = os.path.join(self.runner.base, ".a2s", "pool", "state.json")
            try:
                with open(st, encoding="utf-8") as fh:
                    return 200, json.load(fh)
            except (OSError, json.JSONDecodeError):
                return 200, {"note": "sin telemetría de pool en este workspace"}

        if method == "POST" and path == "/api/users":
            u, r, err = self.check(headers, "users.manage")
            if err:
                return _err(err)
            name = str(payload.get("name", "")).strip()
            role = str(payload.get("role", "viewer"))
            try:
                info = self.users.add(name, role,
                                      hours=float(payload.get("hours", 24)))
            except ValueError as exc:
                return 400, {"error": str(exc)}
            self.audit(u, r, "users.add", True, f"{name} como {role}")
            return 201, info

        return 404, {"error": "endpoint no encontrado"}


def make_server(workspace: str, port: int = 8700, host: str = "127.0.0.1",
                max_time: int = 300) -> tuple[ThreadingHTTPServer, ServeAPI]:
    api = ServeAPI(workspace, max_time=max_time)
    outer = api

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # auditoría propia, no access-log
            pass

        def _dispatch(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            headers = {k: v for k, v in self.headers.items()}
            try:
                code, out = outer.handle(method, self.path, headers, body)
            except Exception as exc:  # noqa: BLE001 — el servicio no muere
                code, out = 500, {"error": f"{type(exc).__name__}: {exc}"}
            data = json.dumps(out, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._dispatch("GET")

        def do_POST(self):  # noqa: N802
            self._dispatch("POST")

    srv = ThreadingHTTPServer((host, port), Handler)
    return srv, api
