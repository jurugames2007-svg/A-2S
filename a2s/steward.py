"""Mayordomo de archivos del workspace: ordenar, mover, renombrar, limpiar.

No controla el escritorio del sistema operativo. Opera solo dentro del
workspace A²S, con diario de deshacer y una lista de rutas protegidas.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any, Optional

from .artifacts import classify_kind
from .control import StopToken
from .models import now_iso

PROTECTED_DIRS = {".a2s", ".git", "__pycache__", ".venv", "node_modules"}
PROTECTED_NAMES = {"quality.json", "book.md", "book.pdf", "book.html",
                   "LICENSE", "README.md"}
PROTECTED_EXTS = {".pem", ".key", ".kdbx", ".wallet", ".asc"}
IMPORTANT_HINTS = ("wallet", "secreto", "backup", "contrato", "factura",
                   "dni", "pasaporte", "nomina", "impuesto", "historial")
SKIP_ROOTS = {".a2s", ".git", "book", "slides", "programs", "counsel",
              "opportunities", "hardware"}

BUCKETS = {
    "image": "media/images",
    "audio": "media/audio",
    "video": "media/video",
    "pdf": "docs/pdf",
    "text": "docs/text",
    "html": "docs/html",
    "archive": "archives",
    "binary": "binaries",
}


def is_protected(relpath: str) -> bool:
    parts = relpath.replace("\\", "/").split("/")
    if any(part in PROTECTED_DIRS for part in parts):
        return True
    name = parts[-1].lower() if parts else ""
    if name in {n.lower() for n in PROTECTED_NAMES}:
        return True
    ext = os.path.splitext(name)[1].lower()
    if ext in PROTECTED_EXTS:
        return True
    folded = name
    return any(hint in folded for hint in IMPORTANT_HINTS)


def _rel(workspace: str, full: str) -> str:
    return os.path.relpath(full, os.path.abspath(workspace)).replace(os.sep, "/")


def _inside(workspace: str, full: str) -> bool:
    base = os.path.abspath(workspace)
    path = os.path.abspath(full)
    return path == base or path.startswith(base + os.sep)


def plan_organize(workspace: str, root: str = ".") -> list[dict[str, str]]:
    base = os.path.abspath(workspace)
    start = os.path.abspath(os.path.join(base, root))
    if not _inside(base, start) or not os.path.isdir(start):
        return []
    moves: list[dict[str, str]] = []
    for name in sorted(os.listdir(start)):
        if name in PROTECTED_DIRS or name in SKIP_ROOTS:
            continue
        full = os.path.join(start, name)
        if not os.path.isfile(full):
            continue
        rel = _rel(base, full)
        if is_protected(rel):
            continue
        dest_dir = BUCKETS.get(classify_kind(name), "misc")
        dest = os.path.join(base, dest_dir, name)
        if os.path.abspath(full) == os.path.abspath(dest):
            continue
        moves.append({"from": rel, "to": _rel(base, dest), "op": "move"})
    return moves


def apply_moves(workspace: str, moves: list[dict[str, str]],
                stop: Optional[StopToken] = None) -> dict[str, Any]:
    base = os.path.abspath(workspace)
    done: list[dict[str, str]] = []
    skipped: list[str] = []
    for item in moves:
        if stop:
            stop.raise_if_set()
        src = os.path.abspath(os.path.join(base, item["from"]))
        dst = os.path.abspath(os.path.join(base, item["to"]))
        if not _inside(base, src) or not _inside(base, dst):
            skipped.append(item["from"])
            continue
        if is_protected(item["from"]) or is_protected(item["to"]):
            skipped.append(item["from"])
            continue
        if not os.path.isfile(src):
            skipped.append(item["from"])
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            skipped.append(item["from"])
            continue
        shutil.move(src, dst)
        done.append({"from": item["from"], "to": item["to"]})
    journal = _append_journal(base, done)
    return {"status": "organized", "moved": len(done), "skipped": skipped,
            "moves": done, "undo": journal, "at": now_iso()}


def undo_last(workspace: str) -> dict[str, Any]:
    path = os.path.join(os.path.abspath(workspace), ".a2s", "steward_journal.json")
    try:
        with open(path, encoding="utf-8") as fh:
            log = json.load(fh)
    except (OSError, ValueError):
        return {"status": "nothing_to_undo", "restored": 0}
    if not log:
        return {"status": "nothing_to_undo", "restored": 0}
    last = log.pop()
    restored = 0
    base = os.path.abspath(workspace)
    for item in reversed(last.get("moves") or []):
        src = os.path.abspath(os.path.join(base, item["to"]))
        dst = os.path.abspath(os.path.join(base, item["from"]))
        if os.path.isfile(src) and _inside(base, src) and _inside(base, dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.move(src, dst)
                restored += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=2)
    return {"status": "undone", "restored": restored}


def rename_file(workspace: str, src: str, dest_name: str) -> dict[str, Any]:
    base = os.path.abspath(workspace)
    full = os.path.abspath(os.path.join(base, src))
    if not _inside(base, full) or not os.path.isfile(full):
        raise FileNotFoundError(src)
    if is_protected(_rel(base, full)):
        raise PermissionError("archivo protegido")
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", dest_name).strip(".-") or "renombrado"
    dst = os.path.join(os.path.dirname(full), clean)
    if os.path.exists(dst):
        raise FileExistsError(clean)
    shutil.move(full, dst)
    move = {"from": _rel(base, full), "to": _rel(base, dst)}
    _append_journal(base, [move])
    return {"status": "renamed", **move}


def cleanup(workspace: str, apply: bool = False,
            stop: Optional[StopToken] = None) -> dict[str, Any]:
    """Borra solo basura evidente. Nunca toca datos importantes."""
    base = os.path.abspath(workspace)
    candidates: list[str] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in PROTECTED_DIRS]
        rel_root = _rel(base, root)
        if any(part in SKIP_ROOTS or part in PROTECTED_DIRS
               for part in rel_root.split("/")):
            continue
        for name in files:
            full = os.path.join(root, name)
            rel = _rel(base, full)
            if is_protected(rel):
                continue
            low = name.lower()
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            trash = low.endswith((".tmp", ".pyc", ".bak", "~")) or (
                size == 0 and low.endswith(".log"))
            if trash:
                candidates.append(rel)
    deleted: list[str] = []
    if apply:
        for rel in candidates:
            if stop:
                stop.raise_if_set()
            full = os.path.join(base, rel)
            if os.path.isfile(full) and not is_protected(rel):
                os.remove(full)
                deleted.append(rel)
    return {"status": "cleaned" if apply else "cleanup_preview",
            "candidates": candidates, "deleted": deleted,
            "protected_skipped": True}


def customize_desktop(workspace: str, theme: str = "aegis",
                      animate: bool = True) -> dict[str, Any]:
    """Escritorio virtual del workspace (HTML), no el del SO."""
    base = os.path.abspath(os.path.join(os.path.abspath(workspace), "desktop"))
    os.makedirs(base, exist_ok=True)
    layout = {"theme": theme, "animate": bool(animate), "at": now_iso(),
              "note": "Escritorio virtual A²S. No modifica iconos del sistema operativo."}
    with open(os.path.join(base, "layout.json"), "w", encoding="utf-8") as fh:
        json.dump(layout, fh, ensure_ascii=False, indent=2)
    icons = []
    ws = os.path.abspath(workspace)
    for name in sorted(os.listdir(ws))[:24]:
        if name.startswith("."):
            continue
        kind = "dir" if os.path.isdir(os.path.join(ws, name)) else classify_kind(name)
        icons.append(f"<div class='icon {kind}'><i></i><span>{_esc(name)}</span></div>")
    motion = "@keyframes float{50%{transform:translateY(-6px)}} .icon{animation:float 3s ease-in-out infinite}" if animate else ""
    html = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Escritorio A²S</title><style>"
        "body{margin:0;background:#07111d;color:#e9f1f7;font:14px/1.4 system-ui}"
        ".desk{display:flex;flex-wrap:wrap;gap:18px;padding:28px}"
        ".icon{width:88px;text-align:center}.icon i{display:block;height:48px;"
        "border:1px solid #31506c;background:#0c1825;border-radius:8px}"
        f"{motion}</style></head><body><header style='padding:16px 28px'>"
        f"<b>Escritorio virtual · tema { _esc(theme) }</b>"
        "<p>No es el escritorio de Windows/macOS. Es el workspace A²S.</p>"
        f"</header><div class='desk'>{''.join(icons)}</div></body></html>"
    )
    path = os.path.join(base, "desktop.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return {"status": "desktop_virtual", "theme": theme, "animate": animate,
            "artifacts": ["desktop/desktop.html", "desktop/layout.json"]}


def run_steward(workspace: str, topic: str,
                stop: Optional[StopToken] = None) -> dict[str, Any]:
    folded = (topic or "").lower()
    artifacts: list[str] = []
    if any(w in folded for w in ("deshacer", "undo", "revertir")):
        result = undo_last(workspace)
    elif any(w in folded for w in ("limpi", "basura", "cleanup")):
        result = cleanup(workspace, apply=True, stop=stop)
    elif any(w in folded for w in ("icono", "personaliz", "anim", "tema")):
        result = customize_desktop(workspace, animate="sin anim" not in folded)
        artifacts = result.get("artifacts") or []
    elif any(w in folded for w in ("renombr",)):
        result = {"status": "need_names",
                  "note": "Indica: renombra archivo X a Y"}
    else:
        moves = plan_organize(workspace)
        result = apply_moves(workspace, moves, stop=stop)
    report = os.path.join(os.path.abspath(workspace), "desktop", "steward.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, "w", encoding="utf-8") as fh:
        fh.write(f"# Mayordomo A²S\n\n{now_iso()}\n\n```json\n"
                 f"{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n")
    artifacts = artifacts + ["desktop/steward.md"]
    result["artifacts"] = artifacts
    result["title"] = "Mayordomo de archivos"
    return result


def _append_journal(workspace: str, moves: list[dict[str, str]]) -> str:
    path = os.path.join(workspace, ".a2s", "steward_journal.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log: list[Any] = []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                log = json.load(fh)
        except (OSError, ValueError):
            log = []
    if moves:
        log.append({"at": now_iso(), "moves": moves})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(log[-50:], fh, ensure_ascii=False, indent=2)
    return ".a2s/steward_journal.json"


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
