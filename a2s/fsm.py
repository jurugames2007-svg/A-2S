"""Nivel determinista de A²S — FSM + eventos + escalado (el "eslabón predecible").

Arquitectura de dos niveles para cubrir cada eslabón:

* **Nivel 0 (predecible, sin IA)**: máquinas de estados finitas dirigidas por
  especificación JSON. Estados con acciones deterministas (herramientas del
  registro, con el modelo de permisos de siempre), transiciones por
  condiciones objetivas (regex / contains / always) sobre la observación,
  cool-downs con **jitter** (uniforme aleatorio: evita rebaños de peticiones
  y sincronización; es educación de red, no evasión) y presupuesto de ciclos.
  Coste cero de tokens: aquí no hay LLM.
* **Nivel 1 (imprevisto)**: cuando NINGUNA transición coincide (el dato no
  encaja en nada previsto), la máquina **escala** al loop completo de A²S
  (planificador heurístico o pool SORL): la observación imprevista se
  convierte en objetivo contextualizado. Lo impredecible se resuelve con
  el agente; lo predecible jamás lo despierta.

Frontera de diseño: el watcher se identifica con un User-Agent honesto y no
rota huellas "para simular entornos de usuario" — eso sería evasión de
controles de terceros (línea de permisos del framework). El jitter aleta los
*nuestros* (rebaño/sincronización), no engaña a nadie.

Especificación (ver ``examples/fsm.example.json``)::

    {
      "name": "clasificador_inbox",
      "initial": "leer",
      "states": {
        "leer":  {"action": {"tool": "shell", "params": {"command": "ls inbox/"}},
                  "cooldown": [0.2, 0.8]},
        "hecho": {"terminal": "done"}
      },
      "transitions": [
        {"from": "leer", "to": "hecho", "when": {"regex": "[0-9a-f]{64}"}},
        {"from": "leer", "to": "leer", "when": {"always": true}}
      ],
      "max_cycles": 50,
      "escalate_to": "agent"
    }
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from typing import Any, Callable, Optional

from .models import now_iso

ActionFn = Callable[[str, dict[str, Any]], str]     # (estado, acción) → observación


def jitter(cooldown: Any) -> float:
    """Cool-down con ruido: número → ±40%; [min, max] → uniforme."""
    if cooldown is None:
        return 0.0
    if isinstance(cooldown, (list, tuple)) and len(cooldown) == 2:
        lo, hi = sorted(float(x) for x in cooldown)
        return random.uniform(lo, hi)
    base = float(cooldown)
    return base * random.uniform(0.6, 1.4)


@dataclass
class FSMResult:
    """Traza verificable de una ejecución determinista."""
    machine: str
    states: list[str] = field(default_factory=list)     # estados visitados en orden
    observations: list[str] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    cycles: int = 0
    stopped: str = ""                                    # terminal|escalate|budget
    terminal: Optional[str] = None                       # done|failed
    escalated: Optional[dict[str, str]] = None           # {state, observation}

    @property
    def resolved_by(self) -> str:
        if self.stopped == "terminal":
            return f"nivel 0 (FSM determinista, terminal={self.terminal})"
        if self.stopped == "escalate":
            return "escalado a nivel 1 (agente)"
        return "presupuesto de ciclos agotado"


class FSMError(ValueError):
    """Especificación inválida: se detecta ANTES de ejecutar."""


class FSMEngine:
    """Ejecuta una máquina determinista; nunca adivina: si nada encaja, escala."""

    def __init__(self, spec: dict[str, Any],
                 action_fn: Optional[ActionFn] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None) -> None:
        self.spec = spec
        self.name = str(spec.get("name", "fsm"))
        self.states: dict[str, dict[str, Any]] = spec.get("states", {})
        self.initial = str(spec.get("initial", ""))
        self.max_cycles = int(spec.get("max_cycles", 50))
        self.transitions = spec.get("transitions", [])
        self._action = action_fn or (lambda state, act: "(sin acción definida)")
        self._sleep = sleep_fn or time.sleep
        self._by_state: dict[str, list[dict[str, Any]]] = {}
        for t in self.transitions:
            self._by_state.setdefault(t.get("from", ""), []).append(t)

    # -- validación estática ---------------------------------------------------

    def validate(self) -> list[str]:
        errors = []
        if not self.states:
            errors.append("sin estados")
        if self.initial not in self.states:
            errors.append(f"estado inicial '{self.initial}' no definido")
        terminal = {n for n, s in self.states.items() if s.get("terminal")}
        seen_non_terminal = False
        for t in self.transitions:
            src, dst = t.get("from", ""), t.get("to", "")
            if src not in self.states:
                errors.append(f"transición desde estado desconocido '{src}'")
            if dst not in self.states:
                errors.append(f"transición hacia estado desconocido '{dst}'")
            if "when" not in t:
                errors.append(f"transición {src}→{dst} sin condición 'when'")
        for name, st in self.states.items():
            if name not in terminal and name not in self._by_state:
                seen_non_terminal = True
                errors.append(
                    f"estado no terminal '{name}' sin transiciones de salida "
                    "(se quedaría bloqueado: añade una o márcalo terminal)")
        if not terminal:
            errors.append("sin estado terminal: la máquina no puede terminar bien")
        return errors

    # -- evaluación de condiciones ----------------------------------------------

    @staticmethod
    def _matches(when: dict[str, Any], observation: str) -> bool:
        if when.get("always"):
            return True
        if "regex" in when:
            return re.search(when["regex"], observation or "") is not None
        if "contains" in when:
            return str(when["contains"]) in (observation or "")
        return False

    # -- ejecución ----------------------------------------------------------------

    def run(self, max_cycles: Optional[int] = None) -> FSMResult:
        result = FSMResult(machine=self.name)
        state = self.initial
        limit = max_cycles or self.max_cycles
        while result.cycles < limit:
            result.cycles += 1
            result.states.append(state)
            node = self.states.get(state, {})
            if node.get("terminal"):
                result.stopped = "terminal"
                result.terminal = str(node.get("terminal", "done"))
                return result
            obs = self._execute(state, node.get("action") or {})
            result.observations.append(obs[:2000])
            nxt = None
            for t in self._by_state.get(state, []):
                if self._matches(t.get("when", {}), obs):
                    nxt = t.get("to")
                    break
            if nxt is None:
                # eslabón IMPREVISTO: no adivinar — escalar con la evidencia
                result.stopped = "escalate"
                result.escalated = {"state": state, "observation": obs[:2000]}
                return result
            cd = node.get("cooldown")
            wait = jitter(cd)
            if wait > 0:
                result.sleeps.append(round(wait, 3))
                self._sleep(wait)
            state = nxt
        result.stopped = "budget"
        return result

    def _execute(self, state: str, action: dict[str, Any]) -> str:
        if not action:
            return "(estado sin acción)"
        try:
            out = self._action(state, action)
            # una acción PUEDE devolver vacío legítimo (dir vacío): no se
            # maquilla — el enrutado regex debe ver la observación real
            return "" if out is None else str(out)
        except Exception as exc:  # noqa: BLE001 — el error ES la observación
            # las transiciones pueden enrutar errores de forma determinista
            return f"ERROR ({type(exc).__name__}): {exc}"


# --------------------------------------------------------------------------
# Watcher dirigido por eventos (el agente duerme hasta que algo pasa)
# --------------------------------------------------------------------------

class WebhookServer:
    """Endpoint local mínimo: cualquier POST/GET encola un evento webhook."""

    def __init__(self, port: int, queue_: "Queue[dict]", host: str = "127.0.0.1") -> None:
        self.port = port
        self.queue = queue_
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # silencioso
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.queue.put({"type": "webhook", "path": urllib.parse.urlparse(self.path).path,
                                 "body": body[:2000].decode("utf-8", "replace"),
                                 "at": now_iso()})
                out = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST = _handle

        self._srv = ThreadingHTTPServer((host, port), H)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()


class Watcher:
    """Disparadores (interval | file | webhook) → correr la máquina → escalar.

    El interval lleva jitter (±40%) para no sincronizarse con otros agentes;
    el polling de archivos es por listado+mtimes (barato, sin inotify: stdlib).
    """

    def __init__(self, spec: dict[str, Any],
                 on_event: Callable[[dict[str, Any]], Any],
                 sleep_fn: Optional[Callable[[float], None]] = None,
                 poll: float = 0.5) -> None:
        self.spec = spec
        self.on_event = on_event
        self._sleep = sleep_fn or time.sleep
        self.poll = poll
        self.events: "Queue[dict]" = Queue()
        self._next_due: dict[int, float] = {}
        self._file_snap: dict[str, dict[str, float]] = {}
        self._webhooks: list[WebhookServer] = []
        self.stopped = False

    # -- disparadores ---------------------------------------------------------

    def _fire_interval(self, trig: dict[str, Any], idx: int, now: float) -> Optional[dict]:
        due = self._next_due.get(idx, now)
        if now < due:
            return None
        base = float(trig.get("seconds", 60))
        self._next_due[idx] = now + max(self.poll, jitter(base))
        return {"type": "interval", "at": now_iso()}

    def _fire_file(self, trig: dict[str, Any], idx: int, now: float) -> Optional[dict]:
        path = trig.get("path", "")
        snap: dict[str, float] = {}
        if os.path.isdir(path):
            for name in sorted(os.listdir(path))[:500]:
                fp = os.path.join(path, name)
                if os.path.isfile(fp):
                    try:
                        snap[fp] = os.path.getmtime(fp)
                    except OSError:
                        pass
        elif os.path.isfile(path):
            try:
                snap[path] = os.path.getmtime(path)
            except OSError:
                pass
        prev = self._file_snap.get(trig.get("key", path))
        self._file_snap[trig.get("key", path)] = snap
        if prev is None:                     # primera pasada: línea base
            return None
        if snap != prev:
            what = "nuevo" if len(snap) > len(prev) else "cambio"
            return {"type": "file", "path": path, "what": what, "at": now_iso()}
        return None

    def _setup_webhooks(self) -> None:
        for trig in self.spec.get("triggers", []):
            if trig.get("type") == "webhook":
                srv = WebhookServer(int(trig.get("port", 8790)), self.events)
                srv.start()
                self._webhooks.append(srv)

    # -- bucle ------------------------------------------------------------------

    def run(self, max_events: Optional[int] = None, idle_timeout: float = 60.0,
            on_tick: Optional[Callable[[dict[str, Any]], None]] = None) -> list[Any]:
        """Ejecuta hasta ``max_events`` eventos (None = para siempre con timeout)."""
        self._setup_webhooks()
        results: list[Any] = []
        last_event = time.monotonic()
        try:
            while not self.stopped and (max_events is None or len(results) < max_events):
                now = time.monotonic()
                fired: Optional[dict] = None
                for i, trig in enumerate(self.spec.get("triggers", [])):
                    t = trig.get("type")
                    if t == "interval":
                        fired = fired or self._fire_interval(trig, i, now)
                    elif t == "file":
                        fired = fired or self._fire_file(trig, i, now)
                if fired is None:
                    try:
                        fired = self.events.get(timeout=self.poll)
                    except Empty:
                        fired = None
                if fired is not None:
                    last_event = time.monotonic()
                    if on_tick:
                        on_tick(fired)
                    results.append(self.on_event(fired))
                else:
                    if time.monotonic() - last_event > idle_timeout:
                        break                        # parada honesta por inactividad
                    self._sleep(self.poll)
        finally:
            self.stop()
        return results

    def stop(self) -> None:
        self.stopped = True
        for srv in self._webhooks:
            srv.stop()
        self._webhooks = []


# --------------------------------------------------------------------------
# Puente de acciones: especificación → herramientas del registro (con permisos)
# --------------------------------------------------------------------------

def registry_action_fn(registry) -> ActionFn:
    """Construye el ejecutor de acciones sobre un ToolRegistry real: cada
    acción pasa por el mismo modelo de permisos que el agente (allowlist de
    red, classify_forbidden, sandbox de rutas)."""

    def action(state: str, act: dict[str, Any]) -> str:
        tool = registry.get(str(act.get("tool", "")))
        if tool is None:
            known = ", ".join(sorted(registry._tools)) or "(ninguna)"
            return f"ERROR: herramienta desconocida '{act.get('tool')}' (disponibles: {known})"
        params = dict(act.get("params", {}))
        return str(tool.func(**params))

    return action


def escalation_goal(machine: str, escalated: dict[str, str]) -> str:
    """Convierte lo imprevisto en objetivo contextualizado para el nivel 1."""
    return (f"[ESCALADO FSM:{machine}] El flujo determinista quedó bloqueado en el "
            f"estado '{escalated['state']}' porque la observación no encajaba en "
            f"ningún patrón previsto. Observación: {escalated['observation'][:800]}. "
            "Analiza la situación, resuélvela y documenta qué transición faltaba "
            "en la especificación.")
