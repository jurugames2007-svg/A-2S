"""Neuroevolución: poblaciones de redes que evolucionan por mutación y
selección, en Python puro.

Honestidad técnica:

* Evoluciona los **pesos** de la red de gobernanza (topología 12-8-1 fija en
  producción) mediante perturbación gaussiana + crecimiento/poda del tamaño
  de la capa oculta en los candidatos; el mejor candidato con 8 ocultas se
  exporta al formato de ``GovernanceNet`` (``governance.json``).
* Necesita un buffer de episodios reales: con pocos datos, es ruido.
* Fitness = precisión sobre un holdout del buffer de episodios.
"""

import json
import math
import os
import random
from typing import Any, Optional

from .neural import GovernanceNet, N_HID, N_IN


class EvolvedNet:
    """MLP de una capa oculta con tamaño variable (evolucionable)."""

    def __init__(self, hidden: int = N_HID, seed: int = 0):
        rng = random.Random(seed)
        self.hidden = hidden
        self.w1 = [[rng.uniform(-1, 1) for _ in range(N_IN)] for _ in range(hidden)]
        self.b1 = [rng.uniform(-1, 1) for _ in range(hidden)]
        self.w2 = [rng.uniform(-1, 1) for _ in range(hidden)]
        self.b2 = rng.uniform(-1, 1)

    def forward(self, x: list[float]) -> float:
        h = [math.tanh(sum(xi * wi for xi, wi in zip(x, row)) + b)
             for row, b in zip(self.w1, self.b1)]
        z = sum(hj * w for hj, w in zip(h, self.w2)) + self.b2
        return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))

    def train_step(self, x: list[float], y: float, lr: float = 0.1) -> None:
        """Un paso SGD (entropía cruzada)."""
        h = [math.tanh(sum(xi * wi for xi, wi in zip(x, row)) + b)
             for row, b in zip(self.w1, self.b1)]
        z = sum(hj * w for hj, w in zip(h, self.w2)) + self.b2
        p = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))
        dz = (p - y) * p * (1.0 - p)
        self.b2 -= lr * dz
        for j in range(self.hidden):
            self.w2[j] -= lr * dz * h[j]
        for j in range(self.hidden):
            dh = dz * self.w2[j] * (1.0 - h[j] * h[j])
            self.b1[j] -= lr * dh
            for i in range(N_IN):
                self.w1[j][i] -= lr * dh * x[i]

    def clone(self) -> "EvolvedNet":
        net = EvolvedNet(self.hidden)
        net.w1 = [row[:] for row in self.w1]
        net.b1 = self.b1[:]
        net.w2 = self.w2[:]
        net.b2 = self.b2
        return net

    def mutate(self, sigma: float = 0.25, rng: Optional[random.Random] = None) -> "EvolvedNet":
        rng = rng or random
        child = self.clone()
        for row in child.w1:
            for i in range(len(row)):
                row[i] += rng.gauss(0, sigma)
        child.b1 = [b + rng.gauss(0, sigma) for b in child.b1]
        child.w2 = [w + rng.gauss(0, sigma) for w in child.w2]
        child.b2 += rng.gauss(0, sigma)
        return child

    def grow(self, rng: Optional[random.Random] = None) -> "EvolvedNet":
        rng = rng or random
        net = EvolvedNet(self.hidden + 1, seed=rng.randint(0, 2 ** 31))
        net.w1 = [row[:] for row in self.w1] + [net.w1[-1]]
        net.b1 = self.b1[:] + [net.b1[-1]]
        net.w2 = self.w2[:] + [net.w2[-1]]
        net.b2 = self.b2
        return net

    def prune(self) -> "EvolvedNet":
        if self.hidden <= 2:
            return self.clone()
        net = EvolvedNet(self.hidden - 1)
        net.w1 = [row[:] for row in self.w1[:-1]]
        net.b1 = self.b1[:-1]
        net.w2 = self.w2[:-1]
        net.b2 = self.b2
        return net

    def to_governance(self) -> Optional[dict[str, Any]]:
        """Exporta al formato de GovernanceNet (solo si hidden == 8)."""
        if self.hidden != N_HID:
            return None
        return {"w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"hidden": self.hidden, "w1": self.w1, "b1": self.b1,
                       "w2": self.w2, "b2": self.b2}, fh)


