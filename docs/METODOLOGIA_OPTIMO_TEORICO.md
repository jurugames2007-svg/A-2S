# Metodología abierta para aproximar un sistema a su óptimo teórico

> **Alcance:** proceso completo de mejora continua usando exclusivamente
> conocimientos públicos, estándares abiertos y software que puede ejecutarse
> sin comprar licencias, suscripciones ni servicios. Un proveedor externo puede
> conectarse únicamente si el operador ya tiene derecho legítimo de uso; nunca
> es requisito del método.

## 1. Qué significa «óptimo teórico»

Un sistema real casi nunca tiene un máximo único y permanente. Rendimiento,
calidad, coste, seguridad, mantenibilidad, consumo energético y experiencia de
usuario compiten entre sí. Además, cambian la carga, el hardware, las amenazas
y las necesidades. Por eso se define el óptimo como una **frontera de Pareto**:
no es posible mejorar una dimensión sin empeorar otra, respetando restricciones
éticas, legales y operativas.

La función de utilidad puede expresarse como:

```text
U(x) = Σ wi · normalizar(mi(x)) − Σ pj · violaciónj(x)
```

- `mi`: métrica observada, no opinión;
- `wi`: peso acordado y versionado;
- `pj`: penalización alta por romper una restricción;
- `x`: configuración o versión candidata.

El proceso no promete perfección. Busca una sucesión verificable
`x0 → x1 → … → xn` donde cada cambio mejora la utilidad o aporta aprendizaje
útil, sin degradaciones ocultas. Se detiene temporalmente cuando el beneficio
marginal es menor que el coste/riesgo, nunca porque se declare «perfecto».

## 2. Principios no negociables

1. **Objetivo falsable:** cada afirmación debe poder fallar ante una prueba.
2. **Baseline antes de cambiar:** sin línea base no existe mejora demostrada.
3. **Una hipótesis por experimento:** reduce confusores y facilita revertir.
4. **Evidencia reproducible:** comando, versión, semilla, datos y entorno.
5. **Seguridad y legalidad como restricciones:** no se compensan con velocidad.
6. **Unknown no es healthy ni exhausted:** la falta de datos se etiqueta como tal.
7. **No ejecutar código encontrado durante la investigación:** primero licencia,
   procedencia, revisión, aislamiento y decisión humana.
8. **Cambios pequeños y reversibles:** feature flags, commits atómicos y rollback.
9. **Automatizar el control, no el autoengaño:** un gate no puede validarse a sí
   mismo sin evidencia independiente.
10. **Mejora continua:** PDCA para gobernanza, OODA para operación rápida, DMAIC
    para defectos persistentes y Teoría de Restricciones para el cuello actual.

## 3. Ciclo metodológico completo

### Fase 0 — Mandato, límites y cadena de decisión

**Objetivo:** saber qué sistema se optimiza, para quién y dentro de qué frontera.

1. Identificar propietarios, usuarios, datos, procesos dependientes y entornos.
2. Dibujar el límite: entradas, salidas, terceros, red, almacenamiento y trust
   boundaries.
3. Registrar restricciones: privacidad, autorización, hardware, energía,
   presupuesto cero, disponibilidad y compatibilidad.
4. Definir quién puede aprobar, desplegar, detener y revertir.
5. Crear un registro de riesgos y un ADR inicial (*Architecture Decision Record*).

**Técnicas:** SIPOC, mapa de contexto C4, RACI, threat modeling STRIDE, análisis
PREmortem. Se pueden documentar con Markdown, Mermaid, PlantUML o draw.io
comunitario; Git conserva la historia.

**Gate:** no se modifica nada hasta que frontera, responsable y rollback estén
escritos.

### Fase 1 — Definir el resultado y sus SLO

**Objetivo:** transformar «mejor» en condiciones cuantificables.

1. Separar métricas de resultado, de proceso y guardrails.
2. Establecer SLI/SLO: latencia p50/p95/p99, tasa de éxito, calidad, seguridad,
   recuperación, consumo y mantenibilidad.
3. Definir criterio de aceptación, tolerancia y ventana temporal.
4. Asignar pesos de utilidad y límites duros.
5. Crear ejemplos positivos, negativos y casos límite.

Ejemplo:

