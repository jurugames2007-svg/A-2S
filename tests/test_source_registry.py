import json
import tempfile
import unittest

from a2s.project import AegisProject
from a2s.source_registry import SourceRegistry
from a2s.recursos import (FuenteExterna, buscar_fuentes, deserializar_fuentes,
                          puede_usarse_fuente, planificar_capacidades,
                          serializar_fuentes, serializar_plan_capacidades,
                          source_registry)


class TestSourceRegistry(unittest.TestCase):
    def test_selector_filtra_politicas_puntua_y_ordena_empates(self):
        registry = SourceRegistry([
            FuenteExterna("b", "https://example.test/b", "B", "dev", "tool",
                          "unknown", "python", ("consulta",), "allowed", "verified"),
            FuenteExterna("a", "https://example.test/a", "A", "dev", "tool",
                          "unknown", "node", ("consulta",), "allowed", "verified"),
            FuenteExterna("r", "https://example.test/r", "R", "dev", "docs",
                          "unknown", "none", ("consulta",), "reference_only", "unavailable"),
            FuenteExterna("x", "https://example.test/x", "X", "dev", "tool",
                          "unknown", "none", ("consulta",), "blocked", "verified"),
        ])
        result = registry.select_tools("consulta", "dev", include_reference_only=True)
        self.assertEqual([row["source"] for row in result["selected"]], ["a", "b"])
        self.assertEqual([row["source"] for row in result["reference_only"]], ["r"])
        self.assertEqual([row["source"] for row in result["blocked"]], ["x"])
        self.assertEqual(result["selected"][0]["score_breakdown"]["exact_capability"], 100)
        self.assertEqual(result["selected"][0]["dependencies"], "node")

    def test_selector_serializacion_y_capacidad_registrada(self):
        registry = SourceRegistry([FuenteExterna(
            "x", "https://example.test/x", "X", "dev", "tool", "unknown",
            "python", ("base",), "allowed", "verified")])
        registry.register_capability("x", "nueva")
        self.assertEqual([row["capability"] for row in registry.capabilities("x")],
                         ["base", "nueva"])
        selection = registry.select_tools("nueva")
        self.assertEqual(json.loads(registry.serialize_selection(selection)), selection)

    def test_selector_traza_exclusiones_y_solo_policy_allowed(self):
        registry = SourceRegistry([
            FuenteExterna("allowed", "https://example.test/allowed", "Allowed",
                          "dev", "tool", "unknown", "python", ("consulta",),
                          "allowed", "unavailable"),
            FuenteExterna("blocked", "https://example.test/blocked", "Blocked",
                          "dev", "tool", "unknown", "python", ("consulta",),
                          "blocked", "verified"),
            FuenteExterna("reference", "https://example.test/reference", "Reference",
                          "dev", "docs", "unknown", "none", ("consulta",),
                          "reference_only", "unavailable"),
        ])

        result = registry.select_tools("consulta", "dev")

        self.assertEqual([row["source"] for row in result["selected"]], ["allowed"])
        self.assertEqual([row["source"] for row in result["excluded"]],
                         ["blocked", "reference"])
        self.assertEqual(result["selected"][0]["dependencies"], "python")
        self.assertIn("policy", result["selected"][0])
        self.assertEqual(result["blocked"][0]["exclusion_reason"],
                         "fuente bloqueada por política")
        self.assertEqual(result["reference_only"][0]["exclusion_reason"],
                         "fuente solo de referencia")
        self.assertEqual(result, registry.select_tools("consulta", "dev",
                                                       include_reference_only=True))

    def test_catalogo_normaliza_campos_y_politica(self):
        registry = source_registry()
        ghidra = registry.get("ghidra")
        self.assertEqual(ghidra.licencia, "unknown")
        self.assertEqual(ghidra.policy, "reference_only")
        self.assertIn(ghidra.tipo, {"code", "tool"})
        self.assertIn("reversing_binario", ghidra.capabilities)
        worm = registry.get("wormgpt")
        self.assertEqual(worm.policy, "blocked")
        self.assertEqual(set(ghidra.to_dict()), {
            "id", "url", "nombre", "categoria", "tipo", "licencia",
            "dependencia", "capabilities", "policy", "adapter_status"})

    def test_busca_por_capacidad_y_categoria(self):
        rows = buscar_fuentes(capability="reversing_binario", categoria="ciber")
        self.assertTrue(rows)
        self.assertTrue(all(row["categoria"] == "ciber" for row in rows))

    def test_decision_no_habilita_reference_only_ni_blocked(self):
        self.assertFalse(puede_usarse_fuente("ghidra")["allowed"])
        self.assertFalse(puede_usarse_fuente("wormgpt")["allowed"])

    def test_decision_habilita_fuente_allowed_con_adapter_verificado(self):
        registry = source_registry()
        source = FuenteExterna("local", "https://example.test/api", "Local API",
                               "dev", "api", "unknown", "unknown",
                               ("consulta",), "allowed", "verified")
        registry.register(source)
        decision = registry.can_use("local", ("consulta",))
        self.assertTrue(decision["allowed"])

    def test_serializacion_es_determinista_y_reversible(self):
        source = FuenteExterna("x", "https://example.test", "X", "dev", "docs",
                               "unknown", "unknown", ("lectura",),
                               "reference_only", "unavailable")
        payload = serializar_fuentes([source])
        self.assertEqual(json.loads(payload)[0]["capabilities"], ["lectura"])
        self.assertEqual(deserializar_fuentes(payload).get("x"), source)

    def test_project_expone_consulta_local(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = AegisProject(workspace)
            self.assertTrue(project.sources(categoria="ciber"))
            self.assertFalse(project.can_use_source("wormgpt")["allowed"])

    def test_plan_filtra_politicas_y_no_incluye_bloqueados(self):
        registry = source_registry()
        registry.register(FuenteExterna(
            "allowed-test", "https://example.test/allowed", "Allowed",
            "dev", "api", "unknown", "unknown", ("consulta",),
            "allowed", "verified"))
        registry.register(FuenteExterna(
            "reference-test", "https://example.test/reference", "Reference",
            "dev", "docs", "unknown", "unknown", ("consulta",),
            "reference_only", "unavailable"))
        registry.register(FuenteExterna(
            "blocked-test", "https://example.test/blocked", "Blocked",
            "dev", "tool", "unknown", "unknown", ("consulta",),
            "blocked", "verified"))

        default = registry.plan("consulta", {"mission": "datos"})
        self.assertEqual([row["source"] for row in default], ["allowed-test"])
        planned = registry.plan("consulta", include_reference_only=True)
        self.assertEqual([row["source"] for row in planned],
                         ["allowed-test", "reference-test"])
        self.assertNotIn("blocked-test", {row["source"] for row in planned})
        self.assertEqual(planned[1]["adapter_status"], "unavailable")

    def test_plan_y_serializacion_son_deterministas(self):
        plan = planificar_capacidades("reversing_binario", include_reference_only=True)
        self.assertTrue(plan)
        self.assertEqual(set(plan[0]), {
            "source", "capabilities", "reason", "policy", "adapter_status"})
        payload = serializar_plan_capacidades(plan)
        self.assertEqual(payload, serializar_plan_capacidades(plan))
        self.assertEqual(json.loads(payload), plan)

    def test_project_expone_plan_de_capacidades(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = AegisProject(workspace)
            plan = project.plan_capabilities(
                "reversing_binario", include_reference_only=True)
            self.assertTrue(plan)
            self.assertTrue(all(row["policy"] != "blocked" for row in plan))

    def test_project_expone_recomendaciones_sin_ejecutar_fuentes(self):
        with tempfile.TemporaryDirectory() as workspace:
            result = AegisProject(workspace).recommend_sources("reversing_binario",
                                                               categoria="ciber")
            self.assertEqual(result["selected"], [])
            self.assertTrue(result["reference_only"])
            self.assertTrue(all(row["policy"] == "reference_only"
                                for row in result["reference_only"]))
            self.assertTrue(all("reason" in row and "score" in row
                                for row in result["reference_only"]))


if __name__ == "__main__":
    unittest.main()