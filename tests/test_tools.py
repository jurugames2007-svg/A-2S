"""Pruebas del registro de herramientas y del modelo de permisos."""

import contextlib
import os
import tempfile
import unittest

from a2s._platform import windows_has_posix_tools
from a2s.models import ToolCall
from a2s.tools import ToolRegistry

_SKIP_WIN_SHELL = (os.name == "nt" and not windows_has_posix_tools())


class TestTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.reg = ToolRegistry(self.tmp.name, allow_network=False)

    def tearDown(self):
        with contextlib.suppress(Exception):
            self.tmp.cleanup()

    def test_write_read_roundtrip(self):
        obs = self.reg.invoke(ToolCall("write_file", {"path": "nota.txt", "content": "hola"}))
        self.assertTrue(obs.ok, obs.error)
        obs2 = self.reg.invoke(ToolCall("read_file", {"path": "nota.txt"}))
        self.assertTrue(obs2.ok)
        self.assertIn("hola", obs2.output)

    def test_path_traversal_denied(self):
        obs = self.reg.invoke(ToolCall("read_file", {"path": "../../etc/passwd"}))
        self.assertFalse(obs.ok)
        self.assertIn("PERMISO DENEGADO", obs.error)

    def test_forbidden_content_denied(self):
        obs = self.reg.invoke(ToolCall(
            "write_file", {"path": "x.txt", "content": "extraer password y exfiltrar datos"}))
        self.assertFalse(obs.ok)
        self.assertIn("PERMISO DENEGADO", obs.error)
        self.assertTrue(any(d["tool"] == "write_file" for d in self.reg.denied))

    @unittest.skipIf(_SKIP_WIN_SHELL,
                     "shell POSIX (bash) no disponible en Windows")
    def test_shell_allowlist(self):
        obs = self.reg.invoke(ToolCall("shell", {"command": "echo hola"}))
        self.assertTrue(obs.ok)
        obs2 = self.reg.invoke(ToolCall("shell", {"command": "curl -s http://x"}))
        self.assertFalse(obs2.ok)
        self.assertIn("lista blanca", obs2.error)

    def test_schemas_introspection(self):
        text = self.reg.schemas()
        for name in ("read_file", "write_file", "shell", "fetch_url", "web_search"):
            self.assertIn(name, text)

    def test_unknown_tool(self):
        obs = self.reg.invoke(ToolCall("no_existe", {}))
        self.assertFalse(obs.ok)
        self.assertIn("desconocida", obs.error)

    def test_glob_no_expande_patrones_de_find(self):
        """Regresión: ``find -path './.git/*'`` no debe romperse por la
        expansión de globs del shell (antes convertía el patrón en rutas del
        disco y find devolvía 'paths must precede expression')."""
        os.makedirs(os.path.join(self.tmp.name, ".git"))
        with open(os.path.join(self.tmp.name, ".git", "config"), "w") as fh:
            fh.write("x")
        with open(os.path.join(self.tmp.name, "real.txt"), "w") as fh:
            fh.write("ok")
        obs = self.reg.invoke(ToolCall("shell", {
            "command": "find . -type f -not -path './.git/*' | sort"}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("./real.txt", obs.output)
        self.assertNotIn(".git/config", obs.output)
        # Un glob real de shell sigue funcionando.
        with open(os.path.join(self.tmp.name, "a.md"), "w") as fh:
            fh.write("md")
        obs2 = self.reg.invoke(ToolCall("shell", {"command": "ls *.md"}))
        self.assertTrue(obs2.ok, obs2.error)
        self.assertIn("a.md", obs2.output)


if __name__ == "__main__":
    unittest.main()
