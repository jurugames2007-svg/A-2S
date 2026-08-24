"""Radar OSS: crecimiento por metadatos públicos, sin ejecutar código ajeno."""

import json
import os
import tempfile
import unittest

from a2s.ecosystem import EcosystemRadar, OPEN_SOURCE_LICENSES
from a2s.learner import GitHubClient


def _github(items):
    def transport(url, headers):
        if "/search/repositories" in url:
            return 200, {"X-RateLimit-Remaining": "9"}, json.dumps(
                {"items": items}).encode()
        return 404, {}, b"{}"
    return GitHubClient(token="fake", transport=transport, max_calls=20)


class TestEcosystemRadar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_semillas_incluyen_omniroute_con_procedencia_auditable(self):
        radar = EcosystemRadar(self.tmp.name, github=_github([]))
        by = {p.repo: p for p in radar.projects}
        self.assertIn("diegosouzapw/OmniRoute", by)
        self.assertEqual(by["diegosouzapw/OmniRoute"].license, "MIT")
        self.assertIn("preview de ruta explicable",
                      by["diegosouzapw/OmniRoute"].lessons)
        snap = radar.snapshot()
        self.assertTrue(snap["open_source_only"])
        self.assertFalse(snap["code_executed"])

    def test_scan_agrega_solo_licencia_abierta_y_relevante(self):
        items = [
            {"full_name": "org/open-router", "html_url": "https://github.com/org/open-router",
             "description": "Open source LLM gateway router with observability",
             "stargazers_count": 500, "language": "Rust",
             "license": {"spdx_id": "Apache-2.0"}, "updated_at": "2026-08-20T00:00:00Z"},
            {"full_name": "org/closed-router", "html_url": "https://github.com/org/closed-router",
             "description": "LLM gateway router", "stargazers_count": 999,
             "license": None, "updated_at": "2026-08-20T00:00:00Z"},
            {"full_name": "org/calendar", "html_url": "https://github.com/org/calendar",
             "description": "simple calendar", "stargazers_count": 5,
             "license": {"spdx_id": "MIT"}, "updated_at": "2026-08-20T00:00:00Z"},
        ]
        radar = EcosystemRadar(self.tmp.name, github=_github(items))
        report = radar.scan(query="llm router", limit_per_query=5)
        self.assertEqual(report["added"], ["org/open-router"])
        rejected = {r["repo"]: r["reason"] for r in report["rejected"]}
        self.assertIn("licencia", rejected["org/closed-router"])
        self.assertIn("relevancia", rejected["org/calendar"])
        self.assertFalse(report["code_executed"])

    def test_persistencia_filtra_licencia_manipulada(self):
        radar = EcosystemRadar(self.tmp.name, github=_github([]))
        path = radar.path
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["projects"].append({
            "repo": "x/cerrado", "url": "https://github.com/x/cerrado",
            "license": "LicenseRef-Proprietary", "description": "LLM router"})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        loaded = EcosystemRadar(self.tmp.name, github=_github([]))
        self.assertNotIn("x/cerrado", {p.repo for p in loaded.projects})
        self.assertTrue(all(p.license in OPEN_SOURCE_LICENSES for p in loaded.projects))

    def test_scan_actualiza_sin_duplicar(self):
        item = {"full_name": "diegosouzapw/OmniRoute",
                "html_url": "https://github.com/diegosouzapw/OmniRoute",
                "description": "LLM gateway router with observability",
                "stargazers_count": 60000, "language": "TypeScript",
                "license": {"spdx_id": "MIT"}, "updated_at": "2026-08-22T00:00:00Z"}
        radar = EcosystemRadar(self.tmp.name, github=_github([item]))
        before = len(radar.projects)
        report = radar.scan(query="omniroute")
        self.assertEqual(len(radar.projects), before)
        self.assertIn("diegosouzapw/OmniRoute", report["updated"])
        rec = next(p for p in radar.projects if p.repo == "diegosouzapw/OmniRoute")
        self.assertEqual(rec.stars, 60000)
        self.assertIn("preview de ruta explicable", rec.lessons)


if __name__ == "__main__":
    unittest.main()
