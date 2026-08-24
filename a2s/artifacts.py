"""Exploración y servicio de artefactos/resultados del workspace.

El panel de "Resultados" del asistente usa estas funciones para:

* Listar los archivos que el agente ha producido en el workspace (excluyendo
  ``.a2s`` y ``.git``, que son estado interno).
* Servir el contenido de un archivo para descargarlo o previsualizarlo en el
  navegador: imágenes (png/jpg/svg/webp/gif), PDF, audio, vídeo, texto y
  Markdown renderizado.

Toda ruta se **valida dentro del workspace**: no se sirve nada fuera de él.
"""

from __future__ import annotations

import mimetypes
import os
from typing import Any, Optional

# Extensiones que el navegador puede previsualizar en línea de forma segura.
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".opus", ".flac", ".m4a", ".aac"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".ogv"}
PDF_EXTS = {".pdf"}
HTML_EXTS = {".html", ".htm"}
TEXT_EXTS = {".txt", ".md", ".markdown", ".json", ".csv", ".log", ".py", ".js",
             ".css", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
             ".sh", ".sql", ".ts", ".tsx", ".jsx", ".go", ".rs", ".c", ".h",
             ".java", ".rb", ".php", ".env", ".gitignore", ".editorconfig"}
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".bz2", ".7z", ".xz", ".pptx", ".docx"}


def classify_kind(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in HTML_EXTS:
        return "html"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in TEXT_EXTS:
        return "text"
    return "binary"


def _resolve(workspace: str, relpath: str) -> Optional[str]:
    """Resuelve y valida que ``relpath`` esté dentro del workspace."""
    relpath = (relpath or "").lstrip("/")
    base = os.path.abspath(workspace)
    full = os.path.abspath(os.path.join(base, relpath))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


EXCLUDE_DIRS = {".a2s", ".git", "__pycache__", ".venv", "node_modules",
                ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next",
                ".nuxt", "dist", "build", ".cache", ".arena", ".output",
                ".parcel-cache", ".tox", "target", ".turbo"}
MAX_PREVIEW_BYTES = 2_000_000


def list_artifacts(workspace: str) -> list[dict[str, Any]]:
    """Lista los archivos del workspace con metadata para el panel."""
    base = os.path.abspath(workspace)
    if not os.path.isdir(base):
        return []
    out: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base)
            try:
                st = os.stat(full)
            except OSError:
                continue
            out.append({
                "path": rel.replace(os.sep, "/"),
                "name": name,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
                "kind": classify_kind(name),
                "previewable": classify_kind(name) in (
                    "image", "audio", "video", "pdf", "html", "text"),
            })
    out.sort(key=lambda a: a["mtime"], reverse=True)
    return out


def get_artifact(workspace: str, relpath: str) -> Optional[dict[str, Any]]:
    """Devuelve metadata + contenido (si es texto) de un artefacto."""
    full = _resolve(workspace, relpath)
    if not full or not os.path.isfile(full):
        return None
    kind = classify_kind(full)
    try:
        st = os.stat(full)
    except OSError:
        return None
    data: dict[str, Any] = {
        "path": relpath, "name": os.path.basename(full),
        "size": st.st_size, "mtime": int(st.st_mtime), "kind": kind,
        "previewable": kind in ("image", "audio", "video", "pdf", "html", "text"),
    }
    if kind == "text" and st.st_size <= MAX_PREVIEW_BYTES:
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                data["text"] = fh.read(MAX_PREVIEW_BYTES)
        except OSError:
            data["text"] = ""
    data["download_url"] = f"/api/artifact?path={_quote(relpath)}&download=1"
    if kind in ("image", "audio", "video", "pdf"):
        data["raw_url"] = f"/api/artifact?path={_quote(relpath)}&raw=1"
    mime, _ = mimetypes.guess_type(full)
    if not mime:
        mime = {"image": "application/octet-stream", "audio": "audio/mpeg",
                "video": "video/mp4", "pdf": "application/pdf",
                "text": "text/plain", "archive": "application/zip",
                "binary": "application/octet-stream"}.get(kind, "application/octet-stream")
    data["mime"] = mime
    return data


def read_artifact_bytes(workspace: str, relpath: str) -> Optional[tuple[bytes, str, str]]:
    """Devuelve (bytes, mime, filename) para servir el archivo tal cual."""
    full = _resolve(workspace, relpath)
    if not full or not os.path.isfile(full):
        return None
    try:
        with open(full, "rb") as fh:
            blob = fh.read()
    except OSError:
        return None
    mime, _ = mimetypes.guess_type(full)
    if not mime:
        mime = "application/octet-stream"
    return blob, mime, os.path.basename(full)


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="/")
