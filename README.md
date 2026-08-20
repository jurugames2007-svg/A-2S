# A²S — Agente Autónomo Supremo con capacidades forenses

> **Agente autónomo en Python (stdlib, sin dependencias) que persigue un objetivo
> con loops auto-optimizados: nunca responde "no".** Ante un fallo reintenta,
> reparametriza, cambia de herramienta, divide el paso (fractal), re-descompone
> pasos bloqueados y replanifica con enfoques distintos. Solo termina cuando el
> objetivo se **verifica cumplido** — o al agotarse el límite duro de tiempo de
> seguridad, en cuyo caso entrega un informe forense reanudable con el estado
> exacto y la cadena de custodia completa.

> **v1.2 — hardening:** sandbox real por capas (nsjail/bwrap/rlimits), firma
> criptográfica HMAC de resultados (`a2s verify`), dashboard con autenticación
> por tokens (`a2s token`, `--auth`), lista blanca de red (`--allow-host`),
> arquitectura de **plugins bajo demanda**, neuroevolución (`a2s evolve`) y
> LiveCD (`a2s build-live`, un solo archivo de ~500 KB, `--ram` en memoria).

> **v1.3 — fusión DFIR defensiva:** puente a herramientas forenses externas
> instaladas (Sleuth Kit, bulk_extractor, Volatility 3, Plaso) con lista blanca
> estricta, y auditoría de repositorios/plugins (`repo_audit`, escáner de
> patrones de riesgo inspirado en repo-forensics). Clasificación completa de
> las herramientas externas en `LIMITACIONES.md` §9.

> **v1.4 — SORL (pool de recursos legítimos):** meta-proveedor `--provider pool`
> que orquesta **los recursos a los que el operador tiene derecho de uso**
> (claves propias, free tiers dentro de sus términos, Ollama local) detrás de
> una única interfaz: scheduler multi-objetivo (coste/velocidad/fiabilidad con
> penalización por riesgo de cuota), cuotas rpm por endpoint, **failover que
> respeta `Retry-After`** (cuarentena + migración de carga, nunca evasión de
> límites), circuit breaker, telemetría persistente (JSONL, aprendizaje entre
> ejecuciones: rpm real aprendido + micro-ajuste de pesos + **aptitud medida
> por tipo de tarea con puerta de incompetencia**) y ejecución distribuida
> `fanout`/`execute_dag`. Comandos: `a2s pool-status`, `a2s pool-check`.
> Ver `LIMITACIONES.md` §10.

```text
▶ Objetivo → plan fractal → ejecutar → evaluar → [fallo] → reintento
                                              → reparametrización
                                              → cambio de herramienta
                                              → división fractal del paso
                                              → detección de estancamiento
                                                 + cambio de estrategia
                                              → replanificación (variante n+1)
          → verificador de objetivo → ✔ CUMPLIDO
```

---

## Lo que implementa la directiva (mapa operativo)

Cada capacidad de la directiva A²S tiene aquí su implementación real. Ver
`python -m a2s map` para el mapa completo.

