"""Búsqueda autónoma de repositorios y memoria, en cualquier idioma.

El operador puede escribir «agentes autónomos», «autonomous agents» o
«forense pdf» y el buscador expande la consulta, busca en GitHub, en el
catálogo local y en la memoria BM25. No aplica el filtro LLMOps del radar:
si pides «calendario» encuentras calendarios.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from .learner import GitHubClient, RepoHit
from .models import now_iso
from .search import workspace_search

# Léxico bidireccional suficiente para consultas técnicas y literarias.
_LEX = {
    "agente": "agent", "agentes": "agents", "autonomo": "autonomous",
    "autonomos": "autonomous", "evaluacion": "evaluation",
    "pruebas": "testing", "repositorio": "repository",
    "repositorios": "repositories", "aprendizaje": "learning",
    "investigacion": "research", "seguridad": "security",
    "enrutamiento": "routing", "libro": "book", "libros": "books",
    "forense": "forensics", "verificable": "verifiable",
    "verificables": "verifiable", "busqueda": "search",
    "memoria": "memory", "red": "network", "herramienta": "tool",
    "herramientas": "tools", "informe": "report", "auditoria": "audit",
    "codigo": "code", "datos": "data", "modelo": "model",
    "modelos": "models", "lenguaje": "language", "documento": "document",
    "documentos": "documents", "pdf": "pdf", "cuento": "story",
    "novela": "novel", "principito": "little prince",
    "observabilidad": "observability", "enrutador": "router",
    "pasarela": "gateway", "calidad": "quality", "prueba": "test",
    "imagen": "image", "audio": "audio", "video": "video",
    "chat": "chat", "conversacion": "conversation",
}
_LEX.update({v: k for k, v in list(_LEX.items()) if v.isalpha() and " " not in v})
_STOP = {"de", "del", "la", "las", "el", "los", "un", "una", "sobre",
         "para", "por", "con", "y", "o", "que", "como", "mas", "the",
         "a", "an", "of", "to", "for", "with", "and", "or", "in", "on"}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def expand_query(query: str) -> list[str]:
    """Devuelve la consulta original, la traducida y una versión relajada."""
    raw = " ".join((query or "").split())[:200]
    if not raw:
        return []
    folded = fold(raw)
    tokens = re.findall(r"[a-z0-9_-]{2,}", folded)
    translated = [_LEX.get(tok, tok) for tok in tokens if tok not in _STOP]
    variants = [raw]
    joined = " ".join(dict.fromkeys(translated))
    if joined and fold(joined) != folded:
        variants.append(joined)
    if len(translated) > 3:
        variants.append(" ".join(translated[:3]))
    # Conserva también la forma plegada (sin tildes) para GitHub.
    if folded != raw.lower():
        variants.append(folded)
    return list(dict.fromkeys(v.strip() for v in variants if v.strip()))


class RepoFinder:
    """Búsqueda por palabra clave: GitHub + catálogo + memoria local."""

    def __init__(self, workspace: str, github: Optional[GitHubClient] = None):
        self.workspace = workspace
        self.github = github or GitHubClient(max_calls=24)

    def search(self, query: str, limit: int = 8,
               allow_network: bool = True) -> dict[str, Any]:
        query = " ".join((query or "").split())[:200]
        if not query:
            return {"query": "", "variants": [], "repositories": [],
                    "memory": [], "errors": ["consulta vacía"],
                    "at": now_iso()}
        variants = expand_query(query)
        errors: list[str] = []
        repos: dict[str, dict[str, Any]] = {}

        if allow_network:
            for variant in variants[:3]:
                try:
                    hits = self.github.discover_repositories(variant, limit=limit)
                except Exception as exc:  # red/cuota: no tumba la búsqueda
                    errors.append(f"GitHub «{variant}»: {type(exc).__name__}: {exc}")
                    continue
                for hit in hits:
                    self._add_hit(repos, hit, variant)

        try:
            from .ecosystem import EcosystemRadar, OPEN_SOURCE_LICENSES
            radar = EcosystemRadar(self.workspace, github=self.github)
            for project in radar.list_projects():
                blob = fold(f"{project.repo} {project.description} {' '.join(project.lessons)}")
                if any(fold(term) in blob for term in re.findall(r"[a-z0-9]{3,}", fold(query))):
                    if project.license not in OPEN_SOURCE_LICENSES:
                        continue
                    repos.setdefault(project.repo, {
                        "full_name": project.repo, "url": project.url,
                        "description": project.description, "stars": project.stars,
                        "language": project.language, "license": project.license,
                        "updated_at": project.updated_at, "source": "catalog",
                    })
        except Exception as exc:
            errors.append(f"catálogo: {type(exc).__name__}")

        memory = []
        try:
            for doc, score in workspace_search(self.workspace, query, top=limit):
                memory.append({"id": doc.doc_id, "origen": doc.origen,
                               "meta": doc.meta, "score": round(score, 3)})
        except Exception as exc:
            errors.append(f"memoria: {type(exc).__name__}")

        ranked = sorted(repos.values(),
                        key=lambda item: (item.get("stars") or 0, item.get("full_name", "")),
                        reverse=True)[: max(1, limit)]
        return {
            "query": query, "variants": variants, "repositories": ranked,
            "memory": memory, "errors": errors, "at": now_iso(),
            "code_executed": False,
        }

    @staticmethod
    def _add_hit(repos: dict[str, dict[str, Any]], hit: RepoHit, variant: str) -> None:
        if not hit.full_name:
            return
        repos[hit.full_name] = {
            "full_name": hit.full_name, "url": hit.html_url,
            "description": hit.description, "stars": hit.stars,
            "language": hit.language, "license": hit.license,
            "updated_at": hit.updated_at, "source": "github",
            "matched": variant,
        }


def format_search(report: dict[str, Any]) -> str:
    if not report.get("query"):
        return "Necesito una palabra clave para buscar."
    lines = [f"Búsqueda «{report['query']}» (variantes: {', '.join(report['variants'])}).", ""]
    repos = report.get("repositories") or []
    if repos:
        lines.append("Repositorios:")
        for repo in repos[:12]:
            lines.append(
                f"- {repo['full_name']} ★{repo.get('stars', 0)} "
                f"[{repo.get('license') or '?'}] {repo.get('url')}")
            if repo.get("description"):
                lines.append(f"  {repo['description'][:220]}")
    else:
        lines.append("No encontré repositorios públicos con esa clave en este momento.")
    memory = report.get("memory") or []
    if memory:
        lines.append("")
        lines.append("Memoria local:")
        for item in memory[:6]:
            lines.append(f"- [{item['origen']}] {item['meta']} ({item['score']})")
    if report.get("errors"):
        lines.append("")
        lines.append("Límites: " + "; ".join(report["errors"][:4]))
    return "\n".join(lines)
