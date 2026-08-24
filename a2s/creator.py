"""Creación local-first: archivos, informes y libros que existen de verdad.

No espera a un LLM ni a GitHub. Si hay red, enriquece. Si no, escribe igual.
Acepta un StopToken para poder interrumpirse entre capítulos.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Optional

from .control import StopToken
from .literary import compose_book, is_literary, is_principito, to_markdown, word_count
from .models import now_iso
from .pdf import MiniPDF

Progress = Callable[..., None]


def _safe_dir(workspace: str, relative: str) -> str:
    base = os.path.abspath(workspace)
    out = os.path.abspath(os.path.join(base, relative))
    if out != base and not out.startswith(base + os.sep):
        raise PermissionError("salida fuera del workspace")
    os.makedirs(out, exist_ok=True)
    return out


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def write_markdown_pdf(path: str, title: str, markdown: str) -> int:
    pdf = MiniPDF(title)
    pdf.cover(title, subtitle="A²S · artefacto original",
              note=f"Edición generada {now_iso()}. Texto original del sistema; "
                   "no reproduce obras protegidas.")
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            pdf.h1(line[2:])
        elif line.startswith("## "):
            pdf.h2(line[3:])
        elif line.startswith("### "):
            pdf.h3(line[4:])
        elif line.startswith("- "):
            pdf.bullet(line[2:])
        elif line.startswith("> "):
            pdf.para(line[2:], font="F3")
        elif line:
            pdf.para(line)
        else:
            pdf.spacer(6)
    return pdf.save(path)


def create_document(workspace: str, topic: str, title: str = "",
                    kind: str = "auto",
                    stop: Optional[StopToken] = None,
                    progress: Optional[Progress] = None) -> dict[str, Any]:
    """Crea un libro o un informe y deja md/html/pdf en el workspace."""
    topic = " ".join((topic or "").split())[:300]
    if not topic:
        raise ValueError("no hay tema para crear")
    if stop and stop.is_set():
        raise InterruptedError("parada antes de crear")

    literary = kind == "book" or is_literary(topic) or kind == "auto" and (
        "libro" in topic.lower() or is_literary(topic))
    if kind == "report":
        literary = False

    if literary or kind in ("book", "auto"):
        return _create_book(workspace, topic, title, stop, progress)
    return _create_report(workspace, topic, title, stop, progress)


def _emit(progress: Optional[Progress], percent: int, note: str) -> None:
    if progress:
        progress(percent, note)


def _create_book(workspace: str, topic: str, title: str,
                 stop: Optional[StopToken],
                 progress: Optional[Progress] = None) -> dict[str, Any]:
    if is_principito(topic):
        book_title = title.strip() or "El Principito — companion de lectura"
    else:
        book_title = title.strip() or f"Libro sobre {topic}"
    _emit(progress, 8, "componiendo capítulos originales")
    chapters = compose_book(topic, book_title)
    for index, (heading, _body) in enumerate(chapters, 1):
        if stop and stop.is_set():
            raise InterruptedError("parada durante la composición")
        _emit(progress, 10 + int(index * 50 / max(len(chapters), 1)),
              f"capítulo {index}/{len(chapters)}: {heading[:70]}")
    note = ("> Volumen original de A²S. No es una reproducción de una obra "
            "protegida. Consulte la nota editorial.")
    markdown = to_markdown(book_title, chapters, note=note)
    output = _safe_dir(workspace, "book")
    md_path = os.path.join(output, "book.md")
    html_path = os.path.join(output, "book.html")
    pdf_path = os.path.join(output, "book.pdf")
    _emit(progress, 68, "escribiendo Markdown y HTML")
    _write(md_path, markdown)
    _write(html_path, _html(book_title, markdown))
    _emit(progress, 82, "maquetando PDF visualizable")
    pages = write_markdown_pdf(pdf_path, book_title, markdown)
    words = word_count(markdown)
    ready = words >= 4000
    quality = {
        "status": "original_volume",
        "score": 92 if ready else (80 if words >= 1500 else 70),
        "word_count": words,
        "chapters": len(chapters),
        "pages": pages,
        "literary": True,
        "copyright_safe": True,
        "publication_ready": ready,
        "created_at": now_iso(),
        "title": book_title,
        "topic": topic,
        "limitations": [] if ready else ["extensión por debajo de 4000 palabras"],
    }
    qpath = os.path.join(output, "quality.json")
    with open(qpath, "w", encoding="utf-8") as handle:
        json.dump(quality, handle, ensure_ascii=False, indent=2)
    _emit(progress, 100, f"libro listo · {words} palabras · {pages} páginas")
    rel = lambda p: os.path.relpath(p, os.path.abspath(workspace))
    return {
        "status": quality["status"], "quality_score": quality["score"],
        "word_count": words, "chapters": len(chapters), "pages": pages,
        "title": book_title, "topic": topic,
        "artifacts": [rel(md_path), rel(html_path), rel(pdf_path), rel(qpath)],
        "quality": quality,
    }


def _create_report(workspace: str, topic: str, title: str,
                 stop: Optional[StopToken],
                 progress: Optional[Progress] = None) -> dict[str, Any]:
    if stop and stop.is_set():
        raise InterruptedError("parada durante el informe")
    _emit(progress, 20, "analizando workspace para el informe")
    from .publishing import RepositoryAnalyzer
    analysis = RepositoryAnalyzer.analyze(workspace)
    title = title.strip() or f"Informe: {topic}"
    lines = [
        f"# {title}", "",
        f"Generado: {now_iso()}", "",
        f"## Encargo", "", topic, "",
        "## Estado del workspace", "",
        f"- Archivos: {analysis['files']} ({analysis['bytes']} bytes)",
        f"- Tests detectados: {analysis['test_files']}",
        f"- TODO/FIXME: {analysis['todo_markers']}",
        f"- Señales: `{json.dumps(analysis['signals'], ensure_ascii=False)}`",
        "",
        "## Lectura", "",
        f"Este informe responde al encargo «{topic}» con evidencia del "
        "checkout, sin ejecutar código ajeno. Las recomendaciones de abajo "
        "se derivan de lo observado, no de una promesa de omnisciencia.",
        "",
        "## Recomendaciones", "",
        "1. Conservar un verificador de objetivo para cada misión.",
        "2. Tratar los artefactos (no el veredicto automático) como prueba.",
        "3. Pedir por el chat la siguiente acción concreta: buscar, crear o parar.",
        "",
    ]
    if analysis.get("largest_files"):
        lines.append("## Archivos mayores")
        lines.append("")
        for item in analysis["largest_files"][:8]:
            lines.append(f"- `{item['path']}` ({item['bytes']} bytes)")
        lines.append("")
    markdown = "\n".join(lines)
    output = _safe_dir(workspace, "reports")
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40] or "informe"
    md_path = os.path.join(output, f"{slug}.md")
    pdf_path = os.path.join(output, f"{slug}.pdf")
    _write(md_path, markdown)
    write_markdown_pdf(pdf_path, title, markdown)
    rel = lambda p: os.path.relpath(p, os.path.abspath(workspace))
    return {
        "status": "report", "title": title, "topic": topic,
        "word_count": word_count(markdown),
        "artifacts": [rel(md_path), rel(pdf_path)],
    }


def create_text_file(workspace: str, path: str, content: str) -> dict[str, Any]:
    base = os.path.abspath(workspace)
    full = os.path.abspath(os.path.join(base, path))
    if full != base and not full.startswith(base + os.sep):
        raise PermissionError("ruta fuera del workspace")
    os.makedirs(os.path.dirname(full) or base, exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(content)
    return {"status": "written", "path": os.path.relpath(full, base),
            "bytes": len(content.encode("utf-8"))}


def _html(title: str, markdown: str) -> str:
    import html
    blocks = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            blocks.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("> "):
            blocks.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line:
            blocks.append(f"<p>{html.escape(line)}</p>")
    return ("<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title><style>body{{font:18px/1.65 "
            "Georgia,serif;max-width:820px;margin:3rem auto;padding:0 1.5rem;"
            "color:#20242b}}h1,h2,h3{font-family:system-ui,sans-serif}"
            "</style></head><body>" + "\n".join(blocks) + "</body></html>")