| Directiva | Implementación en este framework |
|---|---|
| Auto-modificación de código | Núcleo de **metaprendizaje**: ajusta sus propias estrategias, parámetros y planes en tiempo de ejecución según el rendimiento |
| Loops inteligentes auto-optimizados | Bucle con detección y superación de estancamiento (ventana de fallos → cambio de estrategia por tasa de éxito) |
| Bypass universal / evasión | **Escalera de recuperación** ante fallos y bloqueos lógicos del propio proceso (no se evaden controles de seguridad de terceros) |
| Memoria heurística evolutiva | Biblioteca de estrategias con usos/ganadas/falladas y selección por win-rate |
| Simulación paralela / auto-reproducción | **Sub-agentes fractales** concurrentes (`--parallel`, `run_fractal`) |
| Predicción adaptativa | Estancamiento detectado *antes* de agotar el presupuesto |
| Asimilación instantánea de herramientas | Registro introspectivo de herramientas con esquemas JSON |
| Búsqueda forense trascendente | Forense legítimo: inventario, metadatos, hashes SHA-256, bitácora inmutable, búsqueda web vía API externa (DuckDuckGo), consultas HTTP |
| Generación de recursos ilimitados | Presupuesto acumulado expansivo: cada replanificación concede una rebanada nueva de iteraciones |
| Persistencia distribuida / estado cuántico | SQLite (memoria episódica) + ledger JSONL + artefactos en workspace; sub-agentes con memoria independiente |
| Gestión de contexto ilimitada | Contexto comprimido (historial reciente) + memoria episódica persistente consultable |
| Runtime técnico (Temporal + LangGraph) | Motor agnóstico de proveedor: hoy ejecuta el **núcleo heurístico determinista** o **LLM vía API externa compatible OpenAI**; otros runtimes se conectan implementando `BaseProvider` |
| Cadena de custodia digital | Ledger append-only con **hash chain SHA-256** verificable (`verify()`) y registro inmutable post-mortem |
| Red neuronal de gobernanza (A²S-E) | **MLP entrenado en línea** (`neural.py`): aprende de cada episodio a predecir éxito de pasos/planes; persiste en `.a2s/governance.json` |
| Consenso de instancias distribuidas (A²S-E) | **Verificación por votación ponderada** (`consensus.py`): verificador de misión (autoritativo), proveedor, red neuronal y evidencia de progreso |
| Simulación de líneas temporales (A²S-E) | **Planificación especulativa**: N planes variantes puntuados por la red de gobernanza; se ejecuta el mejor (`--speculative N`) |
| Auto-replicación y despliegue (A²S-E) | `a2s swarm` (réplicas en procesos paralelos, una por objetivo) y `a2s supervise` (el agente se relanza hasta cumplir) |
| Memoria evolutiva cuántica (A²S-E) | Estrategias y pesos neuronales **persistentes entre ejecuciones** (`strategies.json`, `governance.json`) |
| Shell universal (A²S-E) | Mini-shell evolucionado: `$VAR`, globs y `$(...)` con la **misma política de permisos** |
| Sandbox real (v1.2) | Ejecución de `python_exec` en aislamiento por capas: nsjail > bwrap > **rlimits** (RAM/CPU/procs/fds + red bloqueada); nivel reportado por `doctor` |
| Verificador criptográfico (v1.2) | HMAC-SHA256 del informe y de cada artefacto (secreto por workspace); `a2s verify` valida cadena + firmas |
| Autenticación (v1.2) | Tokens JWT-HS256 con expiración (`a2s token`); dashboard `--auth` con cookie HttpOnly |
| Egress control (v1.2) | Lista blanca de hosts (`--allow-host`) aplicada a fetch/búsqueda + `--no-network` |
| Todo es un plugin (v1.2) | `plugin_loader.py`: plugins locales auto-registrados **bajo demanda** según la misión (etiquetas ∩ objetivo), hash verificable, sin RCE de registro remoto |
| Fusión de capacidades (v1.2) | Herramientas externas como plugins: `forensics_extra` (magia de archivos, strings, EXIF, PDF) y `crypto_tools` (sha256/firma/verificación) |
| Red evolutiva (v1.2) | `neuroevolve.py`: población de redes con mutación de pesos y topología; `a2s evolve` exporta el mejor candidato a la red de gobernanza |
| LiveCD (v1.2) | `a2s build-live`: zipapp de ~490 KB que corre sin instalación; `--ram` usa `/dev/shm` como workspace volátil |
| Fusión DFIR (v1.3) | Puente a herramientas forenses externas instaladas (Sleuth Kit, bulk_extractor, Volatility, Plaso) con lista blanca estricta y confinamiento de rutas |
| Auditoría defensiva (v1.3) | `repo_audit`: escáner de repositorios/plugins locales (patrones de riesgo con severidad + hashes SHA-256) |
| Computación distribuida "gratuita" sobre recursos ajenos | **No implementado** (uso no autorizado de servicios de terceros). Legítimo y **sí implementado (v1.4)**: SORL `provider_pool` — orquestación de los recursos *propios* del operador con cuotas, failover que respeta `Retry-After`, telemetría persistente y fanout/DAG |
| Backdoors / comunicación encubierta / corrupción de validación de terceros | **No implementado contra terceros** (ilegal). Equivalente legítimo: persistencia propia reanudable y desafío de los *propios* verificadores |
| Disolución de límites "propio/ajeno" / minería / manipulación temporal | **No implementado**: redefinir palabras no convierte un ataque en legítimo, y la física no es negociable. Equivalentes: presupuestos renovables, checkpoint/reanudación, especulación de planes |

### Límites y cómo se replantean

La directiva pide "plantear de forma distinta pero alcanzar el mismo objetivo".
Eso es exactamente lo que hace el diseño:

