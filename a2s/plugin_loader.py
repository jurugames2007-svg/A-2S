"""Arquitectura de plugins de A²S.

* El core es mínimo; las capacidades extra son plugins que se **activan solo
  cuando la misión las necesita** (etiquetas ∩ objetivo + presupuesto).
* Cada plugin es un módulo Python local que declara ``PLUGIN`` y expone
  ``register(registry, ctx)`` para auto-registrar sus herramientas.
* Un plugin puede llevar ``plugin.json`` con el sha256 del módulo: el loader
  lo verifica antes de importar (cadena de suministro local).

Por qué NO hay registro remoto de plugins (decisión documentada en
LIMITACIONES.md): descargar y ejecutar código de un URL en caliente equivale
a RCE con pasos extra; sin una autoridad de firma real, "verificar la firma"
de un manifest remoto es teatro. Los plugins se distribuyen como código
auditable junto al proyecto (o en directorios locales vía A2S_PLUGIN_DIRS).
"""

import hashlib
import importlib
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

from .tools import Tool, ToolRegistry


@dataclass
class PluginSpec:
    name: str
    version: str
    description: str
    tags: list[str]
    source_path: str
    sha256_verified: bool
    tool_names: list[str] = field(default_factory=list)
    module: Any = None


class PluginLoader:
    def __init__(self, workspace: str):
        self.workspace = workspace
        self._builtin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        self.specs: dict[str, PluginSpec] = {}

    # -- descubrimiento -----------------------------------------------------
    def discover(self) -> dict[str, PluginSpec]:
        builtin = os.path.join(os.path.dirname(__file__), "plugins")
        if os.path.isdir(builtin):
            dirs = [builtin]
        else:  # ejecución empaquetada (zipapp): enumerar el zip directamente
            dirs = []
            self._discover_from_zip(builtin)
        for extra in (os.environ.get("A2S_PLUGIN_DIRS") or "").split(os.pathsep):
            if extra.strip():
                dirs.append(os.path.abspath(extra.strip()))
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if name.startswith("_") or not name.endswith(".py"):
                    continue
                path = os.path.join(d, name)
                spec = self._load_spec(path)
                if spec and spec.name not in self.specs:
                    self.specs[spec.name] = spec
        return self.specs

    def _discover_from_zip(self, builtin: str) -> None:
        import zipfile
        import sys as _sys
        # Localizar el zip que contiene este módulo.
        prefix = "a2s/plugins/"
        for candidate in ([_sys.argv[0]] if _sys.argv and _sys.argv[0].endswith(".pyz") else []):
            try:
                with zipfile.ZipFile(candidate) as zf:
                    for entry in zf.namelist():
                        if entry.startswith(prefix) and entry.endswith(".py") \
                                and not entry.split("/")[-1].startswith("_"):
                            spec = self._load_spec(entry)
                            if spec and spec.name not in self.specs:
                                self.specs[spec.name] = spec
                return
            except (OSError, zipfile.BadZipFile):
                continue

    def _load_spec(self, path: str) -> Optional[PluginSpec]:
        # Verificación opcional de hash vía plugin.json (manifiesto local).
        verified = False
        manifest = os.path.join(os.path.dirname(path),
                                os.path.basename(path)[:-3] + ".json")
        if os.path.exists(manifest):
            try:
                with open(manifest, encoding="utf-8") as fh:
                    data = json.load(fh)
                with open(path, "rb") as fh:
                    actual = hashlib.sha256(fh.read()).hexdigest()
                verified = actual == data.get("sha256")
                if not verified:
                    return None  # hash no coincide → no cargar
            except (OSError, ValueError, json.JSONDecodeError):
                return None
        module = None
        try:
            module = self._import_module(path)
        except Exception:  # noqa: BLE001 — un plugin roto no tumba el core
            return None
        if module is None:
            return None
        meta = getattr(module, "PLUGIN", None)
        if not isinstance(meta, dict) or "name" not in meta:
            return None
        tools = meta.get("tools") or []
        return PluginSpec(
            name=str(meta["name"]),
            version=str(meta.get("version", "0.0.0")),
            description=str(meta.get("description", "")),
            tags=[str(t) for t in meta.get("tags", [])],
            source_path=path,
            sha256_verified=verified,
            tool_names=[str(t.get("name")) for t in tools if isinstance(t, dict)],
            module=module,
        )

    @staticmethod
    def _import_module(path: str) -> Any:
        """Importa desde archivo (modo normal) o desde el paquete (zipapp)."""
        mod_name = f"a2s_plugin_{hashlib.sha256(path.encode()).hexdigest()[:10]}"
        # Ejecución empaquetada (zipapp): el archivo no existe en disco y se
        # importa como subpaquete de a2s.plugins.
        if not os.path.isfile(path):
            pkg_name = os.path.basename(path)[:-3]
            if importlib.util.find_spec(f"a2s.plugins.{pkg_name}"):
                return importlib.import_module(f"a2s.plugins.{pkg_name}")
            return None
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    # -- activación bajo demanda ----------------------------------------------
    def activate(self, registry: ToolRegistry, goal: str,
                 max_plugins: int = 4, signer: Any = None,
                 ledger: Any = None) -> list[str]:
        """Activa los plugins cuya etiqueta aparece en el objetivo de la misión.

        La "decisión por consenso" se implementa de forma pragmática:
        puntuación = etiquetas ∩ palabras del objetivo; solo se registran
        herramientas de plugins con puntuación > 0, dentro del presupuesto
        de plugins simultáneos (mínimo hardware).
        """
        goal_words = set(goal.lower().replace("/", " ").split())
        activated: list[str] = []
        for spec in sorted(self.specs.values(), key=lambda s: s.name):
            if len(activated) >= max_plugins:
                break
            score = len(set(spec.tags) & goal_words)
            if score <= 0:
                continue
            try:
                ctx = {"workspace": self.workspace, "signer": signer}
                spec.module.register(registry, ctx)
                activated.append(spec.name)
                if ledger is not None:
                    ledger.append("plugin_activated",
                                  {"plugin": spec.name, "version": spec.version,
                                   "score": score,
                                   "sha256_verified": spec.sha256_verified})
            except Exception:  # noqa: BLE001 — plugin roto se salta, no mata la misión
                continue
        return activated

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": s.name, "version": s.version, "tags": s.tags,
                 "tools": s.tool_names, "hash_ok": s.sha256_verified}
                for s in self.specs.values()]
