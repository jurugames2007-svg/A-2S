#!/usr/bin/env python3
"""Guardián de complejidad: falla si alguna función excede CC máx (default 35)
o si la CC media global supera 6. Ratchet: baja el umbral con cada refactor.

Criterios 2/16 del roadmap: la deuda de complejidad como contrato ejecutable.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAQUETE = "a2s"


def cc_de(func: ast.AST) -> int:
    cc = 1
    for sub in ast.walk(func):
        if isinstance(sub, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                            ast.Assert, ast.IfExp)):
            cc += 1
        elif isinstance(sub, ast.BoolOp):
            cc += len(sub.values) - 1
        elif isinstance(sub, ast.comprehension):
            cc += 1 + len(sub.ifs)
    return cc


def main() -> int:
    max_cc = int(sys.argv[1]) if len(sys.argv) > 1 else 35
    peor, total_fn, total_cc = [], 0, 0
    for name in sorted(os.listdir(os.path.join(ROOT, PAQUETE))):
        if not name.endswith(".py"):
            continue
        path = os.path.join(ROOT, PAQUETE, name)
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                v = cc_de(node)
                total_fn += 1
                total_cc += v
                if v > max_cc:
                    peor.append((v, f"{name}:{node.name}"))
    media = total_cc / max(total_fn, 1)
    if peor:
        print(f"✗ COMPLEJIDAD: funciones sobre CC {max_cc}:")
        for v, donde in sorted(peor, reverse=True):
            print(f"  - CC {v}: {donde}")
        return 1
    if media > 6.0:
        print(f"✗ COMPLEJIDAD: media {media:.2f} > 6.0")
        return 1
    print(f"✔ complejidad: {total_fn} funciones, media {media:.2f}, "
          f"máx permitido {max_cc} (ratchet: bájalo tras cada refactor)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
