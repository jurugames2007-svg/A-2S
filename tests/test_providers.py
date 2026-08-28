"""Pruebas de los proveedores de razonamiento."""

import unittest

from a2s.providers import HeuristicProvider, OpenAICompatProvider, _extract_json


class TestHeuristicProvider(unittest.TestCase):
    def setUp(self):
        self.p = HeuristicProvider()

    def test_plan_forensic(self):
        raw = self.p.plan("Produce un informe forense", "ctx", "tools")
        self.assertTrue(raw["steps"])
        tools = [s["tool"] for s in raw["steps"]]
        self.assertIn("write_file", tools)
        # La recopilación del núcleo heurístico es stdlib (python_exec), no
        # depende de shell POSIX: el plan debe funcionar en cualquier SO.
        self.assertIn("python_exec", tools)
        for step in raw["steps"]:
            if step["tool"] == "python_exec":
                self.assertNotIn("find ", step["params"]["code"])
                self.assertNotIn("sha256sum", step["params"]["code"])

    def test_plan_variants(self):
        a = self.p.plan("investigar algo en la web", "", "tools", variant=0)
        b = self.p.plan("investigar algo en la web", "", "tools", variant=1)
        self.assertEqual([s["tool"] for s in a["steps"]],
                         [s["tool"] for s in b["steps"]])
        self.assertNotEqual(a["steps"][0]["id"], b["steps"][0]["id"])

    def test_evaluate(self):
        ev = self.p.evaluate("paso", "salida con contenido", "criterios")
        self.assertEqual(ev["verdict"], "success")
        ev2 = self.p.evaluate("paso", "PERMISO DENEGADO", "criterios")
        self.assertEqual(ev2["verdict"], "blocked")


class TestOpenAICompatProvider(unittest.TestCase):
    def test_fallback_without_key(self):
        p = OpenAICompatProvider(api_key="")
        raw = p.plan("informe forense", "ctx", "tools")
        self.assertTrue(raw["steps"])
        self.assertIn("llm_fallback_reason", raw)

    def test_extract_json(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(_extract_json('prosa {"a": 2} más'), {"a": 2})
        self.assertIsNone(_extract_json("sin json"))


if __name__ == "__main__":
    unittest.main()
