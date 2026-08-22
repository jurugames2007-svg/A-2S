"""Pruebas del nivel determinista (fsm.py): máquina de estados sin LLM,
condiciones objetivas, jitter, escalado honesto de lo imprevisto y vigía
dirigido por eventos (interval/file/webhook)."""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request

from a2s.fsm import (FSMEngine, Watcher, escalation_goal, jitter,
                     registry_action_fn)
from a2s.tools import ToolRegistry


def _machine():
    return {
        "name": "m", "initial": "leer",
        "states": {
            "leer": {"action": {"tool": "eco", "params": {}}, "cooldown": [0.01, 0.02]},
            "clasificar": {"action": {"tool": "eco", "params": {}}, "cooldown": 0},
            "hecho": {"terminal": "done"},
            "vacio": {"terminal": "done"},
        },
        "transitions": [
            {"from": "leer", "to": "clasificar", "when": {"regex": "\\S"}},
            {"from": "leer", "to": "vacio", "when": {"always": True}},
            {"from": "clasificar", "to": "hecho", "when": {"regex": "[0-9a-f]{64}"}},
            {"from": "clasificar", "to": "hecho", "when": {"regex": "(?i)nota interna"}},
        ],
        "max_cycles": 10,
    }


class TestValidacion(unittest.TestCase):
    def test_maquina_valida_sin_errores(self):
        eng = FSMEngine(_machine())
        self.assertEqual(eng.validate(), [])

    def test_detecta_errores_de_especificacion(self):
        bad = _machine()
        bad["transitions"] = [{"from": "leer", "to": "NIRVANA", "when": {"always": True}}]
        errors = FSMEngine(bad).validate()
        self.assertTrue(any("NIRVANA" in e for e in errors))

    def test_estado_sin_salida_y_sin_terminal(self):
        bad = _machine()
        bad["transitions"] = []
        errors = FSMEngine(bad).validate()
        self.assertTrue(any("sin transiciones de salida" in e for e in errors))


class TestEjecucionDeterminista(unittest.TestCase):
    def _run(self, obs_by_state):
        def action(state, act):
            return obs_by_state.get(state, "")
        eng = FSMEngine(_machine(), action_fn=action, sleep_fn=lambda s: None)
        return eng.run()

    def test_camino_feliz_hasta_terminal(self):
        r = self._run({"leer": "archivo.txt",
                       "clasificar": "hash " + "a" * 64})
        self.assertEqual(r.states, ["leer", "clasificar", "hecho"])
        self.assertEqual((r.stopped, r.terminal), ("terminal", "done"))
        self.assertIn("nivel 0", r.resolved_by)

    def test_inbox_vacio_a_terminal_vacio(self):
        r = self._run({"leer": ""})                  # sin salida → always → vacio
        self.assertEqual(r.states, ["leer", "vacio"])
        self.assertEqual(r.terminal, "done")

    def test_imprevisto_escala_sin_adivinar(self):
        r = self._run({"leer": "algo.txt",
                       "clasificar": "gzorblax fractalino"})   # no encaja NADA
        self.assertEqual(r.stopped, "escalate")
        self.assertEqual(r.escalated["state"], "clasificar")
        self.assertIn("gzorblax", r.escalated["observation"])
        self.assertIn("escalado a nivel 1", r.resolved_by)

    def test_presupuesto_de_ciclos(self):
        m = _machine()
        m["transitions"] = [{"from": "leer", "to": "leer", "when": {"always": True}}]
        m["max_cycles"] = 5
        eng = FSMEngine(m, action_fn=lambda s, a: "x", sleep_fn=lambda t: None)
        r = eng.run()
        self.assertEqual(r.stopped, "budget")
        self.assertEqual(r.cycles, 5)

    def test_error_de_accion_es_observable_y_enutable(self):
        def action(state, act):
            if state == "leer":
                raise PermissionError("PERMISO DENEGADO: red deshabilitada")
            return "ok"
        m = _machine()
        m["transitions"] = [
            {"from": "leer", "to": "vacio", "when": {"regex": "PERMISO DENEGADO"}},
        ]
        eng = FSMEngine(m, action_fn=action, sleep_fn=lambda t: None)
        r = eng.run()
        self.assertEqual(r.states, ["leer", "vacio"])        # error enrutado
        self.assertIn("PERMISO DENEGADO", r.observations[0])

    def test_jitter_en_limites(self):
        for _ in range(50):
            v = jitter([1.0, 2.0])
            self.assertTrue(1.0 <= v <= 2.0)
        for _ in range(50):
            v = jitter(10)
            self.assertTrue(6.0 <= v <= 14.0)
        self.assertEqual(jitter(0), 0.0)
        self.assertEqual(jitter(None), 0.0)

    def test_sleeps_registrados_con_jitter(self):
        seen = []

        def action(state, act):
            return "nota interna" if state == "clasificar" else "x.txt"

        eng = FSMEngine(_machine(), action_fn=action, sleep_fn=seen.append)
        eng.run()
        self.assertEqual(len(seen), 1)                      # solo leer (clasificar cd=0)
        self.assertTrue(all(0.01 <= s <= 0.02 for s in seen))

    def test_goal_de_escalado_lleva_evidencia(self):
        g = escalation_goal("m", {"state": "clasificar", "observation": "gzorblax"})
        self.assertIn("clasificar", g)
        self.assertIn("gzorblax", g)
        self.assertIn("transición faltaba", g)


