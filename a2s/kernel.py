"""Planificador sobre PCB: admitir, despachar, checkpoint, park, reanudar.

Lee las 1000 políticas del catálogo. El efecto vivo: colas MLFQ, aging,
quantum, dedup, backpressure, watchdog, grafo de espera, reanudación.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Optional

from .catalog import apply_all, load_applied, policies_path
from .models import now_iso
from .pcb import PCB, ProcessTable, QUEUES

Handler = Callable[[PCB], dict[str, Any]]

QUEUE_BASE = {"Q0": 80, "Q1": 60, "Q2": 40, "Q3": 20}
DEFAULTS = {
    "aging_ms": 8000,
    "quantum_ms": 250,
    "max_ready": 256,
    "max_running": 4,
    "watchdog_slices": 8,
    "backoff_base_ms": 50,
}


class Kernel:
    """Núcleo de colas. Una instancia por workspace."""

    def __init__(self, workspace: str) -> None:
        self.workspace = os.path.abspath(workspace)
        self.table = ProcessTable(self.workspace)
        self.policies: dict[str, Any] = {}
        self.applied = 0
        self.handlers: dict[str, Handler] = {}
        self._load_policies()

    @classmethod
    def open(cls, workspace: str, apply: bool = True) -> "Kernel":
        if apply:
            apply_all(workspace)
        return cls(workspace)

    def _load_policies(self) -> None:
        path = policies_path(self.workspace)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.policies = dict(data.get("policies") or {})
            self.applied = int(data.get("count") or 0)
        except (OSError, json.JSONDecodeError):
            manifest = load_applied(self.workspace)
            if manifest:
                self.applied = int(manifest.get("applied") or 0)
                self.policies = {i["policy"]: i.get("value", True)
                                 for i in manifest.get("items") or []}

    def policy(self, key: str, default: Any = True) -> Any:
        return self.policies.get(key, default)

    def knob(self, name: str) -> int:
        return int(DEFAULTS.get(name, 0))

    def register(self, kind: str, handler: Handler) -> None:
        self.handlers[kind] = handler

    def admit(self, goal: str, kind: str = "mission", **kw: Any) -> PCB:
        ready = len(self.table.by_state("ready"))
        if ready >= self.knob("max_ready"):
            raise OverflowError("backpressure: cola ready saturada")
        pcb = self.table.admit(goal, kind=kind, **kw)
        pcb.quantum_ms = self.knob("quantum_ms")
        pcb.priority = self.effective_priority(pcb)
        self.table.checkpoint(pcb.pid, registers={"admitted": now_iso()})
        return self.table.get(pcb.pid) or pcb

    def effective_priority(self, pcb: PCB) -> int:
        base = QUEUE_BASE.get(pcb.queue, 50) + pcb.priority - pcb.nice
        if pcb.wait_ms >= self.knob("aging_ms"):
            base += min(20, pcb.wait_ms // self.knob("aging_ms"))
        return max(1, min(99, base))

    def pick(self) -> Optional[PCB]:
        """Siguiente READY: cola más alta, luego prioridad, luego pid."""
        ready = self.table.by_state("ready")
        if not ready:
            return None
        running = len(self.table.by_state("running"))
        if running >= self.knob("max_running"):
            return None
        order = {q: i for i, q in enumerate(QUEUES)}
        ready.sort(key=lambda p: (order.get(p.queue, 9),
                                  -self.effective_priority(p), p.pid))
        return ready[0]

    def dispatch(self, pid: int) -> PCB:
        return self.table.set_state(pid, "running")

    def complete(self, pid: int, result: Optional[dict[str, Any]] = None) -> PCB:
        return self.table.set_state(pid, "completed",
                                    registers={"result": result or {}})

    def fail(self, pid: int, error: str) -> PCB:
        pcb = self.table.get(pid)
        retries = (pcb.retries + 1) if pcb else 1
        if pcb and retries < 3:
            return self.table.set_state(
                pid, "ready", retries=retries,
                wait_channel="", registers={"last_error": error})
        return self.table.set_state(pid, "failed", retries=retries,
                                    registers={"error": error})

    def park(self, pid: int, reason: str = "interrupt") -> PCB:
        return self.table.set_state(pid, "parked",
                                    wait_channel=reason or "interrupt")

    def block(self, pid: int, channel: str) -> PCB:
        return self.table.set_state(pid, "blocked", wait_channel=channel)

    def resume(self, pid: int) -> PCB:
        pcb = self.table.get(pid)
        if pcb is None:
            raise KeyError(pid)
        if pcb.state not in ("parked", "blocked", "waiting", "failed"):
            return pcb
        return self.table.set_state(pid, "ready", wait_channel="",
                                    parked_at="")

    def resume_all(self) -> list[PCB]:
        out = []
        for pcb in list(self.table.by_state("parked", "blocked", "waiting")):
            out.append(self.resume(pcb.pid))
        return out

    def checkpoint(self, pid: int, pc: Optional[int] = None,
                   registers: Optional[dict[str, Any]] = None,
                   cpu_ms: int = 0) -> PCB:
        return self.table.checkpoint(pid, pc=pc, registers=registers,
                                     cpu_ms=cpu_ms)

    def heartbeat(self, pid: int) -> None:
        pcb = self.table.get(pid)
        if pcb is None:
            return
        pcb.touch()

    def detect_deadlock(self) -> list[list[int]]:
        """Ciclos en wait-channel ``pcb:PID``."""
        waiting: dict[int, int] = {}
        for pcb in self.table.by_state("blocked", "waiting"):
            ch = pcb.wait_channel or ""
            if ch.startswith("pcb:"):
                try:
                    waiting[pcb.pid] = int(ch.split(":", 1)[1])
                except ValueError:
                    continue
        cycles: list[list[int]] = []
        seen: set[int] = set()
        for start in waiting:
            if start in seen:
                continue
            path = []
            cur: Optional[int] = start
            while cur is not None and cur not in path:
                path.append(cur)
                cur = waiting.get(cur)
            if cur is not None and cur in path:
                cycle = path[path.index(cur):]
                cycles.append(cycle)
                seen.update(cycle)
        return cycles

    def break_deadlock(self) -> int:
        n = 0
        for cycle in self.detect_deadlock():
            victim = min(cycle)
            self.table.set_state(victim, "ready", wait_channel="deadlock_broken")
            n += 1
        return n

    def watchdog(self) -> int:
        """Park running sin heartbeat más de N quantums."""
        limit = (self.knob("watchdog_slices") * self.knob("quantum_ms")) / 1000.0
        now = time.time()
        n = 0
        for pcb in list(self.table.by_state("running")):
            if now - float(pcb.heartbeat_at or 0) > max(1.0, limit):
                self.park(pcb.pid, "watchdog")
                n += 1
        return n

    def age(self) -> None:
        quantum = self.knob("quantum_ms")
        for pcb in self.table.by_state("ready", "blocked", "waiting", "parked"):
            pcb.wait_ms += quantum
        # persist once
        if self.table.procs:
            self.table.checkpoint(next(iter(self.table.procs)))

    def tick(self) -> Optional[PCB]:
        """Un ciclo: aging, deadlock, watchdog, pick+dispatch."""
        self.age()
        self.break_deadlock()
        self.watchdog()
        self.table.reap()
        nxt = self.pick()
        if nxt is None:
            return None
        return self.dispatch(nxt.pid)

    def run_slice(self, pcb: PCB) -> dict[str, Any]:
        handler = self.handlers.get(pcb.kind)
        t0 = time.time()
        try:
            if handler is None:
                result = {"status": "no_handler", "kind": pcb.kind,
                          "pc": pcb.pc}
            else:
                result = handler(pcb) or {}
            ms = int((time.time() - t0) * 1000)
            self.checkpoint(pcb.pid, pc=pcb.pc + 1, cpu_ms=max(1, ms),
                            registers={"last": result})
            status = str(result.get("status") or "ok")
            if status in ("park", "interrupt"):
                self.park(pcb.pid, status)
            elif status in ("blocked", "wait"):
                self.block(pcb.pid, str(result.get("channel") or "io"))
            elif status in ("fail", "failed", "error"):
                self.fail(pcb.pid, str(result.get("error") or status))
            else:
                self.complete(pcb.pid, result)
            return result
        except Exception as exc:  # noqa: BLE001 — el PCB registra y sigue
            self.fail(pcb.pid, f"{type(exc).__name__}: {exc}")
            return {"status": "failed", "error": str(exc)}

    def drain(self, max_jobs: int = 8) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _ in range(max(0, int(max_jobs))):
            pcb = self.tick()
            if pcb is None:
                break
            out.append({"pid": pcb.pid, **self.run_slice(pcb)})
        return out

    def bind_mission(self, goal: str, run_id: str = "") -> PCB:
        pcb = self.table.find_by_goal(goal, "mission")
        if pcb and pcb.state in ("parked", "blocked", "waiting", "ready"):
            if pcb.state != "ready":
                pcb = self.resume(pcb.pid)
            return self.dispatch(pcb.pid)
        pcb = self.admit(goal, kind="mission",
                         registers={"run_id": run_id})
        return self.dispatch(pcb.pid)

    def snapshot(self) -> dict[str, Any]:
        snap = self.table.snapshot()
        snap["applied"] = self.applied
        snap["policies"] = self.applied
        snap["deadlocks"] = self.detect_deadlock()
        snap["at"] = now_iso()
        return snap
