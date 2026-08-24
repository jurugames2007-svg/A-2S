"""Estudio Jarvis: libros completos, PPT con proceso y obtención OA."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

from .control import StopToken
from .finder import fold
from .intent import wants_obtain, wants_slides
from .literary import is_literary, is_principito
from .models import now_iso

Progress = Callable[..., None]


def classify_job(topic: str, options: Optional[dict[str, Any]] = None) -> str:
    options = options or {}
    kind = str(options.get("kind") or "")
    if kind in {"slides", "book", "report", "obtain"}:
        return kind
    if options.get("slides") or wants_slides(topic):
        return "slides"
    if options.get("obtain") or wants_obtain(topic):
        return "obtain"
    if options.get("book") or is_literary(topic) or "libro" in fold(topic):
        return "book"
    if "informe" in fold(topic) and "libro" not in fold(topic):
        return "report"
    return "book"


def produce(workspace: str, topic: str,
            options: Optional[dict[str, Any]] = None,
            stop: Optional[StopToken] = None,
            progress: Optional[Progress] = None,
            transport=None) -> dict[str, Any]:
    """Punto único de creación. Emite progreso y deja artefactos reales."""
    options = options or {}
    topic = " ".join((topic or "").split())[:300]
    if not topic:
        raise ValueError("no hay tema para el estudio")
    if stop:
        stop.raise_if_set()
    job = classify_job(topic, options)
    log = _ProcessLog(workspace, job, progress)
    log.emit(4, f"encargo clasificado como {job}")
    if job == "slides":
        from .slides import create_deck
        return create_deck(workspace, topic, title=str(options.get("title") or ""),
                           stop=stop, progress=log.forward)
    if job == "obtain":
        return _obtain_or_write(workspace, topic, options, stop, log, transport)
    from .creator import create_document
    kind = "report" if job == "report" else "book"
    return create_document(workspace, topic, title=str(options.get("title") or ""),
                           kind=kind, stop=stop, progress=log.forward)


def _obtain_or_write(workspace: str, topic: str, options: dict[str, Any],
                     stop: Optional[StopToken], log: "_ProcessLog",
                     transport) -> dict[str, Any]:
    from .acquire import fetch_public_domain, to_markdown
    from .creator import _html, _safe_dir, _write, write_markdown_pdf
    from .literary import word_count

    if is_principito(topic):
        log.emit(12, "Principito: no se descarga la novela; companion original")
        from .creator import create_document
        result = create_document(workspace, topic, kind="book", stop=stop,
                                 progress=log.forward)
        result["obtain"] = "refused_copyright"
        return result
    log.emit(15, "buscando edición de dominio público (Gutenberg)")
    got = fetch_public_domain(topic, transport=transport)
    if got.get("status") != "obtained":
        log.emit(30, f"no se obtuvo OA ({got.get('reason', 'sin motivo')}); escribo volumen original")
        from .creator import create_document
        result = create_document(workspace, topic, kind="book", stop=stop,
                                 progress=log.forward)
        result["obtain"] = got.get("status")
        result["obtain_reason"] = got.get("reason")
        return result
    if stop:
        stop.raise_if_set()
    title = got["title"]
    log.emit(45, f"texto OA: {title} (#{got.get('gutenberg_id')})")
    markdown = to_markdown(title, got["text"], got)
    output = _safe_dir(workspace, "book")
    md_path = os.path.join(output, "book.md")
    html_path = os.path.join(output, "book.html")
    pdf_path = os.path.join(output, "book.pdf")
    txt_path = os.path.join(output, "book.txt")
    _write(md_path, markdown)
    _write(txt_path, got["text"])
    _write(html_path, _html(title, markdown))
    log.emit(70, "maquetando PDF visualizable")
    pages = write_markdown_pdf(pdf_path, title, markdown)
    words = word_count(markdown)
    quality = {
        "status": "public_domain_volume",
        "score": 92 if words >= 1500 else 75,
        "word_count": words, "pages": pages,
        "gutenberg_id": got.get("gutenberg_id"),
        "source_url": got.get("source_url"),
        "truncated": got.get("truncated", False),
        "full_chars": got.get("full_chars"),
        "copyright_safe": True,
        "publication_ready": words >= 1500,
        "created_at": now_iso(), "title": title, "topic": topic,
        "limitations": (["extracto maquetado; texto completo en book.txt"]
                        if got.get("truncated") else []),
    }
    qpath = os.path.join(output, "quality.json")
    with open(qpath, "w", encoding="utf-8") as handle:
        json.dump(quality, handle, ensure_ascii=False, indent=2)
    log.emit(100, "libro de dominio público listo")
    rel = lambda p: os.path.relpath(p, os.path.abspath(workspace))
    return {
        "status": "public_domain_volume", "title": title, "topic": topic,
        "word_count": words, "pages": pages, "quality_score": quality["score"],
        "artifacts": [rel(md_path), rel(html_path), rel(pdf_path),
                      rel(txt_path), rel(qpath)],
        "quality": quality, "obtain": "obtained",
    }


class _ProcessLog:
    def __init__(self, workspace: str, kind: str,
                 progress: Optional[Progress]) -> None:
        self.kind = kind
        self.progress = progress
        self.steps: list[dict[str, Any]] = []
        self.path = os.path.join(os.path.abspath(workspace), ".a2s",
                                 "studio_process.json")

    def emit(self, percent: int, note: str, extra: Optional[dict[str, Any]] = None
             ) -> None:
        step = {"percent": int(percent), "note": note, "at": now_iso(),
                "kind": self.kind}
        if extra:
            step.update(extra)
        self.steps.append(step)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({"kind": self.kind, "steps": self.steps[-80:]}, fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        if self.progress:
            self.progress(int(percent), note, extra={"kind": self.kind, **(extra or {})})

    def forward(self, percent: int, note: str, extra: Optional[dict[str, Any]] = None
                ) -> None:
        self.emit(percent, note, extra)
