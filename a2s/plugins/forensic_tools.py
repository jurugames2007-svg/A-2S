"""Plugin: puente a herramientas forenses externas INSTALADAS en el host.

Implementa la "fusión de capacidades" con la mitad defensiva de la lista de
referencia: A²S no reimplementa Sleuth Kit, bulk_extractor ni Volatility 3 —
los invoca como binarios del sistema si el operador los tiene instalados.

Límites estrictos (documentados):

* **Lista blanca de binarios**: solo herramientas forenses legítimas
  (Sleuth Kit, bulk_extractor, Volatility, Plaso). Cualquier otro binario —
  incluidas herramientas ofensivas instaladas en el mismo host — se rechaza
  y se registra como denegado.
* **Sin shell**: los argumentos se parten con shlex y se ejecutan sin
  intérprete intermedio.
* **Confinamiento de rutas**: los argumentos no pueden contener `..` ni
  rutas absolutas (los artefactos a analizar viven en el workspace).
* **Salida**: capturada (truncada) o escrita a un archivo del workspace.

Si el binario no está instalado, la herramienta devuelve un aviso claro —
el loop puede reparametrizar, pero no puede inventar la capacidad.
"""

import shlex
import shutil
import subprocess
import os

PLUGIN = {
    "name": "forensic_tools",
    "version": "1.0.0",
    "description": "Puente a herramientas forenses externas (Sleuth Kit, bulk_extractor, Volatility 3, Plaso)",
    "tags": ["forense", "forensics", "dfir", "memoria", "volatility", "sleuthkit",
            "timeline", "evidencia", "imagen", "analisis", "investigar"],
    "tools": [
        {"name": "forensic_inventory", "description": "Lista qué herramientas forenses externas están disponibles.",
         "params": {}},
        {"name": "forensic_cmd", "description": "Ejecuta una herramienta forense de la lista blanca sobre artefactos del workspace.",
         "params": {"binary": "str (nombre de la lista blanca)",
                    "args": "str opcional (argumentos, rutas relativas al workspace)",
                    "out_file": "str opcional (guardar salida en este archivo del workspace)"}},
    ],
}

FORENSIC_BINARIES = {
    # Sleuth Kit
    "fls": "listar archivos/directorios de una imagen (Sleuth Kit)",
    "icat": "extraer contenido de archivo por inodo (Sleuth Kit)",
    "istat": "metadatos de un inodo (Sleuth Kit)",
    "mmls": "tabla de particiones de una imagen (Sleuth Kit)",
    "fsstat": "estadísticas del sistema de archivos (Sleuth Kit)",
    "tsk_recover": "recuperar archivos borrados de una imagen (Sleuth Kit)",
    # Extracción masiva
    "bulk_extractor": "extracción masiva de emails, URLs y credenciales (bulk_extractor)",
    # Memoria
    "volatility3": "análisis de volcados de memoria (Volatility 3)",
    "vol.py": "análisis de memoria (Volatility 2/3, script)",
    # Línea de tiempo
    "log2timeline.py": "generación de supertimelines (Plaso)",
    "psteal": "supertimeline rápida (Plaso)",
}


def _check_args(args: str) -> list[str]:
    argv = shlex.split(args or "")
    for a in argv:
        if (a == ".." or "/.." in a or "\\.." in a
                or a.startswith(("/", "\\", "~"))
                or (len(a) >= 2 and a[1] == ":")):
            raise PermissionError(
                f"ruta fuera del workspace no permitida: '{a}' (usa rutas relativas)")
    return argv


def forensic_inventory():
    available, missing = [], []
    for binary, desc in FORENSIC_BINARIES.items():
        (available if shutil.which(binary) else missing).append(f"  {binary:18} {desc}")
    lines = ["Herramientas forenses disponibles:"]
    lines += available or ["  (ninguna)"]
    if missing:
        lines.append("No instaladas (instálalas para activar la capacidad):")
        lines += missing
    return "\n".join(lines)


def run_forensic(registry, binary, args, out_file):
    if binary not in FORENSIC_BINARIES:
        raise PermissionError(
            f"'{binary}' no está en la lista blanca de herramientas forenses")
    exe = shutil.which(binary)
    if not exe:
        return (f"{binary} no está instalado en este host. "
                f"Instálalo (p. ej. apt install {'sleuthkit' if binary in ('fls', 'icat', 'istat', 'mmls', 'fsstat', 'tsk_recover') else binary}) "
                "y vuelve a intentar.")
    argv = [exe] + _check_args(args)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=120, cwd=registry.workspace)
    except subprocess.TimeoutExpired:
        return f"(timeout ejecutando {binary})"
    out = (proc.stdout or "") + (proc.stderr or "")
    if out_file:
        full = registry._resolve(out_file)
        if not registry._inside_workspace(full):
            raise PermissionError("out_file fuera del workspace")
        with open(full, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(out)
        return f"salida guardada en {out_file} ({len(out)} chars, exit={proc.returncode})"
    limit = 20000
    return (out[:limit] + f"\n…[truncado, {len(out)} chars]" if len(out) > limit else out) \
        or f"(exit={proc.returncode}, sin salida)"


def register(registry, ctx):
    from a2s.tools import Tool

    def f_cmd(binary, args="", out_file=""):
        return run_forensic(registry, binary, args, out_file)

    registry.register(Tool("forensic_inventory", PLUGIN["tools"][0]["description"],
                           PLUGIN["tools"][0]["params"], forensic_inventory))
    registry.register(Tool("forensic_cmd", PLUGIN["tools"][1]["description"],
                           PLUGIN["tools"][1]["params"], f_cmd))
