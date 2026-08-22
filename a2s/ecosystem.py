"""Radar de ecosistema abierto para la mejora continua de A²S.

Busca metadatos de proyectos públicos relacionados, acepta únicamente
licencias SPDX abiertas conocidas y persiste un catálogo auditable. No clona,
instala ni ejecuta código: las fuentes se usan como señales de diseño, no como
base ni como dependencia de runtime.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .config import classify_forbidden
from .learner import BudgetExhausted, GitHubClient, RepoHit
from .models import now_iso

OPEN_SOURCE_LICENSES = frozenset({
    "0BSD", "AGPL-3.0", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "BSL-1.0",
    "CC0-1.0", "EPL-2.0", "GPL-2.0", "GPL-3.0", "ISC", "LGPL-2.1",
    "LGPL-3.0", "MIT", "MPL-2.0", "Unlicense", "Zlib",
})

DEFAULT_QUERIES = (
    "llm router gateway orchestration archived:false",
    "agent observability evaluation self hosted archived:false",
    "openai compatible gateway routing archived:false",
)

_KEYWORDS = {
    "gateway": 12, "router": 14, "routing": 12, "llm": 8, "agent": 7,
    "observability": 8, "evaluation": 7, "fallback": 8, "guardrail": 6,
    "openai-compatible": 7, "self-host": 7, "telemetry": 6, "workflow": 4,
}

_SEEDS = (
    ("diegosouzapw/OmniRoute", "https://github.com/diegosouzapw/OmniRoute", "MIT",
     "TypeScript", 53130, "Gateway local multi-proveedor con ruteo, fallback y observabilidad.",
     ("topología de proveedores", "preview de ruta explicable", "estados de cuota veraces")),
    ("lm-sys/RouteLLM", "https://github.com/lm-sys/RouteLLM", "Apache-2.0",
     "Python", 5382, "Framework para servir y evaluar routers coste-calidad.",
     ("evaluación del router", "frontera coste-calidad", "datasets reproducibles")),
    ("maximhq/bifrost", "https://github.com/maximhq/bifrost", "Apache-2.0",
     "Go", 7504, "Gateway de IA de alto rendimiento con balanceo adaptativo.",
     ("presupuesto de latencia", "pruebas de carga", "aislamiento del hot path")),
    ("Portkey-AI/gateway", "https://github.com/Portkey-AI/gateway", "MIT",
     "TypeScript", 12797, "Gateway abierto con ruteo y guardrails integrados.",
     ("políticas antes de ejecutar", "fallback declarativo", "gobernanza")),
    ("aurelio-labs/semantic-router", "https://github.com/aurelio-labs/semantic-router", "MIT",
     "Python", 3828, "Capa de decisión rápida para ruteo semántico.",
     ("ruteo nivel 0", "decisión sin llamada generativa", "umbrales calibrables")),
    ("tensorzero/tensorzero", "https://github.com/tensorzero/tensorzero", "Apache-2.0",
     "Rust", 11721, "Plataforma LLMOps abierta para gateway, evaluación y optimización.",
     ("experimentos trazables", "evaluación en producción", "optimización con evidencia")),
    ("Helicone/helicone", "https://github.com/Helicone/helicone", "Apache-2.0",
     "TypeScript", 6092, "Plataforma abierta de observabilidad y evaluación LLM.",
     ("trazas de petición", "métricas operativas", "comparación de variantes")),
    ("microsoft/promptflow", "https://github.com/microsoft/promptflow", "MIT",
     "Python", 11225, "Flujos reproducibles para prototipado, pruebas y monitorización.",
     ("evaluaciones como código", "datasets de regresión", "flujo dev a producción")),
    ("vllm-project/vllm", "https://github.com/vllm-project/vllm", "Apache-2.0",
     "Python", 89714, "Motor abierto de inferencia y serving de alto rendimiento.",
     ("servidor local compatible", "benchmark de throughput", "gestión de memoria")),
    ("katanemo/plano", "https://github.com/katanemo/plano", "Apache-2.0",
     "Rust", 7012, "Proxy y data plane abierto para aplicaciones agénticas.",
     ("separación control/data plane", "guardrails", "observabilidad del agente")),
    ("future-agi/future-agi", "https://github.com/future-agi/future-agi", "Apache-2.0",
     "Python", 1791, "Plataforma autoalojable para evaluar y observar agentes.",
     ("evals como gate", "simulaciones reproducibles", "datasets de regresión")),
    ("api7/aisix", "https://github.com/api7/aisix", "Apache-2.0",
     "Rust", 115, "Gateway abierto compatible con OpenAI, políticas y rate limits.",
     ("rate limits en el borde", "caché explícita", "API compatible")),
    ("openziti/llm-gateway", "https://github.com/openziti/llm-gateway", "Apache-2.0",
     "Go", 89, "Gateway LLM de zero trust con identidad y ruteo semántico.",
     ("identidad por petición", "mínimo privilegio", "segmentación zero trust")),
)


@dataclass
class ProjectRecord:
    repo: str
    url: str
    license: str
    language: str = ""
    stars: int = 0
    description: str = ""
    lessons: list[str] = field(default_factory=list)
    fit_score: int = 0
    updated_at: str = ""
    discovered_at: str = field(default_factory=now_iso)
    source: str = "github_public_metadata"
    snapshot_at: str = ""


class EcosystemRadar:
    """Catálogo creciente de inspiración OSS, sin ingestión de código."""

    def __init__(self, workspace: str, github: Optional[GitHubClient] = None) -> None:
        self.workspace = os.path.abspath(workspace)
        self.github = github or GitHubClient(max_calls=20)
        self.path = os.path.join(self.workspace, ".a2s", "ecosystem", "projects.json")
        self.projects = self._load() or self._seed_records()
        self.last_scan: dict[str, Any] = {}
        if not os.path.isfile(self.path):
            self._save()

    @staticmethod
    def _seed_records() -> list[ProjectRecord]:
        records = []
        for repo, url, license_id, language, stars, desc, lessons in _SEEDS:
            records.append(ProjectRecord(
                repo=repo, url=url, license=license_id, language=language,
                stars=stars, description=desc, lessons=list(lessons),
                fit_score=EcosystemRadar._score(desc, stars, "2026-08-22"),
                updated_at="2026-08-22", source="curated_public_metadata",
                snapshot_at="2026-08-22"))
        return records

    def _load(self) -> list[ProjectRecord]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            return [ProjectRecord(**item) for item in data.get("projects", [])
                    if item.get("license") in OPEN_SOURCE_LICENSES]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "schema_version": 1, "generated_at": now_iso(),
            "policy": {"open_source_only": True, "code_executed": False,
                       "accepted_spdx": sorted(OPEN_SOURCE_LICENSES)},
            "projects": [asdict(p) for p in self.list_projects()],
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def list_projects(self, limit: Optional[int] = None) -> list[ProjectRecord]:
        ordered = sorted(self.projects,
                         key=lambda p: (p.fit_score, p.stars, p.repo.lower()),
                         reverse=True)
        return ordered[:limit] if limit else ordered

    def scan(self, query: str = "", limit_per_query: int = 6) -> dict[str, Any]:
        """Amplía el radar mediante búsqueda pública; solo lee metadatos."""
        queries = (query,) if query.strip() else DEFAULT_QUERIES
        hits: dict[str, RepoHit] = {}
        errors = []
        for q in queries:
            try:
                for hit in self.github.search_repositories(q, per_page=limit_per_query):
                    hits[hit.full_name] = hit
            except BudgetExhausted as exc:
                errors.append(str(exc))
                break
        known = {p.repo: p for p in self.projects}
        added, updated, rejected = [], [], []
        for hit in hits.values():
            reason = self._reject_reason(hit)
            if reason:
                rejected.append({"repo": hit.full_name, "reason": reason})
                continue
            rec = self._from_hit(hit)
            if hit.full_name in known:
                old = known[hit.full_name]
                rec.lessons = old.lessons or rec.lessons
                rec.discovered_at = old.discovered_at
                rec.source = old.source
                rec.snapshot_at = now_iso()[:10]
                self.projects[self.projects.index(old)] = rec
                updated.append(hit.full_name)
            else:
                self.projects.append(rec)
                known[hit.full_name] = rec
                added.append(hit.full_name)
        self._save()
        self.last_scan = {
            "at": now_iso(), "queries": list(queries), "found": len(hits),
            "added": added, "updated": updated, "rejected": rejected,
            "errors": errors, "total": len(self.projects),
            "code_executed": False,
        }
        return self.last_scan

    @staticmethod
    def _reject_reason(hit: RepoHit) -> str:
        if not hit.full_name or not hit.html_url.startswith("https://github.com/"):
            return "fuente no verificable"
        if hit.license not in OPEN_SOURCE_LICENSES:
            return f"licencia no aceptada o desconocida: {hit.license}"
        text = f"{hit.full_name} {hit.description}".lower()
        if classify_forbidden(text):
            return "fuera del modelo de permisos"
        relevance = sum(weight for word, weight in _KEYWORDS.items() if word in text)
        if relevance < 7:
            return "relevancia insuficiente para agentes/ruteo/LLMOps"
        return ""

    @staticmethod
    def _from_hit(hit: RepoHit) -> ProjectRecord:
        return ProjectRecord(
            repo=hit.full_name, url=hit.html_url, license=hit.license,
            language=hit.language, stars=hit.stars, description=hit.description,
            lessons=EcosystemRadar._infer_lessons(hit.description),
            fit_score=EcosystemRadar._score(hit.description, hit.stars, hit.updated_at),
            updated_at=hit.updated_at, snapshot_at=now_iso()[:10])

    @staticmethod
    def _infer_lessons(description: str) -> list[str]:
        text = (description or "").lower()
        lessons = []
        pairs = (("observ", "observabilidad y trazas"),
                 ("evaluat", "evaluación reproducible"),
                 ("router", "ruteo especializado"),
                 ("gateway", "interfaz de gateway"),
                 ("guardrail", "políticas y guardrails"),
                 ("fallback", "resiliencia y fallback"),
                 ("self-host", "despliegue local controlado"))
        for needle, lesson in pairs:
            if needle in text:
                lessons.append(lesson)
        return lessons[:4] or ["revisar arquitectura y pruebas públicas"]

    @staticmethod
    def _score(description: str, stars: int, updated_at: str) -> int:
        text = (description or "").lower()
        relevance = sum(weight for word, weight in _KEYWORDS.items() if word in text)
        popularity = min(22, int(math.log10(max(1, stars)) * 5))
        freshness = 0
        try:
            stamp = time.mktime(time.strptime(updated_at[:10], "%Y-%m-%d"))
            days = max(0.0, (time.time() - stamp) / 86400.0)
            freshness = max(0, 14 - int(days / 90))
        except (ValueError, OverflowError):
            pass
        return max(0, min(100, 32 + relevance + popularity + freshness))

    def snapshot(self, limit: int = 30) -> dict[str, Any]:
        projects = [asdict(p) for p in self.list_projects(limit)]
        return {"projects": projects, "total": len(self.projects),
                "open_source_only": True, "code_executed": False,
                "last_scan": self.last_scan,
                "catalog_path": self.path}
