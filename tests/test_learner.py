"""Pruebas del Ciclo de Enriquecimiento (learner.py): búsqueda en GitHub con
cuotas respetadas, fichas de conocimiento, fronteras de seguridad y el loop
intentar→aprender→reintentar con verificación objetiva."""

import json
import os
import tempfile
import unittest

from a2s.learner import (BudgetExhausted, GitHubClient, Learner,
                         extractive_summary, gap_query_heuristic, load_cards)

REPO_A = {"full_name": "pytest-dev/pytest", "html_url": "https://github.com/pytest-dev/pytest",
          "description": "Framework de testing", "stargazers_count": 12000,
          "language": "Python", "license": {"spdx_id": "MIT"}, "updated_at": "2026-01-01T00:00:00Z"}
REPO_B = {"full_name": "pandas-dev/pandas", "html_url": "https://github.com/pandas-dev/pandas",
          "description": "Análisis de datos", "stargazers_count": 40000,
          "language": "Python", "license": {"spdx_id": "BSD-3-Clause"}, "updated_at": "2026-01-01T00:00:00Z"}

README_A = ("# pytest\n\nFramework de testing maduro. Escribe tests con assert "
            "simple. Usa fixtures para preparar el entorno. Corre con pytest desde la CLI.\n"
            "## Instalación\n\npip install pytest")
README_B = ("# pandas\n\nDataFrames para análisis tabular. Lee CSV con read_csv. "
            "Agrega con groupby.")


def _fake_github(sleeps=None, plans=None):
    """Transporte falso: (url, headers) → (status, headers, body).
    ``plans``: respuestas programadas para las PRIMERAS peticiones
    (una vez consumidas, comportamiento normal)."""
    state = {"i": 0}
    plans = plans or []

    def transport(url, headers):
        if state["i"] < len(plans):
            status, hdrs, body = plans[state["i"]]
            state["i"] += 1
            return status, hdrs, body
        if url.endswith("/search/repositories") or "/search/repositories?" in url:
            return 200, {"X-RateLimit-Remaining": "25"}, json.dumps(
                {"items": [REPO_A, REPO_B]}).encode()
        if "/readme" in url:
            which = README_A if "pytest" in url else README_B
            return 200, {}, which.encode()
        return 404, {}, b"{}"

    return GitHubClient(token="fake", transport=transport,
                        sleep_fn=(sleeps.append if sleeps is not None else None))


class TestGitHubClient(unittest.TestCase):
    def test_search_parsea_hits_con_licencia(self):
        gh = _fake_github()
        hits = gh.search_repositories("python testing", per_page=2)
        self.assertEqual([h.full_name for h in hits],
                         ["pytest-dev/pytest", "pandas-dev/pandas"])
        self.assertEqual(hits[0].license, "MIT")
        self.assertEqual(hits[1].stars, 40000)

    def test_fetch_readme_raw(self):
        gh = _fake_github()
        text = gh.fetch_readme("pytest-dev/pytest")
        self.assertIn("fixtures", text)

    def test_busca_pdf_publico_y_recupera_licencia_repo(self):
        def transport(url, headers):
            if "/search/code?" in url:
                return 200, {}, json.dumps({"items": [{
                    "name": "paper.pdf", "path": "docs/paper.pdf",
                    "html_url": "https://github.com/org/repo/blob/abc/docs/paper.pdf",
                    "repository": {"full_name": "org/repo"},
                }]}).encode()
            if "/repos/org/repo" in url:
                return 200, {}, json.dumps({"license": {"spdx_id": "MIT"}}).encode()
            return 404, {}, b"{}"
        gh = GitHubClient(token="fake", transport=transport)
        hits = gh.search_public_pdfs("agent evaluation", limit=2)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].license, "MIT")
        self.assertEqual(hits[0].raw_url,
                         "https://raw.githubusercontent.com/org/repo/abc/docs/paper.pdf")

    def test_rate_limit_del_servidor_se_respeta(self):
        sleeps = []
        plans = [(403, {"X-RateLimit-Remaining": "0", "Retry-After": "2"}, b"limit")]
        gh = _fake_github(sleeps=sleeps, plans=plans)
        text = gh.fetch_readme("pytest-dev/pytest")   # 1er intento 403 → espera → 200
        self.assertIn("fixtures", text)
        self.assertEqual(sleeps, [2.0])               # esperó lo que dijo el servidor

    def test_rate_limit_persistente_para_honesto(self):
        sleeps = []
        plans = [(403, {"Retry-After": "1"}, b"limit"),
                 (403, {"Retry-After": "1"}, b"limit")]
        gh = _fake_github(sleeps=sleeps, plans=plans)
        with self.assertRaises(BudgetExhausted):
            gh.fetch_readme("pytest-dev/pytest")
        self.assertEqual(sleeps, [1.0])               # esperó una vez, no insistió

    def test_espera_larga_aborta(self):
        sleeps = []
        plans = [(403, {"Retry-After": "3600"}, b"limit")]
        gh = _fake_github(sleeps=sleeps, plans=plans)
        with self.assertRaises(BudgetExhausted):
            gh.fetch_readme("pytest-dev/pytest")
        self.assertEqual(sleeps, [])

    def test_presupuesto_de_llamadas(self):
        gh = _fake_github()
        gh.max_calls = 2
        gh.search_repositories("a")
        gh.search_repositories("b")
        with self.assertRaises(BudgetExhausted):
            gh.search_repositories("c")


