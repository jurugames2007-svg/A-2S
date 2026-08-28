"""Catálogo curado de recursos (v1.21+): integridad, búsqueda, CLI, API y memoria."""

import argparse
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request

from a2s.cli import main
from a2s.recursos import (AVISO_ETICO, CATEGORIAS, ENTRADAS, api_snapshot,
                          buscar, categorias, comprobar_enlaces, como_html,
                          como_markdown, como_pdf, como_pptx, docs_memoria,
                          entradas, estado_check, extras, extra_add,
                          extra_forget, guardar_check, validar)
from a2s.search import workspace_search


class TestCatalogo(unittest.TestCase):
    def test_seis_categorias_con_recuentos(self):
        cats = categorias()
        self.assertEqual([c["id"] for c in cats],
                         [c["id"] for c in CATEGORIAS])
        self.assertEqual(sum(c["count"] for c in cats), len(ENTRADAS))
        self.assertGreater(len(ENTRADAS), 50)

    def test_integridad_ids_urls_y_categorias(self):
        self.assertEqual(validar(), [])

    def test_todas_las_entradas_tienen_nota_y_categoria(self):
        nombres = {c["nombre"] for c in CATEGORIAS}
        for e in entradas():
            self.assertTrue(e["nombre"].strip())
            self.assertTrue(e["desc"].strip())
            self.assertIn(e["categoria"], nombres)
            if e["url"]:
                self.assertTrue(e["url"].startswith(("http://", "https://")))

    def test_entradas_filtradas_por_categoria_id_y_nombre(self):
        self.assertEqual(len(entradas("ciber")),
                         sum(1 for e in ENTRADAS if e["cat"] == "ciber"))
        # el nombre de la categoría (con acento) también filtra
        self.assertEqual(len(entradas("Ciberseguridad")),
                         sum(1 for e in ENTRADAS if e["cat"] == "ciber"))
        self.assertEqual(entradas("no-existe"), [])


class TestBuscar(unittest.TestCase):
    def test_busqueda_por_herramienta(self):
        rows = buscar("ghidra")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["id"], "ghidra")
        self.assertIn("score", rows[0])

    def test_busqueda_por_concepto(self):
        rows = buscar("vulnerabilidades en contenedores")
        ids = {r["id"] for r in rows}
        self.assertIn("trivy", ids)

    def test_busqueda_por_etiqueta(self):
        rows = buscar("vpn")
        ids = {r["id"] for r in rows}
        self.assertTrue({"veepn", "algo"} & ids or "veepn" in ids)

    def test_sin_consulta_no_devuelve_nada(self):
        self.assertEqual(buscar(""), [])
        self.assertEqual(buscar("   "), [])


class TestMarkdown(unittest.TestCase):
    def test_export_markdown_cubre_todo_el_catalogo(self):
        md = como_markdown()
        self.assertIn("# Catálogo de recursos A²S", md)
        self.assertIn(AVISO_ETICO, md)
        for c in CATEGORIAS:
            self.assertIn(c["nombre"], md)
        for e in ENTRADAS:
            self.assertIn(e["nombre"], md)
            if e["url"]:
                self.assertIn(f"]({e['url']})", md)


