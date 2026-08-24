"""Motor de ejecución: loops inteligentes auto-optimizados.

El bucle nunca responde "no": ante un fallo reintenta, reparametriza, cambia
de herramienta, divide el paso (fractal), re-descompone pasos bloqueados y
replanifica con enfoques distintos. Solo termina cuando:

1. el objetivo se verifica cumplido (verificador de objetivo), o
2. se agota el límite duro de tiempo real (seguridad operativa) — y aun así
   entrega un informe forense con el estado exacto y el plan de reanudación.

Además puede desplegar sub-agentes fractales en paralelo (``run_fractal``)
que evolucionan de forma independiente sobre sub-objetivos.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .aegis_protocol import ProtocolDecision, analyze_request
from .config import Config
from .control import StopToken
from .consensus import ConsensusChecker
from .memory import MemoryHub
from .models import (Evaluation, Observation, RunReport, Step, StepStatus,
                     now_iso)
from .neural import GovernanceNet
from .planner import Planner
from .plugin_loader import PluginLoader
from .providers import BaseProvider, get_provider
from .signing import Signer, report_payload
from .tools import ToolRegistry

# Verificadores personalizables.
GoalVerifier = Callable[[MemoryHub], tuple[bool, str]]
StepVerifier = Callable[[Observation], tuple[bool, str]]
EventHandler = Callable[[dict[str, Any]], None]


@dataclass
class AgentLoop:
    """Una instancia de agente autónomo con todo su estado."""
    config: Config
    provider: BaseProvider
    registry: ToolRegistry
    memory: MemoryHub
    goal_verifier: Optional[GoalVerifier] = None
    step_verifiers: Optional[dict[str, StepVerifier]] = None
    on_event: Optional[EventHandler] = None
    _iterations: int = 0
    _started_at: float = field(default_factory=time.time)
    _plan: list[Step] = field(default_factory=list)
    _timeline: list[dict[str, Any]] = field(default_factory=list)
    _workspace_before: set[str] = field(default_factory=set)
    neural: Optional[GovernanceNet] = None
    consensus: Optional[ConsensusChecker] = None
    protocol: Optional[ProtocolDecision] = None
    stop_token: Optional[StopToken] = None
    _stop_reason: str = ""

    # -- fábrica -----------------------------------------------------------
    @classmethod
    def create(cls, goal: str, config: Optional[Config] = None,
               provider: Optional[BaseProvider] = None,
               goal_verifier: Optional[GoalVerifier] = None,
               step_verifiers: Optional[dict[str, StepVerifier]] = None,
               on_event: Optional[EventHandler] = None) -> "AgentLoop":
        config = config or Config()
        registry = ToolRegistry(config.workspace, allow_network=config.allow_network,
                                allow_shell=config.allow_shell,
                                shell_unsafe=config.shell_unsafe,
                                network_allowlist=config.network_allowlist,
                                sandbox=config.sandbox)
        provider = provider or get_provider(config.provider, config=config)
        memory = MemoryHub(config.workspace, goal)
        loop = cls(config=config, provider=provider, registry=registry, memory=memory,
                   goal_verifier=goal_verifier, step_verifiers=step_verifiers,
                   on_event=on_event)
        # Red de gobernanza (MLP) y consenso de verificación — evolucionan
        # dentro de la ejecución y persisten entre ejecuciones.
        loop.neural = GovernanceNet(os.path.join(memory.dir, "governance.json"))
        loop.consensus = ConsensusChecker(loop)
        # Plugins bajo demanda: solo los que la misión necesita (mínimo hardware).
        loader = PluginLoader(config.workspace)
        loader.discover()
        loop.signer = Signer(config.workspace)
        loop.plugins_active = loader.activate(
            registry, goal, max_plugins=config.max_plugins,
            signer=loop.signer, ledger=memory.ledger)
        loop.stop_token = StopToken()
        registry.stop_token = loop.stop_token
        return loop

    def request_stop(self, reason: str = "operator") -> None:
        """Corta el plazo y avisa a herramientas largas. No espera."""
        self._stop_reason = reason or "operator"
        self.config.max_wall_seconds = 0
        if self.stop_token is None:
            self.stop_token = StopToken()
        self.stop_token.set(self._stop_reason)
        if getattr(self, "registry", None) is not None:
            self.registry.stop_token = self.stop_token

    def _stopped(self) -> bool:
        if self.stop_token is not None and self.stop_token.is_set():
            return True
        return time.time() >= self._started_at + max(0, int(self.config.max_wall_seconds))

    def _live_deadline(self) -> float:
        return self._started_at + max(0, int(self.config.max_wall_seconds))

    # -- eventos -------------------------------------------------------------
    def _emit(self, event: str, data: Optional[dict[str, Any]] = None) -> None:
        entry = {"at": now_iso(), "event": event, **(data or {})}
        self._timeline.append(entry)
        if self.on_event:
            try:
                self.on_event(entry)
            except Exception:  # noqa: BLE001 — el observador nunca rompe el loop
                pass

    def _snapshot_workspace(self) -> set[str]:
        out: set[str] = set()
        for root, _dirs, files in os.walk(self.config.workspace):
            if ".a2s" in root or ".git" in root:
                continue
            for f in files:
                out.add(os.path.relpath(os.path.join(root, f), self.config.workspace))
        return out

    # -- bucle principal -----------------------------------------------------
    def run(self, goal: str) -> RunReport:
        self.memory.goal = goal
        self.protocol = analyze_request(goal)
        protocol_data = self.protocol.to_dict()
        self._workspace_before = self._snapshot_workspace()
        self._emit("run_start", {"goal": goal, "provider": self.provider.name,
                                 "workspace": self.config.workspace,
                                 "sandbox": self.registry.sandbox.level_name,
                                 "plugins": list(getattr(self, "plugins_active", []))})
        self._emit("capability_protocol", {"protocol": protocol_data})
        self.memory.ledger.append("capability_protocol", protocol_data)
        self.config.log(f"[A²S] ▶ Objetivo: {goal}")
        self.config.log(f"[A²S] ◉ necesidad: {', '.join(self.protocol.need_types)}")
        self.config.log("[A²S] ◉ capacidades: " + ", ".join(
            capability.label for capability in self.protocol.capabilities))
        self.config.log(f"[A²S] ⚙ proveedor de razonamiento: {self.provider.name}")
        self.config.log(f"[A²S] ⛨ sandbox: {self.registry.sandbox.level_name} "
                        f"| plugins activos: {getattr(self, 'plugins_active', []) or 'ninguno'}")
        self._bind_pcb(goal)

        schemas = self.registry.schemas()
        context = self.planner.context_for(goal, extra=self.protocol.planner_context())
        if not self._plan:  # permite inyectar un plan manual (tests, reanudación)
            win = self._active_win_rate()
            if (self.neural is not None and self.neural.trained > 0
                    and self.config.speculative_candidates > 1):
                scored = self.planner.decompose_candidates(
                    goal, context, schemas, self.config.speculative_candidates,
                    scorer=lambda p: self.neural.predict_plan(p, win, goal))
                best, self._plan = scored[0]
                self._emit("speculative_plan", {"candidates": len(scored),
                                                "best_score": round(best, 3)})
                self.config.log(f"[A²S] ⟁ planificación especulativa: "
                                f"{len(scored)} candidatos, mejor={best:.2f}")
            else:
                self._plan = self.planner.decompose(goal, context, schemas, variant=0)
            self._emit("plan_created", {"round": 0, "steps": [s.goal for s in self._plan]})

        achieved, reason = False, ""
        round_idx = 0

        while not self._stopped():
            round_idx += 1
            self.config.log(f"[A²S] ⬢ Ronda de plan {round_idx}/{self.config.max_rounds}")
            self._execute_plan(self._plan)
            if self._stopped() and not achieved:
                reason = f"parada cooperativa ({self._stop_reason or 'operator'})"
                self._emit("operator_stop", {"note": reason})
                break

            achieved, reason = self._goal_check(goal)
            self._emit("goal_check", {"achieved": achieved, "reason": reason})
            if achieved:
                break
            if self._stopped():
                reason = f"parada cooperativa ({self._stop_reason or 'operator'})"
                break

            if self._iterations >= self.config.max_iterations * self.config.max_rounds:
                self._emit("budget_renewal", {"note": "presupuesto acumulado expandido vía replanificación"})

            blocked = [s for s in self._plan if s.status in (StepStatus.BLOCKED, StepStatus.FAILED)]
            if blocked and round_idx < self.config.max_rounds and not self._stopped():
                self.config.log(f"[A²S] ◈ re-descomposición fractal de {len(blocked)} paso(s) bloqueado(s)")
                self._plan = self._redecompose(blocked)
                self._emit("replan", {"kind": "fractal", "round": round_idx,
                                      "steps": [s.goal for s in self._plan]})
                continue
            if round_idx < self.config.max_rounds and not self._stopped():
                self.config.log("[A²S] ◈ replanificación con enfoque distinto (variante "
                                f"{round_idx})")
                protocol_context = (self.protocol.planner_context()
                                    if self.protocol is not None else "")
                context = self.planner.context_for(
                    goal, extra=(f"Intento global {round_idx}: evita repetir enfoques ya probados.\n"
                                 f"{protocol_context}"))
                self._plan = self.planner.decompose(goal, context, schemas, variant=round_idx)
                self._emit("replan", {"kind": "variant", "round": round_idx,
                                      "steps": [s.goal for s in self._plan]})
                continue
            break  # rondas agotadas → cierre con informe y plan de reanudación

        # Última pasada de verificación y cierre forense.
        if not achieved and not self._stopped():
            achieved, reason = self._goal_check(goal)
        report = self._finalize(goal, achieved, reason, self._live_deadline())
        return report

    # -- ejecución de un plan ------------------------------------------------
    def _execute_plan(self, plan: list[Step]) -> None:
        while not self._stopped():
            pending = [s for s in plan if s.status == StepStatus.PENDING]
            if not pending:
                return
            progressed = False
            for step in pending:
                if self._stopped():
                    return
                if self._deps_ready(step, plan):
                    self.execute_step(step, plan)
                    progressed = True
            if not progressed:
                for s in pending:  # dependencias bloqueadas → no ejecutables
                    s.mark(StepStatus.SKIPPED)
                return

    def _deps_ready(self, step: Step, plan: list[Step]) -> bool:
        by_id = {s.id: s for s in plan}
        return all(by_id.get(d, step).status == StepStatus.SUCCESS for d in step.depends_on)

    # -- ejecución de un paso con escalera de recuperación -------------------
    def execute_step(self, step: Step, plan: list[Step]) -> None:
        if step.status == StepStatus.SUCCESS:
            return
        # Fija la intención original la primera vez (pasos inyectados manualmente).
        if not step.original_tool and step.calls:
            step.original_tool = step.calls[0].tool
            step.original_params = dict(step.calls[0].params)
        step.mark(StepStatus.RUNNING)
        self._emit("step_start", {"step": step.id, "goal": step.goal,
                                  "approach": step.approach})
        attempts = 0
        while time.time() < self._started_at + self.config.max_wall_seconds:
            attempts += 1
            call = step.calls[0] if step.calls else None
            if call is None:
                step.mark(StepStatus.SKIPPED)
                return
            if self._stopped():
                step.mark(StepStatus.SKIPPED)
                return
            obs = self.registry.invoke(call)
            obs.step_id = step.id
            self._iterations += 1
            ev = self._evaluate(step, obs)
            self.memory.record(step, obs, ev)
            self._pcb_checkpoint(step, ev)
            # Entrenamiento en línea de la red de gobernanza (metaprendizaje).
            if self.neural is not None:
                win = self._active_win_rate()
                y = 1.0 if ev.verdict == "success" else 0.0
                self.neural.train(self.neural.features(self.memory.episodes[-1], win), y)
                if self.neural.trained % 10 == 0:  # checkpoint periódico
                    self.neural.save()
            self._emit("evaluation", {"step": step.id, "goal": step.goal,
                                      "attempt": attempts, "verdict": ev.verdict,
                                      "score": ev.score, "reason": ev.reason,
                                      "output": obs.summary(240)})
            self.config.log(f"      • [{ev.verdict}] {step.goal} "
                            f"(intento {attempts}) — {ev.reason[:90]}")

            if ev.verdict == "success":
                step.mark(StepStatus.SUCCESS)
                self.memory.record_strategy(self.planner.active_strategy, won=True)
                self.planner.consecutive_failures = 0
                self._emit("step_done", {"step": step.id, "status": "success"})
                return

            if ev.verdict == "blocked":
                step.mark(StepStatus.BLOCKED)
                self._emit("step_done", {"step": step.id, "status": "blocked",
                                         "reason": ev.reason})
                return

            counter = self.planner.react_to_failure(step, ev)
            self._emit("failure_handled", {"step": step.id, "countermeasure": counter})
            self.config.log(f"      ↻ {counter}")

            if attempts >= 4:
                if step.depth >= self.config.max_fractal_depth:
                    step.mark(StepStatus.FAILED)
                    self._emit("step_done", {"step": step.id, "status": "failed",
                                             "reason": "profundidad fractal máxima alcanzada"})
                    return
                children = self.planner.split_step(step)
                self._emit("split", {"step": step.id, "goal": step.goal,
                                     "children": [c.goal for c in children]})
                self.config.log(f"      ⑂ paso dividido en {len(children)} sub-pasos")
                plan.extend(children)
                all_ok = True
                for child in children:
                    self.execute_step(child, plan)
                    if child.status != StepStatus.SUCCESS:
                        all_ok = False
                step.mark(StepStatus.SUCCESS if all_ok else StepStatus.FAILED)
                self._emit("step_done", {"step": step.id,
                                         "status": "success" if all_ok else "failed"})
                return

            action = self.planner.evolve_step(step, attempts, ev,
                                              self.memory.recent_history(),
                                              self.registry.schemas())
            self._emit("retry", {"step": step.id, "action": action,
                                 "attempt": attempts + 1})
        step.mark(StepStatus.FAILED)

    # -- evaluación -----------------------------------------------------------
    def _evaluate(self, step: Step, obs: Observation) -> Evaluation:
        verifier = None
        if self.step_verifiers:
            verifier = (self.step_verifiers.get(step.goal)
                        or self.step_verifiers.get(step.id)
                        or next((v for k, v in self.step_verifiers.items()
                                 if k.startswith("__suffix__")
                                 and step.goal.endswith(k[len("__suffix__"):])), None))
        if verifier is not None:
            ok, reason = verifier(obs)
            if obs.error and not obs.ok:
                ok = False
            return Evaluation(step_id=step.id, score=1.0 if ok else 0.1,
                              verdict="success" if ok else "failed",
                              reason=reason, evidence=[obs.summary(300)])
        criteria = " ; ".join(step.success_criteria)
        raw = self.provider.evaluate(step.goal, obs.output or obs.error, criteria)
        verdict = str(raw.get("verdict", "failed"))
        score = float(raw.get("score", 0.0))
        return Evaluation(step_id=step.id, score=score, verdict=verdict,
                          reason=str(raw.get("reason", "")),
                          evidence=[obs.summary(300)])

    def _goal_check(self, goal: str) -> tuple[bool, str]:
        # Consenso de gobernanza: verificador de misión (veto), proveedor,
        # red neuronal y evidencia de progreso votan con pesos.
        if self.consensus is not None:
            ok, reason, _votes = self.consensus.check(goal)
            return ok, reason
        if self.goal_verifier is not None:
            ok, reason = self.goal_verifier(self.memory)
            return ok, reason or ("verificador de objetivo: cumplido" if ok else "no cumplido")
        summary = "\n".join(
            f"- {ep['step_goal']}: {ep['observation'][:200]}"
            for ep in self.memory.episodes[-12:])
        return self.provider.goal_check(goal, summary)

    # -- re-descomposición fractal de pasos bloqueados ------------------------
    def _redecompose(self, blocked: list[Step]) -> list[Step]:
        new_plan: list[Step] = []
        for step in self._plan:
            if step in blocked and step.status != StepStatus.SUCCESS:
                if step.depth >= self.config.max_fractal_depth:
                    new_plan.append(step)
                    continue
                self.config.log(f"      ◈ descomponiendo paso bloqueado: {step.goal}")
                context = self.planner.context_for(
                    step.goal, extra="Re-descomposición de un paso bloqueado: sub-objetivo más simple.")
                subs = self.planner.decompose(step.goal, context,
                                              self.registry.schemas(),
                                              variant=self.planner._plan_rounds)
                for sub in subs:
                    sub.depth = step.depth + 1
                    new_plan.append(sub)
            else:
                new_plan.append(step)
        return new_plan

    # -- sub-agentes fractales -------------------------------------------------
    def run_fractal(self, goals: list[str]) -> dict[str, RunReport]:
        """Despliega una instancia hija por sub-objetivo (paralelo, independiente)."""
        self._emit("fractal_deploy", {"subgoals": goals})
        self.config.log(f"[A²S] ⑂ desplegando {len(goals)} sub-agente(s) fractal(es)")
        budget = self.config.max_wall_seconds * self.config.subagent_share
        parent_deadline = self._started_at + self.config.max_wall_seconds
        results: dict[str, RunReport] = {}

        def _worker(i: int, subgoal: str) -> tuple[str, RunReport]:
            cfg = Config(**{**self.config.__dict__,
                            "max_wall_seconds": int(budget),
                            "max_rounds": max(2, self.config.max_rounds // 2)})
            cfg.workspace = os.path.join(self.config.workspace, ".a2s", "subagents", str(i))
            os.makedirs(cfg.workspace, exist_ok=True)
            child = AgentLoop.create(subgoal, config=cfg, provider=self.provider)
            rep = child.run(subgoal)
            self.memory.ledger.append("subagent_finished", {
                "subgoal": subgoal, "success": rep.success,
                "iterations": rep.iterations})
            return subgoal, rep

        with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.config.max_subagents, max(1, len(goals)))) as pool:
            futures = {pool.submit(_worker, i, g): g for i, g in enumerate(goals)}
            pending = set(futures)
            # El padre no espera más allá de su propio límite duro de tiempo.
            while pending and time.time() < parent_deadline:
                remaining = max(0.05, parent_deadline - time.time())
                done, pending = concurrent.futures.wait(
                    pending, timeout=min(1.0, remaining))
                for fut in done:
                    subgoal, rep = fut.result()
                    results[subgoal] = rep
                    self._timeline.extend(rep.timeline)
            for fut in pending:  # plazo agotado: se cancelan y quedan registrados
                fut.cancel()
                self.memory.ledger.append("subagent_cancelled", {
                    "subgoal": futures[fut], "reason": "límite de tiempo del padre agotado"})
        return results

    # -- cierre forense ----------------------------------------------------------
    def _finalize(self, goal: str, achieved: bool, reason: str, deadline: float) -> RunReport:
        # Registrar artefactos nuevos con hash + firma HMAC (verificación
        # criptográfica de resultados: no basta el hash, se exige el secreto).
        signer = getattr(self, "signer", None) or Signer(self.config.workspace)
        after = self._snapshot_workspace()
        new_files = sorted(after - self._workspace_before)
        for rel in new_files:
            full = os.path.join(self.config.workspace, rel)
            try:
                with open(full, "rb") as fh:
                    blob = fh.read()
                digest = hashlib.sha256(blob).hexdigest()
            except OSError:
                continue
            self.memory.register_artifact(rel, digest)
            try:
                sig = signer.sign(blob)
            except OSError:
                sig = ""
            self.memory.ledger.append("artifact_signed",
                                      {"path": rel, "sha256": digest, "hmac": sig})

        integrity_ok, integrity_msg, n_entries = self.memory.ledger.verify()
        wall = time.time() - self._started_at
        note_parts = []
        if achieved:
            note_parts.append(f"OBJETIVO CUMPLIDO: {reason or 'verificación positiva'}")
        else:
            note_parts.append(
                "Objetivo no verificado dentro del límite duro de tiempo. "
                f"Último estado: {reason or 'sin verificación positiva'}. "
                "El estado completo está persistido; reanuda con: "
                f"python -m a2s run --resume \"{goal}\" (el plan de reanudación está "
                "en .a2s/ledger.jsonl).")
        note_parts.append(f"Cadena de custodia: {integrity_msg} ({n_entries} entradas).")
        if self.protocol is not None:
            note_parts.append("Protocolo adaptativo: " + ", ".join(
                capability.label for capability in self.protocol.capabilities) + ".")
        note_parts.append(f"Iteraciones de herramienta: {self._iterations}. "
                          f"Estancamientos superados: {len(self.planner.stagnation_events)}. "
                          f"Tiempo: {wall:.1f}s.")
        if not achieved and (self._stopped() or time.time() >= deadline):
            if self._stop_reason:
                note_parts.append(f"Parada cooperativa: {self._stop_reason}.")
            else:
                note_parts.append("Límite duro de tiempo alcanzado (seguridad operativa).")

        self.memory.finish(achieved, " | ".join(note_parts))
        self._pcb_close(achieved, reason)
        if self.neural is not None:
            self.neural.save()
        report = RunReport(
            goal=goal, success=achieved, iterations=self._iterations,
            steps=len(self.memory.episodes),
            wall_seconds=round(wall, 2),
            stagnation_events=len(self.planner.stagnation_events),
            strategies=[{"name": s.name, "used": s.used, "wins": s.wins,
                         "fails": s.fails, "win_rate": round(s.win_rate, 2)}
                        for s in self.memory.strategies.values() if s.used],
            timeline=self._timeline,
            artifacts=list(self.memory.artifacts),
            capability_protocol=(self.protocol.to_dict()
                                 if self.protocol is not None else {}),
            final_note=" | ".join(note_parts),
            ended_at=now_iso(),
            sandbox_level=self.registry.sandbox.level_name,
        )
        # Firma criptográfica del informe (payload canónico, HMAC del workspace).
        try:
            report.signature = signer.sign(report_payload(report.to_dict()))
        except OSError:
            report.signature = ""
        self.memory.ledger.append("report_signed",
                                  {"run_id": report.run_id,
                                   "signature": report.signature})
        # Neuroevolución opcional al cierre (aprende del buffer de episodios).
        if self.config.evolve_generations > 0 and self.neural is not None:
            try:
                from .neuroevolve import evolve_from_memory
                evolve_from_memory(self.memory, generations=self.config.evolve_generations,
                                   target=os.path.join(self.memory.dir, "governance.json"))
                self.memory.ledger.append("neuroevolution",
                                          {"generations": self.config.evolve_generations})
            except Exception as exc:  # noqa: BLE001 — la evolución es optativa
                self.memory.ledger.append("neuroevolution_failed", {"error": str(exc)})
        self._emit("run_end", {"success": achieved, "note": report.final_note})
        if achieved:
            self.config.log(f"[A²S] ✔ OBJETIVO CUMPLIDO — {reason or ''}")
        else:
            self.config.log("[A²S] ◐ cierre sin verificación completa (estado persistido "
                            "y reanudable)")
        self.config.log(f"[A²S] ⚖ {integrity_msg} | {n_entries} entradas | {wall:.1f}s | "
                        f"{self._iterations} iteraciones")
        return report

    # -- propiedades auxiliares --------------------------------------------------
    @property
    def planner(self) -> Planner:
        if not hasattr(self, "_planner"):
            self._planner = Planner(self.provider, self.memory, self.config)
        return self._planner

    def _bind_pcb(self, goal: str) -> None:
        try:
            from .kernel import Kernel
            self._kernel = Kernel.open(self.config.workspace)
            self._pcb = self._kernel.bind_mission(goal)
            self._emit("pcb_admit", {"pid": self._pcb.pid,
                                    "pc": self._pcb.pc,
                                    "applied": self._kernel.applied})
            self.config.log(f"[A²S] ⊞ PCB pid={self._pcb.pid} pc={self._pcb.pc} "
                            f"· {self._kernel.applied} mejoras aplicadas")
        except Exception as exc:  # noqa: BLE001 — el loop no depende del PCB
            self._kernel = None
            self._pcb = None
            self.config.log(f"[A²S] ◐ PCB no disponible: {type(exc).__name__}")

    def _pcb_checkpoint(self, step: Step, ev: Evaluation) -> None:
        kernel = getattr(self, "_kernel", None)
        pcb = getattr(self, "_pcb", None)
        if kernel is None or pcb is None:
            return
        try:
            kernel.checkpoint(
                pcb.pid, pc=self._iterations,
                registers={"step": step.id, "verdict": ev.verdict,
                           "goal": step.goal[:160]},
                cpu_ms=1)
            kernel.heartbeat(pcb.pid)
        except Exception:
            pass

    def _pcb_close(self, achieved: bool, reason: str) -> None:
        kernel = getattr(self, "_kernel", None)
        pcb = getattr(self, "_pcb", None)
        if kernel is None or pcb is None:
            return
        try:
            if achieved:
                kernel.complete(pcb.pid, {"success": True, "reason": reason})
            else:
                kernel.park(pcb.pid, self._stop_reason or reason or "pending")
        except Exception:
            pass

    def _active_win_rate(self) -> float:
        try:
            strat = self.memory.strategies.get(self.planner.active_strategy)
            return strat.win_rate if strat else 0.0
        except AttributeError:
            return 0.0


def run_goal(goal: str, config: Optional[Config] = None,
             goal_verifier: Optional[GoalVerifier] = None,
             step_verifiers: Optional[dict[str, StepVerifier]] = None,
             on_event: Optional[EventHandler] = None) -> RunReport:
    """API de conveniencia: crea y ejecuta un agente para un objetivo."""
    loop = AgentLoop.create(goal, config=config, goal_verifier=goal_verifier,
                            step_verifiers=step_verifiers, on_event=on_event)
    return loop.run(goal)