class TestHeuristicasStdlib(unittest.TestCase):
    def test_extractive_summary(self):
        text = ("# Lib X. Herramientas. ## Uso. Es una librería que hace cosas. "
                "Soporta archivos grandes. Es rápida.")
        s = extractive_summary(text)
        self.assertTrue(s)
        self.assertLessEqual(len(s), 700)

    def test_gap_query_extrae_terminos(self):
        q = gap_query_heuristic("extraer metadatos de imágenes PNG",
                                "Error: no module named PIL")
        self.assertIn("PIL", q)
        self.assertNotIn(" the ", q)


class TestLearner(unittest.TestCase):
    def _learner(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = tmp.name
        lr = Learner(workspace=ws, github=_fake_github(), **kw)
        self.addCleanup(lambda: lr.cards.clear())
        return lr, ws

    def test_research_crea_y_persiste_fichas(self):
        lr, ws = self._learner()
        cards = lr.research("python testing framework", topic="testing")
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].license, "MIT")
        self.assertTrue(cards[0].summary)
        self.assertTrue(cards[0].url.startswith("https://github.com/"))
        # persistidas y recargables
        loaded = load_cards(ws)
        self.assertEqual({c.repo for c in loaded},
                         {"pytest-dev/pytest", "pandas-dev/pandas"})

    def test_research_no_duplica_repos(self):
        lr, _ = self._learner()
        first = lr.research("testing")
        second = lr.research("testing otra vez")
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 0)

    def test_readme_prohibido_se_rechaza(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bad = dict(REPO_A)
        bad["full_name"] = "mal/malware-tool"
        bad["description"] = "herramienta de exfiltración de credenciales"

        def transport(url, headers):
            if "/search/" in url:
                return 200, {}, json.dumps({"items": [bad]}).encode()
            return 200, {}, ("# malware. Stealer que hace exfiltración de "
                             "password.").encode()
        gh = GitHubClient(token="x", transport=transport)
        lr = Learner(workspace=tmp.name, github=gh)
        cards = lr.research("robbed creds")           # el contenido manda
        self.assertEqual(cards, [])
        self.assertTrue(any("rejected" in e for e in lr.cycle_log))

    def test_knowledge_context_y_mark_result(self):
        lr, _ = self._learner()
        lr.research("testing")
        ctx = lr.knowledge_context()
        self.assertIn("### pytest-dev/pytest", ctx)
        self.assertIn("nunca ejecutes código", ctx)    # frontera visible
        self.assertTrue(all(c.used == 1 for c in lr.cards))
        lr.mark_result(won=True)
        self.assertTrue(any(c.wins == 1 for c in lr.cards))

    def test_loop_hasta_ser_capaz(self):
        lr, _ = self._learner()
        attempts = {"n": 0, "knowledge": []}

        def attempt(knowledge: str):
            attempts["n"] += 1
            attempts["knowledge"].append(knowledge)
            return {"ok": attempts["n"] >= 2}          # falla el 1er intento

        rep = lr.enrich_until_capable(
            "resolver testing en python", attempt, verifier=lambda r: r["ok"],
            max_cycles=3)
        self.assertTrue(rep["capable"])
        self.assertEqual(attempts["n"], 2)
        # el 2º intento llegó con conocimiento asimilado
        self.assertEqual(attempts["knowledge"][0], "")
        self.assertIn("###", attempts["knowledge"][1])
        # y las fichas ganaron
        self.assertTrue(any(c.wins >= 1 for c in lr.cards))

    def test_loop_presupuesto_agotado_es_honesto(self):
        lr, _ = self._learner()
        lr.github.max_calls = 0                        # sin presupuesto de API

        rep = lr.enrich_until_capable(
            "objetivo imposible", attempt=lambda k: {"ok": False},
            verifier=lambda r: r["ok"], max_cycles=2)
        self.assertFalse(rep["capable"])
        self.assertIn("NO verificado", rep["confidence"])

    def test_gap_detection_con_pool(self):
        from a2s.provider_pool import PoolEndpoint, ProviderPool

        def transport(ep, payload):
            return {"choices": [{"message": {
                "content": "python pdf metadata extraction library"}}],
                "usage": {}}
        eps = [PoolEndpoint(name="llm", base_url="http://x", api_key="k",
                            model="m", capabilities=("general",))]
        pool = ProviderPool(eps, transport=transport)
        lr, _ = self._learner(pool=pool)
        gap = lr.detect_gap("procesar PDFs", "no sé extraer metadatos")
        self.assertEqual(gap, "python pdf metadata extraction library")

    def test_research_con_pool_fanout(self):
        from a2s.provider_pool import PoolEndpoint, ProviderPool

        def transport(ep, payload):
            user = payload["messages"][-1]["content"]
            repo = "pytest" if "pytest" in user else "pandas"
            return {"choices": [{"message": {"content": json.dumps({
                "summary": f"{repo} resumido por LLM",
                "recipe": f"instalar y usar {repo}",
                "snippet": "x"})}}], "usage": {}}
        eps = [PoolEndpoint(name="llm", base_url="http://x", api_key="k",
                            model="m", capabilities=("summarize", "general"))]
        pool = ProviderPool(eps, transport=transport)
        lr, _ = self._learner(pool=pool)
        cards = lr.research("testing")
        self.assertTrue(all("resumido por LLM" in c.summary for c in cards))


if __name__ == "__main__":
    unittest.main()
