"""Auto-actualización de A²S en el sitio: ``a2s update`` (alias: ``tkm``).

Actualiza la instalación actual SIN re-descargar el repositorio completo:

* Si la instalación es un **checkout git** (el caso típico del operador),
  solo baja los objetos que faltan (``git fetch``) y avanza la rama con
  fast-forward — segundos en vez de una descarga nueva.
* Si no es un checkout git (instalación npm global), explica cómo pasar al
  flujo en el sitio.

El comando acepta un apelativo opcional por costumbre del operador::

    a2s update tkm          # actualiza en el sitio
    a2s update tkm --check  # solo mira si hay novedades
    update tkm              # vía update.cmd (repo) o el alias de PowerShell

Todo es stdlib (contrato de pureza) y ningún paso modifica nada sin decirlo.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from typing import Callable, Optional

Print = Callable[[str], None]

_EXIT_OK = 0
_EXIT_SIN_GIT = 2
_EXIT_NO_CHECKOUT = 3
_EXIT_SUCIO = 4
_EXIT_DIVERGENTE = 5
_EXIT_RED = 6


def package_root() -> str:
    """Raíz del paquete (donde vive ``a2s/``)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(root: str, *args: str, timeout: int = 120) -> tuple:
    """Ejecuta ``git`` en ``root`` y devuelve ``(rc, salida, error)``.

    Decodificación tolerante: git en Windows puede emitir mensajes
    localizados en cp1252/cp850; nunca debe lanzar UnicodeDecodeError.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, timeout=timeout,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return _EXIT_SIN_GIT, "", "git no está instalado"
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def detect_repo(root: str) -> Optional[dict]:
    """Info del checkout en ``root`` o ``None`` si no es un repo git."""
    rc, out, _ = git(root, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or out != "true":
        return None
    _, branch, _ = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _, head, _ = git(root, "rev-parse", "--short", "HEAD")
    _, remote, _ = git(root, "remote", "get-url", "origin")
    return {"branch": branch or "?", "head": head or "?",
            "remote": remote or "", "root": os.path.abspath(root)}


def _behind_ahead(root: str, branch: str) -> tuple:
    """``(detrás, delante)`` respecto a ``origin/<branch>`` (o -1 si error)."""
    rc, out, _ = git(root, "rev-list", "--count", f"HEAD..origin/{branch}")
    if rc != 0:
        return -1, -1
    behind = int(out or "0")
    rc, out, _ = git(root, "rev-list", "--count", f"origin/{branch}..HEAD")
    return behind, (int(out or "0") if rc == 0 else -1)


def read_version(root: str) -> Optional[str]:
    """Versión declarada en el checkout (tras actualizar), si existe."""
    path = os.path.join(root, "a2s", "__init__.py")
    try:
        with open(path, encoding="utf-8") as fh:
            m = re.search(r'^__version__ = "([^"]+)"', fh.read(), re.M)
    except OSError:
        return None
    return m.group(1) if m else None


def resolve_root(root: Optional[str]) -> str:
    """Checkout a actualizar: el explícito, el del paquete o el cwd."""
    if root:
        return os.path.abspath(root)
    for candidate in (package_root(), os.getcwd()):
        if detect_repo(candidate):
            return candidate
    return package_root()


def _print_status(info: dict, behind: int, ahead: int, out: Print,
                  check_only: bool) -> None:
    out(f"  Rama:          {info['branch']}  (HEAD {info['head']})")
    out(f"  Remoto:        {info['remote'] or '(sin remote origin)'}")
    if behind < 0:
        out("  Estado:        no se pudo comparar con origin (¿rama sin remoto?)")
    elif behind == 0:
        out("  Estado:        ✔ ya estás en la última versión — nada que hacer")
    else:
        out(f"  Estado:        {behind} commit(s) nuevo(s) disponibles"
            + (f" · llevas {ahead} local(es)" if ahead > 0 else ""))
    if check_only:
        out("  (--check: solo lectura, no se tocó nada)")


def _prefetch(root: str, branch: str, out: Print) -> int:
    rc, _, err = git(root, "fetch", "--quiet", "origin", branch)
    if rc != 0:
        out(f"[A²S update] ✗ git fetch falló: {err or 'sin detalle'}")
        return _EXIT_RED
    return _EXIT_OK


def _is_dirty(root: str) -> bool:
    rc, out, _ = git(root, "status", "--porcelain")
    return rc == 0 and bool(out)


def _apply(root: str, branch: str, behind: int, ahead: int, force: bool,
           old_head: str, out: Print) -> int:
    if behind == 0:
        return _EXIT_OK
    if ahead > 0 and not force:
        out(f"[A²S update] ✗ tu rama diverge ({ahead} commit(s) locales). "
            "Usa --force para sincronizar a origin (descarta lo local) o "
            "rebasea manualmente.")
        return _EXIT_DIVERGENTE
    if _is_dirty(root) and not force:
        out("[A²S update] ✗ hay cambios locales sin commit. Haz commit/stash "
            "o usa --force (descarta esos cambios).")
        return _EXIT_SUCIO
    if force:
        rc, _, err = git(root, "reset", "--hard", f"origin/{branch}")
    else:
        rc, _, err = git(root, "merge", "--ff-only", f"origin/{branch}")
    if rc != 0:
        out(f"[A²S update] ✗ no se pudo avanzar la rama: {err or 'sin detalle'}")
        return _EXIT_DIVERGENTE
    _, log, _ = git(root, "log", "--oneline", f"{old_head}..HEAD")
    if log:
        out("  Novedades:")
        for line in log.splitlines()[:15]:
            out(f"    · {line}")
    version = read_version(root)
    out(f"[A²S update] ✔ actualizado en el sitio{f' → v{version}' if version else ''} "
        "(sin re-descargar el repo)")
    return _EXIT_OK


def update(root: Optional[str] = None, alias: Optional[str] = None,
           check_only: bool = False, branch: Optional[str] = None,
           force: bool = False, out: Optional[Print] = None) -> int:
    """Actualiza el checkout actual en el sitio. Devuelve código de salida."""
    say = out or print
    target = resolve_root(root)
    titulo = "[A²S update]"
    if alias:
        titulo += f" {alias}"
    say(f"{titulo} — modo turbo: fetch + fast-forward, sin re-descargar el repo")

    if not _git_present():
        say("[A²S update] ✗ git no está instalado: instálalo "
            "(https://git-scm.com) para actualizar en el sitio.")
        return _EXIT_SIN_GIT
    info = detect_repo(target)
    if info is None:
        say(f"[A²S update] ✗ {target} no es un checkout git. Clona el repo "
            "UNA vez (git clone) y desde entonces usa 'a2s update' para "
            "actualizar sin volver a descargar.")
        return _EXIT_NO_CHECKOUT

    say(f"  Checkout:      {info['root']}")
    rama = branch or info["branch"]
    if rama == "HEAD":
        say("[A²S update] ✗ HEAD está detached: indica la rama con --branch.")
        return _EXIT_DIVERGENTE
    if (rc := _prefetch(info["root"], rama, say)) != _EXIT_OK:
        return rc
    behind, ahead = _behind_ahead(info["root"], rama)
    _print_status(info, behind, ahead, say, check_only)
    if check_only or behind <= 0:
        return _EXIT_OK
    return _apply(info["root"], rama, behind, ahead, force, info["head"], say)


def _git_present() -> bool:
    try:
        proc = subprocess.run(["git", "--version"], capture_output=True,
                              timeout=30, stdin=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def watch(root: Optional[str] = None, alias: Optional[str] = None,
          interval: int = 600, branch: Optional[str] = None,
          force: bool = False, out: Optional[Print] = None,
          stop: Optional["threading.Event"] = None,
          max_cycles: Optional[int] = None) -> int:
    """Guardián de auto-actualización continua (estilo arena.ai).

    Cada ``interval`` segundos hace un ciclo de ``update`` completo (fetch +
    fast-forward). Nunca toca un árbol con cambios locales (a menos que se
    pida ``--force``): un ciclo sucio se reporta y se reintenta al siguiente.
    Usa las credenciales que git YA tiene (gestor de credenciales del sistema);
    A²S no pide ni guarda contraseñas. ``stop``/``max_cycles`` existen para
    tests y embebido; en CLI se sale con Ctrl+C.
    """
    import time as _time
    say = out or print
    titulo = f"[A²S update{' ' + alias if alias else ''} watch]"
    say(f"{titulo} guardián activo: sincronizo solo cada {interval}s "
        "(Ctrl+C para parar)")
    cycles = 0
    while True:
        cycles += 1
        try:
            update(root=root, alias=None, check_only=False, branch=branch,
                   force=force, out=say)
        except Exception as exc:  # noqa: BLE001 — el guardián no muere solo
            say(f"{titulo} ✗ ciclo {cycles} falló: {exc}")
        if max_cycles is not None and cycles >= max_cycles:
            return _EXIT_OK
        if stop is not None:
            if stop.wait(interval):
                return _EXIT_OK
        else:
            try:
                _time.sleep(interval)
            except KeyboardInterrupt:
                say(f"{titulo} detenido tras {cycles} ciclo(s)")
                return _EXIT_OK
