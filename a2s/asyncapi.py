"""Fachada async en stdlib puro — async SIN aiohttp ni dependencias.

Resolución del punto «asyncio» del ROADMAP_V2: la objeción nunca fue a la
ergonomía async sino a meter aiohttp como dependencia runtime. La solución
honesta es el patrón *async wrapper over sync core*: la API pública expone
``async``/``await`` delegando en ``asyncio.to_thread`` sobre el núcleo
síncrono (que es I/O de red acotado con hilos y locks ya probados).

* Cero dependencias nuevas (asyncio es stdlib desde 3.4; to_thread desde 3.9).
* El núcleo NO se duplica: una sola implementación con dos fachadas.
* El event-loop queda libre mientras los hilos hacen el I/O: se puede
  ``await`` pool.fanout() dentro de un servidor async sin bloquearlo.

Cuándo usar cada fachada (documentado en ROADMAP_V2 §adaptados)::

    sync (ProviderPool)   → scripts, CLI, hilos
    async (AsyncPool)     → integraciones async, servidores con event-loop
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from .provider_pool import ProviderPool, build_pool_provider


def _run(coro):
    """Ejecuta una corrutina en el loop actual (helper para el modo sync)."""
    return asyncio.run(coro)


class AsyncPool:
    """Fachada async de ProviderPool: mismas operaciones, await en vez de bloquear."""

    def __init__(self, pool: ProviderPool) -> None:
        self._pool = pool
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def sync(self) -> ProviderPool:
        """Acceso al núcleo síncrono (status, close, telemetría)."""
        return self._pool

    async def chat(self, prompt: str, kind: str = "general",
                   max_tokens: int = 1000) -> Optional[str]:
        return await asyncio.to_thread(self._pool.chat, prompt, kind, max_tokens)

    async def fanout(self, prompts: list[str], kind: str = "general",
                     max_tokens: int = 1000, max_parallel: int = 8
                     ) -> list[Optional[str]]:
        return await asyncio.to_thread(self._pool.fanout, prompts, kind,
                                       max_tokens, max_parallel)

    async def execute_dag(self, tasks: list[dict[str, Any]],
                          aggregate: Optional[Callable[[dict[str, Any]], Any]] = None,
                          max_parallel: Optional[int] = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._pool.execute_dag, tasks,
                                       aggregate, max_parallel)

    async def aclose(self) -> None:
        await asyncio.to_thread(self._pool.close)


def open_async_pool(pool: Optional[ProviderPool] = None, **kw: Any) -> AsyncPool:
    """Abre la fachada async (construye el pool si no se aporta uno)."""
    return AsyncPool(pool if pool is not None else build_pool_provider(**kw) if kw
                     else build_pool_provider())


async def demo_async(pool: AsyncPool, prompts: list[str]) -> dict[str, Any]:
    """Ejemplo canónico: fanout async + DAG async con agregación."""
    fan = await pool.fanout(prompts, max_parallel=4)
    tasks = [{"id": "a", "prompt": "paso-a"},
             {"id": "b", "prompt": "paso-b"},
             {"id": "c", "prompt": "sintesis", "depends_on": ["a", "b"]}]
    dag = await pool.execute_dag(
        tasks, aggregate=lambda r: [r["results"][k] for k in ("a", "b", "c")])
    return {"fanout": fan, "dag_executed": dag["executed"], "dag_total": dag["total"]}
