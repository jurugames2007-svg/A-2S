"""Loop de mejora local, acotado y auditable para Aegis.

Las propuestas son mapas declarativos de ``ruta relativa -> contenido``.
No hay ejecución de comandos, carga de módulos ni acceso a repositorios
externos: el único efecto permitido es escribir o borrar archivos del
workspace explícito.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

from .ledger import Ledger

MetricEvaluator = Callable[[Path], float]


@dataclass(frozen=True)
class ChangeProposal:
    """Cambio declarativo; ``None`` borra el archivo indicado."""

    name: str
    changes: dict[str, Optional[Union[str, bytes]]]
    proposal_id: str = field(default_factory=lambda: f"proposal-{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class ChangeLimits:
    max_iterations: int = 10
    max_changed_files: int = 20
    max_diff_lines: int = 2000
    max_file_bytes: int = 1_000_000
    min_improvement: float = 0.0
    max_mission_tools: int = 50

    def __post_init__(self) -> None:
        if any(value < 1 for value in (self.max_iterations, self.max_changed_files,
                           self.max_diff_lines, self.max_file_bytes,
                           self.max_mission_tools)):
            raise ValueError("los límites enteros deben ser positivos")
        if self.min_improvement < 0:
            raise ValueError("min_improvement no puede ser negativo")


class AutonomousLoop:
    """Evalúa y aplica propuestas únicamente dentro de un workspace dado."""

    def __init__(self, workspace: Union[os.PathLike, str],
                 limits: Optional[ChangeLimits] = None,
                 ledger: Optional[Ledger] = None) -> None:
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError("el workspace debe existir y ser un directorio")
        self.limits = limits or ChangeLimits()
        self.ledger = ledger or Ledger(str(self.workspace / ".a2s"))
        self.state_dir = self.workspace / ".a2s" / "autonomy"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.missions_dir = self.state_dir / "missions"
        self.missions_dir.mkdir(parents=True, exist_ok=True)
        self.baseline: Optional[dict[str, Any]] = None
        self.proposals: dict[str, ChangeProposal] = {}
        self.iterations = 0

    def _path(self, relative: str) -> Path:
        if not relative or Path(relative).is_absolute():
            raise ValueError("la propuesta solo admite rutas relativas")
        candidate = (self.workspace / Path(relative)).resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("la ruta sale del workspace") from exc
        if any(part in {".a2s", ".git"} for part in Path(relative).parts):
            raise ValueError("no se permite modificar estado interno o control de versiones")
        if candidate.exists() and candidate.is_dir():
            raise ValueError("la propuesta no puede reemplazar un directorio")
        return candidate

    def _validate_proposal(self, proposal: ChangeProposal) -> None:
        if not proposal.name or not proposal.changes:
            raise ValueError("la propuesta necesita nombre y cambios")
        if len(proposal.changes) > self.limits.max_changed_files:
            raise ValueError("la propuesta supera max_changed_files")
        for relative, content in proposal.changes.items():
            self._path(relative)
            if content is not None:
                data = content.encode("utf-8") if isinstance(content, str) else content
                if len(data) > self.limits.max_file_bytes:
                    raise ValueError("la propuesta supera max_file_bytes")

    def register_baseline(self, evaluator: MetricEvaluator) -> dict[str, Any]:
        """Mide y registra la baseline actual, sin mutar el workspace."""
        metric = self._metric(evaluator)
        self.baseline = {"metric": metric, "fingerprint": self._fingerprint()}
        self._write_json("baseline.json", self.baseline)
        self.ledger.append("autonomy_baseline", self.baseline)
        return dict(self.baseline)

    def register_proposal(self, proposal: ChangeProposal) -> str:
        self._validate_proposal(proposal)
        self.proposals[proposal.proposal_id] = proposal
        self.ledger.append("autonomy_proposal", {
            "proposal_id": proposal.proposal_id, "name": proposal.name,
            "paths": sorted(proposal.changes),
        })
        return proposal.proposal_id

    def register_mission(self, objective: str, recommended_tools: Iterable[Any] = (),
                         selected_tools: Iterable[Any] = (),
                         excluded_tools: Iterable[Any] = (),
                         baseline: Any = None, cost: float = 0.0,
                         iteration: int = 0,
                         history: Optional[dict[str, Any]] = None) -> str:
        """Registra el contexto de aprendizaje sin ejecutar herramientas externas."""
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("objective debe ser texto no vacío")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ValueError("cost debe ser numérico no negativo")
        if not isinstance(iteration, int) or isinstance(iteration, bool) or iteration < 0:
            raise ValueError("iteration debe ser un entero no negativo")
        tools = {
            "recommended_tools": self._bounded_list(recommended_tools),
            "selected_tools": self._bounded_list(selected_tools),
            "excluded_tools": self._bounded_list(excluded_tools),
        }
        mission_id = f"mission-{uuid.uuid4().hex[:12]}"
        record = {"mission_id": mission_id, "objective": objective,
                  **tools, "baseline": baseline, "before": None, "after": None,
                  "result": None, "cost": float(cost), "iteration": iteration,
                  "decision": "pending", "history": history}
        self._write_json_at(self.missions_dir / f"{mission_id}.json", record)
        self.ledger.append("autonomy_mission", record)
        return mission_id

    def mission_history(self, objective: str = "", tool: str = "") -> dict[str, Any]:
        """Lee el historial local de misiones, sin ejecutar ninguna fuente."""
        if not isinstance(objective, str) or not isinstance(tool, str):
            raise ValueError("objective y tool deben ser texto")
        objective_query = objective.casefold().strip()
        tool_query = tool.casefold().strip()
        records: list[dict[str, Any]] = []
        for path in sorted(self.missions_dir.glob("*.json"), key=lambda item: item.name):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue
            if not isinstance(record, dict) or not isinstance(record.get("mission_id"), str):
                continue
            record_objective = record.get("objective")
            if not isinstance(record_objective, str):
                continue
            if objective_query and objective_query not in record_objective.casefold():
                continue
            if tool_query and not self._mission_has_tool(record, tool_query):
                continue
            records.append(record)
        records.sort(key=lambda record: record["mission_id"])
        return {"records": records, "summary": self._history_summary(records)}

    def read_mission_history(self, objective: str = "", tool: str = "") -> dict[str, Any]:
        """Alias explícito para consultar la memoria histórica persistida."""
        return self.mission_history(objective, tool)

    def learning_report(self, objective: str = "", tool: str = "",
                        limit: int = 1000) -> dict[str, Any]:
        """Construye un informe explicable únicamente desde misiones persistidas.

        Las recomendaciones no consultan fuentes ni ejecutan herramientas: solo
        incluyen herramientas seleccionadas que tienen evidencia de aceptación.
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValueError("limit debe ser un entero entre 1 y 1000")
        history = self.mission_history(objective, tool)
        records = history["records"][:limit]
        metrics = self._report_metrics(records)
        tools_by_objective, recommendations = self._tool_evidence(records)
        exclusions = self._exclusion_evidence(records)
        return {
            "filters": {"objective": objective.strip(), "tool": tool.strip(),
                        "limit": limit},
            "history": {"records": records,
                         "summary": self._history_summary(records)},
            "metrics": metrics,
            "tools_by_objective": tools_by_objective,
            "exclusions": exclusions,
            "recommendations": recommendations,
        }

    @staticmethod
    def _report_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
        summary = AutonomousLoop._history_summary(records)
        costs = [float(record["cost"]) for record in records
                 if isinstance(record.get("cost"), (int, float))
                 and not isinstance(record.get("cost"), bool)]
        accepted_improvements = []
        for record in records:
            result = record.get("result")
            if (record.get("decision") != "accept" or not isinstance(result, dict)
                    or not isinstance(result.get("before"), (int, float))
                    or isinstance(result.get("before"), bool)
                    or not isinstance(result.get("after"), (int, float))
                    or isinstance(result.get("after"), bool)):
                continue
            accepted_improvements.append(float(result["after"]) - float(result["before"]))
        attempts = summary["attempts"]
        return {
            **summary,
            "acceptance_rate": summary["accepted"] / attempts if attempts else 0.0,
            "accepted_average_improvement": (
                sum(accepted_improvements) / len(accepted_improvements)
                if accepted_improvements else 0.0),
            "total_cost": sum(costs),
            "average_cost": sum(costs) / len(costs) if costs else 0.0,
        }

    @classmethod
    def _tool_evidence(cls, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        grouped: dict[str, dict[str, dict[str, Any]]] = {}
        for record in records:
            objective = record["objective"]
            objective_tools = grouped.setdefault(objective, {})
            for item in cls._report_tools(record.get("selected_tools")):
                key = cls._report_tool_key(item)
                evidence = objective_tools.setdefault(key, {
                    "tool": item, "attempts": 0, "accepted": 0,
                    "rejected": 0, "rollbacks": 0, "average_improvement": 0.0,
                    "_improvements": [],
                })
                evidence["attempts"] += 1
                decision = record.get("decision")
                if decision in {"accepted", "accept"}:
                    evidence["accepted"] += 1
                elif decision == "rollback":
                    evidence["rollbacks"] += 1
                elif decision == "reject":
                    evidence["rejected"] += 1
                result = record.get("result")
                if isinstance(result, dict) and isinstance(result.get("before"), (int, float)) \
                        and not isinstance(result.get("before"), bool) \
                        and isinstance(result.get("after"), (int, float)) \
                        and not isinstance(result.get("after"), bool):
                    evidence["_improvements"].append(
                        float(result["after"]) - float(result["before"]))
        by_objective = []
        recommendations = []
        for objective in sorted(grouped):
            tools = []
            for evidence in grouped[objective].values():
                improvements = evidence.pop("_improvements")
                evidence["average_improvement"] = (
                    sum(improvements) / len(improvements) if improvements else 0.0)
                evidence["acceptance_rate"] = (
                    evidence["accepted"] / evidence["attempts"]
                    if evidence["attempts"] else 0.0)
                tools.append(evidence)
            tools.sort(key=lambda item: (-item["accepted"],
                                         -item["average_improvement"], item["tool"]
                                         if isinstance(item["tool"], str) else
                                         cls._report_tool_key(item["tool"])))
            by_objective.append({"objective": objective, "tools": tools})
            for item in tools:
                if item["accepted"]:
                    recommendations.append({"objective": objective, "tool": item["tool"],
                                             "evidence": item["attempts"],
                                             "accepted": item["accepted"],
                                             "acceptance_rate": item["acceptance_rate"],
                                             "reason": "evidencia persistida de aceptación"})
        return by_objective, recommendations

    @classmethod
    def _exclusion_evidence(cls, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            for item in cls._report_tools(record.get("excluded_tools")):
                key = (record["objective"], cls._report_tool_key(item))
                evidence = counts.setdefault(key, {"objective": record["objective"],
                                                   "tool": item, "count": 0})
                evidence["count"] += 1
        return [counts[key] for key in sorted(counts)]

    @staticmethod
    def _report_tools(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _report_tool_key(value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _mission_has_tool(record: dict[str, Any], query: str) -> bool:
        for field_name in ("recommended_tools", "selected_tools", "excluded_tools"):
            for item in record.get(field_name, []):
                values = item.values() if isinstance(item, dict) else (item,)
                if any(query in str(value).casefold() for value in values):
                    return True
        return False

    @staticmethod
    def _history_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        accepted = sum(record.get("decision") == "accept" for record in records)
        rejected = sum(record.get("decision") == "reject" for record in records)
        rollbacks = sum(record.get("decision") == "rollback" for record in records)
        improvements = []
        for record in records:
            result = record.get("result")
            if not isinstance(result, dict):
                continue
            before, after = result.get("before"), result.get("after")
            if (isinstance(before, (int, float)) and not isinstance(before, bool)
                    and isinstance(after, (int, float)) and not isinstance(after, bool)):
                improvements.append(float(after) - float(before))
        average = sum(improvements) / len(improvements) if improvements else 0.0
        return {"attempts": len(records), "accepted": accepted, "rejected": rejected,
                "rollbacks": rollbacks, "average_improvement": average}

    def step(self, proposal: Union[str, ChangeProposal], evaluator: MetricEvaluator,
             mission_id: Optional[str] = None, cost: float = 0.0) -> dict[str, Any]:
        """Evalúa una propuesta y la acepta solo si mejora y respeta límites."""
        if self.baseline is None:
            raise RuntimeError("registra una baseline antes de ejecutar el loop")
        if self.iterations >= self.limits.max_iterations:
            raise RuntimeError("límite de iteraciones alcanzado")
        item = self.proposals[proposal] if isinstance(proposal, str) else proposal
        self._validate_proposal(item)
        mission = self._load_mission(mission_id) if mission_id is not None else None
        normalized_cost = self._cost(cost)
        self.iterations += 1
        before = self._metric(evaluator)
        undo = self._capture(item)
        diff = self._diff(item)
        diff_lines = len(diff.splitlines())
        run_id = f"iteration-{self.iterations}-{uuid.uuid4().hex[:8]}"
        run_dir = self.state_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._write_json_at(run_dir / "undo.json", undo)
        (run_dir / "diff.patch").write_text(diff, encoding="utf-8")
        accepted = False
        reason = ""
        after: Optional[float] = None
        try:
            if diff_lines > self.limits.max_diff_lines:
                reason = "diff supera max_diff_lines"
            else:
                self._apply(item)
                after = self._metric(evaluator)
                accepted = after > before + self.limits.min_improvement
                if not accepted:
                    reason = "la métrica no mejora"
        except Exception as exc:  # el rollback es parte del contrato del loop
            reason = f"evaluación fallida: {type(exc).__name__}: {exc}"
        if not accepted:
            self._restore(undo)
        else:
            self.baseline = {"metric": after, "fingerprint": self._fingerprint()}
        result = {"run_id": run_id, "proposal_id": item.proposal_id,
                  "before": before, "after": after, "accepted": accepted,
                  "reason": reason, "diff_lines": diff_lines,
                  "decision": "accept" if accepted else "reject",
                  "cost": normalized_cost, "iteration": self.iterations}
        if mission is not None:
            mission.update({"before": before, "after": after, "result": result,
                            "cost": result["cost"], "iteration": self.iterations,
                            "decision": result["decision"]})
            self._save_mission(mission)
            result["mission_id"] = mission_id
        self._write_json_at(run_dir / "result.json", result)
        self.ledger.append("autonomy_result", result)
        return result

    def run(self, proposals: Iterable[Union[str, ChangeProposal]],
            evaluator: MetricEvaluator) -> list[dict[str, Any]]:
        """Procesa propuestas en orden con presupuesto finito de iteraciones."""
        results = []
        for proposal in proposals:
            if self.iterations >= self.limits.max_iterations:
                break
            results.append(self.step(proposal, evaluator))
        return results

    def rollback(self, run_id: str) -> None:
        """Restaura una iteración aceptada desde su undo persistido."""
        if not run_id or Path(run_id).name != run_id or Path(run_id).parent != Path("."):
            raise ValueError("identificador de iteración inválido")
        path = self.state_dir / run_id / "undo.json"
        try:
            path.relative_to(self.state_dir)
            undo = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("iteración de rollback no encontrada") from exc
        self._restore(undo)
        result_path = self.state_dir / run_id / "result.json"
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["decision"] = "rollback"
            result["accepted"] = False
            self._write_json_at(result_path, result)
            mission_id = result.get("mission_id")
            if mission_id:
                mission = self._load_mission(mission_id)
                mission["decision"] = "rollback"
                mission["result"] = result
                self._save_mission(mission)
        self.ledger.append("autonomy_rollback", {"run_id": run_id})

    def _load_mission(self, mission_id: str) -> dict[str, Any]:
        if not isinstance(mission_id, str) or Path(mission_id).name != mission_id:
            raise ValueError("identificador de misión inválido")
        path = self.missions_dir / f"{mission_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("misión no encontrada") from exc

    def _save_mission(self, mission: dict[str, Any]) -> None:
        self._write_json_at(self.missions_dir / f"{mission['mission_id']}.json", mission)

    def _bounded_list(self, values: Iterable[Any]) -> list[Any]:
        items = list(values)
        if len(items) > self.limits.max_mission_tools:
            raise ValueError("la misión supera max_mission_tools")
        return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=True,
                                                         sort_keys=True))

    @staticmethod
    def _cost(cost: float) -> float:
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ValueError("cost debe ser numérico no negativo")
        return float(cost)

    def _metric(self, evaluator: MetricEvaluator) -> float:
        metric = evaluator(self.workspace)
        if isinstance(metric, bool) or not isinstance(metric, (int, float)):
            raise TypeError("el evaluador debe devolver una métrica numérica")
        return float(metric)

    def _capture(self, proposal: ChangeProposal) -> dict[str, Optional[str]]:
        captured = {}
        for relative in proposal.changes:
            path = self._path(relative)
            captured[relative] = (base64.b64encode(path.read_bytes()).decode("ascii")
                                  if path.is_file() else None)
        return captured

    def _restore(self, undo: dict[str, Optional[str]]) -> None:
        for relative, encoded in undo.items():
            path = self._path(relative)
            if encoded is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(encoded))

    def _apply(self, proposal: ChangeProposal) -> None:
        for relative, content in proposal.changes.items():
            path = self._path(relative)
            if content is None:
                if path.exists():
                    path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8") if isinstance(content, str) else content
            tmp = path.with_name(path.name + ".a2s-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)

    def _diff(self, proposal: ChangeProposal) -> str:
        output = []
        for relative, content in proposal.changes.items():
            path = self._path(relative)
            old = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if path.is_file() else []
            new = (content.decode("utf-8", "replace") if isinstance(content, bytes) else content or "").splitlines(keepends=True)
            output.extend(difflib.unified_diff(old, new, fromfile=relative, tofile=relative))
        return "".join(output)

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.workspace.rglob("*")):
            if not path.is_file() or ".a2s" in path.parts or ".git" in path.parts:
                continue
            try:
                path.resolve().relative_to(self.workspace)
            except ValueError:
                continue
            digest.update(path.relative_to(self.workspace).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def _write_json(self, name: str, value: dict[str, Any]) -> None:
        self._write_json_at(self.state_dir / name, value)

    @staticmethod
    def _write_json_at(path: Path, value: dict[str, Any]) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")