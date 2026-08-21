"""Pruebas del modo SERVICIO experimental (RBAC real sobre HTTP), de la
fachada async pura-stdlib y del auditor ejecutable."""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from a2s.asyncapi import AsyncPool, demo_async, open_async_pool
from a2s.audit import run_audit
from a2s.provider_pool import PoolEndpoint, ProviderPool
from a2s.serve import ROLE_PERMS, ServeAPI, UserStore, make_server


def _req(url, method="GET", token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


class TestUserStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = UserStore(self.tmp.name)

    def test_add_y_verificar(self):
        info = self.store.add("ana", "operator")
        self.assertEqual(info["role"], "operator")
        user, role = self.store.authenticate(info["token"])
        self.assertEqual((user, role), ("ana", "operator"))

    def test_rol_invalido_rechazado(self):
        with self.assertRaises(ValueError):
            self.store.add("malo", "superuser")

    def test_token_basura_no_autentica(self):
        self.assertEqual(self.store.authenticate("no.soy.jwt"),
                         (None, None))


class TestRBACSobreHTTP(unittest.TestCase):
    """RBAC real: viewer denegado, operator ejecuta, admin administra,
    TODO auditado (denegaciones incluidas)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        ws = cls.tmp.name
        store = UserStore(ws)
        cls.tok_admin = store.add("root", "admin")["token"]
        cls.tok_op = store.add("ana", "operator")["token"]
        cls.tok_view = store.add("leo", "viewer")["token"]
        srv, api = make_server(ws, port=0)
        cls.port = srv.server_address[1]
        cls.api = api
        cls.srv = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_health_anonimo(self):
        code, out = _req(self.url("/health"))
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"])

    def test_sin_token_401(self):
        code, _ = _req(self.url("/api/status"))
        self.assertEqual(code, 401)

    def test_viewer_ve_estado_pero_no_puede_lanzar_misiones(self):
        code, out = _req(self.url("/api/status"), token=self.tok_view)
        self.assertEqual(code, 200)
        self.assertEqual(out["whoami"]["role"], "viewer")
        code, out = _req(self.url("/api/mission"), method="POST",
                         token=self.tok_view, body={"goal": "x"})
        self.assertEqual(code, 403)
        self.assertIn("mission.run", out["error"])

    def test_viewer_no_gestiona_usuarios(self):
        code, _ = _req(self.url("/api/users"), method="POST",
                       token=self.tok_view, body={"name": "x", "role": "admin"})
        self.assertEqual(code, 403)

    def test_operator_lanza_mision_y_ve_informe(self):
        code, out = _req(self.url("/api/mission"), method="POST",
                         token=self.tok_op,
                         body={"goal": "informe forense del workspace"})
        self.assertEqual(code, 202)
        mid = out["mission_id"]
        for _ in range(60):                       # espera la misión (hilo propio)
            code, st = _req(self.url(f"/api/mission/{mid}"), token=self.tok_op)
            self.assertEqual(code, 200)
            if st.get("status") in ("done", "error"):
                break
            time.sleep(0.2)
        self.assertEqual(st["status"], "done")
        self.assertIn(st["success"], (True, False))
        code, rep = _req(self.url(f"/api/report/{mid}"), token=self.tok_view)
        self.assertEqual(code, 200)

    def test_admin_crea_usuario_via_api(self):
        code, out = _req(self.url("/api/users"), method="POST",
                         token=self.tok_admin,
                         body={"name": "nuevo", "role": "viewer"})
        self.assertEqual(code, 201)
        self.assertTrue(out["token"].count("."), 2)
        # el nuevo usuario funciona de inmediato
        code, _ = _req(self.url("/api/status"), token=out["token"])
        self.assertEqual(code, 200)

    def test_aislamiento_por_usuario(self):
        code, out = _req(self.url("/api/mission"), method="POST",
                         token=self.tok_op, body={"goal": "crear archivo x"})
        self.assertEqual(code, 202)
        self.assertIn("u-ana", out["workspace"])
        self.assertTrue(os.path.isdir(os.path.join(
            self.tmp.name, "u-ana", ".a2s")))

    def test_toda_denegacion_queda_auditada(self):
        _req(self.url("/api/mission"), method="POST", token=self.tok_view,
             body={"goal": "x"})
        audit = open(os.path.join(self.tmp.name, ".a2s", "serve_audit.jsonl"),
                     encoding="utf-8").read()
        self.assertIn('"allowed": false', audit)
        self.assertIn('"user": "leo"', audit)


class TestAsyncFacade(unittest.TestCase):
    def _pool(self):
        def transport(ep, payload):
            user = payload["messages"][-1]["content"]
            return {"choices": [{"message": {"content": f"[{ep.name}] {user}"}}],
                    "usage": {}}
        eps = [PoolEndpoint(name=f"e{i}", base_url="http://x", api_key="k",
                            model="m", rpm=100) for i in range(2)]
        return ProviderPool(eps, transport=transport, strategy="round_robin")

    def test_fanout_async_igual_que_sync(self):
        import asyncio
        prompts = [f"tarea-{i}" for i in range(6)]
        sync = self._pool().fanout(prompts, max_parallel=4)
        apool = AsyncPool(self._pool())
        results = asyncio.run(apool.fanout(prompts, max_parallel=4))
        self.assertEqual(results, sync)
        self.assertTrue(all(r is not None for r in results))

    def test_chat_y_dag_async(self):
        import asyncio
        apool = open_async_pool(pool=self._pool())

        async def escenario():
            r = await apool.chat("hola", max_tokens=32)
            out = await demo_async(apool, ["a", "b", "c"])
            await apool.aclose()
            return r, out

        chat, demo = asyncio.run(escenario())
        self.assertIn("[e", chat)
        # round-robin determinista: chat consume e0 → fanout rota e1,e0,e1
        self.assertEqual(demo["fanout"], ["[e1] a", "[e0] b", "[e1] c"])
        self.assertEqual(demo["dag_executed"], 3)

    def test_event_loop_no_bloqueado(self):
        """Mientras fanout corre en hilos, el loop atiende otras corrutinas."""
        import asyncio
        apool = AsyncPool(self._pool())
        ticks = []

        async def reloj():
            for _ in range(6):
                ticks.append(time.monotonic())
                await asyncio.sleep(0.02)

        async def main():
            await asyncio.gather(reloj(), apool.fanout(["x"] * 8))

        asyncio.run(main())
        self.assertGreaterEqual(len(ticks), 5)    # el loop respiró


class TestAuditorVivo(unittest.TestCase):
    def test_audit_coherente(self):
        rep = run_audit()
        self.assertIn("nota_medible", rep)
        self.assertTrue(0 <= rep["nota_medible"] <= 5)
        nombres = {c["nombre"] for c in rep["checks"]}
        self.assertIn("pureza-stdlib", nombres)
        # el 6 no existe: escala 0-5 por contrato
        self.assertTrue(all(c["nota"] <= 5.0 for c in rep["checks"]))
        self.assertTrue(rep["no_medible_aqui"])


if __name__ == "__main__":
    unittest.main()


class TestOmniRouteIntegracion(unittest.TestCase):
    """OmniRoute como servicio local del operador (LIMITACIONES §16)."""

    def test_endpoint_omniroute_cuando_hay_gateway(self):
        from unittest import mock
        import a2s.provider_pool as pp
        with mock.patch.object(pp, "_local_service_alive", return_value=True), \
             mock.patch.dict(os.environ, {"A2S_OMNIROUTE_MODEL": "auto/cheap"}):
            eps = pp.discover_endpoints_from_env()
        omni = [e for e in eps if e.name == "omniroute-local"]
        self.assertEqual(len(omni), 1)
        e = omni[0]
        self.assertEqual(e.base_url, "http://127.0.0.1:20128/v1")
        self.assertEqual(e.model, "auto/cheap")
        self.assertEqual(e.cost_tier, "free")           # el gateway es local
        self.assertEqual(e.rpm, 0)                      # sus cuotas las gestiona él

    def test_sin_gateway_no_hay_endpoint(self):
        from unittest import mock
        import a2s.provider_pool as pp
        with mock.patch.object(pp, "_local_ollama_alive", return_value=False), \
             mock.patch.object(pp, "_local_service_alive", return_value=False):
            eps = pp.discover_endpoints_from_env()
        self.assertFalse([e for e in eps if e.name == "omniroute-local"])

    def test_url_personalizada_por_entorno(self):
        from unittest import mock
        import a2s.provider_pool as pp
        with mock.patch.dict(os.environ,
                             {"A2S_OMNIROUTE_URL": "http://127.0.0.1:20199/v1"}), \
             mock.patch.object(pp, "_local_service_alive", return_value=True):
            eps = pp.discover_endpoints_from_env()
        e = [x for x in eps if x.name == "omniroute-local"][0]
        self.assertIn(":20199", e.base_url)
