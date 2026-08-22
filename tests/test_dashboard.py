"""Control Plane industrial: activos, API, seguridad y parámetros de misión."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from a2s.dashboard import DashboardServer, EventHub, MissionManager, _asset


def request(url, method="GET", body=None, headers=None):
    raw = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=raw, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = response.read()
            return response.status, dict(response.headers), payload
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class FakeMissions:
    def __init__(self):
        self.started = None

    def snapshot(self):
        return {"running": False, "iterations": 0, "report": None,
                "events": [], "options": {}, "started_at": ""}

    def start(self, goal, demo, options=None):
        self.started = (goal, demo, options)
        return True, "misión iniciada"

    def stop(self):
        return True, "parada solicitada"


class TestMissionManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = MissionManager(EventHub(), self.tmp.name)

    def test_rechaza_objetivo_vacio_y_proveedor_invalido(self):
        self.assertEqual(self.manager.start("", False)[0], False)
        ok, message = self.manager.start("objetivo", False,
                                         {"provider": "servidor-arbitrario"})
        self.assertFalse(ok)
        self.assertIn("proveedor", message)

    def test_config_acota_parametros_y_no_ofrece_unsafe(self):
        cfg = self.manager._config({"provider": "pool", "max_time": 99999,
                                    "max_rounds": -5, "speculative": 99,
                                    "allow_network": False,
                                    "pool_strategy": "cost_first"})
        self.assertEqual(cfg.max_wall_seconds, 3600)
        self.assertEqual(cfg.max_rounds, 1)
        self.assertEqual(cfg.speculative_candidates, 8)
        self.assertFalse(cfg.allow_network)
        self.assertFalse(cfg.shell_unsafe)
        self.assertEqual(cfg.pool_strategy, "cost_first")

    def test_stop_sin_mision_es_conflicto(self):
        self.assertFalse(self.manager.stop()[0])


class TestDashboardHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dashboard = DashboardServer(port=0, workspace=self.tmp.name,
                                         auto_demo=False)
        self.dashboard.missions = FakeMissions()
        self.server = self.dashboard.make_http_server()
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_activos_industriales_y_urls_relativas(self):
        code, headers, html = request(self.base + "/")
        self.assertEqual(code, 200)
        self.assertIn(b"A\xc2\xb2S Control Plane", html)
        self.assertIn(b"MISSION CONTROL", html)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        code, _, js = request(self.base + "/app.js")
        self.assertEqual(code, 200)
        self.assertNotIn(b"127.0.0.1", js)
        self.assertNotIn(b"localhost", js)
        self.assertIn(b'EventSource("/api/events")', js)

    def test_health_y_state(self):
        code, _, body = request(self.base + "/healthz")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "ok")
        code, _, body = request(self.base + "/api/state")
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertTrue(data["system"]["stdlib_only"])
        self.assertFalse(data["running"])

    def test_start_transfiere_opciones_validadas_al_manager(self):
        payload = {"goal": "crear evidencia", "demo": False,
                   "options": {"provider": "pool", "max_time": 120,
                               "pool_strategy": "cost_first"}}
        code, _, body = request(self.base + "/api/start", "POST", payload)
        self.assertEqual(code, 202, body)
        goal, demo, options = self.dashboard.missions.started
        self.assertEqual(goal, "crear evidencia")
        self.assertFalse(demo)
        self.assertEqual(options["provider"], "pool")

    def test_post_rechaza_origen_cruzado(self):
        code, _, body = request(self.base + "/api/start", "POST",
                                {"goal": "x"}, {"Origin": "https://evil.example"})
        self.assertEqual(code, 403)
        self.assertIn("origen", json.loads(body)["error"])

    def test_knowledge_incluye_radar_oss(self):
        code, _, body = request(self.base + "/api/knowledge")
        self.assertEqual(code, 200)
        data = json.loads(body)
        repos = {p["repo"] for p in data["ecosystem"]["projects"]}
        self.assertIn("diegosouzapw/OmniRoute", repos)
        self.assertTrue(data["ecosystem"]["open_source_only"])
        self.assertFalse(data["ecosystem"]["code_executed"])


class TestDashboardAuth(unittest.TestCase):
    def test_api_protegida_admite_bearer_valido(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dash = DashboardServer(port=0, workspace=tmp.name, require_auth=True)
        dash.missions = FakeMissions()
        server = dash.make_http_server()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        code, _, _ = request(base + "/api/state")
        self.assertEqual(code, 401)
        token = dash.token_manager.issue(scope="dashboard", hours=1)
        code, _, body = request(base + "/api/state", headers={
            "Authorization": f"Bearer {token}"})
        self.assertEqual(code, 200, body)


class TestPackageAssets(unittest.TestCase):
    def test_todos_los_activos_empaquetados(self):
        for name in ("index.html", "app.css", "app.js", "favicon.svg"):
            self.assertGreater(len(_asset(name)), 100)


if __name__ == "__main__":
    unittest.main()
