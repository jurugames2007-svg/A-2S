"""Crecimiento autónomo: A²S sigue estudiando en segundo plano.

``AutoLearner`` ejecuta Ciclos de Enriquecimiento de forma continua contra
un **currículo de brechas propias** más lo que el operador escriba en
``workspace/.a2s/growth_queue.txt`` (una consulta por línea): el agente
"crece solo" asimilando conocimiento público verificable.

Límites honestos (heredados del Ciclo de Enriquecimiento, no configurables):

* Solo LECTURA de código público vía API de GitHub, respetando rate limits
  (con ``GITHUB_TOKEN``/``GH_TOKEN`` del operador si existe: más cuota).
* Nunca se ejecuta nada de lo estudiado: se asimilan ideas/recetas, no código.
* Presupuestos duros por ciclo (llamadas y tiempo); el fallo de red es
  silencioso y no tumbla el dashboard.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

from .config import Config
from .learner import BudgetExhausted, GitHubClient, Learner
from .models import now_iso
from .provider_pool import ProviderPool

#: Currículo por defecto: capacidades nucleares de A²S que conviene seguir
#: profundizando aunque nadie pida nada. Consultas cortas y de alta señal
#: (verificadas contra la API de GitHub: devuelven resultados reales).
DEFAULT_CURRICULUM: tuple[str, ...] = (
    "digital forensics framework",
    "LLM API gateway routing fallback",
    "autonomous agent framework",
    "append-only audit log",
    "process sandbox isolation",
    "rate limiter",
    "presentation slide design",
    "book typesetting pdf",
)

_QUEUE_FILE = os.path.join(".a2s", "growth_queue.txt")
_LOG_FILE = os.path.join(".a2s", "growth_log.json")
_LOG_MAX = 200


def autolearn_enabled() -> bool:
    """Interruptor global: ``A2S_AUTO_LEARN=0`` desactiva el crecimiento."""
    return os.environ.get("A2S_AUTO_LEARN", "1").strip().lower() not in ("0", "off", "no")


class AutoLearner:
    """Estudio continuo en hilos daemon: busca, lee y destila fichas."""

    def __init__(self, workspace: str, hub: Any = None,
                 interval_seconds: int = 1800, repos_per_cycle: int = 3,
                 max_calls_per_cycle: int = 24) -> None:
        self.workspace = os.path.abspath(workspace)
        self.hub = hub
        self.interval_seconds = max(30, int(interval_seconds))
        self.repos_per_cycle = repos_per_cycle
        self.max_calls_per_cycle = max_calls_per_cycle
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._index = 0
        self.cycles = 0
        self.last_info: dict[str, Any] = {}
        self.last_error = ""

    # -- cola de estudio -------------------------------------------------------

    def queue_path(self) -> str:
        return os.path.join(self.workspace, _QUEUE_FILE)

    def queries(self) -> list[str]:
        """Consultas del operador (si escribió el fichero) + currículo."""
        extra: list[str] = []
        try:
            with open(self.queue_path(), encoding="utf-8",
                      errors="replace") as fh:
                extra = [ln.strip() for ln in fh if ln.strip()
                         and not ln.lstrip().startswith("#")]
        except OSError:
            pass
        return (extra or []) + list(DEFAULT_CURRICULUM)

    def next_query(self) -> str:
        qs = self.queries()
        q = qs[self._index % len(qs)]
        self._index += 1
        return q

    # -- un ciclo ---------------------------------------------------------------

    def _make_learner(self) -> Learner:
        """Learner con el mejor proveedor disponible (pool SORL u heurístico)."""
        from .providers import get_provider
        cfg = Config(workspace=self.workspace, quiet=True, provider="auto")
        provider = get_provider(cfg.provider, config=cfg)
        pool = provider if isinstance(provider, ProviderPool) else None
        github = GitHubClient(max_calls=self.max_calls_per_cycle)
        return Learner(self.workspace, pool=pool, github=github,
                       repos_per_cycle=self.repos_per_cycle)

    def cycle_once(self, query: Optional[str] = None) -> dict[str, Any]:
        """Un ciclo de estudio (bloqueante, acotado). Nunca lanza."""
        q = query or self.next_query()
        info: dict[str, Any] = {"at": now_iso(), "query": q}
        learner = None
        try:
            learner = self._make_learner()
            t0 = time.time()
            cards = learner.research(q)
            info["new_cards"] = [c.repo for c in cards]
            info["cards_total"] = len(learner.cards)
            info["seconds"] = round(time.time() - t0, 1)
        except BudgetExhausted as exc:
            info["budget_stop"] = str(exc)
        except Exception as exc:  # noqa: BLE001 — crecer nunca rompe el plano
            info["error"] = str(exc)[:300]
        finally:
            if learner is not None and learner.pool is not None:
                try:
                    learner.pool.close()
                except Exception:  # noqa: BLE001
                    pass
        self.cycles += 1
        info["cycle"] = self.cycles
        self.last_info = info
        self._persist(info)
        self._publish(info)
        return info

    def _persist(self, info: dict[str, Any]) -> None:
        path = os.path.join(self.workspace, _LOG_FILE)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            log: list[dict[str, Any]] = []
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        log = json.load(fh)
                except (OSError, ValueError):
                    log = []
            log.append(info)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(log[-_LOG_MAX:], fh, ensure_ascii=False)
        except OSError:
            pass

    def _publish(self, info: dict[str, Any]) -> None:
        if self.hub is None:
            return
        try:
            n = len(info.get("new_cards", []))
            ok = not info.get("error")
            self.hub.publish({
                "event": "growth_cycle",
                "at": info.get("at"),
                "success": ok,
                "query": info.get("query", ""),
                "cards": n,
                "note": (f"ciclo {info.get('cycle')} «{info.get('query', '')[:48]}» "
                         f"→ {n} ficha(s) nueva(s)"
                         + (f" · {info.get('error')[:80]}" if info.get("error") else "")),
            })
        except Exception:  # noqa: BLE001 — telemetría best-effort
            pass

    # -- bucle en segundo plano ---------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="a2s-growth",
                                        daemon=True)
        self._thread.start()

    def _run(self) -> None:
        # Primer ciclo enseguida: "al abrirlo ya se pone a estudiar".
        self.cycle_once()
        while not self._stop.wait(self.interval_seconds):
            self.cycle_once()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)

    # -- visibilidad ---------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        active = bool(self._thread and self._thread.is_alive())
        return {"active": active, "cycles": self.cycles,
                "interval_seconds": self.interval_seconds,
                "queue_file": _QUEUE_FILE, "last": self.last_info or None,
                "curriculum": list(DEFAULT_CURRICULUM)}