```yaml
objetivo: "resolver tareas verificables sin degradar seguridad"
slo:
  tasa_verificada: ">= 0.95"
  latencia_p95_s: "<= 8"
  coste_requerido: "0"
guardrails:
  acciones_no_autorizadas: "= 0"
  regresiones_criticas: "= 0"
```

**Gate:** un tercero puede leer la especificación y decidir objetivamente si
una ejecución pasa.

### Fase 2 — Inventario y observabilidad mínima

**Objetivo:** conocer el estado real antes de optimizar.

1. Inventariar código, configuraciones, datos, interfaces, modelos, hardware y
   dependencias.
2. Generar SBOM y hashes de artefactos.
3. Mapear flujo de datos y secretos sin copiar su contenido a logs.
4. Incorporar IDs de correlación, logs estructurados, métricas y trazas.
5. Clasificar telemetría por fuente: oficial, configurada, estimada o unknown.

**Herramientas abiertas:** `git`, SPDX/CycloneDX, Syft, Trivy, Grype,
OpenTelemetry, Prometheus y Grafana autoalojados; en A²S, ledger SHA-256,
firmas HMAC y telemetría JSONL.

**Gate:** toda métrica crítica indica unidad, timestamp, fuente y alcance.

### Fase 3 — Baseline reproducible

**Objetivo:** obtener `x0` con variación conocida.

1. Congelar versión, configuración, semilla y dataset.
2. Preparar entorno limpio y datos sintéticos o públicos sin información
   sensible.
3. Ejecutar warm-up y varias repeticiones; no comparar una sola muestra.
4. Guardar media, mediana, dispersión, percentiles e intervalos de confianza.
5. Medir carga normal, pico, degradación y recuperación.
6. Registrar ruido conocido: CPU, RAM, I/O, red y procesos vecinos.

**Herramientas abiertas:** `unittest`, pytest, Hypothesis, hyperfine, pyperf,
Locust, k6, wrk, GNU time, cProfile, perf y Valgrind. Ninguna requiere un
servicio alojado.

**Gate:** otra máquina compatible puede repetir el comando y obtener un rango
estadísticamente coherente.

### Fase 4 — Diagnóstico y causa raíz

**Objetivo:** mejorar la restricción dominante, no lo más visible.

1. Construir un Pareto de fallos/latencia/coste.
2. Aplicar cinco porqués e Ishikawa a las categorías principales.
3. Seguir una petición extremo a extremo mediante trazas.
4. Perfilar CPU, memoria, bloqueos, I/O y red.
5. Formular hipótesis que predigan una observación medible.
6. Distinguir correlación, causa y síntoma.

**Técnicas:** Teoría de Restricciones, análisis de valor, fault tree, flamegraphs,
heap snapshots, differential profiling y análisis de complejidad ciclomática.

**Gate:** cada mejora propuesta referencia evidencia y una causa candidata; no
se acepta «parece más rápido».

### Fase 5 — Investigación pública y radar de soluciones

**Objetivo:** evitar reinventar patrones, sin convertir un repositorio externo
en dependencia ciega.

1. Buscar estándares, artículos, issues y repositorios públicos relevantes.
2. Verificar licencia SPDX, actividad, seguridad, alcance y mantenibilidad.
3. Registrar URL, fecha, versión/commit y lección de diseño.
4. Comparar al menos tres enfoques, incluida la opción de no cambiar.
5. Extraer patrones, contratos y técnicas de prueba; no copiar por reflejo.
6. Rechazar fuente con licencia desconocida, conducta insegura o procedencia
   dudosa hasta revisión humana.

En A²S:

```bash
python -m a2s scout --workspace workspace
python -m a2s scout --query "open source agent evaluation gateway"
```

`a2s scout` lee metadatos públicos de GitHub, filtra por licencia abierta,
persiste procedencia y declara `code_executed: false`. `a2s learn` puede
estudiar READMEs bajo un presupuesto separado. Ninguno ejecuta código ajeno.

**Gate:** toda idea externa tiene fuente y licencia; la adopción tiene ADR y
pruebas propias.

### Fase 6 — Priorización y diseño experimental

**Objetivo:** elegir el cambio de mayor valor ajustado al riesgo.

Usar una matriz como:

```text
prioridad = (impacto × confianza × alcance) / (esfuerzo × riesgo)
```

