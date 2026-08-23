"""Pruebas del motor de ejecución: escalera de recuperación y superación
de estancamiento (looping hasta conseguir el objetivo)."""

import os
import re
import tempfile
from tests._winutil import temp_dir
import unittest

from a2s.config import Config
from a2s.loop import AgentLoop
from a2s.memory import MemoryHub
from a2s.models import Step, StepStatus, ToolCall

_SHA_RE = re.compile(r"\b[0-9a-f]{64}\b")


def _cfg(workspace: str) -> Config:
    # Proveedor heurístico: estas pruebas validan la escalera de recuperación
    # del núcleo, por lo que deben ser herméticas frente a claves de LLM que
    # existan en el entorno (GITHUB_TOKEN activa github-models en modo auto).
    return Config(workspace=workspace, max_wall_seconds=120,
                  max_iterations=30, max_rounds=4, quiet=True,
                  provider="heuristic")


class TestRecoveryLadder(unittest.TestCase):
    """Un paso que falla N veces debe terminar dividiéndose (fractal) y,
    con verificadores correctos, lograr el objetivo."""

    def setUp(self):
        self.tmp = temp_dir()
        self.ws = self.tmp.name
        # Evidencia de ejemplo para que la recopilación tenga datos reales.
        os.makedirs(os.path.join(self.ws, "evidence"), exist_ok=True)
        with open(os.path.join(self.ws, "evidence", "e1.txt"), "w") as fh:
            fh.write("evidencia uno\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _target_content(self):
        path = os.path.join(self.ws, "objetivo.txt")
        if not os.path.isfile(path):
            return None
        # Encoding explícito: el contenido lo escribe el agente (posiblemente
        # desde el sandbox) y el sistema entero opera en UTF-8.
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def test_split_recovery_achieves_goal(self):
        goal = "Crear objetivo.txt con datos reales (hashes SHA-256), sin marcadores"
        step_name = "crear_archivo_objetivo"

        def goal_verifier(memory: MemoryHub):
            content = self._target_content()
            if content is None:
                return False, "objetivo.txt no existe"
            if "MARCADOR" in content:
                return False, "sigue habiendo marcadores"
            if not _SHA_RE.search(content):
                return False, "sin datos reales (hashes)"
            return True, "objetivo.txt contiene datos reales"

        def write_verifier(obs):
            content = self._target_content()
            if content is None:
                return False, "archivo no creado"
            if "MARCADOR" in content:
                return False, "contenido de marcador, no real"
            if not _SHA_RE.search(content):
                return False, "contenido sin datos reales"
            return True, "contenido real verificado"

        def collect_verifier(obs):
            out = obs.output or ""
            if not out.strip():
                return False, "recopilación vacía"
            if not _SHA_RE.search(out):
                return False, "recopilación sin hashes"
            return True, "datos recopilados"

        def compose_verifier(obs):
            content = self._target_content()
            if content is None:
                return False, "documento no compuesto"
            if "MARCADOR" in content or not _SHA_RE.search(content):
                return False, "composición sin datos reales"
            return True, "documento compuesto con datos reales"

        loop = AgentLoop.create(goal, config=_cfg(self.ws),
                                goal_verifier=goal_verifier)
        step = Step(goal=step_name, approach="directa",
                    success_criteria=["archivo creado con contenido real"])
        step.calls = [ToolCall(tool="write_file",
                               params={"path": "objetivo.txt",
                                       "content": "MARCADOR de posición"},
                               why="crear el archivo")]
        loop._plan = [step]
        loop.step_verifiers = {
            step_name: write_verifier,
            "__suffix__ (parte 1/2: recopilar datos)": collect_verifier,
            "__suffix__ (parte 2/2: componer documento)": compose_verifier,
        }
        loop.execute_step(step, loop._plan)

        self.assertEqual(step.status, StepStatus.SUCCESS,
                         f"estado: {step.status} — variantes: {step.variants_tried}")
        ok, reason = goal_verifier(loop.memory)
        self.assertTrue(ok, reason)
        events = [e["event"] for e in loop._timeline]
        self.assertIn("retry", events)
        self.assertIn("split", events)
        # Bitácora forense íntegra.
        ok, msg, _ = loop.memory.ledger.verify()
        self.assertTrue(ok, msg)

    def test_run_loops_until_goal_verified(self):
        """Un objetivo sencillo con verificador debe cumplirse en el loop."""
        goal = "Crear el archivo meta.txt con el texto OK"
        path = os.path.join(self.ws, "meta.txt")

        def goal_verifier(memory: MemoryHub):
            if not os.path.isfile(path):
                return False, "no existe"
            with open(path) as fh:
                return ("OK" in fh.read()), "contenido OK"

        def step_verifier(obs):
            if not os.path.isfile(path):
                return False, "no existe"
            with open(path) as fh:
                content = fh.read()
            return "OK" in content, "OK presente" if "OK" in content else "sin OK"

        loop = AgentLoop.create(goal, config=_cfg(self.ws),
                                goal_verifier=goal_verifier)
        step = Step(goal="escribir_meta", approach="directa",
                    success_criteria=["archivo con OK"])
        step.calls = [ToolCall(tool="write_file",
                               params={"path": "meta.txt", "content": "OK"},
                               why="escribir meta")]
        loop._plan = [step]
        loop.step_verifiers = {"escribir_meta": step_verifier}
        report = loop.run(goal)
        self.assertTrue(report.success, report.final_note)
        self.assertGreaterEqual(report.iterations, 1)
        ok, msg, n = loop.memory.ledger.verify()
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(n, 2)


class TestRecopilacionSinShell(unittest.TestCase):
    """La recopilación de datos del split (escalera de recuperación) no puede
    depender de herramientas POSIX (find/sha256sum): en Windows sin Git-Bash
    la misión debe poder recopilar hashes reales igualmente (regresión v1.11)."""

    def setUp(self):
        self.tmp = temp_dir()
        self.ws = self.tmp.name
        os.makedirs(os.path.join(self.ws, "evidence"), exist_ok=True)
        with open(os.path.join(self.ws, "evidence", "e1.txt"), "w") as fh:
            fh.write("evidencia uno\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_datos_sin_shell_posix(self):
        from a2s.planner import _COLLECT_DATA_CODE
        from a2s.tools import ToolRegistry
        # allow_shell=False simula un Windows sin shell POSIX disponible.
        reg = ToolRegistry(self.ws, allow_network=False, allow_shell=False)
        obs = reg.invoke(ToolCall("python_exec", {"code": _COLLECT_DATA_CODE}))
        self.assertTrue(obs.ok, obs.error)
        self.assertRegex(obs.output, _SHA_RE)
        with open(os.path.join(self.ws, "datos_hashes.txt"),
                  encoding="utf-8") as fh:
            self.assertRegex(fh.read(), _SHA_RE)


class TestFractalSubagents(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.ws = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_fractal(self):
        cfg = _cfg(self.ws)
        cfg.max_wall_seconds = 60
        loop = AgentLoop.create("madre", config=cfg)
        reports = loop.run_fractal(["Crear a.txt con texto A", "Crear b.txt con texto B"])
        self.assertEqual(len(reports), 2)
        for goal, rep in reports.items():
            self.assertTrue(rep.iterations >= 1 or rep.success is not None, goal)


if __name__ == "__main__":
    unittest.main()