class TestCli(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_cli_completo(self):
        code, out = self._run("recursos")
        self.assertEqual(code, 0)
        self.assertIn(f"{len(ENTRADAS)} entradas en 6 categorías", out)
        self.assertIn(AVISO_ETICO, out)
        self.assertIn("Ghidra", out)
        self.assertIn("https://github.com/NationalSecurityAgency/ghidra", out)

    def test_cli_json(self):
        code, out = self._run("recursos", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["total"], len(ENTRADAS))
        self.assertEqual(len(data["recursos"]), len(ENTRADAS))
        self.assertEqual(len(data["categorias"]), 6)
        self.assertEqual(data["aviso"], AVISO_ETICO)

    def test_cli_categoria_y_busqueda(self):
        code, out = self._run("recursos", "--categoria", "ciber", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["recursos"])
        self.assertTrue(all(r["cat"] == "ciber" for r in data["recursos"]))

        code, out = self._run("recursos", "--buscar", "wireguard", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["consulta"], "wireguard")
        self.assertTrue(data["recursos"])
        self.assertEqual(data["recursos"][0]["id"], "algo")

    def test_cli_md(self):
        code, out = self._run("recursos", "--md")
        self.assertEqual(code, 0)
        self.assertEqual(out, como_markdown() + "\n")  # print añade \n final


class TestApiDashboard(unittest.TestCase):
    def setUp(self):
        from tests.test_dashboard import FakeMissions, request
        from a2s.dashboard import DashboardServer

        self.request = request
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dashboard = DashboardServer(port=0, workspace=self.tmp.name,
                                         auto_demo=False)
        self.dashboard.missions = FakeMissions()
        self.server = self.dashboard.make_http_server()
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _get(self, path):
        code, _headers, body = self.request(self.base + path)
        return code, json.loads(body)

    def test_api_recursos_completa(self):
        code, data = self._get("/api/recursos")
        self.assertEqual(code, 200)
        self.assertEqual(data["total"], len(ENTRADAS))
        self.assertEqual(len(data["recursos"]), len(ENTRADAS))
        self.assertEqual(data["aviso"], AVISO_ETICO)

    def test_api_recursos_busqueda_y_categoria(self):
        code, data = self._get("/api/recursos?q=ghidra")
        self.assertEqual(code, 200)
        self.assertTrue(data["recursos"])
        self.assertEqual(data["recursos"][0]["id"], "ghidra")

        code, data = self._get("/api/recursos?cat=empleo")
        self.assertEqual(code, 200)
        self.assertTrue(all(r["cat"] == "empleo" for r in data["recursos"]))
        self.assertEqual(len(data["recursos"]),
                         sum(1 for e in ENTRADAS if e["cat"] == "empleo"))


class TestMemoriaBM25(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)

    def test_recursos_participan_en_workspace_search(self):
        hits = workspace_search(self.tmp.name, "descompilador inversa ghidra",
                                top=5)
        self.assertTrue(hits)
        origenes = {doc.origen for doc, _ in hits}
        self.assertIn("recurso", origenes)

    def test_filtro_por_origen_recurso(self):
        hits = workspace_search(self.tmp.name, "vulnerabilidades", top=10,
                                origenes={"recurso"})
        for doc, _ in hits:
            self.assertEqual(doc.origen, "recurso")
            self.assertTrue(doc.doc_id.startswith("recurso:"))

    def test_docs_memoria_unicos(self):
        ids = [d.doc_id for d in docs_memoria()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), len(ENTRADAS))


class TestRecursosPropios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.ws = self.tmp.name

    def test_add_persiste_y_aparece_en_todas_las_vistas(self):
        entry = extra_add(self.ws, "Mi curso de pentest",
                          "https://ejemplo.local/curso", "ciber",
                          desc="Curso propio del operador",
                          tags=["pentest", "propio"])
        self.assertEqual(entry["id"], "mi-curso-de-pentest")
        self.assertTrue(entry["custom"])
        # persiste en disco (otra llamada lo ve)
        self.assertEqual([r["id"] for r in extras(self.ws)], [entry["id"]])
        # CLI/visibles
        self.assertEqual(len(entradas(workspace=self.ws)), len(ENTRADAS) + 1)
        self.assertEqual(api_snapshot(workspace=self.ws)["total"],
                         len(ENTRADAS) + 1)
        self.assertIn("Mi curso de pentest", como_markdown(self.ws))
        self.assertIn("Mi curso de pentest", como_html(self.ws))
        self.assertEqual(len(docs_memoria(self.ws)), len(ENTRADAS) + 1)
        # búsqueda lo encuentra
        rows = buscar("curso pentest", workspace=self.ws)
        self.assertIn("mi-curso-de-pentest", {r["id"] for r in rows})

    def test_add_valida_nombre_categoria_y_url(self):
        with self.assertRaises(ValueError):
            extra_add(self.ws, "", "https://x.y", "ia")
        with self.assertRaises(ValueError):
            extra_add(self.ws, "X", "https://x.y", "no-existe")
        with self.assertRaises(ValueError):
            extra_add(self.ws, "X", "ftp://x.y", "ia")

    def test_ids_unicos_y_forget(self):
        a = extra_add(self.ws, "Herramienta Alfa", "https://a.b/1", "dev")
        b = extra_add(self.ws, "Herramienta Alfa", "https://a.b/2", "dev")
        self.assertNotEqual(a["id"], b["id"])
        self.assertTrue(extra_forget(self.ws, a["id"]))
        self.assertEqual([r["id"] for r in extras(self.ws)], [b["id"]])
        # los del catálogo base no se olvidan
        self.assertFalse(extra_forget(self.ws, "ghidra"))

    def test_cli_add_extra_forget(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "add", "Herramienta Beta",
                         "https://beta.local", "--cat", "ciber",
                         "--workspace", self.ws, "--tags", "a, b"])
        self.assertEqual(code, 0)
        self.assertIn("recurso añadido", buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "extra", "--workspace", self.ws])
        self.assertEqual(code, 0)
        self.assertIn("Herramienta Beta", buf.getvalue())
        ident = extras(self.ws)[0]["id"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "forget", ident, "--workspace", self.ws])
        self.assertEqual(code, 0)
        self.assertEqual(extras(self.ws), [])


