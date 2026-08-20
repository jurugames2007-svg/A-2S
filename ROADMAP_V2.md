# ROADMAP v2.0 — Plan de Mejora Integral (anotado y ejecutable)

> Origen: plan de mejora de 250 criterios derivado del Informe de Análisis
> Integral v1.6.0. Este documento lo compromete como roadmap con revisión
> técnica: qué se acepta tal cual, qué se adapta y por qué, y qué queda
> diferido. Estado se actualiza por tranche.

**Leyenda**: ✅ hecho · 🔧 esta tranche · 📋 aceptado (siguiente tranche) ·
🔀 adaptado (cambio justificado) · ⏸ diferido (v2.0, decisión de producto)

## Tranche 1 (v1.7.0) — en ejecución

| # | Acción | Criterios | Estado |
|---|--------|-----------|--------|
| 1 | CI: GitHub Actions (tests + guardianes) | 169 | 🔧 (workflow en tools/ci/ci.yml: copiar a mano, el token del sandbox no tiene permiso workflows) |
| 2 | Guardián de pureza stdlib (test que falla si entra una dependencia) | 12, 133 | 🔧 |
| 3 | Guardián de complejidad (CC máx 35 hoy, ratchet hacia 15; media < 6) | 2, 16 | 🔧 |
| 4 | Memoria semántica: índice BM25 stdlib + `a2s search` | 9, 48, 214 | 🔧 |
| 5 | Notificaciones salientes (webhook/file/print) + `--notify` | 49, 151 | 🔧 |
| 6 | Unlearning: poda de fichas + decaimiento por frescura + decay de estrategias | 98, 109, 110 | 🔧 |
| 7 | Refactor hotspot nº1: `execute_dag` → olas topológicas + ejecutor de ola | 2, 163 | 🔧 |
| 8 | `--seed` global (determinismo reproducible) | 118, 160 | 🔧 |
| 9 | Rotación de telemetry.jsonl por tamaño | 22, 211 | 🔧 |

## Tranche 2 — refactor y calidad (aceptado)

| # | Acción | Criterios | Notas |
|---|--------|-----------|-------|
| 10 | Refactor `tools.py:shell` (parser/ejecutor/redirección) | 2, 163 | tests-first, objetivo CC<15 |
| 11 | Refactor `planner.py:evolve_step`, `dashboard.py:_handler`, `loop.py:execute_step` | 2, 163 | uno por PR |
| 12 | cli.py → subpaquete `a2s/cli/` con router (patrón Command) | 3 | mantener `a2s.cli:main` como shim |
| 13 | `prompt_templates.py` (dedup de prompts providers/pool) | 5b, 164 | contrato: textos idénticos |
| 14 | `logging` en vez de `print` en módulos no-CLI | 5c | con handler JSONL |
| 15 | `--strict-goal` (verificador exigente, default off→on en v2) | 5d, 90 | mitigación §2.9 |
| 16 | fuzzing FSM/pool (1k casos/módulo, seeds) | 28, 168 | stdlib random |
| 17 | suite test_chaos.py (timeouts/500s/kill -9) | 17, 147 | |
| 18 | cobertura con coverage.py (dev-dep, CI >85%) | 15, 156 | dev-only: no rompe stdlib |
| 19 | CHANGELOG.md + firma del zipapp (`a2s verify-live`) | 139, 176 | |

## Tranche 3 — capacidades (aceptado)

| # | Acción | Criterios |
|---|--------|-----------|
| 20 | `search/code` en el CE (fragmentos, no solo READMEs) | 27, 96 |
| 21 | A/B testing (`a2s experiment`) + IC 95% win-rates | 106, 107 |
| 22 | Frescura/autoría en ranking de fichas | 103 |
| 23 | `a2s explore` (curiosidad con presupuesto) | 101 |
| 24 | Aislamiento semántico anti prompt-injection (delimitadores + validación) | 135 |
| 25 | Backups (`a2s backup` snapshot cifrado) | 148 |
| 26 | Exporter Prometheus (/metrics) + `--profile` (cProfile) + `a2s trace` | 24, 203 |
| 27 | Import/export CSV/JSON + `schema_version` + migrate.py | 45, 46, 217 |
| 28 | systemd/ units de ejemplo + INCIDENT_RESPONSE.md + `a2s incident` | 141, 204, 205 |

## Adaptados (cambio justificado)

| Plan original | Adaptación | Por qué |
|---|---|---|
| asyncio con aiohttp como dev-dep opcional (c39) | NO integrar: mantener hilos; documentar en CONCURRENCY.md | aiohttp sería dependencia runtime opcional real; el dominio es I/O acotado; la decisión hilos>asyncio ya está razonada |
| Reorganizar en subpaquetes core/security/ui (c30) | 🔀 solo si tranche 2 lo pide el router CLI | el aplanado a 6,5 kLOC es una virtud de auditabilidad; mover por mover rompe imports y ganancia cero |
| Tests Windows CI matrix (c13) | 🔀 matrix linux+macos primero; windows cuando platform_utils exista | no podemos verificar Windows desde aquí; prometerlo sin ejecutarlo sería lo contrario a la cultura del repo |
| RBAC multiusuario + `a2s serve` + locks distribuidos (c36/50/51/209/210) | ⏸ v2.0 como DECISIÓN DE PRODUCTO separada | 5 días de esfuerzo que cambian la naturaleza de la herramienta (operador→servicio); requiere RGPD/auditoría web primero. El plan lo trata como refactor; es un producto nuevo |
| Benchmark comparativo con Auto-GPT/LangChain (c220-229) | 🔀 comparativa documental (ya en §informe C13); benchmark ejecutable no es reproducible sin esas dependencias | |
| "6/5" en categorías | 🔀 no existe: la escala es 0-5 y §13 de LIMITACIONES prohíbe maquillar | la honestidad es el rasgo valorado nº1 del proyecto |

## No adoptado

Ninguna acción del plan choca con las fronteras éticas (§1.1/§10): todo es
ingeniería legítima. Única excepción vigilada: `provision_spot.py` y BOINC
(c27/197) se mantienen como herramientas del OPERADOR, nunca del agente
(mismo principio que §12).
