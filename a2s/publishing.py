"""Investigación verificable y creación de libros con procedencia.

Este módulo convierte cuatro capacidades difusas en pipelines reproducibles:

* analizar un repositorio local sin ejecutar su código;
* descubrir repositorios públicos recientes **y** destacables;
* localizar PDF académicos de acceso abierto mediante OpenAlex;
* crear Markdown, HTML y PDF con manifiesto de fuentes y control de calidad.

No promete perfección subjetiva. Entrega gates medibles, fuentes fechadas y un
estado honesto (``verified_draft`` o ``draft_needs_expansion``).
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import math
import os
import re
import socket
import subprocess
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from .learner import (GitHubClient, KnowledgeCard, RepoHit, extractive_summary,
                      load_cards, save_card)
from .models import now_iso

OPENALEX_API = "https://api.openalex.org"
_MAX_PDF_BYTES = 20_000_000
_EXCLUDED_DIRS = {".git", ".a2s", "node_modules", "__pycache__", ".venv",
                  "dist", "build", "target", ".next", ".cache", "coverage"}
_TEXT_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
              ".c", ".h", ".cpp", ".md", ".txt", ".toml", ".yaml", ".yml",
              ".json", ".html", ".css", ".sh", ".sql", ".rb", ".php"}
_TRANSLATE_TERMS = {
    "agente": "agent", "agentes": "agents", "autonomo": "autonomous",
    "autonomos": "autonomous", "evaluacion": "evaluation", "pruebas": "testing",
    "repositorio": "repository", "repositorios": "repositories",
    "aprendizaje": "learning", "investigacion": "research", "seguridad": "security",
    "enrutamiento": "routing", "libro": "book", "libros": "books",
    "forense": "forensics", "verificable": "verifiable", "verificables": "verifiable",
}
_QUERY_STOP = {"de", "del", "la", "las", "el", "los", "un", "una", "sobre",
               "para", "por", "con", "y", "o", "que", "como", "mas"}


def _github_query(topic: str) -> str:
    normalized = unicodedata.normalize("NFD", topic.lower())
    normalized = "".join(char for char in normalized
                         if unicodedata.category(char) != "Mn")
    tokens = re.findall(r"[a-z0-9_-]{2,}", normalized)
    translated = [_TRANSLATE_TERMS.get(token, token) for token in tokens
                  if token not in _QUERY_STOP]
    return " ".join(dict.fromkeys(translated[:7])) or topic[:80]


@dataclass
class SourceRecord:
    id: str
    kind: str
    title: str
    url: str
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    published_at: str = ""
    updated_at: str = ""
    license: str = ""
    stars: int = 0
    citations: int = 0
    pdf_url: str = ""
    open_access: bool = False
    accessed_at: str = field(default_factory=now_iso)
    provenance: str = "public_metadata"


class OpenAlexClient:
    """Cliente mínimo para literatura abierta; no busca ni salta paywalls."""

    def __init__(self, transport: Optional[Callable[[str, dict[str, str]],
                                                    tuple[int, dict, bytes]]] = None,
                 max_calls: int = 10) -> None:
        self.transport = transport
        self.max_calls = max(1, max_calls)
        self.calls = 0
        self.last_error = ""

    def _get(self, url: str) -> tuple[int, dict, bytes]:
        self.calls += 1
        if self.calls > self.max_calls:
            return 429, {}, b"{}"
        headers = {"User-Agent": "A2S-research/1.13 (+open-access; read-only)",
                   "Accept": "application/json"}
        if self.transport:
            return self.transport(url, headers)
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.status, dict(response.headers), response.read(2_000_000)
        except urllib.error.HTTPError as exc:
            self.last_error = f"OpenAlex HTTP {exc.code}"
            return exc.code, dict(exc.headers or {}), exc.read(2000)
        except OSError as exc:
            self.last_error = f"OpenAlex no accesible: {str(exc)[:160]}"
            return 0, {}, b"{}"

    def search_open_pdfs(self, query: str, limit: int = 8) -> list[SourceRecord]:
        params = urllib.parse.urlencode({
            "search": query,
            "filter": "is_oa:true,has_fulltext:true",
            "sort": "cited_by_count:desc",
            "per-page": max(1, min(25, int(limit) * 2)),
        })
        status, _, body = self._get(f"{OPENALEX_API}/works?{params}")
        if status != 200:
            if not self.last_error:
                self.last_error = f"OpenAlex HTTP {status}"
            return []
        self.last_error = ""
        try:
            results = json.loads(body.decode("utf-8", "replace")).get("results", [])
        except (ValueError, AttributeError):
            return []
        out = []
        for work in results:
            source = self._from_work(work, len(out) + 1)
            if source and source.pdf_url:
                out.append(source)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _from_work(work: dict[str, Any], index: int) -> Optional[SourceRecord]:
        access = work.get("open_access") or {}
        if not access.get("is_oa"):
            return None
        locations = [work.get("best_oa_location"), work.get("primary_location")]
        locations.extend(work.get("locations") or [])
        pdf_url = ""
        landing = ""
        for location in locations:
            if not isinstance(location, dict):
                continue
            candidate = str(location.get("pdf_url") or "")
            if candidate.startswith("https://") and not pdf_url:
                pdf_url = candidate
            page = str(location.get("landing_page_url") or "")
            if page.startswith("https://") and not landing:
                landing = page
        doi = str(work.get("doi") or "")
        url = landing or doi or str(work.get("id") or "")
        if not url.startswith("https://"):
            return None
        abstract = OpenAlexClient._abstract(work.get("abstract_inverted_index"))
        authors = []
        for authorship in work.get("authorships") or []:
            name = str((authorship.get("author") or {}).get("display_name") or "")
            if name:
                authors.append(name)
        return SourceRecord(
            id=f"P{index}", kind="open_pdf", title=str(work.get("title") or "Sin título")[:500],
            url=url, pdf_url=pdf_url, summary=abstract[:1200], authors=authors[:12],
            published_at=str(work.get("publication_date") or work.get("publication_year") or ""),
            citations=int(work.get("cited_by_count") or 0), open_access=True,
            license=str((next((loc for loc in locations if isinstance(loc, dict)
                              and loc.get("license")), {}) or {}).get("license") or "OA"),
            provenance="openalex_open_access_metadata")

    @staticmethod
    def _abstract(index: Any) -> str:
        if not isinstance(index, dict):
            return ""
        words = []
        for word, positions in index.items():
            for position in positions or []:
                if isinstance(position, int):
                    words.append((position, word))
        return " ".join(word for _, word in sorted(words))


class ArxivClient:
    """Respaldo abierto de literatura; devuelve enlaces PDF oficiales de arXiv."""

    API = "https://export.arxiv.org/api/query"

    def __init__(self, transport: Optional[Callable[[str, dict[str, str]],
                                                    tuple[int, dict, bytes]]] = None) -> None:
        self.transport = transport
        self.last_error = ""

    def search_open_pdfs(self, query: str, limit: int = 8) -> list[SourceRecord]:
        terms = " ".join(re.findall(r"[\w-]{2,}", query, re.UNICODE)[:12])
        params = urllib.parse.urlencode({"search_query": f'all:"{terms}"',
                                        "start": 0, "max_results": max(1, min(25, limit)),
                                        "sortBy": "submittedDate", "sortOrder": "descending"})
        url = f"{self.API}?{params}"
        headers = {"User-Agent": "A2S-research/1.13 (+open-access; read-only)"}
        try:
            if self.transport:
                status, _, body = self.transport(url, headers)
            else:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=25) as response:
                    status, body = response.status, response.read(2_000_000)
        except (OSError, urllib.error.URLError) as exc:
            self.last_error = f"arXiv no accesible: {str(exc)[:160]}"
            return []
        if status != 200:
            self.last_error = f"arXiv HTTP {status}"
            return []
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            self.last_error = f"arXiv XML inválido: {exc}"
            return []
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        out = []
        for entry in root.findall("atom:entry", namespace):
            page = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
            title = " ".join((entry.findtext("atom:title", default="Sin título",
                                              namespaces=namespace) or "").split())
            summary = " ".join((entry.findtext("atom:summary", default="",
                                                namespaces=namespace) or "").split())
            authors = [node.findtext("atom:name", default="", namespaces=namespace)
                       for node in entry.findall("atom:author", namespace)]
            pdf_url = ""
            for link in entry.findall("atom:link", namespace):
                if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                    pdf_url = link.attrib.get("href", "")
                    break
            if pdf_url.startswith("http://"):
                pdf_url = "https://" + pdf_url[7:]
            if page.startswith("http://"):
                page = "https://" + page[7:]
            if not pdf_url.startswith("https://") or not page.startswith("https://"):
                continue
            out.append(SourceRecord(
                id=f"A{len(out) + 1}", kind="open_pdf", title=title[:500], url=page,
                pdf_url=pdf_url, summary=summary[:1200], authors=[name for name in authors if name][:12],
                published_at=(entry.findtext("atom:published", default="",
                                             namespaces=namespace) or "")[:10],
                open_access=True, license="arXiv open access",
                provenance="arxiv_official_atom_feed"))
            if len(out) >= limit:
                break
        self.last_error = ""
        return out


class RepositoryAnalyzer:
    """Inventario estático del checkout; jamás importa ni ejecuta el proyecto."""

    @staticmethod
    def analyze(path: str) -> dict[str, Any]:
        root = os.path.abspath(path)
        extensions: dict[str, int] = {}
        files = 0
        bytes_total = 0
        tests = 0
        todos = 0
        largest: list[tuple[int, str]] = []
        key_files = []
        for current, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED_DIRS)
            for name in names:
                full = os.path.join(current, name)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                files += 1
                bytes_total += size
                ext = os.path.splitext(name)[1].lower() or "[sin extensión]"
                extensions[ext] = extensions.get(ext, 0) + 1
                largest.append((size, rel))
                if "test" in name.lower() or "/tests/" in f"/{rel.lower()}/":
                    tests += 1
                if name.lower() in {"readme.md", "license", "license.md", "package.json",
                                    "pyproject.toml", "cargo.toml", "go.mod"} or \
                        rel.startswith(".github/workflows/"):
                    key_files.append(rel)
                if ext in _TEXT_EXTS and size <= 1_000_000:
                    try:
                        with open(full, encoding="utf-8", errors="replace") as handle:
                            todos += len(re.findall(r"\b(?:TODO|FIXME|XXX)\b", handle.read()))
                    except OSError:
                        pass
        commits = RepositoryAnalyzer._git_log(root)
        names_lower = {name.lower() for name in key_files}
        return {
            "path": root, "analyzed_at": now_iso(), "execution": "none_static_only",
            "files": files, "bytes": bytes_total, "test_files": tests, "todo_markers": todos,
            "extensions": dict(sorted(extensions.items(), key=lambda item: item[1], reverse=True)[:20]),
            "largest_files": [{"path": rel, "bytes": size}
                              for size, rel in sorted(largest, reverse=True)[:15]],
            "key_files": sorted(key_files), "recent_commits": commits,
            "signals": {
                "readme": "readme.md" in names_lower,
                "license": any(name.startswith("license") for name in names_lower),
                "tests": tests > 0,
                "ci": any(name.startswith(".github/workflows/") for name in key_files),
            },
        }

    @staticmethod
    def _git_log(root: str) -> list[dict[str, str]]:
        try:
            result = subprocess.run(
                ["git", "-C", root, "log", "-8", "--date=iso-strict",
                 "--pretty=format:%h%x09%ad%x09%s"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
                stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return []
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                commits.append({"commit": parts[0], "at": parts[1], "subject": parts[2]})
        return commits


class ResearchStudio:
    """Pipeline de fuentes: checkout + GitHub + PDF OA + aprendizaje inmediato."""

    def __init__(self, workspace: str, github: Optional[GitHubClient] = None,
                 openalex: Optional[OpenAlexClient] = None,
                 arxiv: Optional[ArxivClient] = None) -> None:
        self.workspace = os.path.abspath(workspace)
        self.github = github or GitHubClient(max_calls=40)
        self.openalex = openalex or OpenAlexClient()
        self.arxiv = arxiv or ArxivClient()

    def run(self, topic: str, repo_limit: int = 8, pdf_limit: int = 8,
            output_dir: str = "research", analyze_local: bool = True,
            learn: bool = True, download_pdfs: bool = False) -> dict[str, Any]:
        topic = " ".join((topic or "").split())[:500]
        if not topic:
            raise ValueError("tema de investigación vacío")
        output = self._safe_output(output_dir)
        os.makedirs(output, exist_ok=True)
        errors = []
        repos: list[tuple[RepoHit, str]] = []
        discovery_query = _github_query(topic)
        try:
            hits = self.github.discover_repositories(discovery_query, limit=max(1, repo_limit))
            if not hits and len(discovery_query.split()) > 3:
                relaxed = " ".join(discovery_query.split()[:3])
                hits = self.github.discover_repositories(relaxed, limit=max(1, repo_limit))
            for hit in hits:
                repos.append((hit, self.github.fetch_readme(hit.full_name)))
        except Exception as exc:  # red/budget: informe parcial, no pérdida total
            errors.append(f"GitHub: {type(exc).__name__}: {str(exc)[:200]}")
        try:
            pdfs = self.openalex.search_open_pdfs(discovery_query, limit=max(0, pdf_limit))
            openalex_error = getattr(self.openalex, "last_error", "")
            if openalex_error:
                errors.append(openalex_error)
        except Exception as exc:
            errors.append(f"OpenAlex: {type(exc).__name__}: {str(exc)[:200]}")
            pdfs = []
        if not pdfs and pdf_limit > 0:
            try:
                pdfs = self.arxiv.search_open_pdfs(discovery_query, limit=pdf_limit)
                arxiv_error = getattr(self.arxiv, "last_error", "")
                if arxiv_error:
                    errors.append(arxiv_error)
            except Exception as exc:
                errors.append(f"arXiv: {type(exc).__name__}: {str(exc)[:200]}")
        pdf_candidates = self._github_pdf_candidates(discovery_query, pdf_limit) if not pdfs else []
        sources = self._repo_sources(repos) + pdfs + pdf_candidates
        for index, source in enumerate(sources, 1):
            source.id = f"S{index}"
        local = RepositoryAnalyzer.analyze(self.workspace) if analyze_local else None
        learned = self._learn(topic, repos) if learn else []
        downloads = self._download_open_pdfs(pdfs, output) if download_pdfs else []
        report = {
            "schema_version": 1, "topic": topic, "created_at": now_iso(),
            "sources": [asdict(source) for source in sources],
            "source_counts": {"repositories": len(repos), "open_pdfs": len(pdfs),
                              "public_pdf_candidates": len(pdf_candidates)},
            "local_repository": local, "learned_cards": learned,
            "downloads": downloads, "errors": errors,
            "policy": {"repository_code_executed": False,
                       "downloads_open_access_only": True,
                       "public_pdf_candidates_require_license_review": True,
                       "paywalls_bypassed": False},
        }
        self._write_json(os.path.join(output, "sources.json"), report)
        with open(os.path.join(output, "report.md"), "w", encoding="utf-8") as handle:
            handle.write(self._markdown(report))
        self._queue_growth(topic)
        report["artifacts"] = [os.path.relpath(os.path.join(output, name), self.workspace)
                               for name in ("report.md", "sources.json")]
        return report

    def _safe_output(self, relative: str) -> str:
        output = os.path.abspath(os.path.join(self.workspace, relative))
        if output != self.workspace and not output.startswith(self.workspace + os.sep):
            raise PermissionError("salida fuera del workspace")
        return output

    def _github_pdf_candidates(self, topic: str, limit: int) -> list[SourceRecord]:
        try:
            hits = self.github.search_public_pdfs(topic, limit=max(0, limit))
        except Exception:
            return []
        return [SourceRecord(
            id=f"G{index}", kind="public_pdf_candidate", title=hit.name,
            url=hit.html_url, pdf_url=hit.raw_url,
            summary=(f"PDF público localizado en {hit.repository}. No se extrajo su contenido; "
                     "verificar autoría y licencia documental antes de citarlo."),
            license=hit.license, open_access=False,
            provenance="github_code_search_public_repository")
                for index, hit in enumerate(hits, 1)]

    @staticmethod
    def _repo_sources(repos: list[tuple[RepoHit, str]]) -> list[SourceRecord]:
        out = []
        for index, (hit, readme) in enumerate(repos, 1):
            summary = extractive_summary(readme) or hit.description
            out.append(SourceRecord(
                id=f"R{index}", kind="repository", title=hit.full_name,
                url=hit.html_url, summary=summary[:1200], updated_at=hit.updated_at,
                license=hit.license, stars=hit.stars,
                provenance="github_public_metadata_and_readme"))
        return out

    def _learn(self, topic: str, repos: list[tuple[RepoHit, str]]) -> list[str]:
        from .ecosystem import OPEN_SOURCE_LICENSES
        known = {card.repo for card in load_cards(self.workspace)}
        learned = []
        for hit, readme in repos:
            if hit.full_name in known or hit.license not in OPEN_SOURCE_LICENSES or not readme:
                continue
            digest = hashlib.sha256(f"{topic}\0{hit.full_name}".encode()).hexdigest()[:16]
            summary = extractive_summary(readme)
            card = KnowledgeCard(
                id=f"research-{digest}", topic=topic[:80], query=topic,
                repo=hit.full_name, url=hit.html_url, license=hit.license,
                summary=summary, recipe="revisar la documentación citada y validar en pruebas aisladas",
                snippet=summary[:400], stars=hit.stars)
            save_card(card, self.workspace)
            known.add(hit.full_name)
            learned.append(hit.full_name)
        return learned

    def _queue_growth(self, topic: str) -> None:
        path = os.path.join(self.workspace, ".a2s", "growth_queue.txt")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            lines = []
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as handle:
                    lines = [line.rstrip("\n") for line in handle]
            if topic not in lines:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(topic + "\n")
        except OSError:
            pass

    @staticmethod
    def _write_json(path: str, data: Any) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    @staticmethod
    def _markdown(report: dict[str, Any]) -> str:
        lines = [f"# Investigación: {report['topic']}", "",
                 f"Fecha de consulta: {report['created_at']}", "",
                 "## Fuentes verificables", ""]
        for source in report["sources"]:
            details = []
            if source["stars"]:
                details.append(f"★{source['stars']}")
            if source["citations"]:
                details.append(f"{source['citations']} citas")
            if source["updated_at"]:
                details.append(f"actualizado {source['updated_at']}")
            lines.extend([f"### [{source['id']}] {source['title']}",
                          f"- Tipo: {source['kind']} · {' · '.join(details) or 'metadatos públicos'}",
                          f"- URL: {source['url']}",
                          f"- Licencia/acceso: {source['license'] or 'no declarada'}",
                          f"- Síntesis: {source['summary'] or 'sin resumen disponible'}", ""])
        local = report.get("local_repository")
        if local:
            lines.extend(["## Repositorio local", "",
                          f"- Archivos: {local['files']} ({local['bytes']} bytes)",
                          f"- Tests detectados: {local['test_files']}",
                          f"- TODO/FIXME: {local['todo_markers']}",
                          f"- Señales: `{json.dumps(local['signals'], ensure_ascii=False)}`", ""])
        if report["learned_cards"]:
            lines.extend(["## Crecimiento persistido", "",
                          "Fichas nuevas: " + ", ".join(report["learned_cards"]), ""])
        if report["errors"]:
            lines.extend(["## Límites encontrados", ""] +
                         [f"- {error}" for error in report["errors"]] + [""])
        lines.extend(["## Política", "",
                      "Solo lectura de fuentes públicas. No se ejecutó código remoto y no se evitaron paywalls.", ""])
        return "\n".join(lines)

    def _download_open_pdfs(self, sources: list[SourceRecord], output: str) -> list[dict[str, Any]]:
        directory = os.path.join(output, "pdfs")
        os.makedirs(directory, exist_ok=True)
        downloads = []
        for source in sources:
            try:
                blob = self._download_pdf(source.pdf_url)
                name = f"{source.id.lower()}-{_slug(source.title)[:60]}.pdf"
                path = os.path.join(directory, name)
                with open(path, "wb") as handle:
                    handle.write(blob)
                downloads.append({"source": source.id, "path": os.path.relpath(path, self.workspace),
                                  "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()})
            except (OSError, ValueError, urllib.error.URLError) as exc:
                downloads.append({"source": source.id, "error": str(exc)[:200]})
        return downloads

    @staticmethod
    def _download_pdf(url: str) -> bytes:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise ValueError("URL PDF no segura")
        try:
            addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, 443)}
            if any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ValueError("host PDF no público")
        except socket.gaierror as exc:
            raise ValueError("host PDF no resoluble") from exc
        request = urllib.request.Request(url, headers={"User-Agent": "A2S-research/1.13"})
        with urllib.request.urlopen(request, timeout=30) as response:
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > _MAX_PDF_BYTES:
                raise ValueError("PDF supera 20 MB")
            blob = response.read(_MAX_PDF_BYTES + 1)
        if len(blob) > _MAX_PDF_BYTES or not blob.startswith(b"%PDF-"):
            raise ValueError("respuesta no es un PDF válido o supera 20 MB")
        return blob


class BookBuilder:
    """Libro respaldado por fuentes, con revisión automática y tres formatos."""

    def __init__(self, workspace: str, researcher: Optional[ResearchStudio] = None,
                 generator: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self.workspace = os.path.abspath(workspace)
        self.researcher = researcher or ResearchStudio(self.workspace)
        self.generator = generator
        self._pool = None

    def build(self, topic: str, title: str = "", chapters: int = 6,
              target_words: int = 3000, output_dir: str = "book",
              repo_limit: int = 6, pdf_limit: int = 8) -> dict[str, Any]:
        chapters = max(3, min(12, int(chapters)))
        target_words = max(800, min(50_000, int(target_words)))
        title = title.strip() or f"Guía verificable sobre {topic.strip()}"
        output = self.researcher._safe_output(output_dir)
        os.makedirs(output, exist_ok=True)
        research = self.researcher.run(
            topic, repo_limit=repo_limit, pdf_limit=pdf_limit,
            output_dir=os.path.join(output_dir, "research"), learn=True)
        sources = [SourceRecord(**source) for source in research["sources"]]
        evidence_sources = [source for source in sources
                            if source.kind != "public_pdf_candidate"]
        outline = self._outline(topic, chapters)
        generator = self.generator or self._default_generator()
        chapter_texts = []
        per_chapter = max(250, target_words // chapters)
        for index, heading in enumerate(outline, 1):
            assigned = (evidence_sources[(index - 1) % max(1, len(evidence_sources))::chapters]
                        if evidence_sources else [])
            prompt = self._chapter_prompt(title, topic, heading, index, outline,
                                          evidence_sources, per_chapter)
            text = generator(prompt) if generator else None
            if not self._usable_chapter(text):
                text = self._grounded_fallback(
                    heading, topic, assigned or evidence_sources[:3], index)
            elif len(text.split()) < per_chapter // 2 and generator:
                repaired = generator(prompt + "\nAmplía el borrador anterior con más explicación, "
                                     "sin inventar fuentes y conservando las citas [S#]:\n" + text)
                if self._usable_chapter(repaired) and len(repaired.split()) > len(text.split()):
                    text = repaired
            chapter_texts.append(self._normalize_chapter(heading, text or ""))
        markdown = self._assemble(title, topic, outline, chapter_texts, sources)
        md_path = os.path.join(output, "book.md")
        html_path = os.path.join(output, "book.html")
        pdf_path = os.path.join(output, "book.pdf")
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(markdown)
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(_markdown_html(title, markdown))
        write_simple_pdf(pdf_path, title, markdown)
        quality = self._quality(markdown, outline, sources, target_words,
                                research_errors=research["errors"])
        quality.update({"created_at": now_iso(), "topic": topic, "title": title,
                        "research_errors": research["errors"],
                        "publication_ready": quality["status"] == "verified_draft"
                                             and not research["errors"]})
        quality_path = os.path.join(output, "quality.json")
        with open(quality_path, "w", encoding="utf-8") as handle:
            json.dump(quality, handle, ensure_ascii=False, indent=2)
        self.close()
        return {
            "status": quality["status"], "quality_score": quality["score"],
            "word_count": quality["word_count"], "sources": len(sources),
            "chapters": len(outline), "artifacts": [
                os.path.relpath(path, self.workspace) for path in
                (md_path, html_path, pdf_path, quality_path,
                 os.path.join(output, "research", "sources.json"))],
            "quality": quality,
        }

    def _default_generator(self) -> Optional[Callable[[str], Optional[str]]]:
        try:
            from .config import Config
            from .provider_pool import ProviderPool
            from .providers import get_provider
            provider = get_provider("auto", config=Config(workspace=self.workspace, quiet=True,
                                                            provider="auto"))
            if not isinstance(provider, ProviderPool):
                return None
            self._pool = provider
            return lambda prompt: provider.chat(
                prompt, kind="summarize", max_tokens=1800,
                system=("Eres editor de no ficción. Redacta en español claro y coherente. "
                        "Usa exclusivamente las fuentes proporcionadas; cita como [S1]. "
                        "No inventes datos ni bibliografía."), allow_fallback=False)
        except Exception:
            return None

    @staticmethod
    def _outline(topic: str, count: int) -> list[str]:
        templates = [
            "Panorama, propósito y alcance", "Fundamentos y vocabulario",
            "Evidencia reciente y proyectos destacables", "Métodos y proceso reproducible",
            "Aplicaciones prácticas", "Riesgos, límites y criterios de calidad",
            "Tendencias y próximos pasos", "Síntesis y plan de acción",
            "Casos comparados", "Evaluación y métricas", "Operación responsable",
            "Conclusiones verificables",
        ]
        return [f"{templates[index]}: {topic}" for index in range(count)]

    @staticmethod
    def _chapter_prompt(title: str, topic: str, heading: str, index: int,
                        outline: list[str], sources: list[SourceRecord], words: int) -> str:
        source_text = "\n".join(
            f"[{source.id}] {source.title}; {source.summary[:700]}; URL={source.url}"
            for source in sources[:12]) or "No hay fuentes externas disponibles. Decláralo."
        return (f"LIBRO: {title}\nTEMA: {topic}\nÍNDICE: {json.dumps(outline, ensure_ascii=False)}\n"
                f"CAPÍTULO {index}: {heading}\nEXTENSIÓN OBJETIVO: {words} palabras.\n"
                f"FUENTES:\n{source_text}\n\nRedacta solo el cuerpo del capítulo. Mantén continuidad "
                "con el índice, incluye secciones útiles, distingue evidencia de interpretación "
                "y usa citas [S#] únicamente cuando correspondan.")

    @staticmethod
    def _usable_chapter(text: Optional[str]) -> bool:
        if not text or len(text.split()) < 80:
            return False
        bad = ("No tengo un LLM", "conecta un proveedor", "```json")
        return not any(marker.lower() in text.lower() for marker in bad)

    @staticmethod
    def _grounded_fallback(heading: str, topic: str,
                           sources: list[SourceRecord], index: int) -> str:
        lines = [f"En **{heading}**, el tema **{topic}** se estudia desde una perspectiva "
                 "verificable, separando los hechos recuperados de las recomendaciones editoriales.", "",
                 "### Evidencia disponible", ""]
        if sources:
            for source in sources[:4]:
                fact = source.summary or f"Metadatos públicos de {source.title}."
                lines.append(f"- **{source.title}**: {fact[:500]} [{source.id}]")
        else:
            lines.append("- No se recuperaron fuentes externas durante esta ejecución; no se formulan afirmaciones específicas.")
        lines.extend(["", "### Interpretación", "",
                      f"La evidencia anterior permite construir una lectura prudente de {heading.lower()}. "
                      "Una señal destacada no equivale por sí sola a calidad: deben contrastarse actividad, "
                      "licencia, documentación, pruebas y adecuación al caso real.", "",
                      "### Método práctico", "",
                      "1. Definir una pregunta y un criterio observable de éxito.",
                      "2. Comparar fuentes con fechas, procedencia y licencia explícitas.",
                      "3. Probar las ideas en un entorno controlado sin ejecutar código remoto automáticamente.",
                      f"4. Registrar resultados negativos y actualizar la conclusión específica de «{heading}».", "",
                      "### Límite de este capítulo", "",
                      f"El capítulo {index} no sustituye una revisión humana experta. Su alcance queda limitado "
                      "a las fuentes enumeradas y a su estado en la fecha de consulta."])
        return "\n".join(lines)

    @staticmethod
    def _normalize_chapter(heading: str, text: str) -> str:
        text = re.sub(r"^#{1,3}\s+.*\n", "", text.strip(), count=1)
        return f"## {heading}\n\n{text.strip()}"

    @staticmethod
    def _assemble(title: str, topic: str, outline: list[str], chapters: list[str],
                  sources: list[SourceRecord]) -> str:
        lines = [f"# {title}", "", f"**Tema:** {topic}",
                 f"**Edición generada:** {now_iso()}", "",
                 "> Borrador asistido con procedencia verificable. Consulte `quality.json` antes de publicar.",
                 "", "## Índice", ""]
        lines.extend(f"{index}. {heading}" for index, heading in enumerate(outline, 1))
        lines.extend(["", *chapters, "", "## Bibliografía y fuentes", ""])
        for source in sources:
            author = ", ".join(source.authors[:4])
            prefix = f"{author}. " if author else ""
            date = source.published_at or source.updated_at or "s. f."
            lines.append(f"- [{source.id}] {prefix}**{source.title}** ({date}). {source.url}")
        if not sources:
            lines.append("- No se recuperaron fuentes externas; el texto queda marcado como borrador no publicable.")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _quality(markdown: str, outline: list[str], sources: list[SourceRecord],
                 target_words: int,
                 research_errors: Optional[list[str]] = None) -> dict[str, Any]:
        word_count = len(re.findall(r"\b\w+\b", markdown, re.UNICODE))
        headings = len(re.findall(r"^## (?!Índice|Bibliografía)", markdown, re.M))
        citations = re.findall(r"\[S(\d+)\]", markdown)
        valid_ids = {source.id[1:] for source in sources if source.id.startswith("S")}
        invalid = sorted({citation for citation in citations if citation not in valid_ids})
        paragraphs = [re.sub(r"\s+", " ", part.strip().lower())
                      for part in markdown.split("\n\n") if len(part.split()) > 20]
        duplicates = len(paragraphs) - len(set(paragraphs))
        evidence = [source for source in sources
                    if source.kind != "public_pdf_candidate"]
        evidence_kinds = {source.kind for source in evidence}
        checks = {
            "all_chapters_present": headings == len(outline),
            "has_verifiable_sources": bool(evidence),
            "citations_valid": not invalid,
            "citations_present": bool(citations) if evidence else False,
            "no_duplicate_long_paragraphs": duplicates == 0,
            "target_length": word_count >= target_words,
            "pdf_rendered": True,
            "source_diversity": len(evidence_kinds) >= 2,
            "research_channels_complete": not research_errors,
        }
        weights = {"all_chapters_present": 20, "has_verifiable_sources": 20,
                   "citations_valid": 15, "citations_present": 10,
                   "no_duplicate_long_paragraphs": 10, "target_length": 10,
                   "pdf_rendered": 5, "source_diversity": 5,
                   "research_channels_complete": 5}
        score = sum(weight for key, weight in weights.items() if checks[key])
        essential = (checks["all_chapters_present"] and checks["has_verifiable_sources"]
                     and checks["citations_valid"] and checks["no_duplicate_long_paragraphs"])
        return {
            "status": "verified_draft" if essential and score >= 80 else "draft_needs_expansion",
            "score": score, "word_count": word_count, "target_words": target_words,
            "checks": checks, "invalid_citations": invalid,
            "duplicate_paragraphs": duplicates,
            "limitations": ([] if score == 100 else
                            [key for key, value in checks.items() if not value]),
        }

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.close()
            except Exception:
                pass
            self._pool = None


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "documento"


def _markdown_html(title: str, markdown: str) -> str:
    blocks = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            blocks.append("</ul>")
            in_list = False
        if line.startswith("# "):
            blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("> "):
            blocks.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line:
            blocks.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        blocks.append("</ul>")
    return ("<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title><style>body{{font:18px/1.65 Georgia,serif;"
            "max-width:820px;margin:3rem auto;padding:0 1.5rem;color:#20242b}}"
            "h1,h2,h3{font-family:system-ui,sans-serif;line-height:1.2}"
            "blockquote{border-left:4px solid #668;padding-left:1rem;color:#556}"
            "@media print{body{font-size:11pt;margin:0}}</style></head><body>"
            + "\n".join(blocks) + "</body></html>")


def _pdf_escape(text: str) -> bytes:
    data = text.encode("cp1252", "replace")
    out = bytearray()
    for byte in data:
        if byte in (40, 41, 92):
            out.extend(b"\\" + bytes([byte]))
        elif byte < 32 or byte > 126:
            out.extend(f"\\{byte:03o}".encode())
        else:
            out.append(byte)
    return bytes(out)


def write_simple_pdf(path: str, title: str, markdown: str) -> None:
    """PDF de texto válido y portable, sin depender de Pandoc/LibreOffice."""
    plain = re.sub(r"[`*_>#]", "", markdown)
    lines = []
    for paragraph in plain.splitlines():
        lines.extend(textwrap.wrap(paragraph, width=92, replace_whitespace=True) or [""])
    pages = [lines[index:index + 52] for index in range(0, max(1, len(lines)), 52)] or [[title]]
    objects: dict[int, bytes] = {}
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = ("<< /Type /Pages /Count %d /Kids [%s] >>" %
                  (len(pages), " ".join(f"{page_id} 0 R" for page_id in page_ids))).encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        stream = bytearray(b"BT\n/F1 10 Tf\n50 750 Td\n13 TL\n")
        for line in page_lines:
            stream.extend(b"(" + _pdf_escape(line) + b") Tj\nT*\n")
        stream.extend(b"ET\n")
        objects[page_id] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>").encode()
        objects[content_id] = (f"<< /Length {len(stream)} >>\nstream\n".encode()
                               + bytes(stream) + b"endstream")
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max(objects) + 1)
    for object_id in sorted(objects):
        offsets[object_id] = len(payload)
        payload.extend(f"{object_id} 0 obj\n".encode() + objects[object_id] + b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(offsets)}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    with open(path, "wb") as handle:
        handle.write(payload)
