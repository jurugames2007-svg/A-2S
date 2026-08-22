# Validación: ¿A²S cumple el propósito para el que fue diseñado?

**Fecha de validación:** 2026-08-22  
**Versión:** 1.10.0
**Veredicto:** **sí para su alcance declarado; no para interpretaciones
universales o capacidades que no pueden verificarse.**

## Propósito comprobable

Del README y los contratos del código se deriva este propósito:

> Recibir un objetivo sobre recursos propios/autorizados, descomponerlo,
> ejecutar herramientas bajo permisos, evaluar evidencia, recuperarse de
> fallos, persistir el proceso y cerrar únicamente con verificación positiva o
> con un timebox que deje un informe forense reanudable.

No forma parte del propósito: resolver cualquier problema del mundo, ignorar
controles ajenos, crear cuota infinita, reemplazar supervisión humana en
operaciones críticas o demostrar que un resultado semántico es correcto sin un
verificador adecuado.

## Matriz de aceptación

| Requisito de diseño | Evidencia | Resultado |
|---|---|---:|
| Acepta un objetivo y construye un plan | `AgentLoop.run`, planner y test de misión | pasa |
| Reintenta y reparametriza | eventos `retry`/`failure_handled` | pasa |
| Divide un paso bloqueado | `split_step`, test `split_recovery` | pasa |
| Replanifica ante estancamiento | planner + tests de recuperación | pasa |
| Solo declara éxito tras verificador | goal verifier/consenso + tests | pasa con matiz |
| Termina por timebox de seguridad | `max_wall_seconds` y cierre parcial | pasa |
| Deja estado reanudable | SQLite/JSONL/ledger/report | pasa |
| Mantiene cadena de custodia | hash chain, HMAC y pruebas de tamper | pasa |
| Opera sin dependencia o servicio pago | runtime Python stdlib + heurístico | pasa |
| Usa IAs autorizadas como pool opcional | SORL, cuota, 429, circuit breaker | pasa |
| Integra OmniRoute sin ser su base | endpoint explícito/config OpenAI-compatible | pasa |
| Explica el ruteo sin gastar una llamada | `route-preview`, `live_request_executed=false` | pasa |
| Crece buscando proyectos abiertos | `scout`, SPDX, dedup y procedencia | pasa |
| No ejecuta lo encontrado al explorar | contrato y test `code_executed=false` | pasa |
| Ofrece operación industrial visible | Control Plane, SSE, topología y audit | pasa |
| Se instala y ejecuta mediante npm | tarball aislado, tres bins, CLI/HTTP/GUI E2E | pasa |
| Controla exposición web | auth, CSP, Origin, deny framing | pasa con matiz |

### Matiz del verificador

Un verificador específico —por ejemplo, «el archivo existe, contiene hashes
válidos y no tiene marcadores»— ofrece evidencia fuerte. El `goal_check` de un
LLM o del heurístico para un objetivo ambiguo no equivale a una prueba formal.
Por ello A²S cumple la arquitectura de verificación, pero la fuerza de la
conclusión depende del verificador que el operador defina.

## Pruebas ejecutadas

### Suite funcional completa

```bash
python -m unittest discover -s tests -v
```

Resultado esperado de esta versión: **198 tests, 0 fallos, 0 errores, 0 skips**.
Incluye unitarias, integración HTTP real, procesos/sandbox, recuperación,
misiones de punta a punta, RBAC, red local, FSM, DAG, concurrencia, persistencia,
seguridad, empaquetado y radar OSS.

Las misiones completas que v1.8.2 mantenía gated se ejecutan ahora por defecto.
El mini-shell espera todos los procesos del pipeline, cierra descriptores y
recolecta procesos tras timeout; las ejecuciones con `PYTHONWARNINGS=default` no
muestran los `ResourceWarning` anteriores.

### Gates estructurales

```bash
python tools/check_purity.py
python tools/check_cc.py 35
python -m a2s audit --json
node --check a2s/ui/app.js
python -m pip wheel . --no-deps --no-build-isolation
```

Medición de `a2s audit` en esta revisión:

