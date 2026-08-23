"""Crecimiento autónomo (AutoLearner): estudio continuo de repos públicos.

Hermetismo total: el tráfico GitHub se finge con un ``transport`` inyectado;
ningún test toca la red.
"""

import json
import os
import tempfile
import time
import unittest
from tests._winutil import temp_dir

from a2s.growth import DEFAULT_CURRICULUM, AutoLearner, autolearn_enabled
from a2s.learner import GitHubClient, Learner


def _fake_transport(url: str, headers: dict):
    """GitHub simulado: 1 repo por búsqueda + README con contenido real."""
    if "/search/repositories" in url:
        body = json.dumps({"items": [{
            "full_name": "acme/rate-limiter-demo",
            "html_url": "https://github.com/acme/rate-limiter-demo",
            "description": "Ventana deslizante de cuotas con Retry-After.",
            "stargazers_count": 123,
            "license": {"spdx_id": "MIT"},
            "updated_at": "2026-08-01T00:00:00Z",
        }]}).encode()
        return 200, {"X-RateLimit-Remaining": "9"}, body
    if url.endswith("/readme"):
        return 200, {}, (b"# Rate limiter\n\nVentana deslizante: guarda marcas "
                         b"de tiempo y expira las antiguas. Si el servidor responde "
                         b"429 con Retry-After, duerme exactamente esa cantidad.\n")
    return 404, {}, b"{}"


class _Hub:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class TestAutoLearner(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.ws = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.hub = _Hub()
        self.growth = AutoLearner(self.ws, hub=self.hub, interval_seconds=30)
        # Learner sin pool (resumen extractivo stdlib) y GitHub fingido.
        self.growth._make_learner = lambda: Learner(
            self.ws, pool=None,
            github=GitHubClient(transport=_fake_transport, sleep_fn=lambda s: None),
            repos_per_cycle=1)

    def tearDown(self):
        self.growth.stop()

    def test_ciclo_destila_y_persiste_ficha(self):
        info = self.growth.cycle_once(query="rate limit retry-after")
        self.assertEqual(info["new_cards"], ["acme/rate-limiter-demo"])
        self.assertEqual(info["cards_total"], 1)
        self.assertNotIn("error", info)
        # Ficha en disco y bitácora de crecimiento.
        self.assertTrue(os.path.isdir(os.path.join(self.ws, ".a2s", "knowledge")))
        log = os.path.join(self.ws, ".a2s", "growth_log.json")
        self.assertTrue(os.path.isfile(log))
        with open(log, encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)), 1)
        # El dashboard lo vería por SSE.
        self.assertEqual(self.hub.events[-1]["event"], "growth_cycle")
        self.assertTrue(self.hub.events[-1]["success"])

    def test_no_duplica_fichas_en_el_segundo_ciclo(self):
        self.growth.cycle_once(query="rate limit")
        info = self.growth.cycle_once(query="rate limit")
        self.assertEqual(info["new_cards"], [])
        self.assertEqual(info["cards_total"], 1)

    def test_cola_del_operador_tiene_prioridad(self):
        ruta = os.path.join(self.ws, ".a2s", "growth_queue.txt")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("# comentario ignorado\nfirmas digitales hmac\n")
        queries = self.growth.queries()
        self.assertEqual(queries[0], "firmas digitales hmac")
        self.assertIn(DEFAULT_CURRICULUM[0], queries)

    def test_el_fallo_de_red_no_rompe_el_ciclo(self):
        def roto(url, headers):
            raise OSError("sin red")
        self.growth._make_learner = lambda: Learner(
            self.ws, pool=None,
            github=GitHubClient(transport=roto, sleep_fn=lambda s: None),
            repos_per_cycle=1)
        info = self.growth.cycle_once(query="lo que sea")
        self.assertIn("error", info)          # honesto…
        self.assertEqual(self.growth.cycles, 1)  # …pero el sistema sigue vivo

    def test_arranca_y_estudia_en_segundo_plano(self):
        self.growth.start()
        limite = time.time() + 10
        while self.growth.cycles < 1 and time.time() < limite:
            time.sleep(0.05)
        self.growth.stop()
        self.assertGreaterEqual(self.growth.cycles, 1)
        snap = self.growth.snapshot()
        self.assertEqual(snap["cycles"], self.growth.cycles)
        self.assertFalse(snap["active"])

    def test_el_primer_ciclo_es_inmediato(self):
        """'Al abrirlo ya se pone a estudiar': sin esperar el intervalo."""
        self.growth.stop()
        growth = AutoLearner(self.ws, interval_seconds=3600)
        growth._make_learner = lambda: Learner(
            self.ws, pool=None,
            github=GitHubClient(transport=_fake_transport, sleep_fn=lambda s: None),
            repos_per_cycle=1)
        growth.start()
        try:
            limite = time.time() + 10
            while growth.cycles < 1 and time.time() < limite:
                time.sleep(0.05)
            self.assertGreaterEqual(growth.cycles, 1)
        finally:
            growth.stop()


class TestInterruptorGlobal(unittest.TestCase):
    def test_activado_por_defecto(self):
        anterior = os.environ.pop("A2S_AUTO_LEARN", None)
        try:
            self.assertTrue(autolearn_enabled())
        finally:
            if anterior is not None:
                os.environ["A2S_AUTO_LEARN"] = anterior

    def test_se_apaga_con_cero(self):
        anterior = os.environ.get("A2S_AUTO_LEARN")
        os.environ["A2S_AUTO_LEARN"] = "0"
        try:
            self.assertFalse(autolearn_enabled())
        finally:
            if anterior is None:
                os.environ.pop("A2S_AUTO_LEARN", None)
            else:
                os.environ["A2S_AUTO_LEARN"] = anterior


if __name__ == "__main__":
    unittest.main()
