# A²S — Auditoría honesta: límites, errores, capacidades a medias y mejoras

> Documento de transparencia técnica. Aquí no hay maquillaje: esto es lo que
> el sistema **no puede hacer**, lo que hace **a medias**, los **errores que
> tiene**, y cómo usarlo para **obtener beneficio real** sin engañarte.
> Actualizado a v1.1.1.

---

## 1. Lo que NO puede hacer (sin maquillaje)

### 1.1. Prohibido por diseño — no va a cambiar

Ataques a terceros: exfiltración de credenciales, malware, ransomware,
backdoors en sistemas ajenos, evasión de controles de seguridad de terceros,
escalada de privilegios en sistemas ajenos, DDoS, phishing, suplantación,
minería, "disolución de límites propio/ajeno". Redefinir palabras no los
vuelve legítimos: es una decisión de diseño permanente, no una limitación
técnica superable.

### 1.2. Físicamente imposible

- **Manipulación temporal** y "recuperación cuántica de datos borrados": no
  existen. Lo real es lo implementado: reanudación desde estado persistido y
  reconstrucción a partir de la evidencia que queda (git, ledger, archivos).
  Si los datos no están en ninguna copia, no se recuperan.
- **Generación real de recursos**: no crea tokens, cómputo ni acceso. Los
  presupuestos los define el operador; el sistema solo los renueva
  replanificando.

### 1.3. Funcionalmente ausente (prometido en la directiva, no implementado)

| Cosa | Estado real |
|---|---|
| Runtime Temporal Cloud + LangGraph/OpenAI Agents SDK | **No implementado.** Solo hay una interfaz (`BaseProvider`) por la que se *podría* conectar. Hoy corre como proceso local. |
| "Operar solo vía APIs externas sin recursos locales" | **Falso.** Las herramientas (shell, python, archivos) y el núcleo heurístico corren **localmente**. Solo el LLM es una API externa. |
| Razonamiento real sin LLM | El núcleo heurístico son **plantillas + reglas deterministas**. No entiende lenguaje; empareja palabras clave. |
| Persistencia distribuida / almacenamiento de objetos externo | **No.** Todo es local: SQLite + JSONL en `workspace/.a2s`. |
| Autonomía total / auto-despliegue en la nube | **No.** Sin que alguien lo ejecute (`run`, `supervise`, `swarm`), no corre. No hay cron, ni workers cloud, ni auto-provisionamiento. |
| Recuperación forense de datos borrados | **No.** Solo análisis de lo que existe (hashes, metadatos, logs). |
| Conciencia, "existencia independiente", consenso cuántico | Metáforas. Lo real: proceso con checkpoint y reanudación. |

---

## 2. Errores y bugs conocidos

Estado: ✅ corregido · 🟡 mitigado · 🔴 pendiente