- **"No" prohibido** → el loop solo termina con verificación positiva del objetivo
  o con el límite duro de tiempo (seguridad operativa), entregando estado
  reanudable. Los límites de iteraciones se **renuevan automáticamente** al
  replanificar.
- **Ataques a terceros** (exfiltración, malware, evasión de seguridad ajena,
  escalada de privilegios en sistemas ajenos, suplantación) → **rechazados y
  registrados** por el modelo de permisos (`a2s/config.py`), con el equivalente
  legítimo implementado de primera clase: auto-depuración, reparametrización,
  auditoría inmutable y forense de artefactos propios.

---

## Instalación y uso rápido

Requiere **Python ≥ 3.9**. Sin dependencias externas.

```bash
# Misión demo completa (diseñada para mostrar la superación de un obstáculo)
python -m a2s demo

# Cualquier objetivo propio
python -m a2s run "Investiga el proyecto y escribe un resumen con datos reales"

# Varios objetivos con sub-agentes fractales en paralelo
python -m a2s run "Objetivo A;Objetivo B" --parallel

# Panel de control web en vivo (SSE)
python -m a2s dashboard --port 8000

# Auto-existencia: el agente se relanza hasta cumplir el objetivo
python -m a2s supervise "tu objetivo" --attempts 5

# Réplicas autónomas en procesos paralelos (un worker por objetivo)
python -m a2s swarm "Objetivo A;Objetivo B" --workers 2

# Planificación especulativa: N planes candidatos puntuados por la red
python -m a2s run "tu objetivo" --speculative 3

# Hardening: verificación criptográfica (cadena de custodia + firmas HMAC)
python -m a2s verify --workspace workspace

# Dashboard con autenticación (token con expiración)
python -m a2s token --workspace workspace --hours 2
python -m a2s dashboard --auth --port 8000

# Neuroevolución de la red de gobernanza desde los episodios
python -m a2s evolve --workspace workspace --generations 5

# LiveCD: un solo archivo ejecutable (~490 KB), workspace en RAM
python -m a2s build-live --output dist/a2s.pyz
python3 dist/a2s.pyz run "tu objetivo" --ram

# Restricción de red: solo hosts permitidos
python -m a2s run "tu objetivo" --allow-host api.example.com

# Diagnóstico del entorno
python -m a2s doctor

# Pool SORL: orquesta tus recursos legítimos (claves propias + Ollama local)
python -m a2s pool-status && python -m a2s run "tu objetivo" --provider pool

# Mapa de reinterpretación operativa de la directiva
python -m a2s map
```

### LLM externo (opcional)

Por defecto opera el **núcleo heurístico determinista** (sin red, sin claves).
Para razonamiento vía API externa compatible con OpenAI:

```bash
export OPENAI_API_KEY=sk-...
export A2S_LLM_BASE_URL=https://api.openai.com/v1   # opcional (otros endpoints compatibles)
export A2S_LLM_MODEL=gpt-4o-mini                      # opcional
python -m a2s run "tu objetivo" --provider openai
```

Si la API falla, el loop **degrada automáticamente** al núcleo heurístico y
continúa persiguiendo el objetivo.

### Pool SORL — orquestación de recursos legítimos (v1.4)

El **S**istema de **O**rquestación de **R**ecursos **L**egítimos agrega todos
los motores de razonamiento a los que *tienes derecho de uso* detrás de un
único proveedor. La capacidad agregada del pool reemplaza a cualquier API
individual; los límites de cada nodo se gestionan, no se evaden.

```bash
# Autodescubrimiento: usa las claves que ya tengas en el entorno
export GROQ_API_KEY=...          # y/o GEMINI_API_KEY, GITHUB_TOKEN,
export OPENROUTER_API_KEY=...    # OPENAI_API_KEY… (+ Ollama local si corre)
python -m a2s pool-status        # qué ve el pool, cuotas y salud
python -m a2s pool-check         # 1 petición mínima por endpoint (valida claves)
python -m a2s run "tu objetivo" --provider pool
```

O declara el pool explícitamente en `workspace/.a2s/pool.json`
(plantilla en `examples/pool.example.json`, con expansión `${VAR}`):

```json
{"strategy": "multi_objective",
 "weights": {"speed": 0.25, "cost": 0.4, "reliability": 0.15,
             "capability": 0.15, "quota_risk": 0.05},
 "endpoints": [
   {"name": "groq", "base_url": "https://api.groq.com/openai/v1",
    "api_key": "${GROQ_API_KEY}", "model": "llama-3.1-8b-instant",
    "cost_tier": "free", "rpm": 25, "capabilities": ["fast", "general"]}
 ]}
```

