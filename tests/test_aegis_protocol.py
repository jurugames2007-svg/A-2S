"""Protocolo omnimodal adaptativo: selección, contrato y trazabilidad."""

import io
import os
from contextlib import redirect_stdout
from tests._winutil import temp_dir
import unittest

from a2s.aegis_protocol import analyze_request, format_response
from a2s.chat import _prose_chat
from a2s.cli import main
from a2s.config import Config
from a2s.loop import AgentLoop
from a2s.models import Step, ToolCall
from a2s.providers import BaseProvider, HeuristicProvider


class CaptureChatProvider(BaseProvider):
    name = "capture-chat"

    def __init__(self):
        self.prompt = ""
        self.system = ""

    def chat(self, prompt, kind="general", max_tokens=900, system=""):
        self.prompt = prompt
        self.system = system
        return "Síntesis comprobable del resultado."


class TestAdaptiveClassification(unittest.TestCase):
    def test_actualidad_activa_investigacion_y_contraste(self):
        decision = analyze_request(
            "Compara el precio actual y las últimas noticias de tres proveedores en 2026")
        ids = decision.capability_ids
        self.assertIn("current_research", ids)
        self.assertIn("multi_source_verify", ids)
        self.assertIn("facts_vs_analysis", ids)
        self.assertIn("devils_advocate", ids)
        self.assertIn("web_search", decision.tool_candidates)
        self.assertTrue(any("fecha" in item.lower()
                            for item in decision.acceptance_criteria))

    def test_calculo_activa_precision_y_tabla(self):
        decision = analyze_request("Calcula 15% de 240 y presenta la conversión en tabla")
        self.assertIn("math_precision", decision.capability_ids)
        self.assertIn("data_visualization", decision.capability_ids)
        self.assertIn("python_exec", decision.tool_candidates)

    def test_creatividad_activa_variantes_sin_forzar_web(self):
        decision = analyze_request(
            "Crea ideas para un cuento y refina el mejor borrador con tono poético")
        self.assertIn("creativa", decision.need_types)
        self.assertIn("brainstorm", decision.capability_ids)
        self.assertIn("iterative_refinement", decision.capability_ids)
        self.assertIn("tone_adaptation", decision.capability_ids)
        self.assertNotIn("current_research", decision.capability_ids)

    def test_necesidad_emocional_no_activa_herramientas_irrelevantes(self):
        decision = analyze_request(
            "Me siento muy ansioso y frustrado; necesito apoyo para ordenar el día")
        self.assertIn("emocional", decision.need_types)
        self.assertIn("empathy", decision.capability_ids)
        self.assertNotIn("current_research", decision.capability_ids)
        self.assertNotIn("math_precision", decision.capability_ids)

    def test_ambiguedad_real_genera_pregunta_no_bloqueante(self):
        decision = analyze_request("Hazlo")
        self.assertIn("clarification", decision.capability_ids)
        self.assertTrue(decision.clarification_questions)
        self.assertTrue(decision.assumptions)

    def test_decision_compleja_activa_perspectivas_y_escenarios(self):
        decision = analyze_request(
            "Analiza la mejor estrategia, compara opciones, riesgos y escenarios futuros")
        self.assertIn("devils_advocate", decision.capability_ids)
        self.assertIn("multiple_perspectives", decision.capability_ids)
        self.assertIn("predictive_scenarios", decision.capability_ids)

    def test_salida_multimedia_usa_ruta_honesta(self):
        decision = analyze_request("Crea una imagen, un audio y un storyboard del concepto")
        self.assertIn("multimodal_route", decision.capability_ids)
        self.assertIn("visual_explanation", decision.capability_ids)
        self.assertIn("limitations", decision.capability_ids)


class TestResponseContract(unittest.TestCase):
    def test_formato_visible_sin_cadena_privada(self):
        decision = analyze_request("Analiza opciones técnicas y recomienda la mejor")
        output = format_response("La opción B tiene el mejor balance.", decision)
        for section in (
                "[CAPACIDADES ACTIVADAS]", "[RAZONAMIENTO RESUMIDO]",
                "[RESPUESTA PRINCIPAL]", "[DATOS ADICIONALES]",
                "[SIGUIENTES PASOS]"):
            self.assertIn(section, output)
        self.assertNotIn("chain-of-thought", output.lower())
        self.assertNotIn("paso secreto", output.lower())

    def test_descarta_etiquetas_de_deliberacion_privada(self):
        decision = analyze_request("Analiza esta decisión técnica")
        output = format_response(
            "<think>deliberación privada paso a paso</think>Conclusión verificable.",
            decision)
        self.assertNotIn("deliberación privada", output)
        self.assertIn("Conclusión verificable", output)

    def test_saludo_se_mantiene_natural(self):
        decision = analyze_request("Hola")
        self.assertTrue(decision.social_only)
        self.assertEqual(format_response("Hola, ¿en qué te ayudo?", decision),
                         "Hola, ¿en qué te ayudo?")

    def test_prompt_prohibe_omnipotencia_y_exposicion_interna(self):
        prompt = analyze_request("Investiga el estado actual").system_prompt().lower()
        self.assertIn("no reveles cadenas privadas", prompt)
        self.assertIn("no afirmes precisión absoluta", prompt)
        self.assertIn("fuente y fecha", prompt)

    def test_chat_usa_historial_completo_y_contrato_dinamico(self):
        provider = CaptureChatProvider()
        output = _prose_chat(provider, [
            {"role": "user", "content": "Mi proyecto se llama Atlas."},
            {"role": "assistant", "content": "Entendido."},
            {"role": "user", "content": "Analiza tres estrategias para mejorarlo."},
        ])
        self.assertIn("Operador: Mi proyecto se llama Atlas", provider.prompt)
        self.assertIn("Aegis: Entendido", provider.prompt)
        self.assertIn("Múltiples perspectivas", provider.system)
        self.assertIn("[RESPUESTA PRINCIPAL]", output)


class TestProtocolIntegration(unittest.TestCase):
    def test_mision_registra_perfil_en_timeline_informe_y_ledger(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        goal = "Crea protocolo.txt con el texto OK"
        cfg = Config(workspace=tmp.name, provider="heuristic", quiet=True,
                     max_wall_seconds=20, max_rounds=1)

        def verifier(_memory):
            path = os.path.join(tmp.name, "protocolo.txt")
            return (os.path.isfile(path), "artefacto presente")

        loop = AgentLoop.create(goal, config=cfg, provider=HeuristicProvider(),
                                goal_verifier=verifier)
        step = Step(goal="crear protocolo", approach="escritura directa",
                    success_criteria=["archivo presente"])
        step.calls = [ToolCall(tool="write_file",
                               params={"path": "protocolo.txt", "content": "OK"})]
        loop._plan = [step]
        report = loop.run(goal)
        self.assertTrue(report.success, report.final_note)
        self.assertIn("capability_protocol",
                      [event["event"] for event in report.timeline])
        self.assertIn("Protocolo adaptativo", report.final_note)
        self.assertIn("autonomous_execution",
                      [capability["id"] for capability in
                       report.capability_protocol["capabilities"]])
        events = [entry for entry in loop.memory.ledger.entries()
                  if entry.get("event") == "capability_protocol"]
        self.assertTrue(events)

    def test_cli_protocol_es_inspeccionable_sin_proveedor(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["protocol", "Calcula 20% de 50", "--json"])
        self.assertEqual(code, 0)
        value = output.getvalue()
        self.assertIn('"need_types"', value)
        self.assertIn('"math_precision"', value)


if __name__ == "__main__":
    unittest.main()
