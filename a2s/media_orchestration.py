"""Adaptadores opcionales de medios y orquestacion local.

No descarga contenido por defecto, no evade restricciones y no ejecuta codigo
obtenido de Internet. yt-dlp es una dependencia opcional del operador.
"""

from __future__ import annotations

import concurrent.futures
import importlib
import os
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Optional


class MediaExtractor:
    """Adaptador seguro y opcional para metadatos y medios con yt-dlp."""

    def __init__(self, output_dir: str = "downloads") -> None:
        self.output_dir = os.path.abspath(output_dir)

    @staticmethod
    def available() -> bool:
        return shutil.which("yt-dlp") is not None or _yt_dlp_module() is not None

    def status(self) -> dict[str, Any]:
        return {"available": self.available(), "output_dir": self.output_dir,
                "download_requires_rights": True}

    def extract_info(self, url: str) -> dict[str, Any]:
        module = _yt_dlp_module()
        if module is None:
            return {"ok": False, "available": False,
                    "reason": "yt-dlp no instalado"}
        if not url.startswith(("https://", "http://")):
            raise ValueError("URL invalida")
        options = {"quiet": True, "skip_download": True, "noplaylist": True}
        try:
            with module.YoutubeDL(options) as client:
                info = client.extract_info(url, download=False)
            return {"ok": True, "available": True,
                    "title": info.get("title", ""),
                    "description": info.get("description", ""),
                    "duration": info.get("duration"),
                    "view_count": info.get("view_count"),
                    "uploader": info.get("uploader", ""),
                    "webpage_url": info.get("webpage_url", url),
                    "subtitles": sorted((info.get("subtitles") or {}).keys())}
        except Exception as exc:
            return {"ok": False, "available": True,
                    "reason": f"{type(exc).__name__}: {exc}"}

    def download(self, url: str, rights_confirmed: bool = False,
                 audio_only: bool = False) -> dict[str, Any]:
        if not rights_confirmed:
            raise PermissionError("confirma derechos de descarga del contenido")
        module = _yt_dlp_module()
        if module is None:
            return {"ok": False, "available": False,
                    "reason": "yt-dlp no instalado"}
        os.makedirs(self.output_dir, exist_ok=True)
        options: dict[str, Any] = {
            "quiet": True, "noplaylist": True,
            "outtmpl": os.path.join(self.output_dir, "%(title).120s.%(ext)s"),
        }
        if audio_only:
            options["format"] = "bestaudio"
        try:
            with module.YoutubeDL(options) as client:
                result = client.download([url])
            return {"ok": result == 0, "available": True,
                    "output_dir": self.output_dir}
        except Exception as exc:
            return {"ok": False, "available": True,
                    "reason": f"{type(exc).__name__}: {exc}"}


def _yt_dlp_module() -> Any:
    try:
        return importlib.import_module("yt_dlp")
    except ImportError:
        return None


@dataclass(frozen=True)
class Task:
    id: str
    operation: Callable[[], Any]


class TaskOrchestrator:
    """Ejecuta funciones locales independientes con workers acotados."""

    def __init__(self, max_workers: int = 4) -> None:
        if max_workers < 1 or max_workers > 32:
            raise ValueError("max_workers fuera de rango (1..32)")
        self.max_workers = max_workers

    def run(self, tasks: list[Task], timeout: Optional[float] = None) -> dict[str, Any]:
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de tarea duplicados")
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            pending = {pool.submit(task.operation): task.id for task in tasks}
            try:
                for future in concurrent.futures.as_completed(pending, timeout=timeout):
                    task_id = pending[future]
                    try:
                        results[task_id] = future.result()
                    except Exception as exc:
                        errors[task_id] = f"{type(exc).__name__}: {exc}"
            except concurrent.futures.TimeoutError:
                for future, task_id in pending.items():
                    if not future.done():
                        future.cancel()
                        errors[task_id] = "TimeoutError: tarea excedio el limite"
        return {"results": results, "errors": errors,
                "completed": len(results), "failed": len(errors),
                "total": len(tasks)}