class TestCheckEnlaces(unittest.TestCase):
    def setUp(self):
        import http.server

        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        with open(os.path.join(self.tmp.name, "ok.txt"), "w") as fh:
            fh.write("ok")

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

        self.srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            lambda *a, **kw: Handler(*a, directory=self.tmp.name, **kw))
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(self.srv.server_close)

    def test_estado_latencia_y_fallos(self):
        base = f"http://127.0.0.1:{self.port}"
        rows = [{"id": "ok", "cat": "ia", "nombre": "Ok",
                 "url": f"{base}/ok.txt", "desc": "", "tags": ()},
                {"id": "nf", "cat": "ia", "nombre": "Falta",
                 "url": f"{base}/no-existe", "desc": "", "tags": ()},
                {"id": "down", "cat": "ia", "nombre": "Caído",
                 "url": "http://127.0.0.1:1/x", "desc": "", "tags": ()},
                {"id": "sin", "cat": "ia", "nombre": "Sin enlace",
                 "url": "", "desc": "", "tags": ()}]
        results = comprobar_enlaces(rows, timeout=5)
        by_id = {r["id"]: r for r in results}
        self.assertTrue(by_id["ok"]["ok"])
        self.assertEqual(by_id["ok"]["estado"], "HTTP 200")
        self.assertGreaterEqual(by_id["ok"]["ms"], 0)
        self.assertFalse(by_id["nf"]["ok"])
        self.assertEqual(by_id["nf"]["estado"], "HTTP 404")
        self.assertFalse(by_id["down"]["ok"])
        self.assertTrue(by_id["sin"]["sin_enlace"])

    def test_cli_check(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--check",
                         "--id", "kaspersky-cybermap",
                         "--timeout", "3", "--workspace", "/tmp"])
        out = buf.getvalue()
        self.assertIn("enlaces alcanzables", out)
        self.assertIn("Kaspersky Cyberthreat Map", out)
        self.assertIn(code, (0, 1))


