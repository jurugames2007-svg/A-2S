"""Utilidades de prueba para compatibilidad con Windows.

``temp_dir()`` crea un ``TemporaryDirectory`` que no aborta toda la suite si
un manejador (SQLite/WAL, un pipe de subprocess o un archivo recién escrito)
sigue bloqueado un instante en Windows (WinError 32). En Python >= 3.10 usa
``ignore_cleanup_errors=True``; en 3.9 se salta el error de borrado.
"""

import sys
import tempfile

_PY310 = sys.version_info >= (3, 10)


def temp_dir() -> tempfile.TemporaryDirectory:
    if _PY310:
        return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return tempfile.TemporaryDirectory()
