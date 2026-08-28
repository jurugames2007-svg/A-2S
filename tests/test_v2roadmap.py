"""Pruebas de los guardianes meta (pureza stdlib, complejidad, CI, roadmap)
y de las capacidades nuevas: BM25, notificaciones y unlearning."""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from a2s.learner import GitHubClient, Learner, _frescura, load_cards, save_card
from a2s.learner import KnowledgeCard
from a2s.notify import notify
from a2s.search import BM25Index, Doc, tokeniza, workspace_search

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestGuardianesMeta(unittest.TestCase):
    """El roadmap v2 como contrato ejecutable (tranche 1)."""

    def test_pureza_stdlib(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, "tools/check_purity.py"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_guardian_cc(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, "tools/check_cc.py", "35"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("media", r.stdout)

    def test_refactor_execute_dag_bajo_umbral(self):
        """La función refactorizada debe quedar por debajo del ratchet."""
        import ast
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from check_cc import cc_de
        with open(os.path.join(ROOT, "a2s", "provider_pool.py"),
                  encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        ccs = {n.name: cc_de(n) for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "execute_dag"}
        self.assertLessEqual(ccs["execute_dag"], 20)   # era 31

    def test_ci_y_roadmap_comprometidos(self):
        workflow = os.path.join(ROOT, "tools", "ci", "ci.yml")
        self.assertTrue(os.path.isfile(workflow))
        with open(workflow, encoding="utf-8") as fh:
            ci = fh.read()
        self.assertIn("python -m unittest discover -s tests -v", ci)
        self.assertIn("python tools/check_purity.py", ci)
        self.assertIn("python -m pip wheel", ci)
        self.assertIn("npm-package-e2e", ci)
        self.assertIn("windows-latest", ci)
        self.assertIn("npm run test:npm", ci)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "ROADMAP_V2.md")))
        with open(os.path.join(ROOT, "ROADMAP_V2.md"), encoding="utf-8") as fh:
            self.assertIn("Tranche 1", fh.read())


class TestBM25(unittest.TestCase):
    def _idx(self):
        docs = [
            Doc("d1", "extraer metadatos EXIF de imágenes con pillow", "episodio", "1"),
            Doc("d2", "calcular hashes sha256 de la evidencia forense", "episodio", "2"),
            Doc("d3", "resumir documento con modelo de lenguaje", "episodio", "3"),
            Doc("d4", "metadatos EXIF librería exif-py para fotografías", "episodio", "4"),
        ]
        return BM25Index(docs)

    def test_ranking_relevancia(self):
        idx = self._idx()
        hits = idx.search("metadatos EXIF de imágenes", top=3)
        self.assertTrue(hits)
        ids = [d.doc_id for d, _ in hits]
        self.assertEqual(set(ids[:2]), {"d1", "d4"})   # los EXIF dominan

    def test_consulta_sin_cohesion_no_match(self):
        self.assertEqual(self._idx().search("quantum zorblax"), [])

    def test_tokeniza_normaliza_acentos_y_quita_stopwords(self):
        toks = tokeniza("La ejecución DE la misión")
        self.assertEqual(toks, ["ejecucion", "mision"])

    def test_workspace_search_con_fichas_y_pool(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name
        c = KnowledgeCard(id="card-x", topic="pdf metadatos", query="pdf",
                          repo="pdf/pikepdf", url="http://x", license="MPL-2.0",
                          summary="extraer metadatos de PDF", recipe="pikepdf.open")
        save_card(c, ws)
        os.makedirs(os.path.join(ws, ".a2s", "pool"))
        with open(os.path.join(ws, ".a2s", "pool", "state.json"), "w") as fh:
            json.dump({"endpoints": {"groq": {"total": 9, "ok": 9,
                                              "rate_limited": 2}}},
                      fh)
        hits = workspace_search(ws, "metadatos pdf extraer", top=5)
        self.assertTrue(any(d.doc_id == "ficha:pdf/pikepdf" for d, _ in hits))
        solo_fichas = workspace_search(ws, "metadatos", top=5, origenes={"ficha"})
        self.assertTrue(all(d.origen == "ficha" for d, _ in solo_fichas))


class TestNotify(unittest.TestCase):
    def test_file_sink(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "eventos.jsonl")
        res = notify([f"file:{path}"], "prueba", "cuerpo", nivel="warn")
        self.assertIn("→ ok", res[0])
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["asunto"], "prueba")
        self.assertEqual(data["nivel"], "warn")

    def test_esquema_no_soportado_no_explota(self):
        res = notify(["sms:+569..."], "x", "y")
        self.assertIn("esquema no soportado", res[0])

    def test_webhook_real(self):
        recibido = []

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                recibido.append(json.loads(self.rfile.read(n) or b"{}"))
                out = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            res = notify([f"webhook:http://127.0.0.1:{port}/hook"],
                         "misión", "cuerpo del evento")
            self.assertIn("HTTP 200", res[0])
            self.assertEqual(recibido[0]["asunto"], "misión")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_errores_son_best_effort(self):
        res = notify(["webhook:http://127.0.0.1:1/nope"], "x", "y")
        self.assertIn("ERROR", res[0])            # no lanzó