class TestAccionesConRegistroReal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = self.tmp.name
        os.makedirs(os.path.join(self.ws, "inbox"), exist_ok=True)
        self.reg = ToolRegistry(self.ws)

    def test_herramienta_desconocida_devuelve_error_enrutable(self):
        act = registry_action_fn(self.reg)
        out = act("s", {"tool": "inexistente", "params": {}})
        self.assertIn("ERROR: herramienta desconocida", out)

    def test_shell_real_dentro_del_workspace(self):
        with open(os.path.join(self.ws, "inbox", "a.txt"), "w") as fh:
            fh.write("hash " + "a" * 64 + "\n")
        act = registry_action_fn(self.reg)
        out = act("s", {"tool": "shell", "params": {"command": "ls -1 inbox/"}})
        self.assertIn("a.txt", out)
        out2 = act("s", {"tool": "shell",
                         "params": {"command": "grep -oE '[0-9a-f]{64}' inbox/a.txt"}})
        self.assertEqual(out2.strip(), "a" * 64)

    def test_maquina_real_de_punta_a_punta(self):
        with open(os.path.join(self.ws, "inbox", "evid.txt"), "w") as fh:
            fh.write("informe con verificador interno\n")
        with open(os.path.join(self.ws, "examples_dummy.json"), "w") as fh:
            json.dump({}, fh)
        spec = json.load(open(os.path.join(os.path.dirname(__file__), "..",
                                           "examples", "fsm.example.json"),
                              encoding="utf-8"))
        eng = FSMEngine(spec, action_fn=registry_action_fn(self.reg),
                        sleep_fn=lambda t: None)
        self.assertEqual(eng.validate(), [])
        r = eng.run()
        self.assertEqual(r.stopped, "terminal")
        self.assertEqual(r.states[0], "leer")
        self.assertIn("registrar", r.states)


class TestWatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = self.tmp.name

    def test_disparador_interval(self):
        spec = {"triggers": [{"type": "interval", "seconds": 0.1}]}
        got = []
        w = Watcher(spec, on_event=lambda e: got.append(e) or e,
                    sleep_fn=lambda s: None, poll=0.05)
        results = w.run(max_events=2, idle_timeout=3)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["type"] == "interval" for r in results))

    def test_disparador_file_detecta_archivo_nuevo(self):
        d = os.path.join(self.ws, "inbox")
        os.makedirs(d)
        spec = {"triggers": [{"type": "file", "path": d}]}
        got = []

        w = Watcher(spec, on_event=lambda e: got.append(e) or e,
                    sleep_fn=lambda s: None, poll=0.05)

        def producer():
            time.sleep(0.15)                     # deja pasar la línea base
            with open(os.path.join(d, "nuevo.txt"), "w") as fh:
                fh.write("dato")

        threading.Thread(target=producer, daemon=True).start()
        results = w.run(max_events=1, idle_timeout=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "file")
        self.assertEqual(results[0]["what"], "nuevo")

    def test_disparador_webhook(self):
        spec = {"triggers": [{"type": "webhook", "port": 8797}]}
        got = []
        w = Watcher(spec, on_event=lambda e: got.append(e) or e,
                    sleep_fn=lambda s: None, poll=0.05)

        def producer():
            time.sleep(0.2)
            req = urllib.request.Request("http://127.0.0.1:8797/dispara",
                                         data=b'{"x": 1}', method="POST")
            with urllib.request.urlopen(req, timeout=3) as resp:
                resp.read()

        threading.Thread(target=producer, daemon=True).start()
        results = w.run(max_events=1, idle_timeout=4)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "webhook")
        self.assertEqual(results[0]["path"], "/dispara")


if __name__ == "__main__":
    unittest.main()
