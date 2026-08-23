"""Auditor ejecutable: la puntuación del proyecto como comando reproducible.

Resolución del punto «6/5» del ROADMAP_V2: no existe el 6 en una escala 0-5
(LIMITACIONES §14 es su guardián) — lo que SÍ se puede superar es el estándar
de MEDICIÓN: en vez de un informe estático, ``a2s audit`` re-mide cada vez
los criterios objetivamente medibles y muestra el estado vivo del proyecto
con la misma escala honesta de 0 a 5.

Mide (todo reproducible desde el repo, sin opiniones):

* pureza stdlib (tools/check_purity.py)          → 5 si pasa, 0 si no
* complejidad: CC media y máximo (check_cc)      → 5 si media<6 y máx<35
* pruebas: nº de tests y suites                  → escala por tramos
* guardianes/CI y roadmap comprometidos          → presencia de las piezas
* documentación: secciones de LIMITACIONES,     → escala por tramos
  ejemplos ejecutables, ROADMAP_V2
* consistencia de versión (__init__ vs pyproject)

Lo NO medible desde aquí (cobertura real, WCAG, comparativas) sigue
perteneciendo al informe humano: el auditor no inventa notas.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Check:
    nombre: str
    detalle: str
    nota: float          # 0..5
    ok: bool


def _subprocess_ok(script: str, *args: str) -> tuple[bool, str]:
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", script), *args],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.returncode == 0, (r.stdout or r.stderr).strip().splitlines()[-1]
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def _cc_de(func: "ast.AST") -> int:
    """Complejidad ciclomática (misma fórmula que tools/check_cc.py: duplicada
    A PROPÓSITO para que audit.py sea autocontenido y puro stdlib)."""
    import ast as _ast
    cc = 1
    for sub in _ast.walk(func):
        if isinstance(sub, (_ast.If, _ast.For, _ast.While, _ast.ExceptHandler,
                            _ast.Assert, _ast.IfExp)):
            cc += 1
        elif isinstance(sub, _ast.BoolOp):
            cc += len(sub.values) - 1
        elif isinstance(sub, _ast.comprehension):
            cc += 1 + len(sub.ifs)
    return cc


def _cc_stats() -> tuple[float, int]:
    import ast
    cc_de = _cc_de
    total_fn = total_cc = 0
    max_cc = 0
    for name in os.listdir(os.path.join(ROOT, "a2s")):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ROOT, "a2s", name), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                v = cc_de(node)
                total_fn += 1
                total_cc += v
                max_cc = max(max_cc, v)
    return total_cc / max(total_fn, 1), max_cc


def _nota_por_tramos(valor: float, tramos: list[tuple[float, float]]) -> float:
    for limite, nota in tramos:
        if valor >= limite:
            return nota
    return tramos[-1][1]


def run_audit() -> dict:
    checks: list[Check] = []

    # 1. pureza
    ok, det = _subprocess_ok("check_purity.py")
    checks.append(Check("pureza-stdlib", det, 5.0 if ok else 0.0, ok))

    # 2. complejidad
    media, mx = _cc_stats()
    ok = media < 6.0 and mx <= 35
    checks.append(Check("complejidad", f"media {media:.2f} · máx {mx} "
                        f"(umbral ratchet 35)", 5.0 if ok else 2.5, ok))

    # 3. pruebas (conteo estático)
    n_tests = n_suites = 0
    for name in os.listdir(os.path.join(ROOT, "tests")):
        if name.startswith("test_") and name.endswith(".py"):
            n_suites += 1
            with open(os.path.join(ROOT, "tests", name), encoding="utf-8") as fh:
                n_tests += len(re.findall(r"\bdef test_", fh.read()))
    nota_tests = _nota_por_tramos(n_tests, [(120, 5.0), (80, 4.0), (40, 3.0), (0, 2.0)])
    checks.append(Check("pruebas", f"{n_tests} tests en {n_suites} suites",
                        nota_tests, n_tests >= 80))

    # 4. piezas del roadmap comprometidas
    piezas = ["ROADMAP_V2.md", "tools/check_purity.py", "tools/check_cc.py",
              "tools/ci/ci.yml", "examples/mock_llm_server.py"]
    hay = [p for p in piezas if os.path.isfile(os.path.join(ROOT, p))]
    checks.append(Check("roadmap-comprometido", f"{len(hay)}/{len(piezas)} piezas",
                        5.0 * len(hay) / len(piezas), len(hay) == len(piezas)))

    # 5. documentación
    with open(os.path.join(ROOT, "LIMITACIONES.md"), encoding="utf-8") as fh:
        lim = fh.read()
    secciones = len(re.findall(r"^## \d+", lim, re.M))
    ejemplos = len([f for f in os.listdir(os.path.join(ROOT, "examples"))
                    if not f.startswith("_")]) if os.path.isdir(os.path.join(ROOT, "examples")) else 0
    nota_docs = _nota_por_tramos(secciones, [(12, 5.0), (8, 4.0), (4, 3.0), (0, 2.0)])
    checks.append(Check("documentacion", f"LIMITACIONES: {secciones} secciones · "
                        f"examples: {ejemplos}", nota_docs, secciones >= 10))

    # 6. consistencia de versión
    with open(os.path.join(ROOT, "a2s", "__init__.py"), encoding="utf-8") as fh:
        init = fh.read()
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        pyproj = fh.read()
    v1 = re.search(r'__version__ = "([^"]+)"', init)
    v2 = re.search(r'version = "([^"]+)"', pyproj)
    okv = bool(v1 and v2 and v1.group(1) == v2.group(1))
    checks.append(Check("version-consistente",
                        f"{v1.group(1) if v1 else '?'} vs {v2.group(1) if v2 else '?'}",
                        5.0 if okv else 0.0, okv))

    medibles = [c.nota for c in checks]
    return {"version_audit": "1.0", "checks": [c.__dict__ for c in checks],
            "nota_medible": round(sum(medibles) / len(medibles), 2),
            "todos_ok": all(c.ok for c in checks),
            "no_medible_aqui": ["cobertura real de líneas", "WCAG/accesibilidad",
                                "benchmarks comparativos externos",
                                "auditoría web del dashboard"]}


def render(reporte: dict) -> str:
    lineas = ["A²S audit — puntuación viva (escala honesta 0-5; el 6 no existe)",
              "═" * 64]
    for c in reporte["checks"]:
        marca = "ok " if c["ok"] else "MAL"
        lineas.append(f"  [{marca}] {c['nombre']:<20} {c['nota']:>3.1f}/5  {c['detalle']}")
    lineas.append("─" * 64)
    lineas.append(f"  nota medible ahora: {reporte['nota_medible']}/5")
    lineas.append("  no medible desde aquí (siguen en el informe humano): "
                  + ", ".join(reporte["no_medible_aqui"]))
    lineas.append("  regla: si un check falla, el exit-code es 1 (CI-friendly).")
    return "\n".join(lineas)
