#!/usr/bin/env python3
"""Demo SORL end-to-end contra el servidor simulado (examples/mock_llm_server.py).

Muestra en una sola ejecución: reparto de carga multi-objetivo, failover con
``Retry-After`` respetado, rpm aprendido entre ejecuciones y agregación DAG.

Preparación::

    python3 examples/mock_llm_server.py --port 8765 &     # terminal 1
    mkdir -p /tmp/sorl/.a2s
    # /tmp/sorl/.a2s/pool.json con endpoints http://127.0.0.1:8765/{fast,mid,pro}/v1
    # (ver examples/pool.mock.json)

Uso::

    python3 examples/sorl_demo.py --workspace /tmp/sorl --prompts 12
    # ejecútalo DOS veces: la 2ª ya no genera 429s (rpm aprendido)
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2s.config import Config
from a2s.provider_pool import build_pool_provider


def main() -> int:
    ap = argparse.ArgumentParser(description="Demo del pool SORL")
    ap.add_argument("--workspace", default="/tmp/sorl")
    ap.add_argument("--prompts", type=int, default=12)
    ap.add_argument("--max-parallel", type=int, default=8)
    args = ap.parse_args()

    cfg = Config(workspace=args.workspace, quiet=True)
    pool = build_pool_provider(config=cfg)

    print(f"\n▶ FANOUT: {args.prompts} subtareas independientes sobre el pool")
    prompts = [f"subtarea {i}: extraer entidades del documento {i}" for i in range(args.prompts)]
    results = pool.fanout(prompts, max_parallel=args.max_parallel)
    served = Counter(str(r).split("]")[0].lstrip("[") for r in results if r)
    ok = sum(1 for r in results if r)
    print(f"  completadas: {ok}/{len(results)} · reparto por endpoint: {dict(served)}")
    if ok < len(results):
        print(f"  ({len(results) - ok} subtareas sin cuota disponible — degradación honesta, "
              "el fallback heurístico no genera texto)")

    print("\n▶ DAG: 2 resúmenes paralelos → 1 síntesis (dependencias + agregación)")
    tasks = [
        {"id": "res_a", "prompt": "resumir documento A", "kind": "summarize"},
        {"id": "res_b", "prompt": "resumir documento B", "kind": "summarize"},
        {"id": "sintesis", "prompt": "sintetizar A y B en una conclusión",
         "depends_on": ["res_a", "res_b"]},
    ]
    out = pool.execute_dag(tasks, aggregate=lambda r: r["results"]["sintesis"])
    print(f"  ejecutadas: {out['executed']}/{out['total']} · fallidas: {out['failed'] or 'ninguna'}")
    print(f"  síntesis → {out['aggregate']}")

    print("\n▶ Telemetría aprendida en esta ejecución:")
    for e in pool.status()["endpoints"]:
        if e["role"] != "member":
            continue
        rpm = e["rpm_effective"] or "∞"
        learned = f" (aprendido; declarado {e['rpm']})" if e.get("rpm_learned") else ""
        print(f"  {e['name']:<6} rpm_efectivo={rpm}{learned} "
              f"llamadas={e.get('total', 0)} 429s={e.get('rate_limited', 0)} "
              f"p50={e.get('p50_ms')}ms coste≈${e.get('est_cost', 0)}")
    pool.close()
    print("\n(snapshot guardado: la siguiente ejecución arranca con este aprendizaje)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
