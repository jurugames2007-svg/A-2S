"""Bloque de Control de Proceso (PCB) y colas de planificación persistentes.

Si el proceso muere, el journal + la tabla permiten retomar: mismo pid,
mismo PC, mismos registros. No es magia: es estado en disco con fsync.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .models import now_iso

STATES = (
    "new", "ready", "running", "blocked", "waiting",
    "parked", "completed", "failed", "zombie",
)
QUEUES = ("Q0", "Q1", "Q2", "Q3")  # chat, misión, estudio, batch
KIND_QUEUE = {
    "chat": "Q0", "status": "Q0", "search": "Q0", "resume": "Q0",
    "mission": "Q1", "create": "Q2", "studio": "Q2", "steward": "Q2",
    "codegen": "Q2", "counsel": "Q2", "slides": "Q2", "book": "Q2",
    "growth": "Q3", "research": "Q3", "horizon": "Q3", "hardware": "Q3",
    "macro": "Q2", "vault": "Q3",
}


def goal_hash(kind: str, goal: str) -> str:
    raw = f"{kind}|{(goal or '').strip().lower()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _atomic_write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


@dataclass
class PCB:
    """Registro de un trabajo planificable (estilo SO)."""
    pid: int
    name: str
    goal: str
    kind: str = "mission"
    state: str = "new"
    queue: str = "Q1"
    priority: int = 50
    nice: int = 0
    pc: int = 0
    registers: dict[str, Any] = field(default_factory=dict)
    quantum_ms: int = 250
    cpu_ms: int = 0
    wait_ms: int = 0
    retries: int = 0
    ppid: int = 0
    wait_channel: str = ""
    affinity: str = ""
    fingerprint: str = ""
    hash: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    parked_at: str = ""
    heartbeat_at: float = field(default_factory=time.time)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PCB":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def touch(self) -> None:
        self.updated_at = now_iso()
        self.heartbeat_at = time.time()


class ProcessTable:
    """Tabla de PCB + journal. Una instancia por workspace."""

    def __init__(self, workspace: str) -> None:
        self.workspace = os.path.abspath(workspace)
        self.dir = os.path.join(self.workspace, ".a2s", "pcb")
        os.makedirs(self.dir, exist_ok=True)
        self.table_path = os.path.join(self.dir, "table.json")
        self.journal_path = os.path.join(self.dir, "journal.jsonl")
        self._lock = threading.RLock()
        self.procs: dict[int, PCB] = {}
        self.last_pid = 1000
        self._load()

    def _load(self) -> None:
        try:
            with open(self.table_path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        self.last_pid = int(raw.get("last_pid") or 1000)
        for item in raw.get("procs") or []:
            try:
                pcb = PCB.from_dict(item)
            except TypeError:
                continue
            self.procs[pcb.pid] = pcb

    def _dump(self) -> None:
        payload = {
            "last_pid": self.last_pid,
            "at": now_iso(),
            "procs": [p.to_dict() for p in self.procs.values()],
        }
        _atomic_write(self.table_path, payload)

    def journal(self, event: str, pcb: PCB, extra: Optional[dict[str, Any]] = None
                ) -> None:
        entry = {"at": now_iso(), "event": event, "pid": pcb.pid,
                 "state": pcb.state, "pc": pcb.pc, "kind": pcb.kind,
                 "goal": pcb.goal[:240]}
        if extra:
            entry.update(extra)
        with open(self.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def admit(self, goal: str, kind: str = "mission",
              name: str = "", priority: int = 50,
              registers: Optional[dict[str, Any]] = None,
              dedup: bool = True) -> PCB:
        goal = (goal or "").strip()
        kind = (kind or "mission").strip() or "mission"
        digest = goal_hash(kind, goal)
        with self._lock:
            if dedup:
                for pcb in self.procs.values():
                    if pcb.hash == digest and pcb.state in (
                            "new", "ready", "running", "blocked",
                            "waiting", "parked"):
                        return pcb
            self.last_pid += 1
            pcb = PCB(
                pid=self.last_pid,
                name=name or f"{kind}-{self.last_pid}",
                goal=goal, kind=kind,
                state="ready",
                queue=KIND_QUEUE.get(kind, "Q1"),
                priority=max(1, min(99, int(priority))),
                registers=dict(registers or {}),
                hash=digest,
            )
            self.procs[pcb.pid] = pcb
            self._dump()
            self.journal("admit", pcb)
            return pcb

    def get(self, pid: int) -> Optional[PCB]:
        return self.procs.get(int(pid))

    def find_by_goal(self, goal: str, kind: str = "") -> Optional[PCB]:
        want = (goal or "").strip().lower()
        for pcb in self.procs.values():
            if pcb.goal.strip().lower() == want:
                if not kind or pcb.kind == kind:
                    return pcb
        return None

    def set_state(self, pid: int, state: str, **fields: Any) -> PCB:
        if state not in STATES:
            raise ValueError(f"estado desconocido: {state}")
        with self._lock:
            pcb = self.procs[int(pid)]
            pcb.state = state
            for key, value in fields.items():
                if hasattr(pcb, key):
                    setattr(pcb, key, value)
            pcb.touch()
            if state == "parked":
                pcb.parked_at = now_iso()
            self._dump()
            self.journal(f"state:{state}", pcb, fields if fields else None)
            return pcb

    def checkpoint(self, pid: int, pc: Optional[int] = None,
                   registers: Optional[dict[str, Any]] = None,
                   cpu_ms: int = 0) -> PCB:
        with self._lock:
            pcb = self.procs[int(pid)]
            if pc is not None:
                pcb.pc = int(pc)
            if registers:
                pcb.registers.update(registers)
            if cpu_ms:
                pcb.cpu_ms += int(cpu_ms)
            pcb.touch()
            self._dump()
            self.journal("checkpoint", pcb)
            return pcb

    def by_state(self, *states: str) -> list[PCB]:
        wanted = set(states) or set(STATES)
        return [p for p in self.procs.values() if p.state in wanted]

    def snapshot(self) -> dict[str, Any]:
        counts: dict[str, int] = {s: 0 for s in STATES}
        queues: dict[str, int] = {q: 0 for q in QUEUES}
        for pcb in self.procs.values():
            counts[pcb.state] = counts.get(pcb.state, 0) + 1
            queues[pcb.queue] = queues.get(pcb.queue, 0) + 1
        return {
            "last_pid": self.last_pid,
            "total": len(self.procs),
            "counts": counts,
            "queues": queues,
            "ready": counts["ready"],
            "running": counts["running"],
            "parked": counts["parked"],
            "blocked": counts["blocked"],
            "completed": counts["completed"],
            "failed": counts["failed"],
            "procs": [p.to_dict() for p in sorted(
                self.procs.values(), key=lambda p: p.pid)],
        }

    def reap(self) -> int:
        """Elimina zombies y procesos completed antiguos (conserva parked)."""
        removed = 0
        with self._lock:
            drop = [pid for pid, pcb in self.procs.items()
                    if pcb.state in ("zombie",)]
            for pid in drop:
                del self.procs[pid]
                removed += 1
            if removed:
                self._dump()
        return removed
