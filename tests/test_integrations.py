import json
import os
import sys
import tempfile
import unittest

from a2s.integrations import APISpec, ProcessManager, PublicAPIManager


class TestPublicAPIManager(unittest.TestCase):
    def test_search_and_call_registered_api(self):
        calls = []

        def transport(url, method, headers, timeout):
            calls.append((url, method, timeout))
            return json.dumps({"ok": True})

        manager = PublicAPIManager(transport=transport)
        manager.register(APISpec("local", "https://api.example.test", "test",
                                 description="API de prueba"))
        self.assertEqual(manager.search("prueba")[0]["name"], "local")
        self.assertEqual(manager.call("local", "health", {"v": "1"}), {"ok": True})
        self.assertEqual(calls[0][1], "GET")
        self.assertIn("v=1", calls[0][0])

    def test_call_cannot_escape_registered_host(self):
        manager = PublicAPIManager()
        manager.register(APISpec("local", "https://api.example.test"))
        with self.assertRaises(PermissionError):
            manager.call("local", "https://other.example.test/private")


class TestProcessManager(unittest.TestCase):
    def test_start_monitor_stop_and_logs(self):
        with tempfile.TemporaryDirectory() as workspace:
            manager = ProcessManager(workspace)
            started = manager.start("worker", [sys.executable, "-c", "print('ready')"])
            self.assertEqual(started["status"], "online")
            manager.processes["worker"].process.wait(timeout=5)
            state = manager.monitor()
            self.assertEqual(state["worker"]["status"], "stopped")
            self.assertIn("ready", manager.logs("worker"))
            stopped = manager.stop("worker")
            self.assertEqual(stopped["status"], "stopped")

    def test_cwd_must_stay_inside_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            manager = ProcessManager(workspace)
            with self.assertRaises(PermissionError):
                manager.start("worker", [sys.executable, "-c", "pass"], cwd=os.pardir)


if __name__ == "__main__":
    unittest.main()