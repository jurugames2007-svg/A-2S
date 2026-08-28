"""Fuzz determinista de invariantes críticos (stdlib random, seeds reproducibles)."""

import random
import string
import time
import unittest

from a2s.ecosystem import EcosystemRadar
from a2s.provider_pool import PoolEndpoint, ProviderPool, RateWindow


class TestFuzzRateWindow(unittest.TestCase):
    def test_mil_secuencias_nunca_superan_rpm(self):
        rng = random.Random(19001)
        for _case in range(1000):
            rpm = rng.randint(1, 20)
            window = RateWindow(rpm)
            now = time.monotonic()
            for _ in range(rng.randint(5, 60)):
                now += rng.random() * 8
                before = window.used()
                accepted = window.try_acquire(now)
                self.assertLessEqual(window.used(), rpm)
                if not accepted:
                    self.assertGreaterEqual(before, rpm)
                self.assertGreaterEqual(window.seconds_until_slot(now), 0.0)


class TestFuzzRoutePreview(unittest.TestCase):
    def test_quinientos_pools_preview_no_muta_cuota(self):
        rng = random.Random(19002)
        tiers = ("free", "cheap", "paid")
        kinds = ("general", "plan", "code", "evaluate", "summarize")
        for case in range(500):
            endpoints = []
            for index in range(rng.randint(1, 6)):
                endpoints.append(PoolEndpoint(
                    name=f"e-{case}-{index}", base_url="http://example.invalid/v1",
                    api_key="x", model="m", cost_tier=rng.choice(tiers),
                    quality=rng.random(), rpm=rng.randint(0, 8),
                    capabilities=(rng.choice(kinds),)))
            pool = ProviderPool(endpoints, strategy=rng.choice(
                ("round_robin", "cost_first", "speed_first", "multi_objective")))
            try:
                for endpoint in endpoints:
                    window = pool._windows[endpoint.name]
                    for _ in range(rng.randint(0, max(1, endpoint.rpm))):
                        window.try_acquire()
                    if rng.random() < 0.08:
                        pool._states[endpoint.name].cooldown_until = time.monotonic() + 30
                before = {name: win.used() for name, win in pool._windows.items()}
                preview = pool.route_preview(rng.choice(kinds))
                after = {name: win.used() for name, win in pool._windows.items()}
                self.assertEqual(before, after)
                self.assertFalse(preview["live_request_executed"])
                selected = [row for row in preview["candidates"] if row["selected"]]
                self.assertLessEqual(len(selected), 1)
                if preview["selected"]:
                    self.assertEqual(len(selected), 1)
                for row in preview["candidates"]:
                    self.assertIn(row["quota_state"],
                                  ("healthy", "approaching_limit", "exhausted", "unknown"))
                    self.assertTrue(all(0.0 <= value <= 1.0
                                        for value in row["factors"].values()))
            finally:
                pool.close()


class TestFuzzEcosystemScore(unittest.TestCase):
    def test_mil_descripciones_score_acotado(self):
        rng = random.Random(19003)
        alphabet = string.ascii_letters + string.digits + " -_/áé"
        for _ in range(1000):
            description = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
            score = EcosystemRadar._score(description, rng.randint(0, 10**8),
                                          rng.choice(("", "bad", "2026-08-22", "1970-01-01")))
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
