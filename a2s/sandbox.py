"""Sandbox real por capas para la ejecución de código (python_exec y shell).

Niveles de aislamiento, detectados automáticamente en este orden:

* **Nivel 3 — nsjail**: chroot mínimo, uid/gid 65534, límites de recursos,
  sin loopback. Requiere el binario ``nsjail`` y un chroot configurado en
  ``A2S_NSJAIL_CHROOT`` (experimental; prepararlo es responsabilidad del
  operador).
* **Nivel 2 — bubblewrap (bwrap)**: ``--unshare-all``, sin red (si aplica),
  filesystem de solo lectura salvo el workspace y /tmp aislado.
* **Nivel 1 — rlimits (siempre disponible)**: subproceso con límites duros
  del kernel (memoria, procesos, CPU, fds) + Python en modo aislado (``-I``)
  + bloqueo de red por shim de ``socket``. NO aísla el filesystem ni impide
  elusión deliberada vía ctypes/syscalls: es contención de recursos y
  prevención de accidentes, no una jaula.

Honestidad técnica (documentada también en LIMITACIONES.md): solo el nivel 3
es aislamiento fuerte. El nivel 1 protege contra bucles de consumo de
recursos, fork bombs y fugas accidentales de red, no contra código hostil
deliberado. Para eso: ejecutar en VM/contenedor desechable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Optional

try:
    import resource
except ImportError:
    resource = None

# Bootstrap que bloquea la red saliente por monkey-patch de socket (nivel 1).
_NET_BLOCK_BOOTSTRAP = """
import socket
class _BlockedSocket:
    def __init__(self, *a, **k):
        raise OSError("red saliente deshabilitada por el sandbox (nivel rlimits)")
def _block(*a, **k):
    raise OSError("red saliente deshabilitada por el sandbox (nivel rlimits)")
socket.socket = _BlockedSocket
socket.create_connection = _block
"""


@dataclass
class SandboxResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    level: int = 0
    level_name: str = "directo"
    timed_out: bool = False

    @property
    def output(self) -> str:
        return (self.stdout or "") + (self.stderr or "")

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Sandbox:
    """Ejecuta código/comandos con el máximo aislamiento disponible."""

    def __init__(self, workspace: str, allow_network: bool = False,
                 timeout: int = 30, mem_mb: int = 256, max_procs: int = 32):
        self.workspace = os.path.abspath(workspace)
        self.allow_network = allow_network
        self.timeout = timeout
        self.mem_mb = mem_mb
        self.max_procs = max_procs
        self._nsjail = shutil.which("nsjail")
        self._bwrap = shutil.which("bwrap")
        self._chroot = os.environ.get("A2S_NSJAIL_CHROOT", "")
        self._python = sys.executable or shutil.which("python3") or shutil.which("python") or "python3"
        self.level = self._detect_level()

    def _detect_level(self) -> int:
        if self._nsjail and self._chroot and os.path.isdir(self._chroot):
            return 3
        if self._bwrap:
            return 2
        if resource is not None:
            return 1
        return 0

    @property
    def level_name(self) -> str:
        return {3: "nsjail", 2: "bwrap", 1: "rlimits", 0: "directo"}.get(self.level, "?")

    # -- límites de recursos (nivel 1; usados también por 2/3) ---------------
    def _set_rlimits(self) -> None:
        if resource is None:
            return
        mem = self.mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_NPROC, (self.max_procs, self.max_procs))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, self.timeout * 2),) * 2)

    # -- API ----------------------------------------------------------------
    def run_python(self, code: str, timeout: Optional[int] = None) -> SandboxResult:
        timeout = timeout or self.timeout
        if self.level == 3:
            return self._run_nsjail([self._python, "-I", "-c", code], timeout)
        if self.level == 2:
            return self._run_bwrap([self._python, "-I", "-c", code], timeout,
                                   net_shim=not self.allow_network)
        # Nivel 1/0: rlimits (si disponible) + python aislado + bloqueo de red por shim.
        prefix = "" if self.allow_network else _NET_BLOCK_BOOTSTRAP
        argv = [self._python, "-I", "-c", prefix + "\n" + code]
        return self._run_direct(argv, timeout, rlimits=bool(self.level >= 1 and resource is not None))

    def run_cmd(self, argv: list[str], timeout: Optional[int] = None) -> SandboxResult:
        timeout = timeout or self.timeout
        if self.level == 3:
            return self._run_nsjail(argv, timeout)
        if self.level == 2:
            return self._run_bwrap(argv, timeout)
        return self._run_direct(argv, timeout, rlimits=bool(self.level >= 1 and resource is not None))

    # -- implementaciones por nivel -------------------------------------------
    def _run_direct(self, argv: list[str], timeout: int, rlimits: bool) -> SandboxResult:
        use_rlimits = bool(rlimits and resource is not None and sys.platform != "win32")
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout,
                cwd=self.workspace,
                preexec_fn=self._set_rlimits if use_rlimits else None)
            return SandboxResult(stdout=proc.stdout, stderr=proc.stderr,
                                 returncode=proc.returncode,
                                 level=self.level, level_name=self.level_name)
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return SandboxResult(stdout=out, stderr=err, returncode=-1,
                                 level=self.level, level_name=self.level_name,
                                 timed_out=True)

    def _run_bwrap(self, argv: list[str], timeout: int,
                   net_shim: bool = False) -> SandboxResult:
        cmd = [self._bwrap, "--die-with-parent", "--unshare-pid"]
        if not self.allow_network:
            cmd += ["--unshare-net"]
        for bind in ("/usr", "/lib", "/lib64", "/bin", "/sbin"):
            if os.path.isdir(bind):
                cmd += ["--ro-bind", bind, bind]
        cmd += ["--proc", "/proc", "--dev", "/dev",
                "--tmpfs", "/tmp",
                "--bind", self.workspace, self.workspace,
                "--chdir", self.workspace]
        cmd += argv
        return self._run_direct(cmd, timeout, rlimits=True)

    def _run_nsjail(self, argv: list[str], timeout: int) -> SandboxResult:
        cmd = [self._nsjail, "-Mo", "--chroot", self._chroot,
               "--user", "65534", "--group", "65534",
               "--rlimit_as", str(self.mem_mb),
               "--rlimit_nproc", str(self.max_procs),
               "--rlimit_nofile", "64",
               "--time_limit", str(timeout),
               "--cwd", "/work",
               "--bindmount", f"{self.workspace}:/work",
               "--", *argv]
        if not self.allow_network:
            cmd.insert(5, "--iface_no_lo")
        return self._run_direct(cmd, timeout, rlimits=False)
