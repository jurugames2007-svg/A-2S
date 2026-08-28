"""Integraciones nativas y acotadas para capacidades externas de A2S.

Este modulo implementa patrones compatibles con PM2 y Public APIs sin
importar codigo remoto ni ejecutar comandos mediante shell. Los adaptadores
son deliberadamente pequenos: gestionan procesos y HTTP, mientras que la
logica de cada servicio permanece bajo configuracion explicita del operador.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ManagedProcess:
    name: str
    command: tuple[str, ...]
    pid: Optional[int] = None
    started_at: float = 0.0
    restarts: int = 0
    status: str = "stopped"
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    log_file: Any = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": list(self.command),
            "pid": self.pid,
            "started_at": self.started_at,
            "uptime": max(0.0, time.time() - self.started_at) if self.started_at else 0.0,
            "restarts": self.restarts,
            "status": self.status,
        }


class ProcessManager:
    """Gestor local de procesos sin shell ni comandos construidos."""

    def __init__(self, workspace: str, log_dir: str = "logs") -> None:
        self.workspace = os.path.abspath(workspace)
        self.log_dir = os.path.abspath(os.path.join(self.workspace, log_dir))
        os.makedirs(self.log_dir, exist_ok=True)
        self.processes: dict[str, ManagedProcess] = {}
        self._lock = threading.RLock()

    def start(self, name: str, command: list[str], env: Optional[dict[str, str]] = None,
              cwd: str = ".") -> dict[str, Any]:
        name = (name or "").strip()
        if not name or not command or any(not str(part).strip() for part in command):
            raise ValueError("nombre y comando son obligatorios")
        workdir = os.path.abspath(os.path.join(self.workspace, cwd))
        if not (workdir == self.workspace or workdir.startswith(self.workspace + os.sep)):
            raise PermissionError("cwd fuera del workspace")
        with self._lock:
            current = self.processes.get(name)
            if current and current.process and current.process.poll() is None:
                raise RuntimeError(f"proceso ya activo: {name}")
            log_path = os.path.join(self.log_dir, f"{name}.log")
            log = open(log_path, "a", encoding="utf-8")
            merged_env = os.environ.copy()
            if env:
                merged_env.update({str(k): str(v) for k, v in env.items()})
            try:
                process = subprocess.Popen(
                    [str(part) for part in command], cwd=workdir,
                    env=merged_env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, shell=False)
            except OSError:
                log.close()
                raise
            previous_restarts = current.restarts if current else 0
            managed = ManagedProcess(name=name, command=tuple(str(p) for p in command),
                                     pid=process.pid, started_at=time.time(),
                                     restarts=previous_restarts, status="online",
                                     process=process, log_file=log)
            self.processes[name] = managed
            return managed.snapshot()

    def stop(self, name: str, timeout: float = 5.0) -> dict[str, Any]:
        with self._lock:
            managed = self.processes.get(name)
            if managed is None:
                raise KeyError(name)
            process = managed.process
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=timeout)
            managed.status = "stopped"
            managed.pid = None
            if managed.log_file and not managed.log_file.closed:
                managed.log_file.close()
            return managed.snapshot()

    def monitor(self, restart: bool = False) -> dict[str, dict[str, Any]]:
        with self._lock:
            for managed in self.processes.values():
                process = managed.process
                if process and process.poll() is not None:
                    managed.status = "stopped"
                    managed.pid = None
                    if managed.log_file and not managed.log_file.closed:
                        managed.log_file.close()
                    if restart:
                        managed.restarts += 1
                        command = list(managed.command)
                        self.start(managed.name, command)
                elif process:
                    managed.status = "online"
            return {name: item.snapshot() for name, item in self.processes.items()}

    def logs(self, name: str, lines: int = 100) -> str:
        if lines < 1:
            return ""
        path = os.path.join(self.log_dir, f"{name}.log")
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])


@dataclass(frozen=True)
class APISpec:
    name: str
    base_url: str
    category: str = "general"
    auth: str = "none"
    https: bool = True
    description: str = ""


class PublicAPIManager:
    """Catalogo y cliente HTTP de APIs declaradas por el operador."""

    def __init__(self, catalog: Optional[list[dict[str, Any]]] = None,
                 transport: Optional[Callable[..., Any]] = None) -> None:
        rows = catalog or []
        self.catalog: dict[str, APISpec] = {
            str(row["name"]): APISpec(
                name=str(row["name"]), base_url=str(row["base_url"]).rstrip("/"),
                category=str(row.get("category", "general")),
                auth=str(row.get("auth", "none")),
                https=bool(row.get("https", True)),
                description=str(row.get("description", "")))
            for row in rows if row.get("name") and row.get("base_url")
        }
        self.transport = transport or self._request

    def register(self, spec: APISpec) -> None:
        parsed = urllib.parse.urlparse(spec.base_url)
        if spec.https and parsed.scheme != "https":
            raise ValueError("las APIs externas deben usar HTTPS")
        self.catalog[spec.name] = spec

    def search(self, query: str = "", category: str = "", auth: str = "") -> list[dict[str, Any]]:
        needle = (query or "").strip().lower()
        category = (category or "").strip().lower()
        auth = (auth or "").strip().lower()
        out = []
        for spec in self.catalog.values():
            haystack = f"{spec.name} {spec.description} {spec.category}".lower()
            if needle and needle not in haystack:
                continue
            if category and spec.category.lower() != category:
                continue
            if auth and spec.auth.lower() != auth:
                continue
            out.append({"name": spec.name, "base_url": spec.base_url,
                        "category": spec.category, "auth": spec.auth,
                        "https": spec.https, "description": spec.description})
        return sorted(out, key=lambda item: item["name"])

    def call(self, name: str, endpoint: str = "", params: Optional[dict[str, str]] = None,
             method: str = "GET", headers: Optional[dict[str, str]] = None,
             timeout: int = 20) -> Any:
        if name not in self.catalog:
            raise KeyError(name)
        spec = self.catalog[name]
        endpoint = (endpoint or "").strip()
        if urllib.parse.urlparse(endpoint).scheme or urllib.parse.urlparse(endpoint).netloc:
            raise PermissionError("endpoint absoluto no permitido; usa una ruta registrada")
        path = (endpoint or "").lstrip("/")
        url = f"{spec.base_url}/{path}" if path else spec.base_url
        parsed = urllib.parse.urlparse(url)
        base_host = urllib.parse.urlparse(spec.base_url).netloc
        if parsed.scheme != "https" or parsed.netloc != base_host:
            raise PermissionError("endpoint fuera de la API registrada")
        if timeout < 1 or timeout > 120:
            raise ValueError("timeout fuera de rango (1..120)")
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        response = self.transport(url, method.upper(), headers or {}, timeout)
        if isinstance(response, bytes):
            response = response.decode("utf-8", "replace")
        try:
            return json.loads(response)
        except (TypeError, ValueError):
            return response

    @staticmethod
    def _request(url: str, method: str, headers: dict[str, str], timeout: int) -> bytes:
        request = urllib.request.Request(url, method=method, headers={"User-Agent": "A2S/1.28", **headers})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(200_000)