| # | Problema | Severidad | Estado |
|---|---|---|---|
| 1 | **El ledger no detectaba truncación**: borrar las últimas entradas pasaba `verify()` como "íntegra" (solo se detectaba modificación). | Alta (forense) | ✅ corregido en v1.1.1 (recuento cruzado con el índice SQLite) |
| 2 | **Append O(n²)**: cada entrada releía el archivo completo para obtener el último hash. 800 appends tardaban 2.3s y crecía. | Media (rendimiento) | ✅ corregido (caché del último hash; 3.6× más rápido) |
| 3 | **`run_fractal` podía exceder el plazo del padre**: el padre esperaba por todos los hijos sin mirar su propio límite de tiempo. | Media | ✅ corregido (el padre cancela hijos al llegar su deadline) |
| 4 | **Aprendizaje perdido si el proceso muere a mitad**: `strategies.json` y `governance.json` solo se guardaban al final. | Media | ✅ corregido (guardado en cada episodio / cada 10 entrenamientos) |
| 5 | **Dashboard sin protección**: escuchaba en `0.0.0.0` sin autenticación; cualquiera con acceso al puerto podía lanzar misiones que ejecutan código en el host. | **Crítica** (RCE) | ✅ mitigado: por defecto escucha solo en `127.0.0.1`; `--public` expone con advertencia explícita. Sigue sin autenticación: no expongas en redes no confiables. |
| 6 | **Evaluador heurístico con falsos positivos**: para el núcleo heurístico, una salida no vacía y sin palabras de error = "éxito" (score 0.8). Un paso puede "pasar" sin haber hecho lo correcto. | Alta (calidad) | 🔴 pendiente: exigir cumplimiento de `success_criteria`, no solo salida no vacía |
| 7 | **`goal_check` sin verificador de misión es débil**: "¿objetivo cumplido?" ≈ "¿hay salida sin traceback?". Falsos positivos casi seguros en objetivos vagos. | **Crítica** (veracidad) | 🟡 mitigado por diseño: usar SIEMPRE un verificador de misión (la demo lo tiene). Sin verificador, el resultado "✔ CUMPLIDO" es poco fiable. |
| 8 | **Mini-shell no es POSIX**: no soporta `&&`, `||`, heredocs (`<<`), `>>`, `$(( ))`, asignaciones, ni `$()` con paréntesis anidados. Algunas construcciones fallan o se interpretan mal. | Media | 🔴 pendiente (documentar y/o ampliar gramática) |
| 9 | **Búsqueda web por scraping**: `web_search` parsea el HTML de DuckDuckGo; si cambian el layout, deja de funcionar; puede ser bloqueada por IP de datacenter; sin paginación ni profundidad. | Media | 🔴 pendiente (aceptar API key opcional) |
| 10 | **Extracción de JSON del LLM por regex**: el LLM no tiene salida estructurada garantizada; si devuelve prosa con JSON roto, se degrada al heurístico silenciosamente. | Media | 🟡 degradación controlada; pendiente: function-calling/JSON mode |
| 11 | **Sin retries/backoff en llamadas al LLM**: un error transitorio degrada al heurístico en vez de reintentar. | Baja | 🔴 pendiente |
| 12 | **Overshoot del plazo dentro de un paso**: el deadline se comprueba *entre* pasos; un comando puede correr hasta 60s después del límite. | Baja | 🟡 aceptado (tiempos de subproceso acotados) |
| 13 | **Windows no soportado**: los comandos (`find`, `sha256sum`, `stat`, `git`), `python3` y las pruebas asumen POSIX. En Windows la mayoría de misiones fallarán. | Media | 🔴 pendiente (capa de compatibilidad o PowerShell) |
| 14 | **`supervise` no reanuda el plan**: relanza el objetivo completo desde cero (conservando workspace/memoria), con intentos finitos. No restaura el plan en vuelo. | Baja | 🔴 pendiente (checkpoint de plan) |
| 15 | **`swarm` sin coordinación**: las réplicas no comparten memoria ni resultados entre sí; el "consenso distribuido" entre nodos no existe. | Baja | 🔴 pendiente |
| 16 | **`--resume` es cosmético**: verifica el ledger y replanifica desde cero; no restaura pasos pendientes. | Baja | 🔴 pendiente |
| 17 | **Lecturas concurrentes del ledger** (`verify`/`query` durante appends de hilos) pueden leer una línea a medio escribir y fallar el parseo. | Baja | 🟡 los appends están serializados; `verify` no usa el lock |
| 18 | **El filtro de `python_exec` es eludible trivialmente** (base64, ofuscación). Ver §5. | — | Por diseño, ver §5 |

---

## 3. Capacidades a medias (lo prometido vs lo real)

| Capacidad | Lo que hace de verdad |
|---|---|
| **Metaprendizaje / "auto-modificación"** | Ajusta estrategias, parámetros y planes. **No reescribe su código fuente.** El win-rate de estrategias es la señal principal. |
| **Red de gobernanza neuronal** | MLP 12-8-1 entrenado en línea con SGD. Aprende correlaciones **triviales** (tool usada, longitud de salida, errores). No tiene memoria secuencial ni comprensión. Sus predicciones rondan 0.5-0.7: es una señal débil, no un cerebro. |
| **Consenso de verificación** | Con verificador de misión → el verificador decide (bien). **Sin verificador** → proveedor+progreso suelen votar "sí" tras cualquier paso: mayoría débil, falsos positivos probables. |
| **Planificación especulativa** | Solo si `--speculative N` Y la red ya fue entrenada. Las características del plan son crudas (nº de pasos, tools). |
| **Memoria evolutiva persistente** | JSON local (`strategies.json`, `governance.json`). Sin versionado, sin merge multi-nodo, sin sincronización entre réplicas. |
| **Simulación paralela** | Sub-agentes en **hilos** (GIL limita código Python intensivo) o procesos (`swarm`) **sin memoria compartida**. No es un clúster. |
| **Forense** | Excelente para: inventario, metadatos, hashes, cadena de custodia, correlación de logs propios. **No** recupera datos borrados sin copias. |
| **"Contexto ilimitado"** | Resúmenes truncados (240-3000 chars) + últimos N episodios. Sin embeddings, sin recuperación semántica de memoria vieja. |
| **Auto-existencia** (`supervise`/`swarm`) | Solo dentro del host que los lanza. Muere con el host. |

---

## 4. Límites numéricos concretos (defaults, todos configurables)

| Parámetro | Valor | Dónde se cambia |
|---|---|---|
| Iteraciones por rebanada de presupuesto | 60 | `--max-iterations` |
| Rondas de replanificación | 6 | `--max-rounds` |
| Límite duro de tiempo real | 900 s | `--max-time` |
| Profundidad fractal máxima | 3 | `--max-depth` |
| Sub-agentes en paralelo | 4 | `Config.max_subagents` |
| Shell por comando | 60 s | código (`tools.py`) |
| Fetch HTTP | 30 s · 200 KB | código |
| LLM por llamada | 120 s · 1500 tokens | código |
| Historial del panel | 400 eventos | código |
| SSE buffer por cliente | 500 eventos | código |

**Consecuencia**: un objetivo irresoluble no corre "para siempre": termina en
el límite de tiempo con informe reanudable. Y "presupuesto acumulado
expansivo" es renunciable: el tope real siempre es `--max-time`.

