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
| 1 | CI: GitHub Actions (tests + guardianes) | 169 | ✅ plantilla completa en `tools/ci/ci.yml`, matriz Python 3.9/3.11/3.13 + npm E2E multi-OS; pendiente copiarla a workflows por permiso de GitHub App |
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

## Tranche 4 (v1.9.0) — Agent Mode industrial + radar OSS

| # | Acción | Estado | Evidencia |
|---|---|---|---|
| 29 | Control Plane industrial sin dependencias/CDN | ✅ | mission control, SSE, topología, radar y assurance en `a2s/ui/` |
| 30 | Ruta SORL explicable sin ejecutar upstream | ✅ | `a2s route-preview`, factores, estados de cuota con fuente |
| 31 | Radar incremental de proyectos públicos | ✅ | `a2s scout`, filtro SPDX, procedencia y `code_executed: false` |
| 32 | OmniRoute como gateway opcional, no como base | ✅ | env/config explícita, contrato OpenAI-compatible |
| 33 | Quitar gates de misiones completas | ✅ | pasan por defecto; pipeline shell sin procesos/pipes huérfanos |
| 34 | Metodología abierta hacia óptimo teórico | ✅ | `docs/METODOLOGIA_OPTIMO_TEORICO.md` |
| 35 | E2E de navegador con accesibilidad automatizada | 📋 | Playwright + axe-core, solo como dev tools OSS |
| 36 | Perfil/carga sostenida del Control Plane | 📋 | pyperf/Locust o k6 autoalojado; baseline antes de optimizar |

## Tranche 5 (v1.10.0) — distribución npm ejecutable

| # | Acción | Estado | Evidencia |
|---|---|---|---|
| 37 | Launcher npm multiplataforma sin dependencias | ✅ | binarios `a2s`/`a2s-control-plane`, Python ≥3.9 validado |
| 38 | Build reproducible local | ✅ | `npm run build` produce zipapp + tarball versionados |
| 39 | E2E del tarball instalado | ✅ | prefijo aislado, CLI, doctor, healthz y GUI real |
| 40 | Release de un comando | ✅ | `npm run release:local` ejecuta gates + empaquetado |
| 41 | Matriz npm Linux/macOS/Windows | ✅ configurada | job `npm-package-e2e` en GitHub Actions |
| 42 | Publicación al registry npm | ⏸ operador | requiere cuenta npm y decisión explícita; el tarball local ya es utilizable |

## Adaptados (cambio justificado)

| Plan original | Adaptación | Por qué |
|---|---|---|
| asyncio con aiohttp (c39) | ✅ RESUELTO v1.8: fachada async pura-stdlib (`a2s/asyncapi.py`, `asyncio.to_thread` sobre el núcleo síncrono) — async sin dependencias ni duplicación | aiohttp seguía fuera; la ergonomía await ya no |
| Reorganizar en subpaquetes core/security/ui (c30) | 🔀 solo si tranche 2 lo pide el router CLI | el aplanado a 6,5 kLOC es una virtud de auditabilidad; mover por mover rompe imports y ganancia cero |
| Tests Windows CI matrix (c13) | 🔀 matrix linux+macos primero; windows cuando platform_utils exista | no podemos verificar Windows desde aquí; prometerlo sin ejecutarlo sería lo contrario a la cultura del repo |
| RBAC multiusuario + `a2s serve` (c36/50) | ✅ RESUELTO v1.8 como SERVICIO EXPERIMENTAL (`a2s/serve.py`): RBAC admin/operator/viewer, JWT con rol, aislamiento `u-<user>`, auditoría total; §15 documenta el threat model. El SALTO a producto v2.0 (SSO, RGPD operativa, TLS propio, clúster) sigue siendo decisión de producto | locks distribuidos/cluster (c209/210) siguen ⏸ | | 5 días de esfuerzo que cambian la naturaleza de la herramienta (operador→servicio); requiere RGPD/auditoría web primero. El plan lo trata como refactor; es un producto nuevo |
| Benchmark comparativo con Auto-GPT/LangChain (c220-229) | 🔀 comparativa documental (ya en §informe C13); benchmark ejecutable no es reproducible sin esas dependencias | |
| "6/5" en categorías | ✅ RESUELTO v1.8: `a2s audit` — la puntuación como comando reproducible que re-mide lo medible | la escala sigue siendo 0-5; lo superable es la medición, no el número |

## No adoptado

Ninguna acción del plan choca con las fronteras éticas (§1.1/§10): todo es
ingeniería legítima. Única excepción vigilada: `provision_spot.py` y BOINC
(c27/197) se mantienen como herramientas del OPERADOR, nunca del agente
(mismo principio que §12).