class TestHtml(unittest.TestCase):
    def test_html_autocontenido(self):
        html = como_html()
        self.assertIn("<!doctype html>", html)
        self.assertIn(AVISO_ETICO, html)
        self.assertIn("Ghidra", html)
        self.assertIn("https://github.com/NationalSecurityAgency/ghidra", html)
        self.assertIn("ADVERTIDO", html)
        self.assertIn("id=\"q\"", html)  # buscador inline

    def test_cli_html_escribe_archivo(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        ruta = os.path.join(tmp.name, "out", "recursos.html")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--html", ruta])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(ruta))
        content = open(ruta, encoding="utf-8").read()
        self.assertIn("Catálogo de recursos", content)


class TestChatRecursos(unittest.TestCase):
    def test_responde_con_entradas_del_catalogo(self):
        from a2s.chat import HeuristicAssistant
        answer = HeuristicAssistant().reply(
            [{"role": "user", "content": "¿dónde aprendo reverse engineering?"}])
        self.assertIn("Ghidra", answer)
        self.assertIn("Recursos", answer)

    def test_sin_coincidencias_ofrece_el_panel(self):
        from a2s.chat import HeuristicAssistant
        answer = HeuristicAssistant().reply(
            [{"role": "user", "content": "recursos para zzzqqq xyzabc"}])
        self.assertIn("catálogo", answer.lower())


class TestApiRecursosDashboard(unittest.TestCase):
    def setUp(self):
        from tests.test_dashboard import FakeMissions, request
        from a2s.dashboard import DashboardServer

        self.request = request
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dashboard = DashboardServer(port=0, workspace=self.tmp.name,
                                         auto_demo=False)
        self.dashboard.missions = FakeMissions()
        self.server = self.dashboard.make_http_server()
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _api(self, path, method="GET", body=None):
        code, _headers, payload = self.request(self.base + path,
                                               method=method, body=body)
        return code, json.loads(payload)

    def test_post_add_y_get_muestra_recurso_propio(self):
        code, data = self._api("/api/recursos", method="POST",
                               body={"nombre": "Curso del evento",
                                     "url": "https://evento.local/curso",
                                     "cat": "ciber",
                                     "desc": "Añadido desde el panel"})
        self.assertEqual(code, 201)
        self.assertTrue(data["recurso"]["custom"])
        code, data = self._api("/api/recursos")
        self.assertEqual(code, 200)
        self.assertEqual(data["total"], len(ENTRADAS) + 1)
        propios = [r for r in data["recursos"] if r.get("custom")]
        self.assertEqual(len(propios), 1)
        self.assertEqual(propios[0]["nombre"], "Curso del evento")

    def test_post_invalido_da_400(self):
        code, data = self._api("/api/recursos", method="POST",
                               body={"nombre": "", "url": "https://x.y"})
        self.assertEqual(code, 400)
        self.assertIn("error", data)


class TestCheckEstado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.ws = self.tmp.name

    def _results(self):
        return [
            {"id": "a", "url": "https://a.b", "nombre": "A",
             "ok": True, "estado": "HTTP 200", "ms": 5, "sin_enlace": False},
            {"id": "b", "url": "https://c.d", "nombre": "B",
             "ok": False, "estado": "HTTP 500", "ms": 40, "sin_enlace": False},
            {"id": "s", "url": "", "nombre": "S",
             "ok": False, "estado": "sin enlace", "ms": None,
             "sin_enlace": True},
        ]

    def test_guardar_estado_roundtrip(self):
        data = guardar_check(self.ws, self._results(), timeout=4.0)
        self.assertEqual(data["ok"], 1)
        self.assertEqual(data["total"], 2)  # sin_enlace no cuenta
        est = estado_check(self.ws)
        self.assertEqual(est["ok"], 1)
        self.assertIn("a", est["results"])
        # api_snapshot lo expone al dashboard
        self.assertEqual(api_snapshot(workspace=self.ws)["check"]["total"], 2)

    def test_estado_vacio(self):
        self.assertIsNone(estado_check(self.ws))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--estado", "--workspace", self.ws])
        self.assertEqual(code, 1)
        self.assertIn("sin chequeo todavía", buf.getvalue())

    def test_estado_con_resultados(self):
        guardar_check(self.ws, self._results())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--estado", "--workspace", self.ws])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("1/2 alcanzables", out)
        self.assertIn("HTTP 500", out)

    def test_exports_incluyen_nota_de_check(self):
        guardar_check(self.ws, [
            {"id": "ghidra", "url": "https://github.com/NationalSecurityAgency/ghidra",
             "ok": True, "estado": "HTTP 200", "ms": 5, "sin_enlace": False},
            {"id": "vault", "url": "https://github.com/hashicorp/vault",
             "ok": False, "estado": "HTTP 500", "ms": 9, "sin_enlace": False},
        ])
        self.assertIn("HTTP 200", como_markdown(self.ws))
        self.assertIn("HTTP 500", como_markdown(self.ws))
        self.assertIn("sel check fail", como_html(self.ws))
        self.assertIn("sel check ok", como_html(self.ws))


class TestPdf(unittest.TestCase):
    def test_como_pdf_produce_pdf_valido(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        ruta = os.path.join(tmp.name, "cat.pdf")
        pages = como_pdf(ruta)
        self.assertGreaterEqual(pages, 1)
        self.assertTrue(open(ruta, "rb").read(8).startswith(b"%PDF"))

    def test_cli_pdf(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        ruta = os.path.join(tmp.name, "sub", "cat.pdf")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--pdf", ruta, "--workspace", "/tmp"])
        self.assertEqual(code, 0)
        self.assertIn("PDF exportado", buf.getvalue())
        self.assertTrue(os.path.isfile(ruta))


class TestCheckParalelo(unittest.TestCase):
    def setUp(self):
        import http.server

        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        with open(os.path.join(self.tmp.name, "ok.txt"), "w") as fh:
            fh.write("ok")
        open(os.path.join(self.tmp.name, "lento.txt"), "w").write("lento")

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                if self.path == "/lento.txt":
                    import time
                    time.sleep(0.3)
                return super().do_GET()

        self.srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            lambda *a, **kw: Handler(*a, directory=self.tmp.name, **kw))
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(self.srv.server_close)

    def _rows(self):
        base = f"http://127.0.0.1:{self.port}"
        return [{"id": f"e{i}", "cat": "ia", "nombre": f"E{i}",
                 "url": f"{base}/ok.txt" if i % 2 == 0
                 else f"{base}/lento.txt",
                 "desc": "", "tags": ()} for i in range(6)]

    def test_paralelo_mantiene_orden_y_resultados(self):
        import time
        t0 = time.monotonic()
        results = comprobar_enlaces(self._rows(), timeout=5, workers=4)
        total = time.monotonic() - t0
        self.assertEqual([r["id"] for r in results],
                         [f"e{i}" for i in range(6)])
        self.assertTrue(all(r["ok"] for r in results))
        # 6 URLs con 3 lentas (0.3s) y 4 workers: < 3 oleadas secuenciales
        self.assertLess(total, 1.5)

    def test_secuencial_reproducible(self):
        results = comprobar_enlaces(self._rows()[:2], timeout=5, workers=0)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["ok"] for r in results))


