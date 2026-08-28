"""Pruebas de la API de proyecto Aegis para clientes sync/async futuros."""

import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from a2s.control import StopToken
from a2s.autonomy import ChangeProposal
from a2s.project import AegisProject, ProjectConfig
from a2s.provider_pool import PoolEndpoint, ProviderPool


class TestAegisProject(unittest.TestCase):
    def _pool(self, transport):
        endpoint = PoolEndpoint(name="local", base_url="http://local", model="test",
                                rpm=0, capabilities=("general",))
        return ProviderPool([endpoint], transport=transport, strategy="round_robin")

    def test_config_usa_referencia_de_entorno_y_no_persist_secretos(self):
        with tempfile.TemporaryDirectory() as workspace:
            config = ProjectConfig(max_parallel=2, secret_refs={"llm": "env:TEST_A2S_KEY"})
            config.save(os.path.join(workspace, ".a2s", "project.json"))
            with open(os.path.join(workspace, ".a2s", "project.json"), encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("env:TEST_A2S_KEY", content)
            self.assertNotIn("secret-value", content)
            with mock.patch.dict(os.environ, {"TEST_A2S_KEY": "secret-value"}):
                self.assertEqual(ProjectConfig.load(
                    os.path.join(workspace, ".a2s", "project.json")).resolve_secret("llm"),
                    "secret-value")

    def test_run_correlaciona_ids_y_respeta_max_parallel(self):
        state = {"active": 0, "peak": 0}
        lock = threading.Lock()

        def transport(_endpoint, payload):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.03)
            with lock:
                state["active"] -= 1
            return {"choices": [{"message": {"content": payload["messages"][-1]["content"]}}]}

        project = AegisProject(tempfile.mkdtemp(), ProjectConfig(max_parallel=2),
                               self._pool(transport))
        tasks = [{"id": f"task-{i}", "prompt": f"p-{i}"} for i in range(4)]
        result = project.run(tasks)
        self.assertEqual(result["task_ids"], [task["id"] for task in tasks])
        self.assertEqual(result["run_id"][:4], "run-")
        self.assertEqual(result["executed"], 4)
        self.assertLessEqual(state["peak"], 2)

    def test_cancelacion_y_timeout_exponen_tareas_canceladas(self):
        def transport(_endpoint, _payload):
            time.sleep(0.05)
            return {"choices": [{"message": {"content": "ok"}}]}

        project = AegisProject(tempfile.mkdtemp(), ProjectConfig(
            max_parallel=1, timeout_seconds=0.01), self._pool(transport))
        tasks = [{"id": "one", "prompt": "one"}, {"id": "two", "prompt": "two"}]
        result = project.run(tasks)
        self.assertEqual(result["cancelled"], ["one", "two"])
        self.assertEqual(result["executed"], 0)

        stop = StopToken()
        stop.set("test")
        result = AegisProject(tempfile.mkdtemp(), ProjectConfig(),
                              self._pool(transport)).run(tasks, stop=stop)
        self.assertEqual(result["cancelled"], ["one", "two"])

    def test_run_emite_eventos_correlacionados_por_tarea(self):
        def transport(_endpoint, payload):
            return {"choices": [{"message": {"content": payload["messages"][-1]["content"]}}]}

        events = []
        project = AegisProject(tempfile.mkdtemp(), ProjectConfig(),
                               self._pool(transport))
        result = project.run([{"id": "one", "prompt": "one"}], event_sink=events.append)

        self.assertEqual([event["status"] for event in events],
                         ["queued", "running", "done"])
        self.assertTrue(all(event["run_id"] == result["run_id"] for event in events))
        self.assertTrue(all(event["task_id"] == "one" for event in events))

    def test_run_emite_cancelled_para_tareas_no_iniciadas(self):
        events = []
        stop = StopToken()
        stop.set("test")
        project = AegisProject(tempfile.mkdtemp(), ProjectConfig(),
                               self._pool(lambda _endpoint, _payload: None))

        project.run([{"id": "one", "prompt": "one"}], stop=stop, event_sink=events.append)

        self.assertEqual([event["status"] for event in events], ["queued", "cancelled"])

    def test_run_emite_error_si_el_proveedor_no_devuelve_resultado(self):
        events = []
        project = AegisProject(tempfile.mkdtemp(), ProjectConfig(),
                               self._pool(lambda _endpoint, _payload: None))

        result = project.run([{"id": "one", "prompt": "one"}], event_sink=events.append)

        self.assertEqual(result["failed"], ["one"])
        self.assertEqual([event["status"] for event in events],
                         ["queued", "running", "error"])

    def test_iteracion_controlada_conecta_seleccion_y_evidencia(self):
        with tempfile.TemporaryDirectory() as workspace:
            score = os.path.join(workspace, "score.txt")
            with open(score, "w", encoding="utf-8") as handle:
                handle.write("1")
            project = AegisProject(workspace)
            result = project.run_controlled_iteration(
                "reversing_binario", ChangeProposal("mejorar", {"score.txt": "2"}),
                lambda path: float((path / "score.txt").read_text()), cost=3)
            self.assertEqual(result["decision"], "accept")
            self.assertEqual(result["selection"]["excluded"][0]["source"], "ghidra")
            mission_path = os.path.join(workspace, ".a2s", "autonomy", "missions",
                                        result["mission_id"] + ".json")
            with open(mission_path, encoding="utf-8") as handle:
                mission = json.load(handle)
            self.assertEqual(mission["baseline"]["metric"], 1.0)
            self.assertEqual(mission["result"]["after"], 2.0)
            self.assertEqual(mission["cost"], 3.0)

    def test_iteracion_consulta_historial_anterior_antes_de_evaluar(self):
        with tempfile.TemporaryDirectory() as workspace:
            score = os.path.join(workspace, "score.txt")
            with open(score, "w", encoding="utf-8") as handle:
                handle.write("1")
            project = AegisProject(workspace)
            evaluator = lambda path: float((path / "score.txt").read_text())
            project.run_controlled_iteration(
                "consulta historica", ChangeProposal("primera", {"score.txt": "2"}),
                evaluator)
            second = project.run_controlled_iteration(
                "consulta historica", ChangeProposal("segunda", {"score.txt": "3"}),
                evaluator)

            self.assertEqual(second["history"]["summary"]["attempts"], 1)
            self.assertEqual(second["history"]["records"][0]["decision"], "accept")
            mission = project.mission_history(objective="consulta historica")
            self.assertEqual(mission["summary"]["attempts"], 2)

    def test_informe_aprendizaje_es_fachada_del_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = AegisProject(workspace)
            mission_id = project.autonomy_loop().register_mission(
                "objetivo", selected_tools=[{"source": "local"}])

            report = project.learning_report("objetivo")

            self.assertEqual(report["history"]["records"][0]["mission_id"], mission_id)
            self.assertEqual(report["metrics"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()