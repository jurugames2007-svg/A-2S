"""Chat paralelo, parada real, inbox, búsqueda y creación que no se atascan."""

import json
import os
import threading
import time
import unittest

from a2s.chat import ChatManager
from a2s.control import JobSupervisor, RequestInbox, StopToken
from a2s.creator import create_document, write_markdown_pdf
from a2s.dashboard import EventHub, MissionManager
from a2s.finder import RepoFinder, expand_query, format_search
from a2s.intent import classify_intent
from a2s.literary import compose_book, is_principito, word_count
from a2s.loop import AgentLoop
from a2s.models import Step, StepStatus, ToolCall
from tests._winutil import temp_dir
from tests.test_dashboard import request
from a2s.dashboard import DashboardServer


class TestIntent(unittest.TestCase):
    def test_stop_y_busqueda_y_creacion(self):
        self.assertEqual(classify_intent("para").kind, "stop")
        self.assertEqual(classify_intent("detén todo").kind, "stop")
        self.assertEqual(classify_intent("busca repositorios de forense").kind, "search")
        self.assertEqual(classify_intent("search autonomous agents").kind, "search")
        crea = classify_intent("Crea un libro sobre El Principito")
        self.assertEqual(crea.kind, "create")
        self.assertTrue(crea.wants_book)
        self.assertEqual(classify_intent("hola").kind, "chat")
        self.assertEqual(classify_intent("qué haces ahora").kind, "status")


class TestInboxYStopToken(unittest.TestCase):
    def test_inbox_nunca_rechaza_por_ocupado(self):
        box = RequestInbox(maxsize=8)
        for i in range(20):
            ok, _ = box.put({"n": i})
            self.assertTrue(ok)
        self.assertGreaterEqual(box.snapshot()["accepted"], 20)

    def test_stop_token_despierta_espera(self):
        token = StopToken()
        seen = []

        def waiter():
            token.wait(5)
            seen.append(token.reason)

        thread = threading.Thread(target=waiter)
        thread.start()
        token.set("operator")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(seen, ["operator"])