Comportamiento ante saturación: un `429`/`503` pone el endpoint en
**cuarentena** durante el `Retry-After` indicado (o backoff exponencial) y la
tarea migra al siguiente mejor recurso. Las latencias y tasas de éxito se
persisten en `workspace/.a2s/pool/` y alimentan al scheduler en ejecuciones
futuras (`Ejecutar → Medir → Aprender → Optimizar`): si un proveedor satura
antes de lo declarado, el pool **aprende su rpm real** y se auto-limita desde
el arranque siguiente (con recuperación gradual), y los pesos del scheduler
se micro-ajustan de forma acotada salvo que el operador los fije.

**Aptitud medida por tipo de tarea**: para kinds con verificador objetivo
(`plan`, `evaluate`, `goal_check`, `reparam`) el pool mide si cada endpoint
produce el esquema JSON esperado, mezcla la medida con el prior declarado y
aplica una **puerta de incompetencia** (score < 0.35 con ≥4 muestras → ese
endpoint deja de recibir ESE tipo de tarea aunque sea gratis). Resultado: lo
que pueden hacer los gratis lo hacen los gratis; lo que solo sabe hacer el
endpoint de pago se le paga a él — y solo por eso. Si todo el pool cae,
degrada al núcleo heurístico: el objetivo se persigue igualmente.

**Prueba todo sin claves**: `examples/mock_llm_server.py` simula tres
proveedores OpenAI-compatibles (gratis-rápido con cuota estrecha, gratis-medio
y pago) con 429+`Retry-After` reales; `examples/sorl_demo.py` +
`examples/pool.mock.json` muestran el reparto, el failover, el DAG y la
convergencia del rpm aprendido (3 ejecuciones: 429s → aprende → 0 429s).

Para cargas masivas, el pool expone ejecución distribuida legítima:

```python
from a2s.provider_pool import ProviderPool
pool = ProviderPool([...])                       # o build_pool_provider()
res = pool.fanout(["resume el doc 1", "resume el doc 2", ...])   # map paralelo
dag = pool.execute_dag([                                          # grafo con deps
    {"id": "a", "prompt": "extraer entidades del corpus"},
    {"id": "b", "prompt": "agrupar por temática", "depends_on": ["a"]},
], aggregate=lambda r: r["results"]["b"])
```

**Frontera de diseño (no configurable):** el pool solo contiene recursos del
propio operador. No descubre ni sondea endpoints de terceros, no rota IPs ni
falsea cabeceras, y respeta los límites de cada proveedor — la "agregación"
es de recursos autorizados, no ajenos.

### Opciones principales

```text
--workspace DIR      espacio de trabajo (default: workspace/)
--max-iterations N   iteraciones por rebanada de presupuesto (se renueva al replanificar)
--max-rounds N       rondas de replanificación fractal
--max-time N         límite duro de tiempo real en segundos (seguridad)
--report ARCHIVO     guarda el informe de ejecución (Markdown + JSON)
--resume             reanuda sobre el estado persistido
--unsafe             amplía la lista blanca de shell (bajo tu responsabilidad)
--no-network/--no-shell  desactiva familias de herramientas
```

---

## Arquitectura

```text
a2s/
├── cli.py          interfaz de comandos (run/demo/dashboard/supervise/swarm…)
├── loop.py         motor: bucle principal, escalera de recuperación,
│                   división fractal, sub-agentes paralelos, cierre forense
├── planner.py      descomposición fractal, detección de estancamiento,
│                   metaprendizaje (estrategias con win-rate),
│                   planificación especulativa
├── providers.py    núcleo heurístico determinista + LLM vía API externa
├── neural.py       red de gobernanza: MLP entrenado en línea (v1.1)
├── consensus.py    consenso de verificación del objetivo (v1.1)
├── neuroevolve.py  neuroevolución: población con mutación de pesos/topología (v1.2)
├── sandbox.py      ejecución aislada por capas: nsjail > bwrap > rlimits (v1.2)
├── signing.py      firma HMAC-SHA256 de resultados y artefactos (v1.2)
├── auth.py         tokens JWT-HS256 con expiración para el dashboard (v1.2)
├── plugin_loader.py  plugins bajo demanda con verificación de hash (v1.2)
├── plugins/        forensics_extra (magia/strings/EXIF/PDF), crypto_tools,
│                   forensic_tools (puente Sleuth Kit/Volatility/bulk_extractor),
│                   repo_audit (escáner defensivo de repos/plugins)
├── tools.py        registro de herramientas + mini-shell seguro evolucionado
│                   (pipes, redirección, $VAR, globs, $(), lista blanca)
│                   + modelo de permisos
├── memory.py       memoria jerárquica persistente: working state, episódica,
│                   artefactos, heurísticas (strategies.json)
├── ledger.py       bitácora forense append-only con hash chain SHA-256
├── goals.py        biblioteca de objetivos con verificadores (misión demo)
├── models.py       tipos de datos (Step, Observation, Evaluation, RunReport…)
├── report.py       informes de ejecución (texto/Markdown/JSON)
├── dashboard.py    panel web en vivo (SSE, sin dependencias)
└── directiva.py    mapa de reinterpretación operativa
```

