"""Cliente pequeno para usar proyectos Aegis desde Jupyter."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, Union

from .control import StopToken
from .project import AegisProject, ProjectConfig


class AegisJupyter:
    """Fachada notebook-friendly sobre ``AegisProject``.

    El paralelismo, las dependencias y los limites siguen siendo responsabilidad
    del scheduler de ``AegisProject``; esta clase solo adapta la ergonomia.
    """

    def __init__(self, workspace: Optional[Union[str, Path]] = None,
                 project: Optional[AegisProject] = None,
                 config: Optional[ProjectConfig] = None) -> None:
        self.project = project or AegisProject(workspace or Path.cwd(), config=config)
        self.stop_token: Optional[StopToken] = None
        self.events: list[dict[str, Any]] = []
        self.last_result: Optional[dict[str, Any]] = None
        self.remote_url: Optional[str] = None
        self.remote_token: Optional[str] = None
        self.remote_mission_id: Optional[str] = None

    @property
    def workspace(self) -> Path:
        return self.project.workspace

    def configure(self, workspace: Union[str, Path],
                  config: Optional[ProjectConfig] = None) -> "AegisJupyter":
        """Selecciona otro workspace y crea su proyecto Aegis."""
        self.project = AegisProject(workspace, config=config)
        self.stop_token = None
        self.events = []
        self.last_result = None
        self.remote_mission_id = None
        return self

    def configure_remote(self, url: str, token: Optional[str] = None) -> "AegisJupyter":
        """Configura un servicio ``a2s serve`` sin persistir la credencial."""
        self.remote_url = url.rstrip("/")
        self.remote_token = token
        return self

    def _remote_request(self, method: str, path: str,
                        payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.remote_url:
            raise RuntimeError("el servicio remoto no está configurado")
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.remote_token:
            headers["Authorization"] = f"Bearer {self.remote_token}"
        request = urllib.request.Request(self.remote_url + path, data=data,
                                          headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                result = json.loads(exc.read().decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                result = {}
            raise RuntimeError(result.get("error", f"HTTP {exc.code}")) from exc
        if not isinstance(result, dict):
            raise RuntimeError("respuesta remota inválida")
        return result

    def run_remote_tasks(self, tasks: list[dict[str, Any]],
                         event_sink: Optional[Callable[[dict[str, Any]], None]] = None,
                         poll_seconds: float = 0.1,
                         timeout: Optional[float] = None) -> dict[str, Any]:
        """Ejecuta y espera un DAG en ``a2s serve`` usando su API HTTP."""
        self.stop_token = None
        self.events = []
        accepted = self._remote_request("POST", "/api/mission", {"tasks": tasks})
        self.remote_mission_id = accepted.get("mission_id")
        if not self.remote_mission_id:
            raise RuntimeError("la respuesta no contiene mission_id")
        started = time.monotonic()
        seen = 0
        try:
            while True:
                state = self._remote_request("GET", f"/api/mission/{self.remote_mission_id}")
                for event in state.get("events", [])[seen:]:
                    self.events.append(dict(event))
                    if event_sink is not None:
                        event_sink(event)
                seen = len(state.get("events", []))
                if state.get("status") in {"done", "error", "cancelled"}:
                    self.last_result = state.get("result") or state
                    return self.last_result
                if timeout is not None and time.monotonic() - started >= timeout:
                    self.cancel("timeout")
                    raise TimeoutError("tiempo de espera remoto agotado")
                time.sleep(max(0.01, poll_seconds))
        finally:
            self.remote_mission_id = None

    def run_task(self, task_id: str, prompt: str,
                 event_sink: Optional[Callable[[dict[str, Any]], None]] = None,
                 **fields: Any) -> dict[str, Any]:
        """Ejecuta una tarea individual usando el DAG del proyecto."""
        task = {"id": task_id, "prompt": prompt, **fields}
        return self.run_tasks([task], event_sink=event_sink)

    def run_tasks(self, tasks: list[dict[str, Any]],
                  aggregate: Any = None,
                  event_sink: Optional[Callable[[dict[str, Any]], None]] = None) -> dict[str, Any]:
        """Ejecuta tareas, potencialmente en paralelo, mediante ``project.run``."""
        self.stop_token = StopToken()
        self.events = []

        def collect(event: dict[str, Any]) -> None:
            self.events.append(dict(event))
            if event_sink is not None:
                event_sink(event)

        self.last_result = self.project.run(tasks, stop=self.stop_token,
                                            aggregate=aggregate, event_sink=collect)
        return self.last_result

    def get_events(self) -> list[dict[str, Any]]:
        """Devuelve una instantánea de los eventos de la última ejecución."""
        return [dict(event) for event in self.events]

    def learning_report(self, objective: str = "", tool: str = "",
                        limit: int = 1000) -> dict[str, Any]:
        """Consulta el informe de aprendizaje local sin acceder a fuentes externas."""
        return self.project.learning_report(objective, tool, limit)

    def cancel(self, reason: str = "operator") -> bool:
        """Solicita la parada cooperativa de la ejecucion activa, si existe."""
        if self.remote_mission_id:
            try:
                self._remote_request("POST", f"/api/mission/{self.remote_mission_id}/cancel",
                                     {"reason": reason})
                return True
            except RuntimeError:
                return False
        if self.stop_token is None:
            return False
        self.stop_token.set(reason)
        return True