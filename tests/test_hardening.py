"""Pruebas del hardening v1.2: sandbox, firmas HMAC, auth y plugins."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from tests._winutil import temp_dir
import unittest

from a2s.auth import workspace_token_manager
from a2s.config import Config
from a2s.loop import AgentLoop
from a2s.models import ToolCall
from a2s.plugin_loader import PluginLoader
from a2s.sandbox import Sandbox
from a2s.signing import Signer, report_payload
from a2s.tools import ToolRegistry


class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sb = Sandbox(self.tmp, allow_network=False, timeout=10, mem_mb=128)

    def test_level_detected(self):
        self.assertIn(self.sb.level, (0, 1, 2, 3))
        self.assertEqual(self.sb.level_name, {0: "directo", 1: "rlimits", 2: "bwrap", 3: "nsjail"}[self.sb.level])

    def test_runs_python(self):
        res = self.sb.run_python("print(6*7)")
        self.assertTrue(res.ok, res.output)
        self.assertIn("42", res.output)

    def test_blocks_network(self):
        res = self.sb.run_python(
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('example.com', 80), timeout=2)\n"
            "    print('CONECTADO')\n"
            "except OSError as e:\n"
            "    print('BLOQUEADO:', e)")
        if self.sb.level >= 2:
            self.assertNotIn("CONECTADO", res.output)
        else:  # nivel rlimits: shim de socket
            self.assertIn("BLOQUEADO", res.output)

    def test_memory_limit(self):
        if self.sb.level == 0:
            self.skipTest("rlimits no disponibles en esta plataforma")
        res = self.sb.run_python(
            "try:\n"
            "    x = bytearray(512*1024*1024)\n"
            "    print('ASIGNADO')\n"
            "except MemoryError:\n"
            "    print('LIMITADO')")
        self.assertNotIn("ASIGNADO", res.output)

    def test_timeout(self):
        res = self.sb.run_python(
            "import time\nfor i in range(100): time.sleep(0.2)\nprint('FIN')", timeout=1)
        self.assertTrue(res.timed_out or "FIN" not in res.output)

    def test_cwd_is_workspace(self):
        res = self.sb.run_python("import os; print(os.getcwd())")
        self.assertIn(os.path.normcase(os.path.realpath(self.tmp)),
                      os.path.normcase(res.output))


class TestSigning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.signer = Signer(self.tmp)

    def test_sign_verify_roundtrip(self):
        sig = self.signer.sign({"a": 1, "b": [2, 3]})
        self.assertTrue(self.signer.verify({"a": 1, "b": [2, 3]}, sig))
        self.assertFalse(self.signer.verify({"a": 1, "b": [2, 4]}, sig))

    def test_canonical_order_independent(self):
        s1 = self.signer.sign({"a": 1, "b": 2})
        self.assertTrue(self.signer.verify({"b": 2, "a": 1}, s1))

    def test_secret_persisted(self):
        self.assertTrue(os.path.exists(os.path.join(self.tmp, ".a2s", "secret")))
        signer2 = Signer(self.tmp)
        sig = self.signer.sign("hola")
        self.assertTrue(signer2.verify("hola", sig))

    def test_report_payload_detaches(self):
        rep = {"run_id": "r1", "goal": "g", "success": True, "iterations": 3,
               "steps": 4, "wall_seconds": 1.0, "stagnation_events": 0,
               "artifacts": ["b", "a"], "ended_at": "x", "timeline": [1, 2, 3]}
        p1 = report_payload(rep)
        rep["success"] = False
        p2 = report_payload(rep)
        self.assertEqual(p1["artifacts"], ["a", "b"])
        self.assertNotEqual(p1, p2)


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tm = workspace_token_manager(self.tmp)

    def test_issue_verify(self):
        token = self.tm.issue(scope="dashboard", hours=1)
        ok, payload = self.tm.verify(token, scope="dashboard")
        self.assertTrue(ok, payload)
        self.assertEqual(payload["scope"], "dashboard")

    def test_wrong_scope_rejected(self):
        token = self.tm.issue(scope="otro", hours=1)
        ok, info = self.tm.verify(token, scope="dashboard")
        self.assertFalse(ok)

    def test_expired_rejected(self):
        token = self.tm.issue(scope="dashboard", hours=-0.01)
        ok, info = self.tm.verify(token, scope="dashboard")
        self.assertFalse(ok)
        self.assertIn("expirado", info)

    def test_tampered_rejected(self):
        token = self.tm.issue(hours=1)
        tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
        ok, _ = self.tm.verify(tampered, scope="dashboard")
        self.assertFalse(ok)


class TestPlugins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.loader = PluginLoader(self.tmp)
        self.specs = self.loader.discover()

    def test_builtin_plugins_discovered(self):
        names = set(self.specs)
        self.assertIn("forensics_extra", names)
        self.assertIn("crypto_tools", names)

    def test_activation_by_goal(self):
        reg = ToolRegistry(self.tmp)
        active = self.loader.activate(reg, "hacer un análisis forense con metadatos",
                                      signer=Signer(self.tmp))
        self.assertIn("forensics_extra", active)
        self.assertIn("file_magic", reg._tools)

    def test_no_activation_without_match(self):
        reg = ToolRegistry(self.tmp)
        active = self.loader.activate(reg, "crear un archivo de texto")
        self.assertEqual(active, [])

    def test_file_magic_works(self):
        reg = ToolRegistry(self.tmp)
        self.loader.activate(reg, "forense", signer=Signer(self.tmp))
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        with open(os.path.join(self.tmp, "x.png"), "wb") as fh:
            fh.write(png)
        obs = reg.invoke(ToolCall("file_magic", {"path": "x.png"}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("PNG", obs.output)

    def test_sha256_file_matches(self):
        reg = ToolRegistry(self.tmp)
        self.loader.activate(reg, "hash forense", signer=Signer(self.tmp))
        with open(os.path.join(self.tmp, "d.txt"), "w") as fh:
            fh.write("dato")
        obs = reg.invoke(ToolCall("sha256_file", {"path": "d.txt"}))
        self.assertIn(hashlib.sha256(b"dato").hexdigest(), obs.output)

    def test_sign_verify_tools(self):
        reg = ToolRegistry(self.tmp)
        signer = Signer(self.tmp)
        self.loader.activate(reg, "firma", signer=signer)
        sig_obs = reg.invoke(ToolCall("sign_content", {"content": "hola"}))
        sig = sig_obs.output.split(": ", 1)[-1].strip()
        self.assertTrue(signer.verify("hola", sig))
        ok_obs = reg.invoke(ToolCall("verify_content",
                                     {"content": "hola", "signature": sig}))
        self.assertIn("VÁLIDA", ok_obs.output)
        bad_obs = reg.invoke(ToolCall("verify_content",
                                      {"content": "hola", "signature": "0" * 64}))
        self.assertIn("INVÁLIDA", bad_obs.output)


class TestNetworkAllowlist(unittest.TestCase):
    def test_allowlist_enforced(self):
        tmp = tempfile.mkdtemp()
        reg = ToolRegistry(tmp, network_allowlist=["example.com"])
        obs = reg.invoke(ToolCall("fetch_url", {"url": "https://otro.com/x"}))
        self.assertFalse(obs.ok)
        self.assertIn("lista blanca", obs.error)
        obs2 = reg.invoke(ToolCall("fetch_url", {"url": "https://api.example.com/x",
                                                 "timeout": 2}))
        # api.example.com es subdominio → permitido (fallará por DNS/red, no por política)
        self.assertNotIn("lista blanca", obs2.error)


class TestLiveBuild(unittest.TestCase):
    def test_zipapp_runs(self):
        import zipfile
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, "a2s.pyz")
        build = subprocess.run(
            [sys.executable, "-m", "a2s", "build-live", "--output", target],
            capture_output=True, text=True, timeout=60,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        self.assertTrue(os.path.exists(target))
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc")
                             for name in names))
        self.assertIn("a2s/ui/app.js", names)
        proc = subprocess.run([sys.executable, target, "doctor", "--workspace", tmp],
                              capture_output=True, text=True, timeout=60, cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("A²S", proc.stdout)


if __name__ == "__main__":
    unittest.main()
