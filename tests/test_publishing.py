"""Investigación reciente, PDF OA y libros con quality gates verificables."""

import json
import os
import re
import unittest

from a2s.learner import RepoHit, load_cards
from a2s.providers import HeuristicProvider
from a2s.publishing import (BookBuilder, OpenAlexClient, RepositoryAnalyzer,
                            ResearchStudio, SourceRecord, write_simple_pdf)
from a2s.search import workspace_search
from tests._winutil import temp_dir


class FakeGitHub:
    def discover_repositories(self, query, limit=6):
        return [
            RepoHit("org/recent", "https://github.com/org/recent",
                    "Recent autonomous agent framework", 120, "Python", "MIT", "2026-08-20"),
            RepoHit("org/notable", "https://github.com/org/notable",
                    "Notable agent evaluation toolkit", 9000, "Python", "Apache-2.0", "2026-06-01"),
        ][:limit]

    def fetch_readme(self, full_name):
        return (f"# {full_name}\nA documented framework for autonomous agents. "
                "It uses reproducible evaluation, tests and observable quality gates.")


class FakeOpenAlex:
    def search_open_pdfs(self, query, limit=8):
        return [SourceRecord(
            id="P1", kind="open_pdf", title="Open research about agents",
            url="https://doi.org/10.1/example", pdf_url="https://example.org/paper.pdf",
            summary="Peer reviewed analysis of autonomous agent evaluation.",
            authors=["Ada Example"], published_at="2026-07-01", citations=42,
            open_access=True, license="cc-by", provenance="openalex_open_access_metadata")][:limit]


class TestOpenAlex(unittest.TestCase):
    def test_parsea_solo_trabajo_oa_con_pdf_https(self):
        payload = {"results": [{
            "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x",
            "title": "Paper abierto", "publication_date": "2026-01-02",
            "cited_by_count": 9, "open_access": {"is_oa": True},
            "best_oa_location": {"pdf_url": "https://papers.example/x.pdf",
                                 "landing_page_url": "https://papers.example/x",
                                 "license": "cc-by"},
            "authorships": [{"author": {"display_name": "Ana"}}],
            "abstract_inverted_index": {"resultado": [1], "Un": [0]},
        }, {
            "id": "https://openalex.org/W2", "title": "Cerrado",
            "open_access": {"is_oa": False},
        }]}

        def transport(url, headers):
            self.assertIn("is_oa%3Atrue", url)
            return 200, {}, json.dumps(payload).encode()

        sources = OpenAlexClient(transport=transport).search_open_pdfs("agentes", 5)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].title, "Paper abierto")
        self.assertEqual(sources[0].summary, "Un resultado")
        self.assertTrue(sources[0].open_access)