class TestLoopStop(unittest.TestCase):
    def test_stop_corta_el_bucle_externo(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        from a2s.config import Config
        cfg = Config(workspace=tmp.name, max_wall_seconds=120, max_rounds=6,
                     max_iterations=30, quiet=True, provider="heuristic",
                     allow_network=False, allow_shell=False)
        loop = AgentLoop.create("objetivo largo", config=cfg)
        loop.consensus = None
        loop.goal_verifier = lambda _mem: (False, "aún no")
        step = Step(goal="esperar", approach="directa")
        step.calls = [ToolCall(tool="python_exec",
                               params={"code": "import time; time.sleep(2); print('tick')"},
                               why="tick")]
        loop._plan = [step]
        loop.request_stop("test")
        t0 = time.time()
        report = loop.run("objetivo largo")
        self.assertLess(time.time() - t0, 8)
        self.assertFalse(report.success)
        self.assertIn("parada", report.final_note.lower())


class TestFinder(unittest.TestCase):
    def test_expande_espanol_e_ingles(self):
        variants = expand_query("agentes autónomos verificables")
        blob = " ".join(variants)
        self.assertIn("agent", blob)
        self.assertTrue(any("autonom" in v for v in variants))

    def test_busca_catalogo_sin_filtro_llmops(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        finder = RepoFinder(tmp.name, github=_offline_github())
        report = finder.search("omniroute gateway", limit=5, allow_network=True)
        names = [r["full_name"] for r in report["repositories"]]
        self.assertIn("diegosouzapw/OmniRoute", names)
        self.assertFalse(report["code_executed"])

    def test_consulta_vacia_es_honesta(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        report = RepoFinder(tmp.name, github=_offline_github()).search("")
        self.assertIn("vacía", " ".join(report["errors"]))


class TestCreator(unittest.TestCase):
    def test_principito_es_un_libro_de_verdad(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        result = create_document(tmp.name, "El Principito", kind="book")
        self.assertGreaterEqual(result["word_count"], 1500)
        self.assertGreaterEqual(result["chapters"], 8)
        pdf = os.path.join(tmp.name, "book", "book.pdf")
        md = os.path.join(tmp.name, "book", "book.md")
        self.assertTrue(os.path.isfile(pdf))
        with open(pdf, "rb") as fh:
            self.assertEqual(fh.read(5), b"%PDF-")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("companion", text.lower())
        self.assertNotIn("Panorama, propósito y alcance", text)
        self.assertGreater(os.path.getsize(pdf), 4000)

    def test_create_se_puede_interrumpir(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        token = StopToken()
        token.set("test")
        with self.assertRaises(InterruptedError):
            create_document(tmp.name, "cualquier tema", stop=token)

    def test_pdf_con_acentos(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "á.pdf")
        pages = write_markdown_pdf(path, "Título", "# Título\n\nInformación útil.")
        self.assertGreaterEqual(pages, 1)
        with open(path, "rb") as fh:
            self.assertTrue(fh.read().startswith(b"%PDF-"))


class TestChatParalelo(unittest.TestCase):
    def test_encola_mientras_responde(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        hub = EventHub()
        gate = threading.Event()

        class Slow:
            name = "slow"

            def chat(self, *a, **k):
                gate.wait(2)
                return "ok lento"

        mgr = ChatManager(hub, tmp.name, get_provider=lambda: Slow())
        ok1, _ = mgr.send("hola, cuéntame algo largo")
        ok2, msg2 = mgr.send("y otra cosa más mientras tanto")
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertIn("queue", msg2)
        gate.set()
        for _ in range(40):
            snap = mgr.snapshot()
            assistants = [m for m in snap["history"] if m["role"] == "assistant"]
            if len(assistants) >= 1:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(len([m for m in mgr.snapshot()["history"]
                                     if m["role"] == "user"]), 2)

    def test_stop_desde_chat(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        hub = EventHub()
        stopped = []

        def stop_all():
            stopped.append(True)
            return True, "parada solicitada"

        mgr = ChatManager(hub, tmp.name,
                          get_provider=lambda: None,
                          stop_all=stop_all)
        mgr.send("para")
        for _ in range(30):
            if stopped:
                break
            time.sleep(0.1)
        self.assertTrue(stopped)


class TestMissionManagerLive(unittest.TestCase):
    def test_stop_sin_current_aun_asi_senala(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        mgr = MissionManager(EventHub(), tmp.name)
        mgr.running = True
        mgr.current = None
        ok, msg = mgr.stop()
        self.assertTrue(ok)
        self.assertTrue(mgr.stop_token.is_set())

    def test_create_job_en_paralelo(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        mgr = MissionManager(EventHub(), tmp.name)
        ok, job_id = mgr.run_create("El Principito", {"book": True})
        self.assertTrue(ok)
        for _ in range(50):
            jobs = mgr.jobs.snapshot()
            if jobs and not jobs[-1]["alive"]:
                break
            time.sleep(0.1)
        jobs = mgr.jobs.snapshot()
        self.assertTrue(jobs)
        self.assertTrue(jobs[-1]["ok"], jobs[-1].get("error"))
        self.assertTrue(os.path.isfile(os.path.join(tmp.name, "book", "book.pdf")))


class TestDashboardFindYChatLibre(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)
        self.dash = DashboardServer(port=0, workspace=self.tmp.name)
        self.server = self.dash.make_http_server()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_find_y_doble_chat(self):
        code, _, body = request(self.base + "/api/find?q=omniroute")
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertIn("repositories", data)
        code1, _, b1 = request(self.base + "/api/chat", "POST",
                               {"message": "hola"})
        code2, _, b2 = request(self.base + "/api/chat", "POST",
                               {"message": "qué puedes hacer"})
        self.assertEqual(code1, 202, b1)
        self.assertEqual(code2, 202, b2)

    def test_stop_sin_mision_es_409(self):
        code, _, body = request(self.base + "/api/stop", "POST", {})
        self.assertEqual(code, 409, body)


def _offline_github():
    from a2s.learner import GitHubClient

    def transport(url, headers):
        return 200, {}, json.dumps({"items": []}).encode()

    return GitHubClient(token="x", transport=transport, max_calls=5)


if __name__ == "__main__":
    unittest.main()
