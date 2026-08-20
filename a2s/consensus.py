"""Consenso de gobernanza: verificación del objetivo por votación ponderada.

Implementa la "red neuronal de gobernanza que decide mediante consenso de
instancias distribuidas" en su versión técnicamente real: varias señales
independientes votan sobre si el objetivo está cumplido.

Señales (cada una con su peso):

* **Verificador de misión** (peso 2, con derecho a veto si dictamina "no"):
  criterios de aceptación específicos del objetivo.
* **Proveedor de razonamiento** (peso 1): heurístico o LLM externo.
* **Red de gobernanza** (peso 1): predicción media del MLP sobre los últimos
  episodios (solo si ya fue entrenada).
* **Evidencia de progreso** (peso 1): al menos un paso con éxito registrado.

El objetivo se declara cumplido solo con mayoría estricta de pesos a favor.
Esto es "autorización por consenso" aplicada a la PROPIA verificación — no
autoriza acciones sobre terceros.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ConsensusVote:
    name: str
    ok: bool
    weight: float
    reason: str


class ConsensusChecker:
    def __init__(self, loop: Any) -> None:
        self.loop = loop

    def _active_win_rate(self) -> float:
        try:
            strat = self.loop.memory.strategies.get(self.loop.planner.active_strategy)
            return strat.win_rate if strat else 0.0
        except AttributeError:
            return 0.0

    def check(self, goal: str) -> tuple[bool, str, list[ConsensusVote]]:
        votes: list[ConsensusVote] = []

        # 1) Verificador de misión (si existe) — peso 2.
        verifier = self.loop.goal_verifier
        if verifier is not None:
            ok, reason = verifier(self.loop.memory)
            votes.append(ConsensusVote("verificador_de_mision", ok, 2.0,
                                       reason or "sin motivo"))

        # 2) Proveedor de razonamiento — peso 1.
        summary = "\n".join(
            f"- {ep['step_goal']}: {ep['observation'][:200]}"
            for ep in self.loop.memory.episodes[-12:])
        ok2, reason2 = self.loop.provider.goal_check(goal, summary)
        votes.append(ConsensusVote("proveedor", ok2, 1.0, reason2))

        # 3) Red de gobernanza — peso 1 (solo si entrenada).
        net = getattr(self.loop, "neural", None)
        recent = self.loop.memory.episodes[-8:]
        if net is not None and net.trained > 0 and recent:
            win = self._active_win_rate()
            preds = [net.predict_episode(ep, win) for ep in recent]
            p = sum(preds) / len(preds)
            votes.append(ConsensusVote("red_de_gobernanza", p > 0.5, 1.0,
                                       f"p_media={p:.2f} sobre {len(preds)} episodios"))

        # 4) Evidencia de progreso — peso 1.
        done = sum(1 for ep in self.loop.memory.episodes if ep.get("verdict") == "success")
        votes.append(ConsensusVote("progreso_episodico", done >= 1, 1.0,
                                   f"{done} paso(s) con éxito"))

        # Verificador de misión: autoritativo — veto si dice "no", decisivo si dice "sí".
        if verifier is not None:
            mission_vote = votes[0]
            reason = " | ".join(f"{v.name}={v.ok} ({v.reason[:60]})" for v in votes)
            return mission_vote.ok, reason, votes

        w_yes = sum(v.weight for v in votes if v.ok)
        w_no = sum(v.weight for v in votes if not v.ok)
        achieved = w_yes > w_no
        reason = " | ".join(f"{v.name}={v.ok} ({v.reason[:60]})" for v in votes)
        return achieved, reason, votes