class TestRepositoryAnalyzer(unittest.TestCase):
    def test_analisis_estatico_detecta_calidad_sin_ejecutar(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "tests"))
        with open(os.path.join(tmp.name, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("# Proyecto")
        with open(os.path.join(tmp.name, "LICENSE"), "w", encoding="utf-8") as fh:
            fh.write("MIT")
        with open(os.path.join(tmp.name, "tests", "test_x.py"), "w", encoding="utf-8") as fh:
            fh.write("# TODO\nassert True")
        report = RepositoryAnalyzer.analyze(tmp.name)
        self.assertEqual(report["execution"], "none_static_only")
        self.assertTrue(report["signals"]["readme"])
        self.assertTrue(report["signals"]["license"])
        self.assertTrue(report["signals"]["tests"])
        self.assertEqual(report["todo_markers"], 1)


class TestResearchStudio(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)
        with open(os.path.join(self.tmp.name, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("# Workspace")
        self.studio = ResearchStudio(self.tmp.name, github=FakeGitHub(),
                                     openalex=FakeOpenAlex())

    def test_fuentes_procedencia_aprendizaje_y_busqueda(self):
        report = self.studio.run("autonomous agents", repo_limit=2, pdf_limit=1)
        self.assertEqual(report["source_counts"],
                         {"repositories": 2, "open_pdfs": 1,
                          "public_pdf_candidates": 0})
        self.assertEqual([source["id"] for source in report["sources"]],
                         ["S1", "S2", "S3"])
        self.assertFalse(report["policy"]["repository_code_executed"])
        self.assertTrue(report["policy"]["downloads_open_access_only"])
        self.assertTrue(report["policy"]["public_pdf_candidates_require_license_review"])
        self.assertEqual(len(report["learned_cards"]), 2)
        self.assertEqual(len(load_cards(self.tmp.name)), 2)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "research", "report.md")))
        hits = workspace_search(self.tmp.name, "evaluation autonomous", top=5)
        self.assertTrue(any(doc.origen == "investigacion" for doc, _ in hits))

    def test_salida_fuera_del_workspace_es_rechazada(self):
        with self.assertRaises(PermissionError):
            self.studio.run("tema", output_dir="../escape")


class TestBookBuilder(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)
        self.studio = ResearchStudio(self.tmp.name, github=FakeGitHub(),
                                     openalex=FakeOpenAlex())

    @staticmethod
    def generator(prompt):
        match = re.search(r"CAPÍTULO \d+: (.+)", prompt)
        heading = match.group(1) if match else "capítulo"
        sentence = (f"{heading} se analiza mediante evidencia reproducible [S1]. "
                    "La comparación distingue datos, interpretación, riesgos y aplicación práctica. ")
        return "### Desarrollo\n\n" + sentence * 45

    def test_crea_md_html_pdf_y_gate(self):
        result = BookBuilder(self.tmp.name, researcher=self.studio,
                             generator=self.generator).build(
                                 "agentes autónomos", title="Agentes verificables",
                                 chapters=3, target_words=800)
        self.assertEqual(result["status"], "verified_draft")
        self.assertGreaterEqual(result["quality_score"], 80)
        self.assertEqual(result["chapters"], 3)
        for name in ("book.md", "book.html", "book.pdf", "quality.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "book", name)))
        with open(os.path.join(self.tmp.name, "book", "book.pdf"), "rb") as fh:
            self.assertEqual(fh.read(5), b"%PDF-")
        with open(os.path.join(self.tmp.name, "book", "quality.json"), encoding="utf-8") as fh:
            quality = json.load(fh)
        self.assertTrue(quality["checks"]["citations_valid"])
        self.assertTrue(quality["checks"]["target_length"])

    def test_fallback_local_sigue_creando_libro_honesto(self):
        result = BookBuilder(self.tmp.name, researcher=self.studio,
                             generator=lambda _prompt: None).build(
                                 "evaluación de agentes", chapters=3, target_words=3000)
        self.assertIn(result["status"], ("verified_draft", "draft_needs_expansion"))
        self.assertIn("target_length", result["quality"]["limitations"])
        self.assertGreater(result["sources"], 0)

    def test_pdf_writer_portable_con_acentos(self):
        path = os.path.join(self.tmp.name, "á.pdf")
        write_simple_pdf(path, "Título", "# Título\n\nInformación y evaluación.")
        with open(path, "rb") as fh:
            blob = fh.read()
        self.assertTrue(blob.startswith(b"%PDF-1.4"))
        self.assertTrue(blob.endswith(b"%%EOF\n"))


class TestPlannerPublishing(unittest.TestCase):
    def test_libro_y_repos_tienen_herramientas_especializadas(self):
        provider = HeuristicProvider()
        book = provider.plan("Crea un libro sobre agentes", "", "")
        research = provider.plan("Busca repositorios recientes y PDF", "", "")
        self.assertEqual(book["steps"][0]["tool"], "create_book")
        self.assertEqual(research["steps"][0]["tool"], "research_topic")


if __name__ == "__main__":
    unittest.main()