- pureza stdlib: **pasa**;
- complejidad: media **4.53**, máximo **34**, umbral 35;
- pruebas detectadas: **198 en 17 suites**;
- roadmap/CI: **5/5** piezas locales; plantilla remota preparada;
- documentación: **18** secciones de límites;
- versión: **1.10.0 = 1.10.0**;
- nota medible: **5.0/5**.

El 5/5 significa que los seis gates actuales pasan; no prueba perfección. El
propio auditor deja fuera cobertura de líneas, WCAG con tecnología asistiva,
benchmarks comparativos y auditoría web independiente.

### Control Plane

Pruebas HTTP sobre un puerto real verifican:

- entrega de HTML/CSS/JS/SVG empaquetados;
- CSP `default-src 'self'`, `X-Frame-Options: DENY` y `nosniff`;
- URLs browser-facing relativas (sin localhost hardcodeado);
- health, estado, auth bearer y rechazo de Origin cruzado;
- transferencia de opciones al mission manager;
- radar con OmniRoute y política open-source-only.

El wheel generado contiene todos los activos `a2s/ui/*`.

### Distribución npm

```bash
npm run build
npm run test:npm
```

El build produce `artifacts/a2s.pyz` y
`artifacts/a2s-agent-control-plane-1.10.0.tgz`. El E2E instala el tarball en un
prefijo temporal sin hooks, ejecuta `a2s --version`, `a2s doctor`, inicia el
Control Plane instalado, consulta `/healthz` y confirma que la GUI está
incluida. El tarball no contiene dependencias npm de runtime y ocupa
aproximadamente 160 KB comprimido. La matriz CI repite este contrato en Linux,
macOS y Windows cuando el workflow remoto se ejecute.

### SORL y OmniRoute

Se verifican:

- cuatro estrategias de scheduler;
- cuota deslizante y `Retry-After`;
- circuit breaker, fallback, fanout y DAG;
- aprendizaje persistente de RPM/capacidad;
- preview explicable que no llama al transporte ni consume cuota;
- distinción `unknown`/`exhausted`;
- descubrimiento de OmniRoute solo con `A2S_OMNIROUTE_URL` explícita.

### Scouting real

Una ejecución pública del radar encontró 24 candidatos en tres consultas,
incorporó 15 al workspace de prueba, rechazó licencias desconocidas y declaró
`code_executed: false`. Cuatro señales verificadas se añadieron al catálogo
semilla: Plano, Future AGI, Aisix y OpenZiti LLM Gateway.

## Riesgos residuales

1. **No hay prueba formal general.** Los objetivos semánticos requieren
   verificadores de dominio.
2. **Sandbox por capas.** `rlimits` es más débil que bwrap/nsjail; `doctor`
   muestra el nivel real.
3. **Control Plane monoproceso.** No es un clúster HA y la parada es cooperativa.
4. **TLS externo.** `--public` debe ir con `--auth` y reverse proxy TLS.
5. **Cuotas cambiantes.** RPM configurada es estimación hasta tener telemetría.
6. **Metadata OSS no es auditoría.** Licencia, popularidad y descripción no
   garantizan seguridad del código.
7. **E2E visual pendiente.** La API/UI se prueba estructuralmente; falta una
   matriz Playwright + axe-core en navegadores reales.
8. **Rendimiento sin baseline sostenida.** Falta carga prolongada del Control
   Plane y comparación en hardware documentado.
9. **Dependencia opcional de IA.** Sin LLM, el heurístico opera pero su alcance
   de razonamiento es más reducido.

## Conclusión

A²S **cumple su propósito de framework autónomo, recuperable, verificable y
forense dentro de un entorno autorizado**, y v1.10 lo vuelve operable mediante
una GUI industrial y un ecosistema de IA opcional. No cumple —ni afirma
cumplir— una lectura de «agente infalible universal». La ruta correcta hacia el
óptimo es mantener verificadores específicos, baselines, gates y el ciclo de
mejora descrito en
[`METODOLOGIA_OPTIMO_TEORICO.md`](METODOLOGIA_OPTIMO_TEORICO.md).