1. Puntuar impacto en los SLO y guardrails.
2. Estimar reversibilidad, radio de impacto y deuda futura.
3. Diseñar tratamiento, control, métrica primaria y duración.
4. Calcular tamaño de muestra o, como mínimo, número de repeticiones.
5. Definir condición de abortar y rollback antes de ejecutar.

**Técnicas:** RICE/ICE, FMEA, MCDA, diseño factorial, benchmark pareado,
canary, A/B local y pruebas de no inferioridad.

**Gate:** la hipótesis tiene formato «si X, entonces Y cambiará Z, sin romper G».

### Fase 7 — Implementación mínima, segura y reversible

**Objetivo:** cambiar solo lo necesario para probar la hipótesis.

1. Crear rama/commit atómico.
2. Añadir primero prueba de regresión o caracterización.
3. Implementar con interfaces estrechas y defaults seguros.
4. Mantener compatibilidad o documentar migración.
5. Evitar credenciales en código; usar variables y archivos fuera de Git.
6. Añadir telemetría y explicación de decisiones.
7. Preparar rollback automático o comando explícito.

**Técnicas:** test-first, strangler, branch by abstraction, feature flag local,
configuración declarativa, idempotencia y límites de recursos.

**Gate:** el cambio se puede desactivar o revertir sin pérdida de evidencia.

### Fase 8 — Verificación multinivel

**Objetivo:** intentar refutar la mejora desde diferentes capas.

| Capa | Qué debe probar | Opciones abiertas/gratuitas |
|---|---|---|
| Sintaxis/estilo | parseo, imports, formato | `py_compile`, Ruff, Black |
| Unitarias | reglas y casos límite | `unittest`, pytest, doctest |
| Propiedades/fuzz | invariantes y entradas inesperadas | Hypothesis, Atheris, AFL++ |
| Integración | DB, red, archivos, protocolos | servidores fake, WireMock, containers |
| Contrato | OpenAPI/JSON Schema, compatibilidad | Schemathesis, Dredd |
| E2E | flujo de usuario real | Playwright, Selenium |
| Rendimiento | latencia, throughput, memoria | k6, Locust, hyperfine, pyperf |
| Caos | timeout, 429/5xx, caída, disco lleno | Toxiproxy, Pumba, procesos fake |
| Seguridad | SAST, secretos, dependencias, DAST | Bandit, Gitleaks, Trivy, OWASP ZAP |
| Accesibilidad | teclado, contraste, semántica | axe-core, Pa11y, Lighthouse |
| Recuperación | backup, restore, reanudación | scripts reproducibles + hashes |

Reglas:

- ejecutar primero el test afectado y después la suite completa;
- separar fallos deterministas de flakiness y corregir ambos;
- no ocultar tests lentos: clasificarlos y ejecutarlos en un stage conocido;
- fallar el gate ante warnings de recursos, procesos huérfanos o leaks;
- conservar artefactos y semillas de todo fallo.

**Gate:** pasan funcionalidad, guardrails y presupuesto de regresión. Si una
métrica mejora pero seguridad o corrección empeoran, la candidata se rechaza.

### Fase 9 — Evaluación estadística y decisión

**Objetivo:** decidir con evidencia, no con una captura favorable.

1. Comparar candidata y control bajo el mismo entorno.
2. Presentar efecto absoluto y relativo, dispersión e intervalo de confianza.
3. Revisar outliers antes de eliminarlos y documentar el criterio.
4. Evaluar todas las dimensiones de Pareto.
5. Aceptar, iterar o revertir según la regla predefinida.

Para decisiones pequeñas basta mediana + p95 + repeticiones pareadas. Para
experimentos relevantes usar bootstrap, Mann–Whitney o prueba adecuada a la
distribución. Python (`statistics`, `random`) y R son suficientes sin servicios.

**Gate:** el resultado supera el mínimo relevante, no solo una significancia
estadística sin valor práctico.

### Fase 10 — Despliegue progresivo y recuperación

**Objetivo:** limitar el radio de daño y verificar en condiciones reales.

1. Snapshot/backup verificado.
2. Desplegar en entorno aislado, luego canary y finalmente población completa.
3. Vigilar error budget, saturación y métricas guardrail.
4. Detener promoción ante umbral; rollback automático o manual ensayado.
5. Validar migraciones hacia delante y atrás.

