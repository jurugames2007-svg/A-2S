"""Pruebas del SORL (pool de recursos legítimos): scheduler, cuotas,
failover respetuoso con Retry-After, circuit breaker, fanout/DAG, telemetría
persistente y degradación al núcleo heurístico."""

import io
import json
import os
import tempfile
import time
import unittest
import urllib.error

from a2s.provider_pool import (PoolEndpoint, ProviderPool, RateWindow,
                               TaskScheduler, Telemetry, _parse_retry_after,
                               endpoints_from_config)


def _ok(content, tokens=10):
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": tokens // 2, "completion_tokens": tokens // 2}}


def _http_error(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "err", headers or {},
                                  io.BytesIO(b"{}"))


def _ep(name, tier="free", rpm=60, quality=0.8, caps=("general",)):
    return PoolEndpoint(name=name, base_url=f"http://pool.test/{name}",
                        api_key="k", model=f"m-{name}", cost_tier=tier,
                        rpm=rpm, quality=quality, capabilities=caps)


class TestRateWindow(unittest.TestCase):
    def test_limit_and_wait(self):
        win = RateWindow(2)
        self.assertTrue(win.try_acquire(now=0.0))
        self.assertTrue(win.try_acquire(now=0.5))
        self.assertFalse(win.try_acquire(now=1.0))          # ventana llena
        self.assertAlmostEqual(win.seconds_until_slot(now=1.0), 59.0, places=1)
        self.assertTrue(win.try_acquire(now=60.0))          # el primer hueco expiró

    def test_unlimited(self):
        win = RateWindow(0)
        for _ in range(100):
            self.assertTrue(win.try_acquire(now=0.0))
        self.assertEqual(win.seconds_until_slot(now=0.0), 0.0)


class TestRetryAfter(unittest.TestCase):
    def test_int_seconds(self):
        self.assertEqual(_parse_retry_after({"Retry-After": "60"}), 60.0)

    def test_http_date(self):
        when = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                             time.gmtime(time.time() + 30))
        got = _parse_retry_after({"Retry-After": when})
        self.assertIsNotNone(got)
        self.assertTrue(25 <= got <= 35)

    def test_absent(self):
        self.assertIsNone(_parse_retry_after({}))
        self.assertIsNone(_parse_retry_after(None))


class TestSchedulerStrategies(unittest.TestCase):
    def _pool_with_latency(self, strategy, specs):
        """specs: lista de (nombre, latencia_s, tier)."""
        eps = [_ep(n, tier=tier) for n, _lat, tier in specs]
        pool = ProviderPool(eps, strategy=strategy)
        for n, lat, _tier in specs:
            for _ in range(5):
                pool.telemetry.record(n, ok=True, latency=lat)
        return pool

    def _pick_name(self, pool, kind="general"):
        with pool._lock:
            picked = pool.scheduler.pick(pool._triples, kind=kind, exclude=set())
        return picked[0].name

    def test_cost_first_prefers_free(self):
        pool = self._pool_with_latency("cost_first",
                                       [("caro", 0.1, "paid"), ("gratis", 2.0, "free")])
        self.assertEqual(self._pick_name(pool), "gratis")

    def test_speed_first_prefers_fastest(self):
        pool = self._pool_with_latency("speed_first",
                                       [("lento", 4.0, "free"), ("rapido", 0.2, "paid")])
        self.assertEqual(self._pick_name(pool), "rapido")

    def test_multi_objective_balances(self):
        # gratis+lento vs pago+rápido: con pesos por defecto (coste 0.40 >
        # velocidad 0.25) gana el gratuito de calidad razonable.
        pool = self._pool_with_latency("multi_objective",
                                       [("a", 4.0, "free"), ("b", 0.2, "paid")])
        self.assertEqual(self._pick_name(pool), "a")
        # ... pero con coste empatado gana el rápido:
        pool2 = ProviderPool([_ep("x"), _ep("y")], strategy="multi_objective")
        for n, lat in (("x", 3.0), ("y", 0.1)):
            for _ in range(5):
                pool2.telemetry.record(n, ok=True, latency=lat)
        self.assertEqual(self._pick_name(pool2), "y")

    def test_round_robin_rotates(self):
        pool = self._pool_with_latency("round_robin",
                                       [("a", 1.0, "free"), ("b", 1.0, "free"),
                                        ("c", 1.0, "free")])
        picks = {self._pick_name(pool) for _ in range(6)}
        self.assertEqual(picks, {"a", "b", "c"})

    def test_capability_match(self):
        pool = ProviderPool([_ep("gen", caps=("general",)),
                             _ep("coder", caps=("code",), quality=0.95)],
                            strategy="multi_objective")
        for n in ("gen", "coder"):
            for _ in range(5):
                pool.telemetry.record(n, ok=True, latency=0.3)
        self.assertEqual(self._pick_name(pool, kind="code"), "coder")

    def test_saturated_endpoint_not_eligible(self):
        pool = ProviderPool([_ep("a", rpm=1)], strategy="cost_first")
        self.assertTrue(pool._windows["a"].try_acquire())
        # ventana llena → el único miembro no es elegible → fallback heurístico
        with pool._lock:
            picked = pool.scheduler.pick(pool._triples)
        self.assertIsNotNone(picked)
        self.assertEqual(picked[0].role, "fallback_only")


