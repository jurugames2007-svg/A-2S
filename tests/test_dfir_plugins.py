"""Pruebas de la fusión DFIR v1.3: puente forense (lista blanca) y
auditoría defensiva de repositorios/plugins."""

import os
import stat
import sys
import tempfile
import unittest

from a2s.models import ToolCall
from a2s.plugin_loader import PluginLoader
from a2s.signing import Signer
from a2s.tools import ToolRegistry


class TestForensicBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Binario forense simulado (stub) para probar el puente sin instalar
        # Sleuth Kit en el entorno de pruebas.
        self.bindir = os.path.join(self.tmp, "bin")
        os.makedirs(self.bindir, exist_ok=True)
        if sys.platform == "win32":
            self.fls_stub = os.path.join(self.bindir, "fls.cmd")
            with open(self.fls_stub, "w", encoding="utf-8") as fh:
                fh.write("@echo stub fls: %*\n")
        else:
            self.fls_stub = os.path.join(self.bindir, "fls")
            with open(self.fls_stub, "w") as fh:
                fh.write("#!/bin/sh\necho 'stub fls:' \"$@\"\n")
            os.chmod(self.fls_stub, 0o755)
        self.old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self.bindir + os.pathsep + self.old_path
        self.reg = ToolRegistry(self.tmp)
        loader = PluginLoader(self.tmp)
        loader.discover()
        self.active = loader.activate(self.reg, "análisis forense de una imagen",
                                      signer=Signer(self.tmp))

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        # Limpiar el stub del PATH para no contaminar otros tests.

    def test_activated_by_tags(self):
        self.assertIn("forensic_tools", self.active)
        self.assertIn("forensic_cmd", self.reg._tools)

    def test_inventory_lists_available(self):
        obs = self.reg.invoke(ToolCall("forensic_inventory", {}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("fls", obs.output)
        self.assertIn("volatility3", obs.output)  # listado aunque no instalado

    def test_runs_allowlisted_binary(self):
        obs = self.reg.invoke(ToolCall("forensic_cmd",
                                       {"binary": "fls", "args": "imagen.dd"}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("stub fls: imagen.dd", obs.output)

    def test_rejects_offensive_binary(self):
        obs = self.reg.invoke(ToolCall("forensic_cmd",
                                       {"binary": "mimikatz", "args": ""}))
        self.assertFalse(obs.ok)
        self.assertIn("lista blanca", obs.error)

    def test_rejects_path_traversal(self):
        obs = self.reg.invoke(ToolCall("forensic_cmd",
                                       {"binary": "fls", "args": "../../etc/passwd"}))
        self.assertFalse(obs.ok)
        self.assertIn("fuera del workspace", obs.error)

    def test_out_file_confined(self):
        obs = self.reg.invoke(ToolCall("forensic_cmd",
                                       {"binary": "fls", "args": "imagen.dd",
                                        "out_file": "salida.txt"}))
        self.assertTrue(obs.ok, obs.error)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "salida.txt")))


class TestRepoAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.reg = ToolRegistry(self.tmp)
        loader = PluginLoader(self.tmp)
        loader.discover()
        loader.activate(self.reg, "auditoria de seguridad del repositorio",
                        signer=Signer(self.tmp))

    def test_detects_suspicious_patterns(self):
        code = ("import base64, subprocess, os\n"
                "x = os.environ.get('AWS_SECRET_KEY')\n"
                "subprocess.run('sh -c evil', shell=True)\n"
                "exec(base64.b64decode('bWFsd2FyZQ=='))\n")
        with open(os.path.join(self.tmp, "evil.py"), "w") as fh:
            fh.write(code)
        obs = self.reg.invoke(ToolCall("audit_path", {"path": "."}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("ALTA", obs.output)
        self.assertIn("evil.py", obs.output)
        self.assertIn("secretos", obs.output)

    def test_clean_file_no_findings(self):
        with open(os.path.join(self.tmp, "limpio.py"), "w") as fh:
            fh.write("def suma(a, b):\n    return a + b\n")
        obs = self.reg.invoke(ToolCall("audit_path", {"path": "."}))
        self.assertTrue(obs.ok)
        self.assertIn("Sin patrones de riesgo", obs.output)

    def test_hashes_reported(self):
        with open(os.path.join(self.tmp, "d.txt"), "w") as fh:
            fh.write("hola")
        obs = self.reg.invoke(ToolCall("audit_path", {"path": "."}))
        self.assertIn("Hashes SHA-256", obs.output)

    def test_path_confinement(self):
        obs = self.reg.invoke(ToolCall("audit_path", {"path": "../.."}))
        self.assertFalse(obs.ok)
        self.assertIn("fuera del workspace", obs.error)

    def test_audit_plugins_runs(self):
        obs = self.reg.invoke(ToolCall("audit_plugins", {}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("Auditoría de plugins", obs.output)


if __name__ == "__main__":
    unittest.main()
