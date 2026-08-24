"""Acciones de un clic: catálogo, ejecución local y API HTTP."""

import json
import threading
import unittest

from tests._winutil import temp_dir

from a2s.actions import BUTTONS, catalog, get_action, run_local
from a2s.dashboard import DashboardServer, EventHub, MissionManager
from tests.test_dashboard import request


class TestActionCatalog(unittest.TestCase):
    def test_botones_en_espanol_sin_cli(self):
        items = catalog()
        self.assertGreaterEqual(len(items), 12)
        ids = {item["id"] for item in items}
        for needed in ("organize", "book", "slides", "resume", "search",
                       "stop", "results", "undo", "status"):
            self.assertIn(needed, ids)
        for item in items:
            self.assertTrue(item["title"])
            self.assertNotIn("a2s ", item["title"].lower())
            self.assertNotIn("--", item["blurb"])

    def test_desconocida_falla(self):
        self.assertIsNone(get_action("no-existe"))
        result = run_local(".", "no-existe")
        self.assertFalse(result["ok"])

    def test_status_resume_view_undo(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        status = run_local(tmp.name, "status")
        self.assertTrue(status["ok"])
        self.assertIn("Colas", status["message"])
        resume = run_local(tmp.name, "resume")
        self.assertTrue(resume["ok"])
        self.assertEqual(resume["restored"], 0)
        view = run_local(tmp.name, "results")
        self.assertEqual(view.get("view"), "results")
        undo = run_local(tmp.name, "undo")
        self.assertTrue(undo["ok"])
        self.assertEqual(undo["result"]["restored"], 0)


class TestActionDispatch(unittest.TestCase):
    def test_stop_y_mission_desde_manager(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        manager = MissionManager(EventHub(), tmp.name)
        stop = manager.run_action("stop")
        self.assertFalse(stop["ok"])
        analyze = manager.run_action("analyze")
        self.assertTrue(analyze["ok"])
        self.assertTrue(analyze.get("queued"))
        manager.stop()


class TestActionsHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)
        self.dashboard = DashboardServer(port=0, workspace=self.tmp.name)
        self.server = self.dashboard.make_http_server()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_catalogo_y_status(self):
        code, _, body = request(self.base + "/api/actions")
        self.assertEqual(code, 200)
        actions = json.loads(body)["actions"]
        self.assertEqual(len(actions), len(BUTTONS))
        code, _, body = request(self.base + "/api/action", "POST",
                                {"id": "status"})
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertIn("pcb", data)

    def test_ui_tiene_tablero(self):
        code, _, html = request(self.base + "/")
        self.assertEqual(code, 200)
        self.assertIn(b'id="action-board"', html)
        self.assertIn(b'data-action="organize"', html)
        code, _, js = request(self.base + "/app.js")
        self.assertIn(b"/api/action", js)
        self.assertIn(b"fireAction", js)


if __name__ == "__main__":
    unittest.main()
