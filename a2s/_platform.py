"""Utilidades de compatibilidad entre plataformas (Unix / Windows).

En Windows la codificación por defecto de stdout/stderr suele ser ``cp1252``,
que no puede representar caracteres como ``✔``, ``→`` o ``·`` y provoca
``UnicodeEncodeError`` al imprimir (los guardianes ``check_*.py``, ``a2s
doctor`` y cualquier salida con símbolos). ``force_utf8()`` cambia ambos
streams a UTF-8 con reemplazo seguro, sin afectar el contenido de los
archivos (que ya se abren con encoding explícito).

También ayuda a la mini-shell a encontrar un shell POSIX en Windows
(Git-Bash/MSYS2/WSL) para los comandos de la lista blanca. El descubrimiento
**verifica** cada candidato ejecutando un marcador de prueba: el lanzador de
WSL (``System32\bash.exe``) sin distribución instalada responde con un error
localizado (cp1252) y exit != 0 para CUALQUIER comando, así que un bash que
no supera la sonda se descarta y se prueba el siguiente candidato. El
resultado se cachea para no pagar la sonda en cada comando.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, Optional

_UTF8_DONE = False

#: Marcador que el shell candidato debe imprimir para darlo por bueno.
_PROBE_MARK = "__a2s_shell_ok__"

#: Caché del shell verificado (o ``None`` si ninguno funciona).
_SHELL_CACHE: dict = {}


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


def _probe_shell(path: str) -> bool:
    """True si ``path`` ejecuta realmente un comando POSIX.

    Un ``bash.exe`` que es el lanzador de WSL sin distribución instalada
    (o un binario corrupto) contesta con exit != 0 y un mensaje localizado;
    esa clase de candidato rompe TODOS los comandos de la mini-shell y debe
    descartarse aquí, no en caliente. La decodificación es tolerante
    (``errors="replace"``) precisamente porque el mensaje puede venir en
    cp1252/cp850.
    """
    if not path or not os.path.isfile(path):
        return False
    try:
        proc = subprocess.run(
            [path, "-c", f"echo {_PROBE_MARK}"],
            capture_output=True, timeout=10, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and _PROBE_MARK in (proc.stdout or "")


def _candidate_shells() -> List[str]:
    """Candidatos a shell POSIX en orden de preferencia (sin duplicados).

    Git-Bash/MSYS2 van antes que el lanzador de WSL: son entornos POSIX
    autocontenidos, mientras que ``System32\bash.exe`` depende de que haya
    una distribución WSL instalada (caso frecuente de fallo silencioso).
    """
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    ordered = [
        shutil.which("bash.exe"),
        shutil.which("sh.exe"),
        os.path.join(program_files, "Git", "bin", "bash.exe"),
        os.path.join(program_files_x86, "Git", "bin", "bash.exe"),
        os.path.join(program_files, "Git", "usr", "bin", "bash.exe"),
        os.path.join(program_files, "Git", "usr", "bin", "sh.exe"),
        r"C:\msys64\usr\bin\bash.exe",
        r"C:\msys32\usr\bin\bash.exe",
    ]
    # El lanzador de WSL siempre al final: solo sirve si hay distribución.
    wsl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       "System32", "bash.exe")
    seen = set()
    out: List[str] = []
    for path in ordered + [wsl]:
        if not path:
            continue
        key = os.path.normcase(os.path.normpath(path))
        if key in seen:
            continue
        seen.add(key)
        if os.path.normcase(path) == os.path.normcase(wsl):
            continue  # se añade al final, una sola vez
        out.append(path)
    out.append(wsl)
    return out


def find_posix_shell(validate: bool = True) -> Optional[str]:
    """Devuelve la ruta a un shell POSIX **funcional** en Windows o ``None``.

    En sistemas no-Windows devuelve ``None`` (se usa ejecución directa).
    Con ``validate=True`` (default) cada candidato se somete a una sonda
    real (``echo`` + marcador) y el resultado se cachea por proceso; con
    ``validate=False`` se devuelve el primer candidato existente sin
    probarlo (útil para tests y diagnósticos rápidos).
    """
    if os.name != "nt":
        return None
    if validate and "path" in _SHELL_CACHE:
        return _SHELL_CACHE["path"]
    for path in _candidate_shells():
        if validate and not _probe_shell(path):
            continue
        if not validate and not os.path.isfile(path):
            continue
        if validate:
            _SHELL_CACHE["path"] = path
        return path
    if validate:
        _SHELL_CACHE["path"] = None
    return None


def _clear_shell_cache() -> None:
    """Vacía la caché del shell verificado (uso en tests)."""
    _SHELL_CACHE.clear()


def windows_has_posix_tools() -> bool:
    """True si hay disponible un shell POSIX VERIFICADO en el que los
    comandos de la lista blanca (ls, grep, find, sha256sum...) existen."""
    return find_posix_shell() is not None