class TestPpt(unittest.TestCase):
    def _deck(self, ws, ruta):
        n = como_pptx(ruta, workspace=ws)
        self.assertGreaterEqual(n, 8)
        self.assertTrue(open(ruta, "rb").read(2) == b"PK")
        return n

    def test_como_pptx_valido(self):
        import zipfile
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        ruta = os.path.join(tmp.name, "deck.pptx")
        n = self._deck(tmp.name, ruta)
        with zipfile.ZipFile(ruta) as z:
            names = z.namelist()
        self.assertEqual(len([x for x in names
                              if x.startswith("ppt/slides/slide")
                              and x.endswith(".xml")]), n)

    def test_ppt_con_check_tiene_diapositiva_estado(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        guardar_check(tmp.name, [
            {"id": "ghidra", "url": "u", "ok": False, "estado": "HTTP 404",
             "ms": 1, "sin_enlace": False}])
        ruta = os.path.join(tmp.name, "deck.pptx")
        n = self._deck(tmp.name, ruta)
        import zipfile
        with zipfile.ZipFile(ruta) as z:
            all_xml = b" ".join(z.read(nm) for nm in z.namelist()
                                if nm.startswith("ppt/slides/slide"))
        self.assertIn("Estado de enlaces".encode(), all_xml)
        self.assertIn(b"HTTP 404", all_xml)

    def test_cli_ppt_y_watch_sin_check(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        ruta = os.path.join(tmp.name, "d.pptx")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--ppt", ruta, "--workspace", tmp.name])
        self.assertEqual(code, 0)
        self.assertIn("PPT exportado", buf.getvalue())
        self.assertTrue(os.path.isfile(ruta))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["recursos", "--watch", "60", "--workspace", tmp.name])
        self.assertEqual(code, 1)
        self.assertIn("--watch requiere --check", buf.getvalue())


class TestCheckWatch(unittest.TestCase):
    def test_ciclos_persisten_estado(self):
        import http.server
        from a2s.cli import _recursos_check_watch

        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        open(os.path.join(tmp.name, "ok.txt"), "w").write("ok")

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

        srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            lambda *a, **kw: Handler(*a, directory=tmp.name, **kw))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        port = srv.server_address[1]

        args = argparse.Namespace(workspace=tmp.name, timeout=1.0, id=None,
                                  workers=2, watch=0)
        data = {"recursos": [
            {"id": "x1", "cat": "ia", "nombre": "X1",
             "url": f"http://127.0.0.1:{port}/ok.txt", "desc": "", "tags": ()},
            {"id": "x2", "cat": "ia", "nombre": "X2",
             "url": f"http://127.0.0.1:{port}/no-existe",
             "desc": "", "tags": ()},
        ]}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _recursos_check_watch(args, data, max_cycles=2)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("ciclo 1", out)
        self.assertIn("ciclo 2", out)
        est = estado_check(tmp.name)
        self.assertIsNotNone(est)
        self.assertEqual(est["total"], 2)
        self.assertEqual(est["ok"], 1)