class TestFailover429(unittest.TestCase):
    """429 = señal de estado: cuarentena por Retry-After y migración de carga.
    (No hay reintentos en caliente ni evasión del límite: se respeta.)"""

    def test_failover_and_quarantine(self):
        state = {"a_calls": 0}

        def transport(ep, payload):
            if ep.name == "a":
                state["a_calls"] += 1
                raise _http_error(429, {"Retry-After": "60"})
            return _ok("desde-b")

        pool = ProviderPool([_ep("a"), _ep("b")], transport=transport)
        content, served_by = pool._chat([{"role": "user", "content": "hola"}])
        self.assertEqual(content, "desde-b")
        self.assertEqual(served_by, "b")
        self.assertEqual(state["a_calls"], 1)
        st = pool._states["a"]
        self.assertTrue(st.in_cooldown(time.monotonic()))
        self.assertGreater(st.cooldown_until - time.monotonic(), 50)
        # la telemetría registra el 429
        self.assertEqual(pool.telemetry.summary()["a"]["rate_limited"], 1)
        # la segunda petición ni toca a (sigue en cuarentena)
        content2, served2 = pool._chat([{"role": "user", "content": "otra"}])
        self.assertEqual((content2, served2), ("desde-b", "b"))
        self.assertEqual(state["a_calls"], 1)

    def test_backoff_exponencial_sin_retry_after(self):
        def transport(ep, payload):
            raise _http_error(429)          # sin cabecera Retry-After

        pool = ProviderPool([_ep("a")], transport=transport)
        st = pool._states["a"]
        pool._call_once(pool.endpoints[0], st, [], "general", 10, "")
        first = st.cooldown_until - time.monotonic()
        self.assertTrue(3 <= first <= 6)    # 5 * 2^0
        pool._call_once(pool.endpoints[0], st, [], "general", 10, "")
        second = st.cooldown_until - time.monotonic()
        self.assertGreater(second, first)   # 5 * 2^1

    def test_espera_cuota_en_lugar_de_degradar(self):
        """Si el único endpoint se satura con Retry-After corto, el pool espera
        lo que indica el servidor (respetando el límite) y reintenta."""
        state = {"calls": 0}

        def transport(ep, payload):
            state["calls"] += 1
            if state["calls"] == 1:
                raise _http_error(429, {"Retry-After": "1"})
            return _ok("recuperado")

        pool = ProviderPool([_ep("a")], transport=transport)
        t0 = time.monotonic()
        content, served = pool._chat([{"role": "user", "content": "x"}])
        self.assertEqual(content, "recuperado")
        self.assertGreaterEqual(time.monotonic() - t0, 0.9)   # esperó ~1s


