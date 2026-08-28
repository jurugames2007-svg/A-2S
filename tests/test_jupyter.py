import tempfile
import unittest

from a2s.control import StopToken
from a2s.jupyter import AegisJupyter
from a2s.project import AegisProject, ProjectConfig


class RecordingProject(AegisProject):
    def __init__(self, workspace):
        self.workspace = workspace
        self.config = ProjectConfig(max_parallel=2)
        self.calls = []

    def run(self, tasks, stop=None, aggregate=None, event_sink=None):
        self.calls.append((tasks, stop, aggregate, event_sink))
        return {"results": {task["id"]: "ok" for task in tasks},
                "failed": [], "cancelled": [], "executed": len(tasks),
                "total": len(tasks), "task_ids": [task["id"] for task in tasks]}


class TestAegisJupyter(unittest.TestCase):
    def test_configura_y_ejecuta_tarea_a_traves_del_proyecto(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = RecordingProject(workspace)
            client = AegisJupyter(project=project)

            result = client.run_task("one", "hazlo")

            self.assertEqual(result["results"], {"one": "ok"})
            self.assertEqual(project.calls[0][0], [{"id": "one", "prompt": "hazlo"}])

    def test_lote_reutiliza_scheduler_y_cancelar_comparte_stop_token(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = RecordingProject(workspace)
            client = AegisJupyter(project=project)

            result = client.run_tasks([{"id": "a", "prompt": "A"},
                                       {"id": "b", "prompt": "B"}])
            token = project.calls[-1][1]
            self.assertEqual(result["executed"], 2)
            self.assertIsInstance(token, StopToken)
            self.assertIs(client.stop_token, token)

            client.cancel("user")
            self.assertTrue(token.is_set())
            self.assertEqual(token.reason, "user")

    def test_lote_expone_eventos_y_sink_sin_crear_scheduler(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = RecordingProject(workspace)
            client = AegisJupyter(project=project)
            received = []

            client.run_tasks([{"id": "a", "prompt": "A"},
                              {"id": "b", "prompt": "B"}], event_sink=received.append)

            self.assertTrue(callable(project.calls[-1][3]))
            project.calls[-1][3]({"status": "done", "task_id": "a"})
            self.assertEqual(received, [{"status": "done", "task_id": "a"}])
            self.assertEqual(client.get_events(), received)

    def test_informe_aprendizaje_se_expone_desde_jupyter(self):
        with tempfile.TemporaryDirectory() as workspace:
            client = AegisJupyter(workspace=workspace)
            client.project.autonomy_loop().register_mission(
                "objetivo", selected_tools=["local"])

            report = client.learning_report("objetivo")

            self.assertEqual(report["metrics"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()