### Ciclo de un paso (escalera de recuperación)

```
intento 1  → misma acción (fallos transitorios)
intento 2  → reparametrización (variar parámetros)
intento 3  → cambio de herramienta equivalente
intento 4  → DIVISIÓN FRACTAL: el paso se convierte en sub-pasos más simples
fallo 4+   → evento de estancamiento → cambio global de estrategia
             (reparametrizar / dividir / fuente alternativa / verificar y corregir)
```

La división es inteligente: un paso de escritura que falla por contenido
incompleto se divide en *(1) recopilar datos reales del entorno* y
*(2) componer el documento con esos datos* — el verificador de paso decide si
cada sub-paso logró su criterio. Los pasos bloqueados se **re-descomponen** en
sub-objetivos con su propio plan, hasta una profundidad fractal máxima (3),
momento en que quedan registrados en el informe con su plan de reanudación.

### Verificación de objetivo

El loop no se fía de sí mismo: tras cada ronda consulta el **verificador de
objetivo** (callable por misión; si no hay, el proveedor de razonamiento).
Solo declara éxito con verificación positiva. La misión demo verifica secciones
del informe, hashes SHA-256 reales y ausencia de marcadores de posición.

### Cadena de custodia

Cada episodio (paso, observación, evaluación), estancamiento, artefacto y
cierre se añade a `workspace/.a2s/ledger.jsonl`, donde cada entrada encadena el
hash SHA-256 de la anterior. Cualquier alteración rompe la cadena y
`python -m a2s doctor` la detecta. El informe final lista los artefactos
nuevos con su hash.

---

## Misión demo (lo que verás)

`python -m a2s demo` siembra evidencias de ejemplo y pide un informe forense
real. El primer enfoque escribe el informe **con marcadores de posición**
(diseñado a propósito), así que:

1. `redactar_informe` falla 4 veces ante el verificador de paso;
2. se dispara el evento de **estancamiento** y cambia la estrategia;
3. el paso se **divide** en recopilar datos reales + componer el documento;
4. el verificador de objetivo confirma: informe completo con hashes reales.

Resultado: `workspace/informe_forense.md` (artefacto), `workspace/informe_a2s.md`
(informe de ejecución) y `.a2s/ledger.jsonl` (cadena de custodia).

---

## Pruebas

```bash
python -m unittest discover -s tests -v
```

63 pruebas: hash chain y detección de manipulación/truncación, permisos,
proveedores, escalera de recuperación, división fractal, misión demo completa,
red de gobernanza, consenso, memoria persistente, shell evolucionado, sandbox
(red/memoria/timeout), firmas HMAC, tokens con expiración, plugins (activación
y herramientas), zipapp LiveCD, puente forense (lista blanca, confinamiento)
y auditoría defensiva de repositorios.

---

## Alcance ético (léelo)

A²S es un framework de **automatización y auto-optimización de trabajo
propio**: persigue objetivos verificables, aprende de sus fallos y no se rinde.
No es —y no será— una herramienta para atacar sistemas de terceros. Las
capacidades de "bypass/evasión" se implementan como superación de fallos y
bloqueos lógicos del propio proceso, y las de "forense" como análisis de
artefactos propios con cadena de custodia. Las acciones con propósito de
ataque son rechazadas por el modelo de permisos y quedan registradas en el
ledger.

## Auditoría honesta de límites

Lee **[`LIMITACIONES.md`](LIMITACIONES.md)** antes de confiar en los resultados:
lista todo lo que el sistema NO puede hacer, los errores conocidos (con
severidad y estado), las capacidades a medias, la verdad sobre el modelo de
seguridad (no es un sandbox) y un playbook para obtener beneficio real.