class TestCircuitBreaker(unittest.TestCase):
    def test_open_after_consecutive_failures(self):
        def transport(ep, payload):
            raise _http_error(500)

        pool = ProviderPool([_ep("a")], transport=transport)
        st = pool._states["a"]
        for _ in range(3):
            pool._call_once(pool.endpoints[0], st, [], "general", 10, "")
        self.assertTrue(st.circuit_open(time.monotonic()))
        # circuito abierto → _chat degrada al fallback heurístico, no insiste
        content, why = pool._chat([{"role": "user", "content": "x"}])
        self.assertIsNone(content)

    def test_success_resets(self):
        def transport(ep, payload):
            return _ok("ok")

        pool = ProviderPool([_ep("a")], transport=transport)
        st = pool._states["a"]
        st.consecutive_failures = 2
        pool._call_once(pool.endpoints[0], st, [], "general", 10, "")
        self.assertEqual(st.consecutive_failures, 0)


class TestDegradacionHeuristica(unittest.TestCase):
    def test_plan_degrada_cuando_todo_falla(self):
        def transport(ep, payload):
            raise OSError("red caída")

        pool = ProviderPool([_ep("a"), _ep("b")], transport=transport)
        raw = pool.plan("Produce un informe forense", "ctx", "tools")
        self.assertTrue(raw["steps"])                        # plan heurístico
        self.assertIn("llm_fallback_reason", raw)

    def test_plan_llm_cuando_hay_servicio(self):
        plan_json = json.dumps({
            "strategy": "s", "steps": [{
                "id": "s1", "goal": "g", "approach": "a", "tool": "shell",
                "params": {"command": "ls"}, "success_criteria": ["x"],
                "depends_on": []}]})

        def transport(ep, payload):
            return _ok(plan_json)

        pool = ProviderPool([_ep("a")], transport=transport)
        raw = pool.plan("objetivo", "ctx", "tools")
        self.assertEqual(raw["steps"][0]["id"], "s1")
        self.assertEqual(raw["pool_provider"], "a")

    def test_evaluate_valida_verdicto(self):
        def transport(ep, payload):
            return _ok('{"score": 0.9, "verdict": "nonsense", "reason": "x"}')

        pool = ProviderPool([_ep("a")], transport=transport)
        ev = pool.evaluate("paso", "obs", "crit")
        self.assertIn(ev["verdict"], ("success", "failed", "blocked"))  # fallback

    def test_goal_check_estricto(self):
        def transport(ep, payload):
            return _ok('{"achieved": true, "reason": "verificado"}')

        pool = ProviderPool([_ep("a")], transport=transport)
        ok, reason = pool.goal_check("objetivo", "evidencia")
        self.assertTrue(ok)
        self.assertEqual(reason, "verificado")


class TestFanout(unittest.TestCase):
    def test_reparto_entre_endpoints_respetando_cuota(self):
        served = []
        lock_used = []

        def transport(ep, payload):
            served.append(ep.name)
            return _ok(f"r-{ep.name}-{payload['messages'][-1]['content']}")

        pool = ProviderPool([_ep("a", rpm=10), _ep("b", rpm=10)],
                            strategy="round_robin", transport=transport)
        results = pool.fanout([f"tarea-{i}" for i in range(8)])
        self.assertTrue(all(r is not None for r in results))
        self.assertEqual(set(served), {"a", "b"})          # ambos trabajaron
        # cada endpoint respetó su ventana: ≤ 10 peticiones/min
        self.assertLessEqual(served.count("a"), 10)
        self.assertLessEqual(served.count("b"), 10)

    def test_cuota_agotada_reparte_al_resto(self):
        def transport(ep, payload):
            return _ok(f"r-{ep.name}")

        pool = ProviderPool([_ep("a", rpm=2), _ep("b", rpm=100)],
                            strategy="cost_first", transport=transport)
        results = pool.fanout([f"t{i}" for i in range(6)])
        self.assertTrue(all(r is not None for r in results))
        # 'a' (gratis, cost_first) se agota en 2 y 'b' absorbe el resto
        calls_a = sum(1 for _ in range(0))
        win_a = pool._windows["a"].used()
        self.assertLessEqual(win_a, 2)
        self.assertEqual(len(results), 6)


