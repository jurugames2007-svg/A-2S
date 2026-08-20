#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera docs/INFORME_ANALISIS_A2S.pdf — análisis integral de 250 criterios.

Uso: python3 tools/gen_informe.py   (desde la raíz del repo)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from pdf_min import MiniPDF                          # noqa: E402
from informe_contenido import SECTIONS               # noqa: E402

TITULO = "Informe de Análisis Integral — A²S v1.6.0"
FECHA = "2026-08-20"

METRICAS = [
    ("Versión analizada", "1.6.0 (rama arena/01a02086-a-2s, commits 58ca50f..03eab6f)"),
    ("Líneas de código (a2s/)", "6.489 en 24 módulos Python (stdlib al 100%)"),
    ("Funciones / clases", "309 funciones · 51 clases · CC media 4,8"),
    ("Complejidad máx. (hotspots)", "shell=33, execute_dag=31, evolve_step=26, _handler=23, execute_step=19"),
    ("Pruebas", "139 tests en 11 suites · ~3,4 s · 6 corridas consecutivas en verde"),
    ("Dependencias externas", "0 (ni runtime ni build más allá de setuptools)"),
    ("Documentación", "README 427 líneas · LIMITACIONES 439 líneas · 6 ejemplos ejecutables"),
    ("Interfaces de usuario", "CLI (14 comandos) · dashboard SSE · API Python · informes PDF/MD firmables"),
    ("Persistencia", "SQLite + JSONL append-only (hash chain) + JSON atómico + artefactos HMAC"),
    ("Verificación en vivo", "SORL: failover/429/aprendizaje · CE: API real GitHub · FSM: escalado nivel 0->1"),
]

PUNTUACIONES = [
    ("C1 Arquitectura", "4,0"), ("C2 Funcionalidad", "3,5"), ("C3 UI/UX", "2,5"),
    ("C4 Analítica", "3,5"), ("C5 Crecimiento", "3,0"), ("C6 Seguridad", "3,5"),
    ("C7 Fiabilidad", "3,5"), ("C8 Código/Pruebas", "3,5"), ("C9 Documentación", "5,0"),
    ("C10 Ética", "5,0"), ("C11 Operación/Coste", "3,5"), ("C12 Escalabilidad", "3,0"),
    ("C13 Comparativa", "3,5"),
]

ROADMAP = [
    "1. CI mínima: GitHub Actions con los 139 tests (6 líneas, cero deps).",
    "2. Refactor de los 5 hotspots CC>19 con tests-first (shell, execute_dag, evolve_step, _handler, execute_step).",
    "3. Memoria semántica local opcional (índice invertido BM25 stdlib antes que embeddings externos).",
    "4. Alertamiento saliente: webhook/email cuando el pool degrade o el watcher escale.",
    "5. Unlearning real: caducidad y poda de fichas perdedoras; decay de win-rates.",
    "6. search/code en el CE (estudiar fragmentos, no solo READMEs) con los mismos presupuestos y permisos.",
    "7. Auditoría web del dashboard (CSRF/headers/ARIA) antes de cualquier exposición.",
    "8. a2s learn que EDITE la especificación FSM a partir de los escalados (cerrar el ciclo nivel 1->nivel 0).",
    "9. Rotación/compresión de telemetry.jsonl y CHANGELOG.md formal.",
    "10. Provisionador spot del §12 como herramienta del operador (no del agente).",
]


def main() -> int:
    pdf = MiniPDF(TITULO)
    # ---------- portada ----------
    pdf.spacer(160)
    pdf.para("A²S", size=34, font="F2")
    pdf.para("Agente Autónomo Supremo con capacidades forenses", size=13, font="F3")
    pdf.spacer(26)
    pdf.para(TITULO, size=20, font="F2")
    pdf.para("250 criterios en 14 categorías · metodología: análisis estático (AST), "
             "métricas medidas, ejecución de la suite completa y verificaciones en vivo "
             "documentadas en el historial del proyecto.", size=10.5)
    pdf.spacer(14)
    pdf.para(f"Fecha: {FECHA} · Rama: arena/01a02086-a-2s · Licencia: MIT", size=9.5, font="F3")
    pdf.spacer(30)
    pdf.para("Convención de veredictos por criterio: [SÍ] implementado y verificable · "
             "[PARCIAL] implementado con matices declarados · [NO] ausente (y por qué). "
             "Ningún criterio se maquilla: los NO son parte del resultado.", size=10)

    # ---------- resumen ejecutivo ----------
    pdf.h1("Resumen ejecutivo")
    pdf.para(
        "A²S es un framework de agente autónomo en Python puro (stdlib, cero dependencias) "
        "que persigue objetivos con loops auto-optimizados hasta verificar su cumplimiento, "
        "y entrega informes con cadena de custodia criptográfica. La versión analizada "
        "(1.6.0) integra cuatro capas complementarias: (1) núcleo de recuperación fractal "
        "con escalera reintento->reparametrización->cambio de herramienta->división->"
        "replanificación; (2) SORL, un pool de proveedores legítimos con tres niveles de "
        "aprendizaje (cuota real observada, micro-ajuste de pesos, aptitud medida por tipo "
        "de tarea con puerta de incompetencia); (3) el Ciclo de Enriquecimiento, que aprende "
        "de repositorios públicos de GitHub hasta verificar capacidad; y (4) el nivel "
        "determinista (FSM + vigía por eventos) que resuelve lo predecible sin gastar un "
        "token y escala lo imprevisto al agente.")
    pdf.para(
        "Su rasgo diferencial no es la potencia (un Auto-GPT con GPT-4 razona mejor) sino "
        "la confianza verificable: cada decisión deja huella auditable (ledger con hash "
        "chain, firmas HMAC, telemetría), cada límite está documentado como contrato "
        "(LIMITACIONES.md, 13 secciones) y las fronteras éticas están ejecutadas en el "
        "modelo de permisos, no prometidas en un documento. Ponderado sobre 250 criterios: "
        "3,7/5, con máximo en documentación/ética (5,0) y mínimo en UI/UX (2,5).")
    pdf.h2("Métricas medidas del código")
    for k, v in METRICAS:
        pdf.kv(k, v)
    pdf.h2("Puntuaciones por categoría (0-5)")
    pdf.table(["categoría", "nota"], [[k, v] for k, v in PUNTUACIONES], [330, 80])

    # ---------- categorías ----------
    for sec in SECTIONS:
        pdf.h1(sec["titulo"])
        if sec.get("intro"):
            pdf.para(sec["intro"])
        for num, nombre, analisis in sec["criterios"]:
            pdf.h3(f"{num}. {nombre}")
            pdf.para(analisis, indent=8)

    # ---------- roadmap ----------
    pdf.h1("Roadmap priorizado (derivado de este análisis)")
    for item in ROADMAP:
        pdf.bullet(item)
    pdf.spacer(8)
    pdf.para("Generado con tools/gen_informe.py (motor PDF en stdlib puro, sin "
             "dependencias). Todas las afirmaciones son reproducibles con los comandos "
             "citados en README.md y LIMITACIONES.md.", size=8.5, font="F3")

    os.makedirs("docs", exist_ok=True)
    out = os.path.join("docs", "INFORME_ANALISIS_A2S.pdf")
    n = pdf.save(out)
    print(f"OK: {out} · {n} páginas · {os.path.getsize(out)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
