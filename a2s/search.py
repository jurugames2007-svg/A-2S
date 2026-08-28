"""Memoria semántica ligera: índice invertido BM25 en stdlib puro.

Criterios 9/48/214 del roadmap: búsqueda por relevancia sobre lo que el
sistema SABE — episodios de la memoria (SQLite), fichas de conocimiento y
artefactos del pool — sin embeddings ni dependencias: BM25 (Okapi) clásico.

* ``BM25Index``: construye/consulta un índice sobre documentos (id, texto).
* ``workspace_search``: recopila documentos de un workspace real y busca.
* CLI: ``a2s search "consulta" --workspace ws --top 5``
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

_TOKEN_RE = re.compile(r"[a-z0-9áéíóúñü]{2,}")
_STOP = set("""de la el los las un una y o en para con como por que se al del lo
the a an of to for with and or is are be this that it as on at by from""".split())


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def tokeniza(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(_norm(text).lower()) if t not in _STOP]


@dataclass
class Doc:
    doc_id: str
    texto: str
    origen: str            # episodio | ficha | pool | investigacion | recurso
    meta: str = ""         # línea descriptiva para mostrar


class BM25Index:
    """Okapi BM25 (k1=1.5, b=0.75): ranking estándar, explicable y barato."""

    def __init__(self, docs: Iterable[Doc]) -> None:
        self.docs = list(docs)
        self._tf: dict[str, dict[str, int]] = {}      # term → {doc_id: freq}
        self._len: dict[str, int] = {}
        for d in self.docs:
            toks = tokeniza(d.texto)
            self._len[d.doc_id] = len(toks)
            for t in toks:
                self._tf.setdefault(t, {}).setdefault(d.doc_id, 0)
                self._tf[t][d.doc_id] += 1
        self._n = max(1, len(self.docs))
        self._avg = (sum(self._len.values()) / self._n) or 1.0
        self._df = {t: len(post) for t, post in self._tf.items()}
        self._by_id = {d.doc_id: d for d in self.docs}

    def search(self, consulta: str, top: int = 5) -> list[tuple[Doc, float]]:
        k1, b = 1.5, 0.75
        scores: dict[str, float] = {}
        for t in tokeniza(consulta):
            post = self._tf.get(t)
            if not post:
                continue
            idf = math.log(1 + (self._n - len(post) + 0.5) / (len(post) + 0.5))
            for doc_id, f in post.items():
                den = f * (k1 + 1)
                norm = k1 * (1 - b + b * self._len[doc_id] / self._avg)
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * den / (f + norm)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
        return [(self._by_id[i], s) for i, s in ranked if s > 0]


# --------------------------------------------------------------------------
# Recopilación de documentos de un workspace
# --------------------------------------------------------------------------

def _docs_episodios(workspace: str) -> list[Doc]:
    db = os.path.join(os.path.abspath(workspace), ".a2s", "memory.sqlite")
    if not os.path.isfile(db):
        return []
    out = []
    con = None
    try:
        con = sqlite3.connect(db)
        for row in con.execute(
                "SELECT at, step_goal, approach, tool, reason FROM episodes "
                "ORDER BY at DESC LIMIT 2000"):
            at, goal, approach, tool, reason = row
            out.append(Doc(
                doc_id=f"ep:{at}:{goal}:{len(out)}",
                texto=" ".join(str(x) for x in (goal, approach, tool, reason) if x),
                origen="episodio",
                meta=f"{at} · {goal} ({tool})"))
    except sqlite3.Error:
        pass
    finally:
        if con is not None:
            con.close()
    return out


def _docs_fichas(workspace: str) -> list[Doc]:
    from .learner import load_cards
    out = []
    for c in load_cards(workspace):
        out.append(Doc(
            doc_id=f"ficha:{c.repo}",
            texto=f"{c.topic} {c.summary} {c.recipe} {c.repo}",
            origen="ficha",
            meta=f"{c.repo} (lic. {c.license}, ganadas {c.wins}/{c.used})"))
    return out


def _docs_recursos() -> list[Doc]:
    """Catálogo curado de recursos del operador (``a2s recursos``)."""
    from .recursos import docs_memoria
    return docs_memoria()


def _docs_pool(workspace: str) -> list[Doc]:
    st = os.path.join(os.path.abspath(workspace), ".a2s", "pool", "state.json")
    out = []
    if os.path.isfile(st):
        try:
            with open(st, encoding="utf-8") as fh:
                data = json.load(fh)
            for name, agg in data.get("endpoints", {}).items():
                out.append(Doc(
                    doc_id=f"pool:{name}",
                    texto=f"endpoint pool {name} llamadas {agg.get('total')} "
                          f"exitos {agg.get('ok')} rpm_aprendido "
                          f"{data.get('learned_rpm', {}).get(name, 'no')}",
                    origen="pool",
                    meta=f"{name}: {agg.get('total', 0)} llamadas, "
                         f"{agg.get('rate_limited', 0)} saturaciones"))
        except (OSError, json.JSONDecodeError):
            pass
    return out


def _docs_investigacion(workspace: str) -> list[Doc]:
    """Fuentes producidas por ``a2s research``/``a2s book``."""
    base = os.path.abspath(workspace)
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [directory for directory in dirs
                   if directory not in (".git", ".a2s", "node_modules", ".venv")]
        if "sources.json" not in files or os.path.basename(root) != "research":
            continue
        try:
            with open(os.path.join(root, "sources.json"), encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, ValueError):
            continue
        for source in report.get("sources", [])[:100]:
            out.append(Doc(
                doc_id=f"research:{source.get('id')}:{source.get('url')}",
                texto=" ".join(str(source.get(key, "")) for key in
                               ("title", "summary", "authors", "kind", "updated_at")),
                origen="investigacion",
                meta=f"{source.get('id')} · {source.get('title', '')} · {source.get('url', '')}"))
    return out


def workspace_search(workspace: str, consulta: str, top: int = 5,
                     origenes: Optional[set[str]] = None
                     ) -> list[tuple[Doc, float]]:
    docs = (_docs_episodios(workspace) + _docs_fichas(workspace) +
            _docs_pool(workspace) + _docs_investigacion(workspace) +
            _docs_recursos())
    if origenes:
        docs = [d for d in docs if d.origen in origenes]
    if not docs:
        return []
    return BM25Index(docs).search(consulta, top=top)
