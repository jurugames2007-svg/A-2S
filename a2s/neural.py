"""Red de gobernanza: mini red neuronal (MLP) entrenada en línea, en Python puro.

Implementa dos capacidades de la directiva en su versión técnicamente real:

* **"Razonamiento sin LLM"** — el núcleo aprende de cada episodio a predecir la
  probabilidad de éxito de un paso (forward + retropropagación manual, sin
  dependencias, sin red).
* **"Red neuronal de gobernanza"** — sus predicciones votan en el consenso de
  verificación del objetivo (``consensus.py``) y puntúan los planes
  candidatos en la planificación especulativa.

Persistencia: ``.a2s/governance.json`` (pesos + contador de entrenamiento),
por lo que el conocimiento sobrevive entre ejecuciones.
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import Any, Optional

N_IN = 12
N_HID = 8


class GovernanceNet:
    """Perceptrón multicapa 12→8(tanh)→1(sigmoid) con entrenamiento SGD."""

    def __init__(self, path: Optional[str] = None, seed: int = 42):
        rng = random.Random(seed)
        self.w1 = [[rng.uniform(-1.0, 1.0) for _ in range(N_IN)] for _ in range(N_HID)]
        self.b1 = [rng.uniform(-1.0, 1.0) for _ in range(N_HID)]
        self.w2 = [rng.uniform(-1.0, 1.0) for _ in range(N_HID)]
        self.b2 = rng.uniform(-1.0, 1.0)
        self.trained = 0
        self.path = path
        if path and os.path.exists(path):
            try:
                self.load(path)
            except (OSError, ValueError, json.JSONDecodeError):
                pass

    # -- persistencia ------------------------------------------------------
    def save(self, path: Optional[str] = None) -> None:
        target = path or self.path
        if not target:
            return
        with open(target, "w", encoding="utf-8") as fh:
            json.dump({"w1": self.w1, "b1": self.b1, "w2": self.w2,
                       "b2": self.b2, "trained": self.trained}, fh)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.w1, self.b1 = data["w1"], data["b1"]
        self.w2, self.b2 = data["w2"], data["b2"]
        self.trained = int(data.get("trained", 0))

    # -- forward / train ----------------------------------------------------
    @staticmethod
    def _tanh(x: float) -> float:
        return math.tanh(x)

    @staticmethod
    def _sigmoid(x: float) -> float:
        x = max(-60.0, min(60.0, x))
        return 1.0 / (1.0 + math.exp(-x))

    def forward(self, x: list[float]) -> float:
        h = [self._tanh(sum(xi * wi for xi, wi in zip(x, row)) + b)
             for row, b in zip(self.w1, self.b1)]
        z = sum(hj * w for hj, w in zip(h, self.w2)) + self.b2
        return self._sigmoid(z)

    def train(self, x: list[float], y: float, lr: float = 0.05) -> None:
        """Un paso SGD con pérdida de entropía cruzada binaria."""
        h = [self._tanh(sum(xi * wi for xi, wi in zip(x, row)) + b)
             for row, b in zip(self.w1, self.b1)]
        z = sum(hj * w for hj, w in zip(h, self.w2)) + self.b2
        p = self._sigmoid(z)
        dz = (p - y) * p * (1.0 - p)          # dL/dz (BCE)
        self.b2 -= lr * dz
        for j in range(N_HID):
            self.w2[j] -= lr * dz * h[j]
        for j in range(N_HID):
            dh = dz * self.w2[j] * (1.0 - h[j] * h[j])   # dL/dh · tanh'
            self.b1[j] -= lr * dh
            for i in range(N_IN):
                self.w1[j][i] -= lr * dh * x[i]
        self.trained += 1

    # -- ingeniería de características ---------------------------------------
    @staticmethod
    def features(episode: dict[str, Any], win_rate: float = 0.0) -> list[float]:
        """Vector de 12 características de un episodio."""
        tool = episode.get("tool", "")
        out = episode.get("observation", "") or ""
        goal = episode.get("step_goal", "")
        gl = goal.lower()
        return [
            1.0 if tool == "shell" else 0.0,
            1.0 if tool in ("write_file", "python_exec") else 0.0,
            1.0 if tool in ("fetch_url", "web_search") else 0.0,
            min(1.0, float(episode.get("attempt", 0)) / 4.0),
            min(1.0, float(episode.get("depth", 0)) / 3.0),
            min(1.0, math.log10(len(out) + 1) / 5.0),
            1.0 if "PERMISO DENEGADO" in out else 0.0,
            1.0 if ("Traceback" in out or "Error" in out) else 0.0,
            min(1.0, max(0.0, win_rate)),
            min(1.0, float(episode.get("score", 0.0))),
            1.0 if any(k in gl for k in ("forense", "informe", "hash")) else 0.0,
            1.0 if any(k in gl for k in ("buscar", "web", "investig")) else 0.0,
        ]

    @staticmethod
    def plan_features(steps: list[Any], win_rate: float, goal: str) -> list[float]:
        """Vector de 12 características de un PLAN (para especulación)."""
        tools = [s.calls[0].tool for s in steps if s.calls]
        goals = " ".join(s.goal.lower() for s in steps)
        depth = min(1.0, max((s.depth for s in steps), default=0) / 3.0)
        return [
            1.0 if "shell" in tools else 0.0,
            1.0 if "write_file" in tools else 0.0,
            1.0 if any(t in ("fetch_url", "web_search") for t in tools) else 0.0,
            0.0,                                   # sin intentos aún
            depth,
            min(1.0, len(steps) / 8.0),
            1.0 if any("verific" in g for g in (s.goal.lower() for s in steps)) else 0.0,
            0.0,
            min(1.0, max(0.0, win_rate)),
            0.5,                                   # score a priori neutro
            1.0 if any(k in (goal + goals) for k in ("forense", "informe", "hash")) else 0.0,
            1.0 if any(k in (goal + goals) for k in ("buscar", "web", "investig")) else 0.0,
        ]

    def predict_episode(self, episode: dict[str, Any], win_rate: float = 0.0) -> float:
        return self.forward(self.features(episode, win_rate))

    def predict_plan(self, steps: list[Any], win_rate: float, goal: str) -> float:
        return self.forward(self.plan_features(steps, win_rate, goal))
