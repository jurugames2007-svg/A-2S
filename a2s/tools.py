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
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import SHELL_ALLOWLIST, classify_forbidden
from .models import Observation, ToolCall


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
                 allow_shell: bool = True, shell_unsafe: bool = False):
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        self.allow_network = allow_network
        self.allow_shell = allow_shell
        self.shell_unsafe = shell_unsafe
        self.denied: list[dict[str, Any]] = []
        self._tools: dict[str, Tool] = {}
        self._register_builtins()

    # -- descubrimiento -----------------------------------------------------
    def _register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def _register_builtins(self) -> None:
        self._register(Tool("read_file", "Lee un archivo del espacio de trabajo.",
                            {"path": "str (ruta relativa al workspace)", "limit": "int opcional"},
                            self.read_file))
        self._register(Tool("write_file", "Escribe/crea un archivo en el espacio de trabajo.",
                            {"path": "str", "content": "str"},
                            self.write_file, destructive=True))
        self._register(Tool("list_dir", "Lista el contenido de un directorio del workspace.",
                            {"path": "str opcional (por defecto '.')"},
                            self.list_dir))
        self._register(Tool("shell", "Ejecuta un comando de shell (lista blanca).",
                            {"command": "str"},
                            self.shell, destructive=True))
        self._register(Tool("fetch_url", "Descarga el contenido de una URL externa (APIs, páginas).",
                            {"url": "str", "method": "GET|POST", "body": "str opcional",
                             "headers": "dict opcional", "timeout": "int opcional"},
                            self.fetch_url, network=True))
        self._register(Tool("web_search", "Búsqueda web vía API externa (DuckDuckGo HTML).",
                            {"query": "str", "max_results": "int opcional"},
                            self.web_search, network=True))
        self._register(Tool("python_exec", "Ejecuta un fragmento Python aislado (subproceso).",
                            {"code": "str"},
                            self.python_exec, destructive=True))
        self._register(Tool("save_artifact", "Guarda un artefacto inmutable (hash) en la bitácora forense.",
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

    def shell(self, command: str, depth: int = 0) -> str:
        """Mini-shell seguro: ';', '|', '>', '2>&1', \$VAR, globs y \$().

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
            procs: list[subprocess.Popen] = []
            for p in pipes:
                argv = shlex.split(p)
                if len(argv) > 1:  # expansión de globs solo en argumentos
                    expanded: list[str] = [argv[0]]
                    for a in argv[1:]:
                        if "*" in a or "?" in a:
                            matches = sorted(glob.glob(os.path.join(self.workspace, a)))
                            expanded.extend(matches or [a])
                        else:
                            expanded.append(a)
                    argv = expanded
                redirect_err = None
                if "2>&1" in argv:
                    argv.remove("2>&1")
                    redirect_err = subprocess.STDOUT
                elif "2>/dev/null" in argv:
                    argv.remove("2>/dev/null")
                    redirect_err = subprocess.DEVNULL
                if not argv:
                    continue
                if not self.shell_unsafe and argv[0] not in SHELL_ALLOWLIST:
                    raise PermissionError(
                        f"comando '{argv[0]}' fuera de la lista blanca (usa --unsafe para ampliar)")
                stdin = procs[-1].stdout if procs else None
                proc = subprocess.Popen(
                    argv, stdin=stdin, stdout=subprocess.PIPE,
                    stderr=redirect_err if redirect_err is not None else subprocess.PIPE,
                    text=True, cwd=self.workspace)
                procs.append(proc)
                if stdin is not None:
                    stdin.close()
            if not procs:
                continue
            last = procs[-1]
            out, err = last.communicate(timeout=60)
            final_rc = last.returncode
            text = (out or "") + (err or "")
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

    def fetch_url(self, url: str, method: str = "GET", body: str = "",
                  headers: Optional[dict[str, str]] = None, timeout: int = 30) -> str:
        if not self.allow_network:
            raise PermissionError("red deshabilitada")
        if reason := classify_forbidden(url + (body or "")):
            raise PermissionError(reason)
        req = urllib.request.Request(url, method=method.upper(),
                                     data=body.encode() if body else None,
                                     headers={"User-Agent": "A2S/1.0 (+forensic agent)",
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
        proc = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            timeout=60, cwd=self.workspace)
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
