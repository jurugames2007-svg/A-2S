"""Prueba de misión completa: la demo debe superar el obstáculo inicial
y entregar el informe forense verificable (el "loop hasta el objetivo")."""

import tempfile
from tests._winutil import temp_dir
import unittest

from a2s.config import Config
from a2s.goals import (DEMO_GOAL, build_demo_step_verifiers,
                       forensic_report_goal_verifier, prepare_demo_workspace)
from a2s.loop import AgentLoop


class TestDemoMission(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.ws = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_demo_mission_achieves_goal(self):
        config = Config(workspace=self.ws, quiet=True,
                        max_wall_seconds=180, max_iterations=40, max_rounds=5,
                        provider="heuristic")
        loop = AgentLoop.create(DEMO_GOAL, config=config,
                                goal_verifier=forensic_report_goal_verifier)
        prepare_demo_workspace(loop.memory)
        loop.step_verifiers = build_demo_step_verifiers(loop.memory)
        report = loop.run(DEMO_GOAL)

        self.assertTrue(report.success, report.final_note)
        # Evidencia del proceso de superación: reintentos y al menos una división.
        events = [e["event"] for e in report.timeline]
        self.assertIn("retry", events)
        self.assertIn("split", events)
        self.assertIn("goal_check", events)
        # El artefacto debe existir y ser válido.
        ok, reason = forensic_report_goal_verifier(loop.memory)
        self.assertTrue(ok, reason)
        # Cadena de custodia íntegra y artefactos registrados.
        integrity, msg, n = loop.memory.ledger.verify()
        self.assertTrue(integrity, msg)
        self.assertIn("informe_forense.md", report.artifacts)
        self.assertGreaterEqual(n, 8)


if __name__ == "__main__":
    unittest.main()
