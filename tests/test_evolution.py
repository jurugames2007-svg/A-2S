"""Pruebas del paquete de evolución v1.1: red de gobernanza, consenso,
memoria evolutiva persistente y shell evolucionado."""

import os
import tempfile
import unittest

from a2s.config import Config
from a2s.consensus import ConsensusChecker
from a2s.loop import AgentLoop
from a2s.memory import MemoryHub
from a2s.models import Step, ToolCall
from a2s.neural import GovernanceNet
from a2s.tools import ToolRegistry


class TestGovernanceNet(unittest.TestCase):
    def test_learns_signal(self):
        """El MLP debe aprender una señal simple y predecir mejor que al azar."""
        net = GovernanceNet()
        # Señal: la característica 0 predice el resultado casi perfectamente.
        base = [0.0] * 12
        for _ in range(400):
            x = base[:]
            y = 1.0 if (_ % 2) == 0 else 0.0
            x[0] = y
            net.train(x, y, lr=0.15)
        self.assertGreater(net.forward([1.0] + base[1:]), 0.9)
        self.assertLess(net.forward([0.0] + base[1:]), 0.1)
        self.assertGreaterEqual(net.trained, 400)

    def test_persistence(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "net.json")
        net = GovernanceNet(path=path)
        net.train([0.0] * 12, 1.0)
        net.save()
        net2 = GovernanceNet(path=path)
        self.assertEqual(net2.trained, net.trained)
        self.assertEqual(net2.w2, net.w2)


class TestConsensus(unittest.TestCase):
    def _loop(self, ws, verifier=None):
        cfg = Config(workspace=ws, quiet=True, max_wall_seconds=30)
        return AgentLoop.create("objetivo", config=cfg, goal_verifier=verifier)

    def test_verifier_veto(self):
        tmp = tempfile.mkdtemp()
        loop = self._loop(tmp, verifier=lambda m: (False, "aún no"))
        ok, reason, votes = loop.consensus.check("objetivo")
        self.assertFalse(ok)
        self.assertEqual(votes[0].name, "verificador_de_mision")

    def test_verifier_true_wins(self):
        tmp = tempfile.mkdtemp()
        loop = self._loop(tmp, verifier=lambda m: (True, "cumplido"))
        ok, _reason, votes = loop.consensus.check("objetivo")
        self.assertTrue(ok)
        self.assertIn("verificador_de_mision", _reason)

    def test_no_verifier_majority(self):
        tmp = tempfile.mkdtemp()
        loop = self._loop(tmp)
        ok, _reason, _votes = loop.consensus.check("objetivo")
        self.assertIsInstance(ok, bool)  # sin verifier decide el consenso


class TestMemoryPersistence(unittest.TestCase):
    def test_strategies_survive_runs(self):
        tmp = tempfile.mkdtemp()
        m1 = MemoryHub(tmp, "g")
        m1.record_strategy("directa", won=True)
        m1.record_strategy("directa", won=True)
        m1.record_strategy("directa", won=False)
        m1.finish(False, "nota")
        m2 = MemoryHub(tmp, "g")
        self.assertEqual(m2.strategies["directa"].wins, 2)
        self.assertEqual(m2.strategies["directa"].fails, 1)


class TestShellEvolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.reg = ToolRegistry(self.tmp)
        self.invoke = lambda cmd: self.reg.invoke(ToolCall("shell", {"command": cmd}))

    def test_env_expansion(self):
        obs = self.invoke("echo $HOME")
        self.assertTrue(obs.ok)
        self.assertNotIn("$HOME", obs.output)

    def test_glob_expansion(self):
        from a2s.models import ToolCall as TC
        self.reg.invoke(TC("write_file", {"path": "a.txt", "content": "uno"}))
        self.reg.invoke(TC("write_file", {"path": "b.txt", "content": "dos"}))
        obs = self.invoke("cat *.txt")
        self.assertTrue(obs.ok)
        self.assertIn("uno", obs.output)
        self.assertIn("dos", obs.output)

    def test_command_substitution(self):
        obs = self.invoke("echo $(echo hola)")
        self.assertTrue(obs.ok)
        self.assertIn("hola", obs.output)

    def test_substitution_respects_allowlist(self):
        obs = self.invoke("echo $(curl -s http://x)")
        self.assertFalse(obs.ok)
        self.assertIn("PERMISO DENEGADO", obs.error)


if __name__ == "__main__":
    unittest.main()
