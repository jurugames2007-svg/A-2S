"""Modelos de datos compartidos por el núcleo A²S."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"          # fallo que se puede reparametrizar
    BLOCKED = "blocked"        # fallo que requiere cambio de estrategia
    SKIPPED = "skipped"


@dataclass
class ToolCall:
    """Invocación concreta de una herramienta (acción ejecutable)."""
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    why: str = ""               # justificación generada por el planificador
    retries: int = 0


@dataclass
class Step:
    """Paso atómico de un plan fractal."""
    id: str = field(default_factory=lambda: new_id("step"))
    goal: str = ""                          # enunciado del sub-objetivo
    approach: str = ""                      # estrategia actual (se reparametriza)
    calls: list[ToolCall] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    depth: int = 0                          # nivel de descomposición fractal
    original_tool: str = ""                 # intención original (pre-mutaciones)
    original_params: dict[str, Any] = field(default_factory=dict)
    variants_tried: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def mark(self, status: StepStatus) -> None:
        self.status = status
        self.updated_at = now_iso()


@dataclass
class Observation:
    """Resultado observado tras ejecutar una acción."""
    step_id: str
    ok: bool
    output: str = ""
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    elapsed: float = 0.0
    at: str = field(default_factory=now_iso)

    def summary(self, limit: int = 500) -> str:
        body = self.output or self.error or ""
        if len(body) > limit:
            body = body[:limit] + f"… [+{len(body) - limit} chars]"
        return body


@dataclass
class Evaluation:
    """Veredicto del evaluador sobre una observación."""
    step_id: str
    score: float                # 0..1
    verdict: str                # success | failed | blocked
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    at: str = field(default_factory=now_iso)


@dataclass
class Strategy:
    """Estrategia de resolución (objeto del núcleo de metaprendizaje)."""
    name: str
    description: str
    template: str = ""
    used: int = 0
    wins: int = 0
    fails: int = 0

    @property
    def win_rate(self) -> float:
        total = self.wins + self.fails
        return (self.wins / total) if total else 0.0


@dataclass
class RunReport:
    """Informe forense de una ejecución completa."""
    run_id: str = field(default_factory=lambda: new_id("run"))
    goal: str = ""
    success: bool = False
    iterations: int = 0
    steps: int = 0
    wall_seconds: float = 0.0
    stagnation_events: int = 0
    strategies: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    final_note: str = ""
    signature: str = ""               # HMAC del informe (verificación criptográfica)
    sandbox_level: str = ""           # nivel de aislamiento usado
    started_at: str = field(default_factory=now_iso)
    ended_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ActionFactory = Callable[..., ToolCall]