class TestUnlearning(unittest.TestCase):
    def _card(self, ws, nombre, dias, used, wins):
        c = KnowledgeCard(
            id=f"card-{nombre}", topic="t", query="q", repo=f"org/{nombre}",
            url="http://x", license="MIT", summary="s", recipe="r",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                     time.gmtime(time.time() - dias * 86400)),
            used=used, wins=wins)
        save_card(c, ws)
        return c

    def test_prune_olvida_perdedoras_viejas(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name
        self._card(ws, "perdedora", dias=120, used=8, wins=0)     # pierde siempre
        self._card(ws, "ganadora", dias=120, used=8, wins=7)      # conserva
        self._card(ws, "nova", dias=1, used=8, wins=0)            # joven: conserva
        self._card(ws, "sinuso", dias=120, used=0, wins=0)        # sin datos: conserva
        lr = Learner(workspace=ws, github=GitHubClient(token="x"))
        self.assertEqual(len(lr.cards), 4)
        olvidadas = lr.prune()
        self.assertEqual(olvidadas, ["org/perdedora"])
        self.assertEqual(len(lr.cards), 3)
        self.assertEqual({c.repo for c in load_cards(ws)},
                         {"org/ganadora", "org/nova", "org/sinuso"})

    def test_frescura_decae(self):
        self.assertAlmostEqual(_frescura(time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())), 1.0, places=3)
        vieja = _frescura("2020-01-01T00:00:00Z")
        self.assertLess(vieja, 0.01)

    def test_ranking_prioriza_fresca_con_mismo_winrate(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name
        self._card(ws, "vieja", dias=400, used=6, wins=6)
        self._card(ws, "fresca", dias=1, used=6, wins=6)
        lr = Learner(workspace=ws, github=GitHubClient(token="x"))
        ctx = lr.knowledge_context(topic_like="")
        self.assertIn("org/fresca", ctx)
        # la vieja pierde prioridad: aparece después en el contexto
        self.assertLess(ctx.index("org/fresca"), ctx.index("org/vieja"))


class TestDecayEstrategias(unittest.TestCase):
    def test_decay_anti_popularidad_al_cargar(self):
        from a2s.memory import MemoryHub, Strategy
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        mem = MemoryHub(tmp.name, "(test)")
        # simulamos historia enorme persistida
        for name in ("explorar", "documentar"):
            mem.strategies[name] = Strategy(name, "d", used=90, wins=80, fails=10)
        mem._save_strategies()
        # al recargar con historia >50, los contadores se reducen a la mitad
        mem2 = MemoryHub(tmp.name, "(test2)")
        s = mem2.strategies["explorar"]
        self.assertLessEqual(s.used, 46)          # (90+1)//2
        self.assertEqual(s.wins, 40)              # 80//2


if __name__ == "__main__":
    unittest.main()
