"""Contratos de la distribución npm y del launcher multiplataforma."""

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

    def test_bins_existen_y_omniroute_es_dependencia_fijada(self):
        package = _json("package.json")
        self.assertEqual(set(package["bin"]),
                         {"a2s", "a2s-control-plane", "a2s-agent-control-plane"})
        for relative in package["bin"].values():
            path = os.path.join(ROOT, relative)
            self.assertTrue(os.path.isfile(path), path)
            self.assertTrue(os.access(path, os.X_OK), path)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.readline().strip(), "#!/usr/bin/env node")
        self.assertEqual(package["dependencies"], {"omniroute": "3.8.49"})
        self.assertNotIn("devDependencies", package)
        self.assertIn(">=22.22.2", package["engines"]["node"])

    def test_instalacion_delega_setup_nativo_en_omniroute(self):
        # A²S no oculta un hook propio. npm sí ejecuta el postinstall publicado
        # por OmniRoute para dejar sus módulos nativos listos en cada plataforma.
        scripts = _json("package.json")["scripts"]
        for hidden_hook in ("install", "postinstall", "prepare", "preinstall"):
            self.assertNotIn(hidden_hook, scripts)
        lock = _json("package-lock.json")
        self.assertEqual(lock["packages"][""]["dependencies"],
                         {"omniroute": "3.8.49"})
        omni = lock["packages"]["node_modules/omniroute"]
        self.assertEqual(omni["version"], "3.8.49")
        self.assertTrue(omni["hasInstallScript"])
        self.assertEqual(omni["bin"]["omniroute"], "bin/omniroute.mjs")
        self.assertTrue(omni.get("integrity", "").startswith("sha512-"))

    def test_runtime_conserva_gramatica_python39(self):
        for path in pathlib.Path(ROOT, "a2s").rglob("*.py"):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path),
                          feature_version=(3, 9))

    def test_gateway_evade_cli_src_y_supervisa_bundle_dist(self):
        runtime = pathlib.Path(ROOT, "npm", "lib", "omniroute.mjs").read_text(
            encoding="utf-8")
        launcher = pathlib.Path(ROOT, "npm", "bin", "a2s.mjs").read_text(
            encoding="utf-8")
        scripts = _json("package.json")["scripts"]
        self.assertIn("dist/server-ws.mjs", runtime)
        self.assertIn("dist/server.js", runtime)
        self.assertNotIn("bin/omniroute.mjs", runtime)
        self.assertNotIn("tsx/esm", runtime)
        self.assertIn("setInterval", launcher)
        self.assertNotIn("omniroute serve", scripts["gateway"])


class _OmniCatalogHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — contrato de BaseHTTPRequestHandler
        if self.path != "/v1/models":
            self.send_error(404)
            return
        body = b'{"object":"list","data":[{"id":"auto"}]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


class TestNpmLauncher(unittest.TestCase):
    def test_launcher_ejecuta_version_real(self):
        with open(os.path.join(ROOT, "a2s", "__init__.py"),
                  encoding="utf-8") as fh:
            version = re.search(r'^__version__ = "([^"]+)"', fh.read(),
                                re.M).group(1)
        result = subprocess.run(
            ["node", "npm/bin/a2s.mjs", "--version"], cwd=ROOT,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"A²S {version}", result.stdout)

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

    def test_gateway_detectado_se_inyecta_sin_elegir_proveedor(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _OmniCatalogHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = dict(os.environ)
            env.pop("A2S_OMNIROUTE", None)
            env.pop("A2S_OMNIROUTE_URL", None)
            env["OMNIROUTE_PORT"] = str(server.server_address[1])
            script = (
                'import { ensureOmniRoute } from "./npm/lib/omniroute.mjs"; '
                "const result = await ensureOmniRoute({timeoutMs: 1000}); "
                "console.log(JSON.stringify({result, url: process.env.A2S_OMNIROUTE_URL, "
                "managed: process.env.A2S_OMNIROUTE_MANAGED}));"
            )
            result = subprocess.run(
                ["node", "--input-type=module", "--eval", script], cwd=ROOT,
                env=env, capture_output=True, text=True, timeout=10)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"]["state"], "ready")
        self.assertFalse(payload["result"]["started"])
        self.assertEqual(payload["url"],
                         f"http://127.0.0.1:{server.server_address[1]}/v1")
        self.assertEqual(payload["managed"], "1")

    def test_gateway_solo_arranca_para_comandos_de_razonamiento(self):
        script = (
            'import { shouldEnsureOmniRoute as check } from "./npm/lib/omniroute.mjs"; '
            "console.log(JSON.stringify([check(['run','x']), check(['update']), "
            "check(['--version']), check(['run','x','--provider=heuristic'])]));"
        )
        env = dict(os.environ)
        env.pop("A2S_OMNIROUTE", None)
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script], cwd=ROOT,
            env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), [True, False, False, False])

    def test_gateway_puede_desactivarse_explicitamente(self):
        env = {**os.environ, "A2S_OMNIROUTE": "off"}
        script = (
            'import { ensureOmniRoute } from "./npm/lib/omniroute.mjs"; '
            "console.log(JSON.stringify(await ensureOmniRoute({timeoutMs: 1})));"
        )
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script], cwd=ROOT,
            env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
