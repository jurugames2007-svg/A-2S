"""API de dominio para proyectos Aegis compartida por Jupyter y VS Code."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Union

from .control import StopToken
from .provider_pool import ProviderPool, build_pool_provider
from .autonomy import AutonomousLoop, ChangeLimits


@dataclass
class ProjectConfig:
    """Configuración persistible sin valores secretos."""

    provider: str = "pool"
    max_parallel: int = 8
    timeout_seconds: Optional[float] = 900.0
    pool_config: Optional[str] = None
    secret_refs: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_parallel < 1:
            raise ValueError("max_parallel debe ser >= 1")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        for name, ref in self.secret_refs.items():
            if not isinstance(ref, str) or not ref.startswith("env:") or len(ref) <= 4:
                raise ValueError(f"la referencia secreta {name!r} debe ser env:NOMBRE")

    @classmethod
    def load(cls, path: Union[os.PathLike, str]) -> "ProjectConfig":
        with open(path, encoding="utf-8") as handle:
            return cls(**json.load(handle))

    def save(self, path: Union[os.PathLike, str]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, indent=2, sort_keys=True)

    def resolve_secret(self, name: str) -> str:
        ref = self.secret_refs[name]
        variable = ref[4:]
        value = os.environ.get(variable)
        if not value:
            raise RuntimeError(f"variable de secreto no definida: {variable}")
        return value


class AegisProject:
    """Punto de entrada estable para notebooks, extensiones y otros clientes."""

    def __init__(self, workspace: Union[os.PathLike, str],
                 config: Optional[ProjectConfig] = None,
                 pool: Optional[ProviderPool] = None) -> None:
        self.workspace = Path(workspace)
        self.config = config or self._load_or_default()
        self.pool = pool or build_pool_provider(self._pool_config())

    @property
    def config_path(self) -> Path:
        return self.workspace / ".a2s" / "project.json"

    def _load_or_default(self) -> ProjectConfig:
        return ProjectConfig.load(self.config_path) if self.config_path.is_file() else ProjectConfig()

    def _pool_config(self) -> Any:
        return type("PoolConfig", (), {
            "workspace": str(self.workspace),
            "pool_config": self.config.pool_config,
            "pool_max_parallel": self.config.max_parallel,
            "pool_strategy": "multi_objective",
            "quiet": True,
        })()

    def save_config(self) -> None:
        self.config.save(self.config_path)

    def autonomy_loop(self, limits: Optional[ChangeLimits] = None) -> AutonomousLoop:
        """Crea el loop seguro asociado exclusivamente a este workspace."""
        return AutonomousLoop(self.workspace, limits=limits)

    def mission_history(self, objective: str = "", tool: str = "") -> dict[str, Any]:
        """Consulta la memoria histórica local de iteraciones autónomas."""
        return self.autonomy_loop().mission_history(objective, tool)

    def learning_report(self, objective: str = "", tool: str = "",
                        limit: int = 1000) -> dict[str, Any]:
        """Devuelve el informe explicable basado en evidencia persistida local."""
        return self.autonomy_loop().learning_report(objective, tool, limit)

    def sources(self, capability: str = "", categoria: str = "") -> list[dict[str, Any]]:
        """Consulta fuentes locales sin acceder, descargar ni ejecutar URLs."""
        from .recursos import buscar_fuentes
        return buscar_fuentes(capability, categoria, workspace=str(self.workspace))

    def can_use_source(self, source_id: str,
                       mission_capabilities: tuple[str, ...] = ()) -> dict[str, Any]:
        """Evalúa política y capacidad declarada antes de una misión."""
        from .recursos import puede_usarse_fuente
        return puede_usarse_fuente(source_id, mission_capabilities,
                                   workspace=str(self.workspace))

    def plan_capabilities(self, goal: str, context: Any = None,
                          include_reference_only: bool = False) -> list[dict[str, Any]]:
        """Consulta un plan de capacidades sin acceder ni ejecutar fuentes."""
        from .recursos import planificar_capacidades
        return planificar_capacidades(
            goal, context, include_reference_only=include_reference_only,
            workspace=str(self.workspace))

    def recommend_sources(self, goal: str, categoria: str = "",
                          limit: Optional[int] = None,
                          include_reference_only: bool = False) -> dict[str, Any]:
        """Recomienda fuentes declaradas; nunca las accede ni ejecuta."""
        from .source_registry import select_tools
        return select_tools(goal, categoria, workspace=str(self.workspace),
                            limit=limit,
                            include_reference_only=include_reference_only)

    def run_controlled_iteration(self, objective: str, proposal: Any,
                                 evaluator: Callable[[Path], float],
                                 categoria: str = "", limit: Optional[int] = None,
                                 cost: float = 0.0) -> dict[str, Any]:
        """Registra capacidades locales y ejecuta una única iteración segura."""
        selection = self.recommend_sources(objective, categoria, limit)
        loop = self.autonomy_loop()
        history = loop.mission_history(objective=objective)
        baseline = loop.register_baseline(evaluator)
        mission_id = loop.register_mission(
            objective, selection["selected"], selection["selected"],
            selection["excluded"], baseline=baseline, cost=cost,
            iteration=loop.iterations + 1, history=history)
        result = loop.step(proposal, evaluator, mission_id=mission_id, cost=cost)
        return {**result, "selection": selection, "history": history}

    def run(self, tasks: list[dict[str, Any]], stop: Optional[StopToken] = None,
            aggregate: Any = None,
            event_sink: Optional[Callable[[dict[str, Any]], None]] = None) -> dict[str, Any]:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        token = stop or StopToken()
        result = self.pool.execute_dag(
            tasks, aggregate=aggregate, max_parallel=self.config.max_parallel,
            stop=token, timeout=self.config.timeout_seconds,
            event_sink=event_sink, run_id=run_id)
        result["run_id"] = run_id
        result["project"] = str(self.workspace)
        result["task_ids"] = [task["id"] for task in tasks]
        return result