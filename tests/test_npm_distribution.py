"""Contratos de la distribución npm y del launcher multiplataforma."""

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return json.load(fh)


class TestNpmMetadata(unittest.TestCase):
    def test_versiones_python_npm_sincronizadas(self):
        package = _json("package.json")
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            pyproject = fh.read()
        with open(os.path.join(ROOT, "a2s", "__init__.py"), encoding="utf-8") as fh:
            init = fh.read()
        pyproject_version = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
        init_version = re.search(r'^__version__ = "([^"]+)"', init, re.M).group(1)
        self.assertEqual(package["version"], pyproject_version)
        self.assertEqual(package["version"], init_version)

    def test_bins_existen_y_no_hay_dependencias_runtime(self):
        package = _json("package.json")
        self.assertEqual(set(package["bin"]),
                         {"a2s", "a2s-control-plane", "a2s-agent-control-plane"})
        for relative in package["bin"].values():
            path = os.path.join(ROOT, relative)
            self.assertTrue(os.path.isfile(path), path)
            self.assertTrue(os.access(path, os.X_OK), path)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.readline().strip(), "#!/usr/bin/env node")
        self.assertNotIn("dependencies", package)
        self.assertNotIn("devDependencies", package)

    def test_instalacion_no_ejecuta_hooks_ocultos(self):
        scripts = _json("package.json")["scripts"]
        for unsafe_hook in ("install", "postinstall", "prepare", "preinstall"):
            self.assertNotIn(unsafe_hook, scripts)
        lock = _json("package-lock.json")
        self.assertEqual(set(lock["packages"]), {""})

    def test_runtime_conserva_gramatica_python39(self):
        for path in pathlib.Path(ROOT, "a2s").rglob("*.py"):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path),
                          feature_version=(3, 9))


class TestNpmLauncher(unittest.TestCase):
    def test_launcher_ejecuta_version_real(self):
        result = subprocess.run(
            ["node", "npm/bin/a2s.mjs", "--version"], cwd=ROOT,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("A²S 1.11.0", result.stdout)

    def test_launcher_informa_python_ausente_sin_stacktrace(self):
        with tempfile.TemporaryDirectory() as empty_path:
            env = dict(os.environ)
            env["PATH"] = empty_path
            env.pop("A2S_PYTHON", None)
            # Node se invoca por ruta absoluta antes de vaciar PATH para el hijo.
            node = shutil.which("node")
            self.assertIsNotNone(node)
            result = subprocess.run(
                [node, "npm/bin/a2s.mjs", "--version"], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requiere Python 3.9", result.stderr)
        self.assertNotIn(" at ", result.stderr)


if __name__ == "__main__":
    unittest.main()
