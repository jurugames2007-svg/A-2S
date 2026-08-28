import tempfile
import time
import unittest
from unittest import mock

from a2s.jupyter import AegisJupyter
from a2s.serve import MissionRunner


class FakeProject:
    def __init__(self, workspace, config):
        self.workspace = workspace

    def run(self, tasks, stop=None, event_sink=None):
        event_sink({"event": "task", "run_id": "run-test", "task_id": "a",
                    "status": "done"})
        return {"run_id": "run-test", "results": {"a": "ok"}, "failed": [],
                "cancelled": [], "executed": 1, "total": len(tasks)}


class TestExecutionContract(unittest.TestCase):
    def test_runner_dag_conserva_run_id_eventos_y_cancelacion(self):
        with tempfile.TemporaryDirectory() as workspace, \
                mock.patch("a2s.project.AegisProject", FakeProject):
            runner = MissionRunner(workspace, max_time=2)
            mission_id = runner.start("ana", tasks=[{"id": "a", "prompt": "A"}])
            for _ in range(20):
                state = runner.get(mission_id)
                if state["status"] != "running":
                    break
                time.sleep(0.01)
            self.assertEqual(state["status"], "done")
            self.assertEqual(state["run_id"], "run-test")
            self.assertEqual(state["events"][0]["task_id"], "a")
            self.assertFalse(runner.cancel(mission_id))

    def test_jupyter_consume_estado_http_sin_red(self):
        client = AegisJupyter(workspace=tempfile.mkdtemp())
        client.configure_remote("http://test", "token-no-se-guarda")
        responses = iter([
            {"mission_id": "m-1"},
            {"status": "running", "events": [{"task_id": "a", "status": "running"}]},
            {"status": "done", "events": [{"task_id": "a", "status": "running"},
                                             {"task_id": "a", "status": "done"}],
             "result": {"run_id": "run-1", "results": {"a": "ok"}}},
        ])
        with mock.patch.object(client, "_remote_request", side_effect=lambda *args: next(responses)), \
                mock.patch("a2s.jupyter.time.sleep"):
            result = client.run_remote_tasks([{"id": "a", "prompt": "A"}])
        self.assertEqual(result["run_id"], "run-1")
        self.assertEqual([event["status"] for event in client.get_events()],
                         ["running", "done"])
        self.assertEqual(client.remote_token, "token-no-se-guarda")


if __name__ == "__main__":
    unittest.main()