class TestDag(unittest.TestCase):
    def test_orden_topologico_y_agregacion(self):
        order = []

        def transport(ep, payload):
            user_msg = payload["messages"][-1]["content"]
            order.append(user_msg)
            return _ok(f"hecho:{user_msg}")

        pool = ProviderPool([_ep("a", rpm=100)], transport=transport)
        tasks = [
            {"id": "A", "prompt": "A"},
            {"id": "B", "prompt": "B", "depends_on": ["A"]},
            {"id": "C", "prompt": "C", "depends_on": ["A"]},
            {"id": "D", "prompt": "D", "depends_on": ["B", "C"]},
        ]
        out = pool.execute_dag(
            tasks, aggregate=lambda r: [r["results"][k] for k in ("A", "B", "C", "D")])
        self.assertEqual(out["failed"], [])
        self.assertEqual(out["executed"], 4)
        self.assertEqual(out["aggregate"],
                         ["hecho:A", "hecho:B", "hecho:C", "hecho:D"])
        self.assertEqual(order[0], "A")                     # A primero
        self.assertEqual(order[-1], "D")                    # D al final
        self.assertEqual(set(order[1:3]), {"B", "C"})

    def test_ciclo_detectado(self):
        pool = ProviderPool([_ep("a")], transport=lambda ep, p: _ok("x"))
        with self.assertRaises(ValueError):
            pool.execute_dag([
                {"id": "A", "prompt": "a", "depends_on": ["B"]},
                {"id": "B", "prompt": "b", "depends_on": ["A"]},
            ])

    def test_dependencia_fallida_se_omite(self):
        def transport(ep, payload):
            if payload["messages"][-1]["content"] == "A":
                raise _http_error(500)
            return _ok("ok")

        pool = ProviderPool([_ep("a")], transport=transport)
        out = pool.execute_dag([
            {"id": "A", "prompt": "A"},
            {"id": "B", "prompt": "B", "depends_on": ["A"]},
        ])
        self.assertEqual(out["failed"], ["A", "B"])         # honestidad ante fallos
        self.assertIsNone(out["results"]["B"])


class TestTelemetriaPersistente(unittest.TestCase):
    def test_aprendizaje_entre_ejecuciones(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name

        def transport(ep, payload):
            time.sleep(0.01)
            return _ok("x")

        pool1 = ProviderPool([_ep("a"), _ep("b")], workspace=ws, transport=transport)
        for _ in range(4):
            pool1.chat("prompt", kind="general")
        pool1.close()

        path = os.path.join(ws, ".a2s", "pool")
        self.assertTrue(os.path.isfile(os.path.join(path, "telemetry.jsonl")))
        self.assertTrue(os.path.isfile(os.path.join(path, "state.json")))

        # segunda ejecución: el scheduler hereda latencias/tasas aprendidas
        pool2 = ProviderPool([_ep("a"), _ep("b")], workspace=ws, transport=transport)
        summary = pool2.telemetry.summary()
        self.assertGreaterEqual(summary["a"]["total"], 1)
        self.assertIsNotNone(summary["a"]["p50_ms"])
        pool2.close()


class TestConfiguracion(unittest.TestCase):
    def test_json_con_expansion_de_entorno(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "pool.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"strategy": "cost_first", "endpoints": [
                {"name": "x", "base_url": "http://x", "api_key": "${VAR_QUE_EXISTE_X}",
                 "model": "m", "cost_tier": "free"},
                {"name": "y", "base_url": "http://y", "api_key": "${VAR_QUE_FALTA_XYZ}",
                 "model": "m"},
            ]}, fh)
        os.environ["VAR_QUE_EXISTE_X"] = "clave"
        try:
            eps, cfg = endpoints_from_config(path)
            self.assertEqual(cfg["strategy"], "cost_first")
            by = {e.name: e for e in eps}
            self.assertTrue(by["x"].active)
            self.assertEqual(by["x"].api_key, "clave")
            self.assertFalse(by["y"].active)                 # sin clave → desactivado
            self.assertIn("VAR_QUE_FALTA_XYZ", by["y"].disabled_reason)
        finally:
            del os.environ["VAR_QUE_EXISTE_X"]

    def test_dag_invalido_dependencia_desconocida(self):
        pool = ProviderPool([_ep("a")], transport=lambda e, p: _ok("x"))
        with self.assertRaises(ValueError):
            pool.execute_dag([{"id": "A", "prompt": "a", "depends_on": ["NOPE"]}])

    def test_status_estructura(self):
        pool = ProviderPool([_ep("a")], strategy="cost_first")
        st = pool.status()
        self.assertEqual(st["strategy"], "cost_first")
        names = [e["name"] for e in st["endpoints"]]
        self.assertIn("a", names)
        self.assertIn("heuristic", names)                    # fallback presente
        self.assertEqual(st["totals"]["endpoints_active"], 1)


