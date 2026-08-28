"""Memoria evolutiva jerárquica.

Niveles (de más efímero a más persistente):

1. **Working state** — estado de la ejecución actual (en RAM + snapshot JSON).
2. **Memoria episódica** — historial de pasos, observaciones y evaluaciones
   (base SQLite consultable).
3. **Artefactos externos** — archivos producidos en el workspace + bitácora
   forense inmutable con cadena de custodia.
4. **Memoria heurística** — biblioteca de estrategias con tasa de éxito
   (núcleo de metaprendizaje: aprende qué funciona y lo reutiliza).
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Optional

from .ledger import Ledger
from .models import Evaluation, Observation, Step, Strategy, now_iso


class MemoryHub:
    def __init__(self, workspace: str, goal: str) -> None:
        self.workspace = os.path.abspath(workspace)
        self.goal = goal
        self._dir = os.path.join(self.workspace, ".a2s")
        os.makedirs(self._dir, exist_ok=True)
        self.ledger = Ledger(self._dir)
        self.episodes: list[dict[str, Any]] = []       # working copy
        self.artifacts: dict[str, str] = {}            # nombre → hash
        self.strategies: dict[str, Strategy] = {}
        self._init_strategies()
        self.ledger.append("run_started", {"goal": goal, "workspace": self.workspace})

    @property
    def dir(self) -> str:
        """Directorio de persistencia (.a2s)."""
        return self._dir

    # -- estrategias iniciales (memoria heurística de arranque) ------------
    def _init_strategies(self) -> None:
        self.strategies["directa"] = Strategy("directa", "Ejecutar la acción más directa posible.")
        self.strategies["reparametrizar"] = Strategy(
            "reparametrizar", "Cambiar parámetros/herramienta del paso fallido y reintentar.")
        self.strategies["dividir"] = Strategy(
            "dividir", "Dividir el paso fallido en sub-pasos más simples.")
        self.strategies["fuente_alternativa"] = Strategy(
            "fuente_alternativa", "Buscar la información por una vía distinta (otra fuente).")
        self.strategies["verificar_y_corregir"] = Strategy(
            "verificar_y_corregir", "Inspeccionar el estado actual y corregir lo que falta.")
        self._load_strategies()

    def _strategies_path(self) -> str:
        return os.path.join(self._dir, "strategies.json")

    def _load_strategies(self) -> None:
        """Memoria evolutiva persistente: reutiliza el aprendizaje previo."""
        path = self._strategies_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for name, s in (data or {}).items():
                if name in self.strategies:
                    self.strategies[name].used += int(s.get("used", 0))
                    self.strategies[name].wins += int(s.get("wins", 0))
                    self.strategies[name].fails += int(s.get("fails", 0))
                else:
                    self.strategies[name] = Strategy(
                        name, str(s.get("description", "estrategia aprendida")),
                        used=int(s.get("used", 0)), wins=int(s.get("wins", 0)),
                        fails=int(s.get("fails", 0)))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        # Decay anti-popularidad: si hay mucha historia acumulada, se
        # reduce a la mitad (techo 1) para que la historia RECIENTE pese
        # más que la antigua (criterio 98: sesgo de popularidad).
        if any((s.used + s.wins + s.fails) > 50 for s in self.strategies.values()):
            for s in self.strategies.values():
                s.used = max(1, (s.used + 1) // 2)
                s.wins = s.wins // 2
                s.fails = s.fails // 2

    def _save_strategies(self) -> None:
        try:
            with open(self._strategies_path(), "w", encoding="utf-8") as fh:
                json.dump({k: {"used": s.used, "wins": s.wins, "fails": s.fails,
                               "description": s.description}
                           for k, s in self.strategies.items()}, fh, ensure_ascii=False)
        except OSError:
            pass

    # -- working state ------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "workspace": self.workspace,
            "episodes": len(self.episodes),
            "strategies": {k: {"used": s.used, "wins": s.wins, "fails": s.fails}
                           for k, s in self.strategies.items()},
        }

    # -- memoria episódica ---------------------------------------------------
    def record(self, step: Step, observation: Optional[Observation],
               evaluation: Optional[Evaluation]) -> None:
        ep = {
            "at": now_iso(),
            "step_id": step.id,
            "step_goal": step.goal,
            "approach": step.approach,
            "tool": (step.calls[0].tool if step.calls else ""),
            "params": (step.calls[0].params if step.calls else {}),
            "attempt": step.attempts,
            "depth": step.depth,
            "observation": observation.summary() if observation else "",
            "ok": observation.ok if observation else False,
            "verdict": evaluation.verdict if evaluation else "unknown",
            "score": evaluation.score if evaluation else 0.0,
            "reason": evaluation.reason if evaluation else "",
        }
        self.episodes.append(ep)
        self.ledger.append("step_episode", ep)
        self._insert_episode(ep)

    def _insert_episode(self, ep: dict[str, Any]) -> None:
        # Persistencia tolerante: un fallo de almacenamiento nunca rompe el loop.
        con = None
        try:
            con = sqlite3.connect(os.path.join(self._dir, "memory.sqlite"))
            with con:
                con.execute(
                    """CREATE TABLE IF NOT EXISTS episodes (
                           at TEXT, step_id TEXT, step_goal TEXT, approach TEXT,
                           tool TEXT, params TEXT, observation TEXT, ok INTEGER,
                           verdict TEXT, score REAL, reason TEXT)""",
                )
                con.execute(
                    "INSERT INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ep["at"], ep["step_id"], ep["step_goal"], ep["approach"], ep["tool"],
                     json.dumps(ep["params"], ensure_ascii=False), ep["observation"],
                     int(ep["ok"]), ep["verdict"], ep["score"], ep["reason"]),
                )
        except Exception:  # noqa: BLE001 — la memoria en RAM ya conserva el episodio
            pass
        finally:
            if con is not None:
                con.close()

    def recent_history(self, n: int = 8) -> str:
        lines = []
        for ep in self.episodes[-n:]:
            lines.append(f"- [{ep['verdict']}] {ep['step_goal']} → {ep['observation'][:160]}")
        return "\n".join(lines) or "(sin historial)"

    # -- artefactos -----------------------------------------------------------
    def register_artifact(self, relpath: str, digest: str) -> None:
        self.artifacts[relpath] = digest
        self.ledger.append("artifact_registered", {"path": relpath, "sha256": digest})

    # -- metaprendizaje --------------------------------------------------------
    def record_strategy(self, name: str, won: bool) -> None:
        s = self.strategies.get(name)
        if s is None:
            s = Strategy(name, "estrategia emergente")
            self.strategies[name] = s
        s.used += 1
        if won:
            s.wins += 1
        else:
            s.fails += 1
        self.ledger.append("strategy_feedback", {"strategy": name, "won": won})
        self._save_strategies()  # el aprendizaje no se pierde si el proceso muere

    def best_strategy(self, exclude: Optional[set[str]] = None) -> str:
        exclude = exclude or set()
        ranked = sorted(
            (s for k, s in self.strategies.items() if k not in exclude),
            key=lambda s: (s.win_rate, s.used), reverse=True)
        return ranked[0].name if ranked else "reparametrizar"

    def finish(self, success: bool, note: str) -> None:
        self._save_strategies()
        self.ledger.append("run_finished", {"success": success, "note": note,
                                            "snapshot": self.snapshot()})
