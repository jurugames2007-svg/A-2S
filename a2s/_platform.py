"""Utilidades de compatibilidad entre plataformas (Unix / Windows).

En Windows la codificación por defecto de stdout/stderr suele ser ``cp1252``,
que no puede representar caracteres como ``✔``, ``→`` o ``·`` y provoca
``UnicodeEncodeError`` al imprimir (los guardianes ``check_*.py``, ``a2s
doctor`` y cualquier salida con símbolos). ``force_utf8()`` cambia ambos
streams a UTF-8 con reemplazo seguro, sin afectar el contenido de los
archivos (que ya se abren con encoding explícito).

También ayuda a la mini-shell a encontrar un shell POSIX en Windows
(Git-Bash/MSYS2/WSL) para los comandos de la lista blanca.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Optional

_UTF8_DONE = False


def force_utf8() -> None:
    """Reconfigura stdout/stderr a UTF-8 (idempotente y seguro sin TTY)."""
    global _UTF8_DONE
    if _UTF8_DONE:
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    _UTF8_DONE = True


def find_posix_shell() -> Optional[str]:
    """Devuelve la ruta a un shell POSIX en Windows (bash de Git/MSYS2/WSL) o
    ``None`` si no hay ninguno. En sistemas no-Windows devuelve ``None`` (se
    usa ejecución directa como hasta ahora).
    """
    if os.name != "nt":
        return None
    for candidate in ("bash.exe", "sh.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    # Rutas típicas cuando el PATH no las expone.
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        os.path.join(program_files, "Git", "bin", "bash.exe"),
        os.path.join(program_files_x86, "Git", "bin", "bash.exe"),
        os.path.join(program_files, "Git", "usr", "bin", "bash.exe"),
        os.path.join(program_files, "Git", "usr", "bin", "sh.exe"),
        r"C:\msys64\usr\bin\bash.exe",
        r"C:\msys32\usr\bin\bash.exe",
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "bash.exe"),  # WSL
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def windows_has_posix_tools() -> bool:
    """True si hay disponible un shell POSIX en el que los comandos de la
    lista blanca (ls, grep, find, sha256sum...) existen."""
    return find_posix_shell() is not None