class NeuroEvolve:
    """Población evolutiva sobre un buffer de episodios (X, y)."""

    def __init__(self, pop_size: int = 8, seed: int = 7):
        self.pop_size = pop_size
        self.rng = random.Random(seed)

    def _accuracy(self, net: EvolvedNet, X: list[list[float]], y: list[float]) -> float:
        if not X:
            return 0.0
        correct = sum(1 for x, t in zip(X, y)
                      if (net.forward(x) > 0.5) == bool(t))
        return correct / len(X)

    def evolve(self, X: list[list[float]], y: list[float], generations: int = 5
               ) -> tuple[EvolvedNet, float]:
        if len(X) < 3 or len(y) < 3:
            raise ValueError("buffer insuficiente: se necesitan al menos 3 episodios")
        n_train = max(1, int(len(X) * 0.8))
        Xt, yt, Xv, yv = X[:n_train], y[:n_train], X[n_train:], y[n_train:]
        if len(Xv) < 2:
            raise ValueError("holdout insuficiente: se necesitan al menos 2 episodios")
        pop = [EvolvedNet(N_HID, seed=self.rng.randint(0, 2 ** 31))
               for _ in range(self.pop_size)]
        for gen in range(generations):
            for net in pop:  # un barrido corto de SGD por individuo
                for x, t in zip(Xt, yt):
                    net.train_step(x, t, lr=0.05)
            pop.sort(key=lambda n: self._accuracy(n, Xv, yv), reverse=True)
            survivors = [pop[0].clone(), pop[1].clone()] if len(pop) > 2 else [pop[0].clone()]
            children = [s.mutate(sigma=0.25 - 0.02 * gen, rng=self.rng)
                        for s in survivors
                        for _ in range(self.pop_size // len(survivors))]
            # Variación de topología: crecer/podar con probabilidad baja.
            for i in range(len(children)):
                r = self.rng.random()
                if r < 0.15:
                    children[i] = children[i].grow(self.rng)
                elif r > 0.85:
                    children[i] = children[i].prune()
            pop = children[: self.pop_size]
        pop.sort(key=lambda n: self._accuracy(n, Xv, yv), reverse=True)
        best = pop[0]
        return best, self._accuracy(best, Xv, yv)


def buffer_from_memory(memory: Any) -> tuple[list[list[float]], list[float]]:
    """Convierte la memoria episódica en (X, y) para la evolución."""
    X, y = [], []
    for ep in memory.episodes:
        X.append(GovernanceNet.features(ep))
        y.append(1.0 if ep.get("verdict") == "success" else 0.0)
    return X, y


def evolve_from_memory(memory: Any, generations: int = 5, target: str = "") -> float:
    """Evoluciona desde la memoria episódica y exporta el mejor candidato
    compatible (hidden=8) a ``governance.json``. Devuelve el fitness."""
    X, y = buffer_from_memory(memory)
    if len(X) < 8:
        raise ValueError(f"buffer insuficiente: {len(X)} episodios (mínimo 8)")
    evo = NeuroEvolve()
    best, fitness = evo.evolve(X, y, generations)
    gov = best.to_governance()
    if gov is None:
        raise ValueError("candidato incompatible: la topología no es 12→8→1")
    gov["trained"] = len(X)
    path = target or os.path.join(memory.dir, "governance.json")
    baseline = GovernanceNet(path=path)
    n_train = max(1, int(len(X) * 0.8))
    holdout_x, holdout_y = X[n_train:], y[n_train:]
    baseline_fitness = sum(
        (baseline.forward(x) > 0.5) == bool(t)
        for x, t in zip(holdout_x, holdout_y)
    ) / len(holdout_x)
    if fitness < baseline_fitness:
        return baseline_fitness
    backup = path + ".bak"
    if os.path.isfile(path):
        with open(path, "rb") as source, open(backup, "wb") as saved:
            saved.write(source.read())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(gov, fh)
        os.replace(tmp, path)
    except OSError:
        try:
            if os.path.isfile(backup):
                os.replace(backup, path)
        finally:
            if os.path.isfile(tmp):
                os.unlink(tmp)
        raise
    return fitness


def rollback_governance(memory_dir: str, target: str = "") -> bool:
    """Restaura el último modelo gobernado sin tocar otros artefactos."""
    path = target or os.path.join(memory_dir, "governance.json")
    backup = path + ".bak"
    if not os.path.isfile(backup):
        return False
    os.replace(backup, path)
    return True