**Herramientas abiertas:** systemd, Podman, Docker Engine/Moby, Ansible, k3s,
Kubernetes, Argo Rollouts y Velero. Para un único host, systemd + script de
backup suele ser más óptimo que introducir un clúster.

**Gate:** restore y rollback se probaron, no solo se documentaron.

### Fase 11 — Control operativo

**Objetivo:** impedir que la mejora se degrade silenciosamente.

1. Dashboard de SLI, alertas accionables y runbooks.
2. Error budgets y capacidad; alertar sobre síntomas, no ruido.
3. Detección de drift en datos, dependencias y configuración.
4. Auditoría de permisos, negaciones y cambios.
5. Rotación/retención de logs y pruebas periódicas de restore.
6. Postmortem sin culpa ante incidente, con acciones y propietario.

**Gate:** cada alerta indica impacto, evidencia, acción y escalado; toda métrica
sin decisión asociada se elimina o reclasifica.

### Fase 12 — Estandarizar, aprender y repetir

**Objetivo:** convertir el resultado en una nueva baseline y buscar la siguiente
restricción.

1. Actualizar ADR, changelog, runbook, threat model y baseline.
2. Persistir qué hipótesis ganó, perdió o fue inconclusa.
3. Podar conocimiento obsoleto después de suficiente evidencia.
4. Automatizar la regresión descubierta.
5. Recalcular Pareto y escoger el próximo cuello de botella.
6. Revisar pesos y SLO con los interesados; no moverlos para «aprobar».

El ciclo completo queda:

```text
Definir → Inventariar → Medir → Diagnosticar → Investigar → Experimentar
   ↑                                                            ↓
Controlar ← Desplegar ← Verificar ← Implementar ← Priorizar ←───┘
```

## 4. Cadencia recomendada

- **Por commit:** sintaxis, unitarias afectadas, secretos, complejidad.
- **Por integración:** suite completa, contratos, integración, SBOM.
- **Diaria/nocturna:** fuzz, rendimiento corto, flakiness y restore de muestra.
- **Semanal:** DAST, caos, capacidad, dependencias y radar OSS.
- **Por release:** E2E, benchmark completo, amenaza, firma, rollback y canary.
- **Trimestral:** revisar SLO, Pareto, arquitectura, retención y conocimiento.

La frecuencia se adapta al riesgo; no requiere plataformas SaaS. `cron`,
systemd timers o un runner GitHub Actions para repositorios públicos cubren la
automatización básica.

## 5. Aplicación concreta en A²S

| Fase | Evidencia implementada |
|---|---|
| Definir | objetivo + verificadores de paso y misión |
| Inventariar | herramientas introspectivas, hashes y ledger |
| Medir | episodios, telemetría SORL, `a2s audit` |
| Diagnosticar | estancamiento, historial de fallos, BM25 |
| Investigar | `a2s scout` y `a2s learn` |
| Priorizar | scheduler multiobjetivo y red de gobernanza |
| Implementar | planes fractales, reparametrización, plugins acotados |
| Verificar | unit/integration/E2E, consenso y firmas HMAC |
| Desplegar | zipapp, servicio y Control Plane local |
| Controlar | SSE, circuit breakers, cuota, auditoría y reanudación |

Comandos de control:

```bash
python -m a2s dashboard --port 8000             # Control Plane local
python -m a2s dashboard --public --auth          # exposición deliberada + token
python -m a2s route-preview --kind plan --json   # decisión sin llamada real
python -m a2s scout --json                       # radar OSS incremental
python -m a2s audit                              # gates medibles
python -m unittest discover -s tests -v          # suite completa
python tools/check_purity.py && python tools/check_cc.py 35
```

## 6. Criterio de parada honesto

Una iteración puede cerrarse cuando:

- todos los límites duros pasan;
- el SLO se cumple con margen durante la ventana acordada;
- no queda una candidata de mayor impacto/riesgo razonable;
- el beneficio marginal es inferior al coste de cambio;
- restore y rollback están probados;
- riesgos residuales y unknowns están documentados.

Esto es un **óptimo operativo provisional**, no el óptimo absoluto. Cualquier
cambio de demanda, amenaza, herramienta o evidencia reabre el ciclo.