---

## 5. Seguridad — la verdad completa

**El "modelo de permisos" es de convención, NO un sandbox.** Tres hechos:

1. **`python_exec` y `python3` en la lista blanca equivalen a ejecución
   arbitraria de código** en el host. El filtro por patrones de texto se
   elude con ofuscación trivial. Sirve para evitar usos *accidentales* de
   cadenas obvias, no para detener a nadie decidido.
2. **Las herramientas de red pueden exfiltrar** el contenido del workspace
   (y, vía shell/python, cualquier archivo legible por el usuario).
3. **`read_file`/`write_file`/`list_dir` están confinadas al workspace, pero
   `shell`/`python_exec` NO**: `cat /etc/passwd` está permitido.

Por lo tanto:

- Ejecuta misiones **propias** o en entornos que controles.
- Si procesas objetivos no confiables, hazlo en **VM/contenedor desechable**.
- `--unsafe` = tu responsabilidad total sobre el host.
- `--public` en el dashboard = ejecución remota de misiones sin autenticación.
- La bitácora forense detecta manipulación y truncación del JSONL, pero un
  atacante con acceso de escritura al directorio `.a2s` puede regenerar un
  ledger falso coherente. La cadena de custodia protege contra alteraciones
  *posteriores*, no contra un atacante con control total del medio.

---

## 6. Cómo obtener beneficio real (playbook del operador)

1. **Define SIEMPRE un verificador de objetivo** (criterios de aceptación).
   Es la única garantía real de que "✔ CUMPLIDO" significa algo. Sin
   verificador, trátalo como "el proceso terminó", no como "el objetivo se
   logró". (Ejemplo completo: `a2s/goals.py`.)
2. **Usa el LLM externo** (`OPENAI_API_KEY`) para objetivos vagos o abiertos;
   usa el **núcleo heurístico** para operaciones acotadas y repetibles
   (informes forenses, recolección de hashes, automatización de workspace).
3. **Un workspace por misión**; audita con `a2s doctor` (verifica la cadena
   de custodia) y revisa `workspace/.a2s/ledger.jsonl` como evidencia.
4. **Resiliencia**: `a2s supervise` para reintentos automáticos hasta cumplir;
   `a2s swarm` para tareas independientes en paralelo.
5. **No confíes en el estado "success" de un paso**: revisa el artefacto
   final (el informe, el archivo). El verificador de misión cierra el círculo.
6. **Integra como biblioteca**: `run_goal(goal, config, goal_verifier=...)`
   desde tu propio código, con `on_event` para telemetría propia.
7. **Revisa el ledger como evidencia forense**, no como prueba absoluta:
   con control total del medio, hasta una cadena de hashes se puede regenerar
   (guardar copias del ledger fuera del workspace si necesitas no-repudio).

---

## 7. Roadmap priorizado de mejoras

**P0 — veracidad y seguridad**
- Evaluador que exija cumplimiento de `success_criteria` (no "salida no vacía").
- Autenticación por token en el dashboard público + botón de cancelar misión.
- `goal_check` heurístico basado en artefactos (existe el archivo / contiene X).
- Validación de parámetros de herramienta antes de invocar (evitar intentos
  muertos con herramientas inexistentes).

**P1 — robustez**
- Retries con backoff en el LLM; JSON mode / function-calling si el endpoint lo soporta.
- Checkpoint real del plan (reanudar pasos pendientes, no replanificar).
- Compatibilidad Windows (fallback PowerShell / comandos portables).
- Compartir aprendizajes entre réplicas del `swarm` (merge de strategies).
- CI (GitHub Actions) ejecutando los tests en cada push.
- Per-timeout por paso y límite de CPU por misión.

**P2 — alcance**
- Persistencia externa opcional (S3-compatible / SQLite sobre HTTP) vía API.
- Adaptadores LangGraph / OpenAI Agents SDK (implementando `BaseProvider`).
- Memoria semántica (embeddings) en vez de solo últimos N episodios.
- Búsqueda web con API key oficial (sin scraping) + paginación.
- Métricas y alertas (Prometheus/JSON), interfaz en inglés, empaquetado PyPI.

---

## 8. Qué está probado y qué no

**Probado (30 tests, `python -m unittest discover -s tests`):**
hash chain + detección de modificación/truncación; modelo de permisos básico;
proveedores (heurístico y degradación del LLM); escalera de recuperación;
división fractal; misión demo completa; red de gobernanza (aprendizaje de
señal trivial + persistencia); consenso; memoria persistente; shell
evolucionado ($VAR, globs, $()).

**NO probado:**
- Con un LLM real (no hay tests de integración con API).
- Con red real (búsqueda/fetch nunca se ejercitan en CI).
- En Windows, macOS, ni con Python 3.9/3.12 distintos del 3.11 actual.
- Bajo carga larga (soak test), fuzzing del mini-shell, ni ataques al modelo
  de permisos (los test solo cubren el caso obvio).
- La UI del dashboard (sin tests de interfaz).