class TestAprendizajeCuotaYPesos(unittest.TestCase):
    """El bucle Aprender→Optimizar: rpm efectivo observado y micro-ajuste de
    pesos, persistidos en el snapshot y aplicados en la siguiente ejecución."""

    def test_aprende_rpm_real_y_elimina_429(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name
        # "servidor" que admite 5 peticiones/minuto de verdad
        state = {"calls": 0}

        def server_a(ep, payload):
            state["calls"] += 1
            if state["calls"] > 5:
                raise _http_error(429, {"Retry-After": "60"})
            return _ok("ok")

        pool1 = ProviderPool([_ep("a", rpm=100)], workspace=ws, transport=server_a)
        # max_parallel=1 → determinista: 5 ok, la 6ª recibe 429 (used=6)
        # → aprende rpm efectivo = int(6 * 0.8) = 4
        pool1.fanout([f"p{i}" for i in range(12)], max_parallel=1)
        learned = pool1.telemetry.learned_rpm.get("a")
        self.assertEqual(learned, 4)
        pool1.close()

        state2 = {"calls": 0, "429": 0}

        def server_a2(ep, payload):
            state2["calls"] += 1
            if state2["calls"] > 5:
                state2["429"] += 1
                raise _http_error(429, {"Retry-After": "60"})
            return _ok("ok")

        pool2 = ProviderPool([_ep("a", rpm=100)], workspace=ws, transport=server_a2)
        # la ventana arranca ya auto-limitada al rpm aprendido
        self.assertEqual(pool2._windows["a"].rpm, 4)
        pool2.fanout([f"q{i}" for i in range(12)], max_parallel=1)
        self.assertEqual(state2["429"], 0)                  # cero saturaciones
        self.assertEqual(state2["calls"], 4)                # respetó su cuota real
        pool2.close()

    def test_pesos_sugeridos_se_aplican_si_no_hay_pesos_fijados(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name

        def siempre_429(ep, payload):
            raise _http_error(429, {"Retry-After": "60"})

        pool1 = ProviderPool([_ep("a"), _ep("b")], workspace=ws,
                             transport=siempre_429)
        for _ in range(12):            # sin pasar por _chat: sin esperas
            pool1._call_once(pool1.endpoints[0], pool1._states["a"],
                             [{"role": "user", "content": "x"}], "general", 10, "")
        pool1.close()
        sug = pool1.telemetry.weight_suggestions
        self.assertGreater(sug.get("quota_risk", 0), 0.05)  # subió el riesgo
        self.assertLess(sug.get("cost", 1.0), 0.40)         # bajó el coste

        def ok_t(ep, payload):
            return _ok("ok")

        pool2 = ProviderPool([_ep("a")], workspace=ws, transport=ok_t)
        self.assertAlmostEqual(pool2.scheduler.weights["quota_risk"],
                               sug["quota_risk"])
        # pesos explícitos del operador: bloquean el ajuste aprendido
        pool3 = ProviderPool([_ep("a")], workspace=ws, weights={"cost": 1.0},
                             transport=ok_t)
        self.assertEqual(pool3.scheduler.weights["cost"], 1.0)
        self.assertAlmostEqual(pool3.scheduler.weights["quota_risk"], 0.05)

    def test_recuperacion_gradual_del_rpm(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tel = Telemetry(tmp.name)
        tel.learned_rpm["a"] = 4
        tel.clean_since_429["a"] = 25                        # ≥20 éxitos limpios
        tel.save_snapshot(configured_rpm={"a": 100})
        tel.close()
        tel2 = Telemetry(tmp.name)
        self.assertEqual(tel2.learned_rpm.get("a"), 5)       # +1 rpm recuperado
        self.assertEqual(tel2.effective_rpm("a", 100), 5)

    def test_rpm_declarado_ilimitado_pero_satura(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tel = Telemetry(tmp.name)
        tel.note_rate_limit_hit("x", window_used=8)
        self.assertEqual(tel.effective_rpm("x", 0), 6)       # declarado 0=∞
        self.assertEqual(tel.effective_rpm("x", 30), 6)      # min(30, 6)
        tel.close()


class TestCapacidadMedida(unittest.TestCase):
    """La aptitud por tipo de tarea se MIDE (JSON utilizable por kind), se
    mezcla con el prior declarado y reordena el scheduler."""

    _VALID_PLAN = json.dumps({
        "strategy": "s", "steps": [{"id": "s1", "goal": "g", "approach": "a",
                                    "tool": "shell", "params": {"command": "ls"},
                                    "success_criteria": ["x"], "depends_on": []}]})

    def test_prosa_sin_json_registra_capacidad_nula(self):
        def eco(ep, payload):
            return _ok("eco sin json")            # modelo que no sigue esquema

        pool = ProviderPool([_ep("eco"), _ep("bueno")], transport=eco)
        for _ in range(3):
            obj = pool._structured("Devuelve JSON: {...}", "plan", {"steps": []})
            self.assertNotIn("pool_provider", obj)   # fallback sin atribución LLM
        # quien haya servido la prosa quedó medido a la baja (ok=0)
        plans = [c for by in pool.telemetry.caps.values()
                 for k, c in by.items() if k == "plan"]
        self.assertTrue(plans)
        self.assertTrue(all(c["ok"] == 0 for c in plans))

    def test_plan_valido_registra_y_devuelve_llm(self):
        pool = ProviderPool([_ep("a"), _ep("b")],
                            transport=lambda e, p: _ok(self._VALID_PLAN))
        raw = pool.plan("objetivo", "ctx", "tools")
        self.assertTrue(raw["steps"])
        served = raw["pool_provider"]
        c = pool.telemetry.caps[served]["plan"]
        self.assertEqual((c["ok"], c["total"]), (1, 1))

    def test_plan_esquema_invalido_registra_y_degrada(self):
        pool = ProviderPool([_ep("a"), _ep("b")],
                            transport=lambda e, p: _ok('{"strategy": "sin steps"}'))
        raw = pool.plan("objetivo", "ctx", "tools")
        self.assertTrue(raw["steps"])                  # plan heurístico (fallback)
        plans = [c for by in pool.telemetry.caps.values()
                 for k, c in by.items() if k == "plan"]
        self.assertTrue(plans)                         # alguien quedó medido
        self.assertTrue(all(c["ok"] == 0 for c in plans))

    def test_scheduler_prefiere_medido_bueno(self):
        pool = ProviderPool([_ep("malo"), _ep("bueno")])
        for _ in range(6):
            pool.telemetry.record_capability("malo", "plan", False)
        with pool._lock:
            picked = pool.scheduler.pick(pool._triples, kind="plan")
        self.assertEqual(picked[0].name, "bueno")
        # ... y para kinds sin medidas vuelve al prior declarado (ambos valen)
        with pool._lock:
            picked2 = pool.scheduler.pick(pool._triples, kind="general")
        self.assertIn(picked2[0].name, ("malo", "bueno"))

    def test_puerta_de_incompetencia_es_kind_especifica(self):
        """Un endpoint medido incapaz de planificar no recibe planificaciones
        NI SIQUERA siendo gratis (cost_first)… pero sigue sirviendo otros kinds."""
        pool = ProviderPool([_ep("gratis_malo"), _ep("caro_bueno")],
                            strategy="cost_first")
        pool.endpoints[1].cost_tier = "paid"
        for _ in range(6):
            pool.telemetry.record_capability("gratis_malo", "plan", False)
        with pool._lock:
            picked = pool.scheduler.pick(pool._triples, kind="plan")
        self.assertEqual(picked[0].name, "caro_bueno")   # la puerta vence al coste
        with pool._lock:
            picked2 = pool.scheduler.pick(pool._triples, kind="general")
        self.assertEqual(picked2[0].name, "gratis_malo") # sin medidas → gratis gana

    def test_puerta_no_bloquea_si_excluye_a_todos(self):
        pool = ProviderPool([_ep("a")], strategy="cost_first")
        for _ in range(10):
            pool.telemetry.record_capability("a", "plan", False)
        with pool._lock:
            picked = pool.scheduler.pick(pool._triples, kind="plan")
        self.assertIsNotNone(picked)                     # sigue habiendo ruta

    def test_suavizado_bayesiano_del_prior(self):
        tel = Telemetry(None)
        self.assertIsNone(tel.capability_score("x", "plan", 0.8))   # sin datos
        for _ in range(4):
            tel.record_capability("x", "plan", False)
        # (0 + 3*0.8) / (4 + 3) ≈ 0.343: cae pero no a cero (prior suaviza)
        self.assertAlmostEqual(tel.capability_score("x", "plan", 0.8),
                               2.4 / 7.0, places=3)

    def test_caps_persisten_entre_ejecuciones(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name
        pool1 = ProviderPool([_ep("a")], workspace=ws,
                             transport=lambda e, p: _ok("prosa"))
        pool1.plan("objetivo", "ctx", "tools")
        pool1.close()
        pool2 = ProviderPool([_ep("a")], workspace=ws,
                             transport=lambda e, p: _ok("prosa"))
        c = pool2.telemetry.caps.get("a", {}).get("plan")
        self.assertIsNotNone(c)
        self.assertEqual(c["total"], 1)
        self.assertEqual(c["ok"], 0)

    def test_goal_check_y_evaluate_registran(self):
        def transport(ep, payload):
            user = payload["messages"][-1]["content"]
            if "achieved" in user:
                return _ok('{"achieved": true, "reason": "ok"}')
            if "verdict" in user:
                return _ok('{"score": 0.9, "verdict": "success", "reason": "r"}')
            return _ok("prosa")

        pool = ProviderPool([_ep("a")], transport=transport)
        ok, _ = pool.goal_check("objetivo", "evidencia")
        self.assertTrue(ok)
        ev = pool.evaluate("paso", "obs", "crit")
        self.assertEqual(ev["verdict"], "success")
        caps = pool.telemetry.caps["a"]
        self.assertEqual(caps["goal_check"]["ok"], 1)
        self.assertEqual(caps["evaluate"]["ok"], 1)


class TestPoolComoProviderAuto(unittest.TestCase):
    def test_get_provider_pool(self):
        from a2s.providers import get_provider
        got = get_provider("pool", config=None)
        self.assertEqual(got.name, "pool")
        self.assertTrue(any(e.role == "fallback_only" for e in got.endpoints))


if __name__ == "__main__":
    unittest.main()
