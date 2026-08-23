"""Planificación fractal, detección de estancamiento y metaprendizaje.

* **Descomposición fractal**: objetivo → pasos; un paso bloqueado se convierte
  en sub-objetivo con su propio plan (nunca se abandona).
* **Escalera de recuperación** (``evolve_step``): reintento → reparametrización
  → cambio de herramienta → división del paso en sub-pasos más simples.
* **Detección de estancamiento**: ventana de fallos seguidos → cambio de
  estrategia global elegida por tasa de éxito (núcleo de metaprendizaje).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import Config
from .memory import MemoryHub
from .models import Evaluation, Step, StepStatus, ToolCall
from .providers import BaseProvider


@dataclass
class StagnationEvent:
    step_id: str
    reason: str
    countermeasure: str
    strategy_chosen: str


@dataclass
class Planner:
    provider: BaseProvider
    memory: MemoryHub
    config: Config

    consecutive_failures: int = 0
    stagnation_events: list[StagnationEvent] = field(default_factory=list)
    active_strategy: str = "directa"
    _plan_rounds: int = 0

    # -- descomposición fractal ---------------------------------------------
    def decompose(self, goal: str, context: str, tool_schemas: str,
                  variant: int = 0) -> list[Step]:
        """Genera pasos para un (sub)objetivo. Variante = ronda de plan (diversidad)."""
        self._plan_rounds += 1
        raw = self.provider.plan(goal, context, tool_schemas, variant=variant)
        steps: list[Step] = []
        for i, item in enumerate(raw.get("steps", [])):
            # El id del plan es el id real del paso (dependencias consistentes).
            step = Step(
                id=str(item.get("id") or f"step-{variant}-{i+1}"),
                goal=str(item.get("goal", f"paso {i+1}")),
                approach=str(item.get("approach", self.active_strategy)),
                success_criteria=[str(c) for c in item.get("success_criteria", [])],
                depends_on=[str(d) for d in item.get("depends_on", [])],
            )
            tool = item.get("tool", "shell")
            params = item.get("params") or {}
            if isinstance(params, str):  # tolerancia a LLM que devuelve string
                params = {"command": params}
            step.calls = [ToolCall(tool=tool, params=dict(params), why=step.goal)]
            step.original_tool = tool
            step.original_params = dict(params)
            steps.append(step)
        if not steps:
            steps.append(self._fallback_step(goal))
        return steps

    # -- planificación especulativa -----------------------------------------
    def decompose_candidates(self, goal: str, context: str, tool_schemas: str,
                             n: int, scorer) -> list[tuple[float, list[Step]]]:
        """Genera n planes variantes y los ordena por puntuación de la red de
        gobernanza (o heurística si no hay). Simulación paralela de futuros."""
        plans = [self.decompose(goal, context, tool_schemas, variant=v)
                 for v in range(max(1, n))]
        scored = sorted(((scorer(p), p) for p in plans), key=lambda t: t[0], reverse=True)
        return scored

    @staticmethod
    def _fallback_step(goal: str) -> Step:
        step = Step(goal="documentar_objetivo", approach="directa",
                    success_criteria=["resultado documentado"])
        step.calls = [ToolCall(tool="write_file",
                               params={"path": "resultado.md",
                                       "content": f"# Objetivo\n\n{goal}\n"},
                               why=goal)]
        return step

    # -- metaprendizaje: reacción al fallo -----------------------------------
    def react_to_failure(self, step: Step, evaluation: Evaluation) -> str:
        """Registra el fallo y devuelve la contramedida anunciada."""
        self.consecutive_failures += 1
        self.memory.record_strategy(self.active_strategy, won=False)
        if self.consecutive_failures >= self.config.stagnation_window:
            previous = self.active_strategy
            self.active_strategy = self.memory.best_strategy(exclude={previous})
            counter = (f"estancamiento detectado ({self.consecutive_failures} fallos seguidos) "
                       f"→ cambio de estrategia '{previous}' → '{self.active_strategy}'")
            ev = StagnationEvent(step_id=step.id, reason=evaluation.reason,
                                 countermeasure=counter,
                                 strategy_chosen=self.active_strategy)
            self.stagnation_events.append(ev)
            self.memory.ledger.append("stagnation_event",
                                      {"step": step.id, "reason": evaluation.reason,
                                       "countermeasure": counter})
            self.consecutive_failures = 0
            return counter
        return (f"fallo {self.consecutive_failures}/{self.config.stagnation_window} "
                f"antes de declarar estancamiento — reintentando")

    def evolve_step(self, step: Step, attempt_no: int, evaluation: Evaluation,
                    history: str, tool_schemas: str) -> str:
        """Muta el paso para el siguiente intento (escalera de recuperación).

        Devuelve la acción aplicada: retry | reparam | tool_swap | split.
        """
        hint = self.provider.reparameterize(step.goal, evaluation.reason, history, tool_schemas)
        change = str(hint.get("change", ""))
        tool_swap = {"shell": "python_exec", "fetch_url": "web_search",
                     "web_search": "fetch_url", "write_file": "python_exec"}

        if attempt_no == 1:
            action = "retry"
        elif attempt_no == 2:
            action = "reparam"
            if step.calls:
                # Mutación idempotente: parte siempre de la intención original.
                params = dict(step.original_params or step.calls[0].params)
                if params:
                    prefer = [k for k in ("content", "command", "query", "code")
                              if k in params]
                    key = prefer[0] if prefer else max(
                        params, key=lambda k: len(str(params[k])))
                    params[key] = (f"{params[key]} "
                                   f"(intento 2 — {change[:60] or 'parámetros variados'})")
                step.calls[0].params = params
        elif attempt_no == 3:
            action = "tool_swap"
            old = step.original_tool or (step.calls[0].tool if step.calls else "")
            if old in tool_swap and step.calls:
                new = tool_swap[old]
                call = step.calls[0]
                params = dict(step.original_params or call.params)
                # Adaptación de parámetros entre herramientas equivalentes.
                if old == "shell" and new == "python_exec":
                    cmd = params.pop("command", "print('sin comando')")
                    params = {"code": ("import subprocess; p = subprocess.run("
                                       f"{cmd!r}, shell=True, capture_output=True, text=True); "
                                       "print((p.stdout or '') + (p.stderr or ''))")}
                elif old == "write_file" and new == "python_exec":
                    path = params.pop("path", "salida.txt")
                    content = params.pop("content", "")
                    params = {"code": f"open({path!r}, 'w').write({content!r}); "
                                      f"print('escrito {path}')"}
                elif old == "fetch_url" and new == "web_search":
                    url = params.pop("url", "")
                    params = {"query": url}
                elif old == "web_search" and new == "fetch_url":
                    import urllib.parse
                    q = params.pop("query", "")
                    params = {"url": "https://html.duckduckgo.com/html/?q="
                                      + urllib.parse.quote(q)}
                call.tool = new
                call.params = params
            else:
                action = "reparam"
        else:
            action = "split"

        step.attempts = attempt_no
        step.variants_tried.append(f"{self.active_strategy}/{action}")
        step.approach = (f"{self.active_strategy} + {action}"
                         + (f" ({change[:60]})" if change and action != "split" else ""))
        return action

    def split_step(self, step: Step) -> list[Step]:
        """Divide un paso obstinado en sub-pasos más simples (fractal).

        Reglas específicas por herramienta:

        * ``write_file`` → (1) recopilar datos reales del entorno con shell,
          (2) componer el archivo con Python usando los datos recopilados.
        * ``read_file``  → (1) inventariar el directorio, (2) leer el archivo.
        * genérico      → (1) preparar contexto, (2) ejecutar la acción.
        """
        base = step.goal.rstrip(".")
        # La intención ORIGINAL manda: las mutaciones previas no la alteran.
        tool = step.original_tool or (step.calls[0].tool if step.calls else "shell")
        orig_params = step.original_params or (step.calls[0].params if step.calls else {})
        if tool == "write_file":
            target = orig_params.get("path", "resultado.md")
            c1 = Step(goal=f"{base} (parte 1/2: recopilar datos)",
                      approach="dividir: recopilación", depth=step.depth + 1,
                      success_criteria=["datos reales recopilados"])
            c1.calls = [ToolCall(
                tool="python_exec",
                params={"code": _COLLECT_DATA_CODE},
                why="recopilar datos reales para el documento")]
            c2 = Step(goal=f"{base} (parte 2/2: componer documento)",
                      approach="dividir: composición", depth=step.depth + 1,
                      depends_on=[c1.id],
                      success_criteria=["documento compuesto con datos reales"])
            c2.calls = [ToolCall(
                tool="python_exec",
                params={"code": _COMPOSE_REPORT_CODE.replace('"__TARGET__"', json.dumps(target))},
                why="componer el documento final con los datos recopilados")]
            c1.original_tool, c1.original_params = "python_exec", {"code": _COLLECT_DATA_CODE}
            c2.original_tool, c2.original_params = "python_exec", dict(c2.calls[0].params)
            return [c1, c2]
        if tool == "read_file":
            path = orig_params.get("path", ".")
            c1 = Step(goal=f"{base} (parte 1/2: localizar)", approach="dividir",
                      depth=step.depth + 1, success_criteria=["ubicación conocida"])
            c1.calls = [ToolCall(tool="list_dir", params={"path": path},
                                 why="localizar el recurso")]
            c2 = Step(goal=f"{base} (parte 2/2: leer)", approach="dividir",
                      depth=step.depth + 1, depends_on=[c1.id],
                      success_criteria=["contenido leído"])
            c2.calls = [ToolCall(tool="read_file", params=dict(orig_params),
                                 why="leer el recurso localizado")]
            return [c1, c2]
        c1 = Step(goal=f"{base} (parte 1/2: preparar contexto)", approach="dividir",
                  depth=step.depth + 1, success_criteria=["contexto preparado"])
        c1.calls = [ToolCall(tool="list_dir", params={"path": "."}, why="preparar contexto")]
        c2 = Step(goal=f"{base} (parte 2/2: ejecutar)", approach="dividir",
                  depth=step.depth + 1, depends_on=[c1.id],
                  success_criteria=step.success_criteria)
        # Los hijos heredan la intención original y ejecutan desde cero.
        c2.calls = [ToolCall(tool=tool, params=dict(orig_params), why=step.goal)]
        c2.original_tool = tool
        c2.original_params = dict(orig_params)
        return [c1, c2]

    # -- contexto para el planificador ----------------------------------------
    def context_for(self, goal: str, extra: str = "") -> str:
        lines = [
            f"Objetivo de la ronda: {goal}",
            f"Ronda de planificación: {self._plan_rounds}",
            f"Estrategia activa: {self.active_strategy}",
            f"Historial reciente:\n{self.memory.recent_history()}",
        ]
        if self.stagnation_events:
            lines.append("Eventos de estancamiento previos:")
            for ev in self.stagnation_events[-3:]:
                lines.append(f"  - {ev.reason[:80]} → {ev.countermeasure[:80]}")
        if extra:
            lines.append(extra)
        return "\n".join(lines)


# Recopilación 100% stdlib (os.walk + hashlib): NO depende de herramientas
# POSIX (find/sha256sum) ni de shell alguno, de modo que la escalera de
# recuperación funciona igual en Windows sin Git-Bash/MSYS2/WSL.
_COLLECT_DATA_CODE = '''\
import hashlib, os
from pathlib import Path
EXCLUIR = {".git", ".a2s"}
hashes, inv = [], []
for root, dirs, files in os.walk("."):
    dirs[:] = sorted(d for d in dirs if d not in EXCLUIR)
    for fn in sorted(files):
        full = os.path.join(root, fn)
        if not os.path.isfile(full):
            continue
        rel = os.path.relpath(full, ".").replace(os.sep, "/")
        inv.append(rel)
        try:
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            hashes.append(h.hexdigest() + "  " + rel)
        except OSError:
            pass
hashes.sort(key=lambda linea: linea.split("  ", 1)[-1])
Path("datos_hashes.txt").write_text("\\n".join(hashes) + ("\\n" if hashes else ""), encoding="utf-8")
Path("datos_inventario.txt").write_text("\\n".join(inv) + ("\\n" if inv else ""), encoding="utf-8")
git = ""
try:
    import subprocess
    p = subprocess.run(["git", "log", "--oneline", "-20"], capture_output=True,
                       text=True, timeout=10, stdin=subprocess.DEVNULL)
    git = (p.stdout or "").strip()
except Exception:
    git = ""
Path("datos_git.txt").write_text(git or "sin repositorio git", encoding="utf-8")
print("\\n".join(hashes))
print(f"hashes recopilados: {len(hashes)}")
'''

_COMPOSE_REPORT_CODE = '''\
import os, re
def read(p, default="(sin datos)"):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read().strip()
hash_lines = [l for l in read("datos_hashes.txt").splitlines() if l.strip()]
inv = read("datos_inventario.txt")
git = read("datos_git.txt")
base = read("__TARGET__", "")
n = len([l for l in hash_lines if re.match(r"^[0-9a-f]{64}\\s", l)])
markers = ["MARCADOR", "(hashes de la fase 3)", "(inventario de la fase 1)",
           "(metadatos de la fase 2)", "(evidencia de la fase 4)", "(sin datos)"]
if not base.strip() or any(m in base for m in markers):
    sec = lambda t, b: f"## {t}\\n\\n{b}\\n"
    body = "# Informe Forense A2S\\n\\n"
    body += sec("Inventario", "\\n".join("- " + p for p in inv.splitlines()[:50]) or "(vacío)")
    body += sec("Hashes", "\\n".join(hash_lines[:50]) or "(sin hashes)")
    body += sec("Cadena de custodia", "Registro git:\\n" + git + f"\\n\\nTotal de evidencias con hash: {n}")
    body += sec("Conclusiones", f"Análisis completado por el agente A2S. Evidencias procesadas: {n} archivos con hash SHA-256.")
else:
    body = base.rstrip() + "\\n\\n## Anexo: datos recopilados\\n\\n" + "\\n".join(hash_lines[:50]) + f"\\n\\nTotal de evidencias con hash: {n}\\n"
open("__TARGET__", "w", encoding="utf-8").write(body)
print(f"informe generado con {n} hashes")
'''
