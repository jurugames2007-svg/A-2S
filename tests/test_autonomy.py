import os
import json
from tests._winutil import temp_dir
import unittest

from a2s.autonomy import AutonomousLoop, ChangeLimits, ChangeProposal
from a2s.ledger import Ledger


class TestAutonomousLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.workspace = self.tmp.name
        with open(os.path.join(self.workspace, "score.txt"), "w", encoding="utf-8") as fh:
            fh.write("1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_acepta_mejora_guarda_evidencia_y_rollback(self):
        loop = AutonomousLoop(self.workspace)
        metric = lambda path: float((path / "score.txt").read_text())
        loop.register_baseline(metric)
        proposal = ChangeProposal("subir", {"score.txt": "2"})
        proposal_id = loop.register_proposal(proposal)
        result = loop.step(proposal_id, metric)
        self.assertTrue(result["accepted"])
        self.assertEqual(metric(loop.workspace), 2.0)
        run_dir = os.path.join(self.workspace, ".a2s", "autonomy", result["run_id"])
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "diff.patch")))
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "result.json")))
        loop.rollback(result["run_id"])
        self.assertEqual(metric(loop.workspace), 1.0)
        self.assertTrue(Ledger(os.path.join(self.workspace, ".a2s")).verify()[0])

    def test_rechaza_y_restaurar_si_no_mejora(self):
        loop = AutonomousLoop(self.workspace)
        metric = lambda path: float((path / "score.txt").read_text())
        loop.register_baseline(metric)
        result = loop.step(ChangeProposal("bajar", {"score.txt": "0"}), metric)
        self.assertFalse(result["accepted"])
        self.assertEqual(metric(loop.workspace), 1.0)

    def test_limites_ruta_y_iteraciones(self):
        loop = AutonomousLoop(self.workspace, ChangeLimits(max_iterations=1, max_diff_lines=1))
        loop.register_baseline(lambda _path: 1)
        with self.assertRaises(ValueError):
            loop.register_proposal(ChangeProposal("fuera", {"../x": "1"}))
        result = loop.step(ChangeProposal("ok", {"new.txt": "2"}), lambda _path: 2)
        self.assertFalse(result["accepted"])
        with self.assertRaises(RuntimeError):
            loop.step(ChangeProposal("otra", {"new.txt": "3"}), lambda _path: 3)

    def test_rollback_no_acepta_ruta_de_estado_fuera_del_workspace(self):
        loop = AutonomousLoop(self.workspace)
        with self.assertRaises(ValueError):
            loop.rollback("../fuera")

    def test_mision_guarda_traza_y_decision_rollback(self):
        loop = AutonomousLoop(self.workspace)
        metric = lambda path: float((path / "score.txt").read_text())
        baseline = loop.register_baseline(metric)
        mission_id = loop.register_mission(
            "mejorar consulta", [{"source": "b"}, {"source": "a"}],
            [{"source": "a"}], [{"source": "blocked"}], baseline=baseline,
            cost=2, iteration=1)
        result = loop.step(ChangeProposal("subir", {"score.txt": "2"}), metric,
                           mission_id=mission_id, cost=2)
        self.assertEqual(result["decision"], "accept")
        mission_path = os.path.join(self.workspace, ".a2s", "autonomy", "missions",
                                    mission_id + ".json")
        with open(mission_path, encoding="utf-8") as handle:
            mission = json.load(handle)
        self.assertEqual(mission["decision"], "accept")
        self.assertEqual(mission["selected_tools"], [{"source": "a"}])
        self.assertEqual(mission["excluded_tools"], [{"source": "blocked"}])
        loop.rollback(result["run_id"])
        with open(mission_path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["decision"], "rollback")

    def test_mision_rechazada_conserva_metricas_y_no_muta_workspace(self):
        loop = AutonomousLoop(self.workspace)
        metric = lambda path: float((path / "score.txt").read_text())
        baseline = loop.register_baseline(metric)
        mission_id = loop.register_mission("empeorar", baseline=baseline)
        result = loop.step(ChangeProposal("bajar", {"score.txt": "0"}), metric,
                           mission_id=mission_id)
        self.assertEqual(result["decision"], "reject")
        self.assertEqual(result["before"], 1.0)
        self.assertEqual(result["after"], 0.0)
        self.assertEqual(metric(loop.workspace), 1.0)

    def test_historial_filtra_resume_y_ignora_registros_corruptos(self):
        loop = AutonomousLoop(self.workspace)
        missions = loop.missions_dir
        records = [
            {"mission_id": "mission-b", "objective": "mejorar consulta",
             "selected_tools": [{"source": "tool-b"}], "decision": "accept",
             "result": {"before": 1, "after": 3}},
            {"mission_id": "mission-a", "objective": "mejorar consulta",
             "excluded_tools": [{"source": "tool-a"}], "decision": "reject",
             "result": {"before": 3, "after": 2}},
            {"mission_id": "mission-c", "objective": "otra meta",
             "selected_tools": [{"source": "tool-b"}], "decision": "rollback",
             "result": {"before": 3, "after": 4}},
        ]
        for record in records:
            (missions / f"{record['mission_id']}.json").write_text(
                json.dumps(record), encoding="utf-8")
        (missions / "corrupt.json").write_text("{no es json", encoding="utf-8")

        history = loop.mission_history(objective="consulta", tool="tool-b")

        self.assertEqual([record["mission_id"] for record in history["records"]],
                         ["mission-b"])
        self.assertEqual(history["summary"], {
            "attempts": 1, "accepted": 1, "rejected": 0, "rollbacks": 0,
            "average_improvement": 2.0,
        })
        self.assertEqual(loop.mission_history()["summary"], {
            "attempts": 3, "accepted": 1, "rejected": 1, "rollbacks": 1,
            "average_improvement": 2 / 3,
        })

    def test_informe_aprendizaje_agrega_evidencia_y_recomienda_solo_seleccionadas(self):
        loop = AutonomousLoop(self.workspace)
        missions = loop.missions_dir
        records = [
            {"mission_id": "mission-b", "objective": "consulta",
             "selected_tools": [{"source": "alpha"}],
             "excluded_tools": [{"source": "beta"}], "decision": "accept",
             "cost": 2, "result": {"before": 1, "after": 3}},
            {"mission_id": "mission-a", "objective": "consulta",
             "selected_tools": [{"source": "alpha"}],
             "excluded_tools": [{"source": "beta"}], "decision": "reject",
             "cost": 1, "result": {"before": 3, "after": 2}},
            {"mission_id": "mission-c", "objective": "otra",
             "selected_tools": [{"source": "alpha"}],
             "excluded_tools": [{"source": "blocked"}], "decision": "rollback",
             "cost": 4, "result": {"before": 2, "after": 4}},
        ]
        for record in records:
            (missions / f"{record['mission_id']}.json").write_text(
                json.dumps(record), encoding="utf-8")

        report = loop.learning_report(objective="consulta")

        self.assertEqual([item["mission_id"] for item in report["history"]["records"]],
                         ["mission-a", "mission-b"])
        self.assertEqual(report["metrics"], {
            "attempts": 2, "accepted": 1, "rejected": 1, "rollbacks": 0,
            "acceptance_rate": 0.5, "average_improvement": 0.5,
            "accepted_average_improvement": 2.0, "total_cost": 3.0,
            "average_cost": 1.5,
        })
        self.assertEqual(report["tools_by_objective"][0]["objective"], "consulta")
        self.assertEqual(report["tools_by_objective"][0]["tools"][0]["tool"],
                         {"source": "alpha"})
        self.assertEqual(report["tools_by_objective"][0]["tools"][0]["accepted"], 1)
        self.assertEqual(report["exclusions"], [{"objective": "consulta",
                               "tool": {"source": "beta"},
                               "count": 2}])
        self.assertEqual(report["recommendations"][0]["tool"], {"source": "alpha"})
        json.dumps(report)

    def test_informe_rechaza_limites_invalidos(self):
        loop = AutonomousLoop(self.workspace)
        with self.assertRaises(ValueError):
            loop.learning_report(limit=0)
        with self.assertRaises(ValueError):
            loop.learning_report(limit=1001)


if __name__ == "__main__":
    unittest.main()