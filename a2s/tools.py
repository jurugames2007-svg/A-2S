"""Registro de herramientas ("asimilación instantánea de herramientas").

Cada herramienta es un objeto con esquema JSON declarativo y una función de
ejecución. El agente las descubre por introspección (``ToolRegistry.schemas``)
y las invoca mediante ``ToolCall``. El modelo de permisos de ``config.py`` se
aplica aquí: acciones con propósito de ataque son rechazadas y registradas.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ._platform import find_posix_shell
from .config import SHELL_ALLOWLIST, classify_forbidden
from .models import Observation, ToolCall
from .sandbox import Sandbox, SandboxResult


def _close_process_pipes(processes: list[subprocess.Popen]) -> None:
    for proc in processes:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def _abort_pipeline(processes: list[subprocess.Popen]) -> None:
    """Mata y espera los procesos ya lanzados cuando una etapa posterior no
    pudo arrancar (p.ej. ejecutable ausente), cerrando sus pipes."""
    for proc in processes:
        try:
            proc.kill()
        except OSError:
            pass
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
    _close_process_pipes(processes)


def _finish_pipeline(processes: list[subprocess.Popen], timeout: int = 60
                     ) -> tuple[str, str, int]:
    """Recolecta un pipeline completo y no deja procesos/pipes huérfanos."""
    last = processes[-1]
    try:
        out, err = last.communicate(timeout=timeout)
        for proc in processes[:-1]:
            proc.wait(timeout=timeout)
        return out or "", err or "", int(last.returncode or 0)
    except subprocess.TimeoutExpired:
        for proc in processes:
            proc.kill()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        raise
    finally:
        _close_process_pipes(processes)


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, Any]              # esquema JSON (tipos simples)
    func: Callable[..., Any]
    network: bool = False
    destructive: bool = False


class ToolRegistry:
    """Descubrimiento + invocación segura de herramientas."""

    def __init__(self, workspace: str, allow_network: bool = True,
                 allow_shell: bool = True, shell_unsafe: bool = False,
                 network_allowlist: Optional[list[str]] = None,
                 sandbox: bool = True):
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        self.allow_network = allow_network
        self.allow_shell = allow_shell
        self.shell_unsafe = shell_unsafe
        self.network_allowlist = list(network_allowlist or [])
        self.denied: list[dict[str, Any]] = []
        self._tools: dict[str, Tool] = {}
        self.sandbox_enabled = sandbox
        self.sandbox = Sandbox(self.workspace, allow_network=allow_network)
        self._register_builtins()

    # -- descubrimiento -----------------------------------------------------
    def register(self, tool: Tool) -> None:
        """Registro público (usado por el sistema de plugins)."""
        self._tools[tool.name] = tool

    def _register_builtins(self) -> None:
        self.register(Tool("read_file", "Lee un archivo del espacio de trabajo.",
                            {"path": "str (ruta relativa al workspace)", "limit": "int opcional"},
                            self.read_file))
        self.register(Tool("write_file", "Escribe/crea un archivo en el espacio de trabajo.",
                            {"path": "str", "content": "str"},
                            self.write_file, destructive=True))
        self.register(Tool("list_dir", "Lista el contenido de un directorio del workspace.",
                            {"path": "str opcional (por defecto '.')"},
                            self.list_dir))
        self.register(Tool("shell", "Ejecuta un comando de shell (lista blanca).",
                            {"command": "str"},
                            self.shell, destructive=True))
        self.register(Tool("fetch_url", "Descarga el contenido de una URL externa (APIs, páginas).",
                            {"url": "str", "method": "GET|POST", "body": "str opcional",
                             "headers": "dict opcional", "timeout": "int opcional"},
                            self.fetch_url, network=True))
        self.register(Tool("web_search", "Búsqueda web vía API externa (DuckDuckGo HTML).",
                            {"query": "str", "max_results": "int opcional"},
                            self.web_search, network=True))
        self.register(Tool("python_exec", "Ejecuta un fragmento Python aislado (subproceso).",
                            {"code": "str"},
                            self.python_exec, destructive=True))
        self.register(Tool("save_artifact", "Guarda un artefacto inmutable (hash) en la bitácora forense.",
                            {"name": "str", "content": "str", "kind": "str opcional"},
                            self.save_artifact, destructive=True))

    def schemas(self) -> str:
        """Descripción legible por el planificador (introspección)."""
        lines = []
        for t in self._tools.values():
            lines.append(f"- {t.name}: {t.description} params={json.dumps(t.params, ensure_ascii=False)}")
        return "\n".join(lines)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    # -- resolución de rutas ------------------------------------------------
    def _resolve(self, path: str) -> str:
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.workspace, path)
        return os.path.abspath(path)

    def _inside_workspace(self, path: str) -> bool:
        return path == self.workspace or path.startswith(self.workspace + os.sep)

    # -- implementaciones ---------------------------------------------------
    def read_file(self, path: str, limit: int = 20000) -> str:
        full = self._resolve(path)
        if not self._inside_workspace(full):
            raise PermissionError("lectura fuera del workspace denegada")
        with open(full, encoding="utf-8", errors="replace") as fh:
            data = fh.read(limit)
        return data + ("\n…[truncado]" if len(data) == limit else "")

    def write_file(self, path: str, content: str) -> str:
        if reason := classify_forbidden(content):
            raise PermissionError(reason)
        full = self._resolve(path)
        if not self._inside_workspace(full):
            raise PermissionError("escritura fuera del workspace denegada")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
        return f"escrito {os.path.relpath(full, self.workspace)} ({len(content)} chars)"

    def list_dir(self, path: str = ".") -> str:
        full = self._resolve(path)
        if not self._inside_workspace(full) or not os.path.isdir(full):
            raise PermissionError("directorio fuera del workspace o inexistente")
        names = sorted(os.listdir(full))
        out = []
        for n in names:
            p = os.path.join(full, n)
            kind = "dir" if os.path.isdir(p) else "file"
            out.append(f"{kind:4} {n} ({os.path.getsize(p)} bytes)" if kind == "file" else f"{kind:4} {n}/")
        return "\n".join(out)

    @staticmethod
    def _split_top(seg: str, sep: str) -> list[str]:
        """Divide por el separador respetando comillas y escapes (\\;)."""
        parts, cur, quote = [], [], None
        i = 0
        while i < len(seg):
            ch = seg[i]
            if quote:
                cur.append(ch)
                if ch == quote:
                    quote = None
            elif ch == "\\" and i + 1 < len(seg):  # escape: siguiente char literal
                cur.append(ch)
                cur.append(seg[i + 1])
                i += 1
            elif ch in "'\"":
                quote = ch
                cur.append(ch)
            elif ch == sep:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
            i += 1
        parts.append("".join(cur))
        return parts

    _ENV_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")

    def _expand_env(self, text: str) -> str:
        """Expansión de variables de entorno ($VAR, ${VAR})."""
        return self._ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), text)

    def _expand_substitution(self, command: str, depth: int) -> str:
        """Sustitución de comandos $(...), un nivel, con la misma política."""
        if depth >= 3:
            return command
        return re.sub(r"\$\(([^()]*)\)",
                      lambda m: self.shell(m.group(1), depth=depth + 1).strip(),
                      command)

    # Patrones de predicado de `find` cuyo valor NO debe expandirse como ruta
    # del disco: `find` lo interpreta como patrón (p.ej. -path "./.git/*").
    _FIND_PATTERN_PREDS = frozenset((
        "-path", "-ipath", "-name", "-iname", "-lname", "-ilname",
        "-wholename", "-iwholename", "-samefile",
    ))

    def _expand_argv_globs(self, argv: list[str]) -> list[str]:
        """Expande comodines (* ? [) en argumentos que son rutas del disco.

        Excluye los valores de predicados de patrón de ``find`` y los
        patrones sueltos del propio ``find``, para no corromper mandatos como
        ``find . -not -path "./.git/*"`` cuando el workspace es un repo.
        """
        if len(argv) <= 1:
            return argv
        expanded: list[str] = [argv[0]]
        skip_next = False
        is_find = argv[0] == "find"
        for token in argv[1:]:
            if skip_next:
                expanded.append(token)
                skip_next = False
                continue
            if token in self._FIND_PATTERN_PREDS:
                expanded.append(token)
                skip_next = True
                continue
            if "*" in token or "?" in token or "[" in token:
                if is_find:
                    expanded.append(token)            # patrón del propio find
                else:
                    matches = sorted(glob.glob(os.path.join(self.workspace, token)))
                    expanded.extend(matches or [token])
            else:
                expanded.append(token)
        return expanded

    def _check_pipeline_allowlist(self, pipes: list[str]) -> None:
        """El primer comando de cada etapa del pipeline debe estar permitido."""
        for p in pipes:
            argv0 = shlex.split(p, posix=(os.name != "nt"))
            if not argv0:
                continue
            if not self.shell_unsafe and argv0[0] not in SHELL_ALLOWLIST:
                raise PermissionError(
                    f"comando '{argv0[0]}' fuera de la lista blanca (usa --unsafe para ampliar)")

    def _spawn_windows_shell(self, segment: str) -> subprocess.Popen:
        """Ejecuta el segmento completo en bash (Git/MSYS2/WSL) en Windows."""
        posix_shell = find_posix_shell()
        if posix_shell is None:
            raise PermissionError(
                "shell POSIX no disponible en Windows: instala Git-Bash, "
                "MSYS2 o WSL para ejecutar comandos de la lista blanca")
        try:
            return subprocess.Popen(
                [posix_shell, "-c", segment],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, cwd=self.workspace)
        except OSError as exc:
            raise PermissionError(f"no se pudo invocar bash: {exc}") from exc

    def _spawn_unix_pipeline(self, pipes: list[str]) -> list[subprocess.Popen]:
        """Lanza un pipeline POSIX directo, limpiando procesos si una etapa
        falla al arrancar (evita pipes/procesos huérfanos)."""
        procs: list[subprocess.Popen] = []
        for pipe_index, p in enumerate(pipes):
            argv = shlex.split(p)
            if len(argv) > 1:  # expansión de globs en argumentos de ruta
                argv = self._expand_argv_globs(argv)
            redirect_err = None
            if "2>&1" in argv:
                argv.remove("2>&1")
                redirect_err = subprocess.STDOUT
            elif "2>/dev/null" in argv:
                argv.remove("2>/dev/null")
                redirect_err = subprocess.DEVNULL
            if not argv:
                continue
            prev_out = procs[-1].stdout if procs else None
            # Sin redirección de entrada en la mini-shell: el primer comando
            # lee de DEVNULL (evita bloqueos heredando la stdin del agente).
            stdin = prev_out if prev_out is not None else subprocess.DEVNULL
            # El stderr de etapas intermedias entra al pipeline: evita un PIPE
            # sin lector que podría bloquear o quedar abierto.
            default_err = (subprocess.PIPE if pipe_index == len(pipes) - 1
                           else subprocess.STDOUT)
            try:
                proc = subprocess.Popen(
                    argv, stdin=stdin, stdout=subprocess.PIPE,
                    stderr=redirect_err if redirect_err is not None else default_err,
                    text=True, cwd=self.workspace)
            except OSError as exc:
                _abort_pipeline(procs)
                raise PermissionError(
                    f"comando '{argv[0]}' no disponible: {exc}") from exc
            procs.append(proc)
            if prev_out is not None:
                prev_out.close()
        return procs

    def shell(self, command: str, depth: int = 0) -> str:
        """Mini-shell seguro: ';', '|', '>', '2>&1', $VAR, globs y $().

        Cada comando de cada pipeline se valida contra la lista blanca (o el
        flag --unsafe) y las acciones con propósito de ataque se rechazan.
        La expansión de variables, globs y sustitución de comandos opera con
        la MISMA política de permisos — ampliación funcional, no bypass de
        confinamiento.
        """
        if not self.allow_shell:
            raise PermissionError("shell deshabilitada")
        if reason := classify_forbidden(command):
            raise PermissionError(reason)
        command = self._expand_env(command)
        command = self._expand_substitution(command, depth)
        out_parts: list[str] = []
        final_rc = 0
        for segment in self._split_top(command, ";"):
            segment = segment.strip()
            if not segment:
                continue
            redirect_out: Optional[str] = None
            if "2>" not in segment and ">" in segment:
                left, right = self._split_top(segment, ">")[:2]
                if not left.strip():
                    raise PermissionError("redirección sin comando")
                segment, redirect_out = left, right.strip()
            pipes = [p.strip() for p in self._split_top(segment, "|") if p.strip()]
            self._check_pipeline_allowlist(pipes)
            if os.name == "nt":
                procs = [self._spawn_windows_shell(segment)]
            else:
                procs = self._spawn_unix_pipeline(pipes)
            if not procs:
                continue
            out, err, final_rc = _finish_pipeline(procs, timeout=60)
            text = out + err
            if redirect_out:
                full = self._resolve(redirect_out)
                if not self._inside_workspace(full):
                    raise PermissionError("redirección fuera del workspace denegada")
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(text)
                out_parts.append(f"(guardado en {redirect_out})")
            else:
                out_parts.append(text)
        combined = "\n".join(p for p in out_parts if p.strip())
        if not combined.strip():
            combined = f"(exit={final_rc}, sin salida)"
        elif final_rc != 0:
            combined += f"\n(exit={final_rc})"
        return combined

    def _host_allowed(self, url: str) -> bool:
        if not self.network_allowlist:
            return True
        host = urllib.parse.urlparse(url).hostname or ""
        return any(host == a or host.endswith("." + a)
                   for a in self.network_allowlist)

    def fetch_url(self, url: str, method: str = "GET", body: str = "",
                  headers: Optional[dict[str, str]] = None, timeout: int = 30) -> str:
        if not self.allow_network:
            raise PermissionError("red deshabilitada")
        if reason := classify_forbidden(url + (body or "")):
            raise PermissionError(reason)
        if not self._host_allowed(url):
            raise PermissionError(f"host '{urllib.parse.urlparse(url).hostname}' "
                                  "fuera de la lista blanca de red")
        req = urllib.request.Request(url, method=method.upper(),
                                     data=body.encode() if body else None,
                                     headers={"User-Agent": "A2S/1.2 (+forensic agent)",
                                              **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(200_000)
        text = data.decode("utf-8", errors="replace")
        return text if len(data) < 200_000 else text + "\n…[truncado]"

    def web_search(self, query: str, max_results: int = 5) -> str:
        q = urllib.parse.urlencode({"q": query})
        html = self.fetch_url(f"https://html.duckduckgo.com/html/?{q}")
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html)
        urls = re.findall(r'class="result__a" href="([^"]+)"', html)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
        out = []
        for i, (t, u) in enumerate(zip(titles, urls)):
            if i >= max_results:
                break
            snip = re.sub(r"<[^>]+>", "", snippets[i]) if i < len(snippets) else ""
            out.append(f"{i+1}. {re.sub('<[^>]+>', '', t)} — {u}\n   {snip.strip()}")
        return "\n".join(out) if out else "(sin resultados)"

    def python_exec(self, code: str) -> str:
        if reason := classify_forbidden(code):
            raise PermissionError(reason)
        if self.sandbox_enabled:
            res = self.sandbox.run_python(code, timeout=60)
            if res.timed_out:
                return f"(sandbox {res.level_name}: TIEMPO AGOTADO)\n" + res.output[-1000:]
            return res.output.strip() or f"(exit={res.returncode}, sin salida)"
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=60, cwd=self.workspace, stdin=subprocess.DEVNULL)
        out = proc.stdout + proc.stderr
        return out if out.strip() else "(sin salida)"

    def save_artifact(self, name: str, content: str, kind: str = "artifact") -> str:
        # La persistencia real la hace MemoryHub/ledger; aquí se normaliza.
        return json.dumps({"name": name, "kind": kind, "size": len(content)})

    # -- invocación genérica ------------------------------------------------
    def invoke(self, call: ToolCall) -> Observation:
        """Ejecuta un ToolCall devolviendo una Observation (nunca lanza excepción)."""
        import time
        t0 = time.time()
        tool = self._tools.get(call.tool)
        if tool is None:
            return Observation(step_id="", ok=False,
                               error=f"herramienta desconocida: {call.tool}")
        try:
            out = tool.func(**call.params)
            obs = Observation(step_id="", ok=True, output=str(out))
        except PermissionError as exc:
            self.denied.append({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "tool": call.tool, "reason": str(exc)})
            obs = Observation(step_id="", ok=False, error=f"PERMISO DENEGADO: {exc}")
        except Exception as exc:  # noqa: BLE001 — el loop decide cómo reparametrizar
            obs = Observation(step_id="", ok=False, error=f"{type(exc).__name__}: {exc}")
        obs.elapsed = time.time() - t0
        obs.metrics["tool"] = call.tool
        return obs
