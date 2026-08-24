# A²S — Auditoría honesta: límites, errores, capacidades a medias y mejoras

> Documento de transparencia técnica. Aquí no hay maquillaje: esto es lo que
> el sistema **no puede hacer**, lo que hace **a medias**, los **errores que
> tiene**, y cómo usarlo para **obtener beneficio real** sin engañarte.
> Actualizado a v1.15.0 (Protocolo Adaptativo Aegis: clasificación y composición
> omnimodal auditable, sin promesas de omnipotencia ni razonamiento privado).

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
| 5 | **Dashboard sin protección**: escuchaba en `0.0.0.0` sin autenticación; cualquiera con acceso al puerto podía lanzar misiones que ejecutan código en el host. | **Crítica** (RCE) | ✅ corregido en v1.2.0: localhost por defecto, `--public` con advertencia y **`--auth` con tokens HMAC con expiración** (login por cookie HttpOnly) |
| 6 | **`python_exec` sin contención de recursos** | **Crítica** | ✅ corregido en v1.2.0: **sandbox por capas** (nsjail > bwrap > rlimits), por defecto activo. El nivel rlimits contiene RAM/CPU/procesos/fds y bloquea red por shim — **pero no aísla filesystem** (ver §5). |
| 7 | **Verificación sin firma**: los resultados podían alterarse sin dejar rastro criptográfico. | Alta (forense) | ✅ corregido en v1.2.0: **firma HMAC-SHA256** de informe y artefactos con secreto del workspace; `a2s verify` comprueba todo. Límite: el secreto es local (ver §5). |
| 8 | **Evaluador heurístico con falsos positivos**: para el núcleo heurístico, una salida no vacía y sin palabras de error = "éxito" (score 0.8). Un paso puede "pasar" sin haber hecho lo correcto. | Alta (calidad) | 🔴 pendiente: exigir cumplimiento de `success_criteria`, no solo salida no vacía |
| 9 | **`goal_check` sin verificador de misión es débil**: "¿objetivo cumplido?" ≈ "¿hay salida sin traceback?". Falsos positivos casi seguros en objetivos vagos. | **Crítica** (veracidad) | 🟡 mitigado por diseño: usar SIEMPRE un verificador de misión (la demo lo tiene). Sin verificador, el resultado "✔ CUMPLIDO" es poco fiable. |
| 10 | **Mini-shell no es POSIX**: no soporta `&&`, `||`, heredocs (`<<`), `>>`, `$(( ))`, asignaciones, ni `$()` con paréntesis anidados. | Media | 🔴 pendiente (documentar y/o ampliar gramática) |
| 11 | **Búsqueda web por scraping**: `web_search` parsea el HTML de DuckDuckGo; si cambian el layout, deja de funcionar; puede ser bloqueada por IP de datacenter. | Media | 🔴 pendiente (aceptar API key opcional) |
| 12 | **Extracción de JSON del LLM por regex**: el LLM no tiene salida estructurada garantizada. | Media | 🟡 degradación controlada; pendiente: function-calling/JSON mode |
| 13 | **Sin retries/backoff en llamadas al LLM**. | Baja | 🔴 pendiente |
| 14 | **Overshoot del plazo dentro de un paso**: el deadline se comprueba *entre* pasos. | Baja | 🟡 aceptado (tiempos de subproceso acotados) |
| 15 | **Windows**: el núcleo heurístico ya es portable (recopilación stdlib vía `python_exec`, UTF-8 forzado, tests con skip/simulación), pero la herramienta `shell` sigue requiriendo un shell POSIX (Git-Bash/MSYS2/WSL) y las máquinas FSM de los ejemplos usan comandos POSIX. | Media | 🟡 mitigado en v1.12: el shell POSIX se **verifica con sonda real** antes de usarlo (un WSL sin distribución ya no envenena todos los comandos con `exit=1`) y toda salida de subproceso se decodifica UTF-8 con reemplazo (los mensajes localizados cp1252/cp850 ya no lanzan `UnicodeDecodeError`). Sin bash funcional: error claro y el agente continúa por `python_exec`. Pendiente: fallback PowerShell nativo. |
| 16 | **`supervise` no reanuda el plan**; **`swarm` sin coordinación entre réplicas**; **`--resume` cosmético**. | Baja | 🔴 pendiente (checkpoint de plan, merge de aprendizajes) |
| 17 | **Lecturas concurrentes del ledger** durante appends pueden leer una línea a medio escribir. | Baja | 🟡 los appends están serializados; `verify` no usa el lock |
| 18 | **El filtro de texto de `python_exec` es eludible** (base64, ofuscación). | — | Por diseño: ahora el sandbox aporta la contención real; el filtro sigue siendo cosmético |
| 19 | **Egress por iptables no auto-aplicado**: requiere root y administración de firewall; el control de red real hoy es la **lista blanca de hosts** (`--allow-host`) + `--no-network`. | Media | 🟡 lista blanca implementada y testeada; iptables queda como tarea del operador |
| 20 | **Neuroevolución con buffer pequeño es ruido** (mínimo 8 episodios; resultados útiles desde cientos). | Baja | 🟡 documentado; `a2s evolve` avisa si el buffer es insuficiente |
| 21 | **Autonomía nueva (v1.12–1.13)**: OmniRoute se liga y sondea SOLO en loopback (si cambias el puerto, usa `A2S_OMNIROUTE_URL`); A²S ejecuta el bundle `dist` sin `src`/tsx y recupera su sidecar, pero no puede garantizar la disponibilidad de los upstreams keyless externos. El crecimiento autónomo depende de la cuota de GitHub y estudia TEXTO público sin ejecutarlo; el guardián `update --watch` nunca fuerza un árbol sucio. | Baja | 🟡 aceptado: fallback local sin pedir proveedor; salud y crecimiento observables (`a2s doctor`, `/api/growth`, UI y logs) y desconectables (`A2S_AUTO_LEARN=0`, `A2S_OMNIROUTE=off`, Ctrl+C). El sidecar administrado no exige login; `--auth` sigue disponible al exponer A²S. |
| 22 | **Investigación/libros (v1.14)**: estrellas, citas y actualidad son señales, no prueba de verdad; OpenAlex/arXiv o GitHub pueden estar inaccesibles o devolver metadatos incompletos. Un PDF público puede conservar restricciones propias aunque viva en un repo abierto. El PDF puro-stdlib prioriza portabilidad, no maquetación editorial avanzada. Un `quality_score=100` mide gates estructurales, no perfección factual o literaria. | Media | 🟡 mitigado: manifiesto fechado, candidatos separados de fuentes OA, descarga solo HTTPS público + PDF válido ≤20 MB, citas validadas, `publication_ready`, errores y limitaciones explícitos. Revisión humana obligatoria antes de publicar. |
| 23 | **Protocolo adaptativo (v1.15)**: la clasificación se basa en palabras y señales deterministas; puede omitir una capacidad útil o activar una innecesaria. Declarar «investigación» no garantiza que la red o una fuente respondan. El fallback heurístico conserva estructura y ejecución acotada, pero no obtiene comprensión general equivalente a un LLM. | Media | 🟡 mitigado: perfil visible/inspeccionable con `a2s protocol`, criterios y supuestos en ledger, respuesta con límites, investigación actual convertida en misión y tests de selección negativa. El operador puede reformular o especificar el criterio de éxito. |

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

## 5. Seguridad — la verdad completa (actualizada v1.2.0)

**El hardening real implementado:**

1. **Sandbox por capas** (`a2s/sandbox.py`): nsjail (nivel 3, requiere chroot
   preparado) → bwrap (nivel 2, sin red ni filesystem) → **rlimits (nivel 1,
   siempre disponible)**: límites duros de RAM/CPU/procesos/fds + Python `-I`
   + bloqueo de red por shim. `a2s doctor` informa el nivel activo.
2. **Firma criptográfica** (`a2s/signing.py`): HMAC-SHA256 del informe y de
   cada artefacto con un secreto por workspace (0600); `a2s verify` valida
   cadena + firmas.
3. **Autenticación** (`a2s/auth.py`): tokens estilo JWT-HS256 con expiración;
   `a2s token` los emite; el dashboard con `--auth` los exige (login por
   cookie HttpOnly + SameSite=Strict).
4. **Control de egress aplicativo**: `--no-network` + lista blanca de hosts
   (`--allow-host`), aplicada en `fetch_url`/`web_search`.

**Lo que SIGUE siendo verdad (residuales honestos):**

1. **El nivel rlimits NO es una jaula**: no aísla el filesystem (el código
   puede leer `/etc/passwd`) ni impide elusión deliberada vía ctypes/syscalls
   directos o recarga del módulo socket. Nivel 2 (bwrap) sí aísla; nivel 3
   (nsjail) es el fuerte, pero requiere configuración con root que el
   programa no hace por ti. Para código hostil: VM/contenedor desechable.
2. **`shell` no pasa por el sandbox**: sigue siendo la mini-shell con lista
   blanca; `python_exec` sí está sandboxeado por defecto (`--no-sandbox` lo
   desactiva, no recomendado).
3. **El secreto HMAC es local**: quien tenga acceso de escritura al workspace
   puede re-firmar. Para no-repudio real, copia `.a2s/secret` a un sistema
   separado. La firma certifica "no alterado después de firmar", NO que la
   tarea se hizo bien (eso es el verificador de misión).
4. **Los tokens sin TLS viajan en claro** en redes no confiables; la
   expiración mitiga el robo, no lo elimina.
5. **El filtro de texto de `python_exec` sigue siendo eludible**: es
   convención, no seguridad; la contención real la aporta el sandbox.
6. **Sin registro remoto de plugins a propósito**: descargar y ejecutar
   código de un URL en caliente es RCE con pasos extra; los plugins son
   código local auditable, con verificación de hash opcional (`plugin.json`).
7. La cadena de custodia protege contra alteración posterior; no contra un
   atacante con control total del medio (puede regenerar un ledger coherente
   y, si el secreto está local, re-firmarlo).

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

**Hecho en v1.2.0 (Fase 0-1 del plan de hardening/fusión):**
- ✅ Sandbox por capas (nsjail/bwrap/rlimits) para `python_exec`
- ✅ Firma criptográfica HMAC de informe y artefactos (`a2s verify`)
- ✅ Dashboard con autenticación por tokens con expiración
- ✅ Lista blanca de hosts para egress (`--allow-host`)
- ✅ Arquitectura de plugins bajo demanda (loader + 2 plugins reales)
- ✅ Neuroevolución básica (pesos + topología, exporta a governance.json)
- ✅ LiveCD (zipapp de ~490 KB) + workspace en RAM (`--ram`)

**P0 — veracidad (pendiente)**
- Evaluador que exija cumplimiento de `success_criteria` (no "salida no vacía").
- Botón de cancelar misión en el dashboard.
- `goal_check` heurístico basado en artefactos (existe el archivo / contiene X).
- Validación de parámetros de herramienta antes de invocar.

**P1 — robustez**
- Retries con backoff en el LLM; JSON mode / function-calling si el endpoint lo soporta.
- Checkpoint real del plan (reanudar pasos pendientes, no replanificar).
- Compatibilidad Windows: fallback PowerShell nativo para la mini-shell (lo
  portable — recopilación stdlib y UTF-8 — ya está en v1.11).
- Compartir aprendizajes entre réplicas del `swarm` (merge de strategies).
- CI (GitHub Actions) ejecutando los tests en cada push.
- Sandbox para `shell` además de `python_exec`; nivel nsjail con chroot preconfigurado.

**P2 — alcance**
- Persistencia externa opcional (S3-compatible / SQLite sobre HTTP) vía API.
- Adaptadores LangGraph / OpenAI Agents SDK (implementando `BaseProvider`).
- Memoria semántica (embeddings) en vez de solo últimos N episodios.
- Búsqueda web con API key oficial (sin scraping) + paginación.
- Métricas y alertas (Prometheus/JSON), interfaz en inglés, empaquetado PyPI.

---

## 8. Qué está probado y qué no

**Probado (274 tests, `python -m unittest discover -s tests`):**
hash chain + detección de modificación/truncación; modelo de permisos básico;
clasificación adaptativa y selección negativa de capacidades; contrato de
respuesta sin bloques privados; trazabilidad del perfil en misión; proveedores
(heurístico y degradación del LLM); escalera de recuperación;
división fractal; misión demo completa; red de gobernanza (aprendizaje de
señal trivial + persistencia); consenso; memoria persistente; shell
evolucionado ($VAR, globs, $()).

**NO probado:**
- Con un LLM real (no hay tests de integración con API).
- Con red real (búsqueda/fetch nunca se ejercitan en CI).
- En Windows físico la suite completa (se simula con `allow_shell=False` y el
  e2e npm corre en `windows-latest`); macOS; Python 3.9/3.12 distintos del
  3.11 actual (la matriz CI cubre 3.9/3.11/3.13 en Linux).
- Bajo carga larga (soak test), fuzzing del mini-shell, ni ataques al modelo
  de permisos (los test solo cubren el caso obvio).
- La UI del dashboard (sin tests de interfaz).

## 9. Clasificación de herramientas externas (53 repositorios de referencia)

Ante la lista de 53 repositorios propuestos para "integrar en el agente
supremo", la política es: **la mitad defensiva se integra (vía puente o como
inspiración); la mitad ofensiva no entra** — no por falta de técnica, sino
porque es malware u ofensa contra terceros. La lista blanca del puente
forense (`forensic_tools.py`) rechaza explícitamente cualquier binario
ofensivo aunque esté instalado en el mismo host.

| Categoría | Repositorios | Decisión |
|---|---|---|
| Forense de disco/imagen | Sleuth Kit, Autopsy, Recuperabit, Rifiuti2, Galleta, Emldump | ✅ Integrado vía puente (`forensic_cmd` invoca binarios del sistema); Autopsy solo como plataforma externa del operador |
| Forense de memoria | Volatility 3 / Volatility-MCP-Server, Rekall | ✅ Integrado vía puente (`volatility3`, `vol.py`) sobre volcados propios |
| Extracción masiva | bulk_extractor | ✅ Integrado vía puente (`bulk_extractor`) |
| Línea de tiempo | Plaso, Timesketch, Beagle, MISP | 🟡 Roadmap: plataformas pesadas, integración vía API externa (no empaquetadas) |
| Forense de navegadores/apps | Chromefreak, SkypeFreak, Dumpzilla | 🟡 Roadmap: plugins puente (análisis de artefactos propios) |
| Escáner defensivo de repos | repo-forensics | ✅ Implementado como plugin propio: `repo_audit` (patrones + hashes) |
| DFIR con veredicto firmado | VERDICT | ✅ Equivalente ya implementado: verificador de misión + firma HMAC (`a2s verify`) |
| OSINT | llm_osint, ai_osint | ✅ Equivalente: `web_search`/`fetch_url` con lista blanca de hosts |
| Agentes autónomos generales | Auto-GPT, BabyAGI, GPT-Engineer | ✅ Ya implementado en el propio loop (planificación fractal + escalera de recuperación) |
| ML pesado | TensorFlow, PyTorch, scikit-learn | 🟡 No integrados: el core es stdlib a propósito (LiveCD ~500 KB); compatibles como plugins locales del operador |
| Despliegue | Docker, Kubernetes, Ansible | 🟡 Herramientas del OPERADOR para desplegar A²S, no capacidades del agente |
| **Exfiltración/destrucción** | ai-forensics-data-exfiltration | ❌ No integrable: exfiltración de datos y destrucción de privacidad |
| **Agentes ofensivos autónomos** | PentAGI, Strix, CAI, CVE-Bench | ❌ No integrables: explotación autónoma de vulnerabilidades de terceros |
| **Post-explotación / credenciales** | Mimikatz, Empire, Cobalt Strike, PowerSploit, Metasploit, ExploitDB, BeEF | ❌ No integrables: malware y robo de credenciales |
| **Anti-forense / evasión** | awesome-anti-forensic (x2), HiddenVM, BleachBit, DBAN | ❌ No integrables como capacidades del agente. Excepción documentable: borrado seguro SOLO del workspace propio (higiene operativa), nunca de sistemas ajenos |
| **Anonimato encubierto** | Tor, I2P, Signal-Desktop | ❌ No integrables como canal de comunicación encubierta del agente |

Si el operador quiere usar las herramientas ofensivas **por su cuenta** en su
propio entorno autorizado (lab, red team contratado), puede hacerlo fuera de
A²S: el agente no las invoca, no las lista y el modelo de permisos rechaza
objetivos que lo pidan (quedan registrados en el ledger como denegados).

---

## 10. SORL — pool de recursos legítimos (v1.4): la verdad completa

`provider_pool.py` implementa el Sistema de Orquestación de Recursos
Legítimos. Transparencia total sobre lo que es y lo que no es:

### 10.1. Lo que NO es (por diseño, no va a cambiar)

- **No es un sistema para usar APIs ajenas sin permiso.** No descubre,
  clona, sondea ni consume endpoints de terceros encontrados en repos o en
  internet. El pool solo contiene: (a) endpoints declarados por el operador
  en `pool.json`, (b) endpoints cuyas **claves posee el operador** y están en
  su entorno (`GROQ_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`,
  `OPENROUTER_API_KEY`, `OPENAI_API_KEY`), y (c) Ollama local si corre en la
  propia máquina.
- **No evade rate limits.** No hay rotación de IPs, no se falsifican
  cabeceras (`X-Forwarded-For` u otras), no hay reintentos en caliente. Un
  `429`/`503` se interpreta como señal de estado: cuarentena durante
  `Retry-After` (o backoff exponencial 5s→300s) y migración de la carga a
  otro recurso **autorizado**. Redefinir palabras no convierte la evasión en
  "benchmarking": aquí no hay nada que redefinir.
- **No genera recursos.** Agregar 3 free tiers no crea cuota infinita: crea
  la suma de las cuotas que el operador legítimamente tiene, gestionada sin
  desperdiciarla. Si todo el pool se agota, **degrada al núcleo heurístico**
  (y espera, si `Retry-After` es razonable ≤45s).

### 10.2. Lo que SÍ es

| Componente | Qué hace de verdad |
|---|---|
| `TaskScheduler` | Elige endpoint por estrategia: `round_robin`, `cost_first`, `speed_first` o `multi_objective` (utilidad = velocidad + coste + fiabilidad + aptitud − riesgo de cuota; pesos configurables) |
| `RateWindow` | Ventana deslizante de rpm por endpoint: el pool **se auto-limita antes** de recibir un 429 |
| Failover | 429/503 → cuarentena + siguiente mejor endpoint; otros fallos → circuit breaker (3 fallos → abierto 30s, duplicando hasta 300s) |
| `Telemetry` | p50/p95, tasa de éxito, 429s, tokens y coste estimado por endpoint; JSONL + snapshot en `workspace/.a2s/pool/`; **se recarga al iniciar** (el scheduler aprende entre ejecuciones) |
| `fanout` / `execute_dag` | Map paralelo y DAG por olas topológicas (ThreadPool, stdlib) con failover por tarea y dependencias respetadas |
| Fallback | Endpoint `heuristic` siempre presente: el pool nunca devuelve "imposible" |

### 10.3. Límites y medias verdades conocidos

- Los **rpm por defecto** del autodescubrimiento (groq 25, gemini 10, github
  14, openrouter 15, openai 60) son estimaciones conservadoras de free tiers
  que **cambian sin avisar**; ajústalos en `pool.json` si tienes datos
  mejores (`a2s pool-status` muestra el uso real).
- El **aprendizaje entre ejecuciones** tiene dos niveles, ambos heurísticos y
  acotados (no reentrenamiento): (1) **rpm aprendido** — si un proveedor
  satura antes de lo declarado, el pool aprende el rpm real observado
  (80% de las peticiones en vuelo al recibir el 429) y se auto-limita en
  ejecuciones futuras, con recuperación gradual (+1 rpm tras ≥20 éxitos
  limpios); (2) **micro-ajuste de pesos** — muchas saturaciones suben
  `quota_risk` (máx 0.30) y bajan `cost` (mín 0.05); muchos errores suben
  `reliability`. Los pesos explícitos del operador bloquean el ajuste. La
  optimización completa de pesos (p. ej. por gradiente o bandits) NO está
  implementada.
- La **tasa de éxito excluye los 429s** (saturación ≠ fallo del endpoint; la
  saturación la gestionan cuarentena y riesgo de cuota). Métrica honesta:
  "¿funciona cuando estamos dentro de cuota?".
- La **aptitud por tipo de tarea se MIDE desde v1.4.2** — pero con una señal
  objetiva limitada: ¿produce JSON con el esquema esperado para ese kind
  (`plan`/`evaluate`/`goal_check`/`reparam`)? El score mezcla prior declarado
  + observado (3 pseudo-muestras) y por debajo de 0.35 (≥4 muestras) el
  endpoint queda excluido de ESE kind (puerta de incompetencia), aunque sea
  gratis. Lo que NO mide: calidad semántica — un plan sintácticamente válido
  pero estúpido puntúa 1.0; juzgarlo necesitaría otro modelo (circular y con
  coste). Kinds sin verificador objetivo (chat/fanout) → sigue el prior
  declarado.
- `execute_dag` falla honesto: si una tarea agota el pool, sus dependientes
  quedan `skipped` (no se inventan resultados) — distinto del loop principal,
  que reparametriza: el DAG es una API de herramienta, no el núcleo.
- **Prometheus/Grafana no integrados** (el core es stdlib a propósito):
  `a2s pool-status --json` da el mismo dato para graphite/grafana externos.
- `pool-check` hace **1 petición real** por endpoint: valida claves y mide
  latencia de tus propios recursos; no es un "escáner" de nada ajeno.
- **BOINC/cómputo voluntario y spot instances: NO implementados.** Sería la
  vía legítima para escalar más allá de las claves propias; queda en roadmap.

---

## 11. Ciclo de Enriquecimiento (v1.5): la verdad completa

`learner.py` implementa el "búscalo en GitHub hasta sentirte capaz". Así se
tradujo de forma verificable y qué no se maquilla:

| Pedido | Implementación real |
|---|---|
| "Buscar repositorios de GitHub" | API oficial de búsqueda (`/search/repositories`, `/repos/{}/readme`) con la clave del OPERADOR (`GITHUB_TOKEN`/`GH_TOKEN`), ventanas de cuota auto-impuestas por debajo del límite real (20/min auth vs 30; 8/min sin token vs 10) y `Retry-After` respetado con espera acotada y UN reintento |
| "Enriquecerse" | Fichas de conocimiento (fuente + licencia + resumen + receta + extracto) persistidas en `.a2s/knowledge/` y reinyectadas en la planificación; resumen vía pool SORL (fanout) o extractivo stdlib sin LLM |
| "Hasta sentirse capaz" | **El criterio es el verificador del objetivo, no una sensación**: `capaz` ⇔ misión verificada. La "confianza" se reporta como evidencia (fichas aplicadas/con éxito, ciclos, brechas) |

### 11.1. Fronteras de diseño (no configurables)

- **Solo lectura**: nunca se ejecuta código de los repos estudiados ni se
  instala nada de ellos (riesgo de supply-chain cero por construcción).
- **No hay SORD**: no se buscan claves/endpoints expuestos para usarlos; se
  estudia documentación pública como conocimiento. La línea de §1.1 sigue.
- **Modelo de permisos**: cada ficha pasa `classify_forbidden`; contenido
  que describa conductas prohibidas se rechaza y queda en el registro.
- **Presupuesto acotado**: máx. 60 llamadas de API por sesión y 1 espera de
  rate limit; agotar el presupuesto es parada honesta, no bucle infinito.

### 11.2. Límites y medias verdades conocidos

- **La calidad de lo aprendido depende del resumidor**: sin LLM (sin pool),
  el resumen es extractivo (primeras frases + cabeceras) — pobre pero
  honesto; con pool SORL, cada ficha es un resumen real del README.
- **La selección de repos es por estrellas del ranking de GitHub**, no por
  afinidad semántica fina: para consultas de brecha muy específicas puede
  devolver repos mediocres (verificado en vivo: ★0 para una consulta rara).
- La **detección de brecha heurística** (sin LLM) usa identificadores
  técnicos del fallo (EXIF, CamelCase, snake_case); la primera versión
  mezclaba palabras del error ("Error module named") y no encontraba nada —
  corregido y con test de regresión.
- **La atribución de éxito a fichas es aproximada**: se acredita a las
  últimas fichas inyectadas, no a un contrafactual real.
- **No se clona ni se indexa el código** de los repos (solo README): buscar
  patrones dentro del código (`search/code`) está en roadmap.

## 12. Escalar más allá de las claves propias: BOINC/spot (diseño, NO implementado)

La vía legítima para más cómputo que el que tus claves dan:

1. **Cómputo voluntario (BOINC)**: tareas embolsadas (bag-of-tasks) que
   voluntarios ejecutan CONSENTIDAmente — modelo Folding@home. Diseño: un
   servidor de colas (el ledger JSONL ya es append-only) + cliente BOINC
   que reclama subtareas `fanout` y publica resultados firmados (HMAC del
   workspace ya existe). Solo tiene sentido para subtareas sin datos
   sensibles y verificables barato (la firma + verificación de muestras ya
   está). NO implementado: requiere infraestructura pública propia.
2. **Instancias spot/preemptibles**: entrenamiento/inferencia masiva a
   ~0.1x precio aceptando interrupciones. A²S ya tiene las piezas
   (checkpoint en ledger, memoria persistente, `supervise` que relanza);
   falta el provisionador (Terraform/CLI) y el worker que reclama trabajo.
   NO implementado: es herramienta del OPERADOR, no del agente.

Lo que NO habrá: usar la cuota de terceros sin consentimiento. Ese es el
SORD de siempre con otro nombre, y sigue siendo no.

---

## 13. Nivel determinista (v1.6): FSM + eventos — la verdad completa

`fsm.py` implementa el "eslabón predecible": máquinas de estados finitas sin
LLM y un vigía dirigido por eventos. Cubrir "cada eslabón" funciona así:

| Eslabón | Quién lo resuelve | Coste |
|---|---|---|
| Predecible (la observación encaja en un patrón previsto) | **Nivel 0**: FSM determinista (regex/contains/always sobre la observación real) | 0 tokens, milisegundos |
| Imprevisto (NINGUNA transición encaja) | **Nivel 1**: escalado al loop completo del agente (heuristic o pool SORL) con la observación como objetivo contextualizado | solo cuando hace falta |

### 13.1. Lo que ES y lo que NO ES

- Las acciones FSM usan el **mismo modelo de permisos** que el agente
  (lista blanca de shell, allowlist de red, `classify_forbidden`): no hay
  una vía lateral de ejecución.
- El **jitter** (±40% o uniforme [min,max]) existe para no sincronizarnos
  con otros clientes ni formar rebaños — NO es camuflaje: el vigía lleva
  User-Agent honesto (`A2S-*`) y **no rota huellas "para simular entornos
  de usuario"**: eso sería evasión de controles de terceros (§1.1).
- Una acción que devuelve **vacío legítimo** (directorio vacío) se enruta
  como vacío — no se maquilla con texto placebo (bug corregido en la
  primera versión, con test de regresión).

### 13.2. Límites y medias verdades conocidos

- **La FSM no se adapta sola**: si el formato del dato cambia, la máquina
  escala (correcto), pero aprender la transición nueva es cosa tuya — el
  informe de escalado te dice exactamente qué transición faltaba. La
  generación automática de especificaciones FSM desde los escalados está
  en roadmap, no implementada.
- El vigía **poll-ea** (listado+mtimes, ~0.5s): sin inotify/watchdog —
  stdlib a propósito; para miles de archivos usa interval.
- El webhook escucha en **127.0.0.1** y acepta cualquier POST sin
  autenticar: úsalo detrás de un reverse proxy con auth si lo expones
  (misma política que el dashboard: `--public` bajo tu responsabilidad).
- El escalado ejecuta una misión completa del agente: si tu FSM escala
  por diseño cada minuto, el "coste 0 tokens" del nivel 0 se evapora —
  las especificaciones deben dejar el `always` como última transición.

---

## 14. ROADMAP_V2 (v1.7+): plan de 250 criterios con revisión técnica

El plan de mejora integral está comprometido en `ROADMAP_V2.md` (tranches,
adaptaciones justificadas y decisiones de producto diferidas). Estado real de
la tranche 1 (v1.7.0), sin maquillar:

| Entregado | Matices honestos |
|---|---|
| CI GitHub Actions (tests + guardianes) | Workflow completo listo en `tools/ci/ci.yml`; debe copiarse a `.github/workflows/ci.yml` cuando la GitHub App tenga permiso `workflows`. Localmente pasan guardianes/suite/wheel/npm E2E |
| Guardián de pureza stdlib | Solo vigila `import` de runtime; un dev-dep de CI (coverage, mypy) seguiría siendo legítimo (no se ha añadido ninguno aún) |
| Guardián de complejidad (CC<35, media<6) | El ratchet es conservador: quedan 4 hotspots CC>19 (shell=33, evolve_step=26, _handler=23, execute_step=19) para tranches 2 |
| BM25 (`a2s search`) | BM25 léxico NO es semántica profunda: sin embeddings no sinonimia («hash» no encuentra «digest»); verificado en vivo con episodios reales |
| Notificaciones `--notify` | Solo webhook/file/print (JSON saliente, sin secretos); SMTP sigue en roadmap |
| Unlearning | Poda requiere ≥5 usos + 90 días de edad (no borra fichas jóvenes); el decay de estrategias solo actúa con historia >50 — es conservador a propósito |
| `execute_dag` refactorizado | CC 31→18: mejora, no perfección (objetivo final CC<15 en tranche 2) |
| `--seed` | Siembra `random` global: jitter/fanout reproducibles; NO controla el orden de `as_completed` de hilos del SO |

Lo NO adoptado o diferido está razonado en el propio ROADMAP_V2.md (§ adaptados):
asyncio/aiohttp runtime, subpaquetes por mover, matrix Windows sin poder
ejecutarla, RBAC multiusuario como producto v2.0 (no como refactor), y la
escala «6/5» (no existe: la escala es 0-5 y este documento es su guardián).

---

## 15. Modo SERVICIO experimental (v1.8): RBAC real, amenazas reales

`a2s serve` + `a2s users` implementan el multiusuario que el roadmap
difería. Lo que hay y lo que NO hay, sin maquillar:

| Hay (verificado con tests sobre HTTP real) | No hay (usar reverse proxy / v2.0) |
|---|---|
| RBAC admin/operator/viewer con permisos por endpoint | TLS propio (HTTP plano: proxy con certificados) |
| Tokens JWT-HS256 con expiración y claim de rol | SSO/OAuth/federación: usuarios locales del operador |
| Aislamiento por usuario: `workspaces/u-<user>/` | Rate-limiting del login (protege el proxy) |
| Auditoría TOTAL: denegaciones incluidas, en `serve_audit.jsonl` | Retención/RGPD operativa (derecho al olvido, DPO) |
| Misiones con timebox en hilos propios, informe persistido | Clúster/multi-proceso: una instancia, un workspace base |
| Bootstrap físico: usuarios creados SOLO desde la máquina que sirve | Sesiones/refresh tokens: el token vive lo que dura `--hours` |

**Modelo de amenazas asumido**: el operador de la máquina es de confianza
(crea usuarios); la red NO lo es (por eso localhost por defecto y proxy
obligatorio si se expone). Un token robado vale hasta su expiración y no
hay revocación: `--hours` cortos. El viewer puede LEER informes de todos
(los metadatos de misión no se filtran por usuario en /api/report — gap
conocido, documentado, corregible en v2.0).

**Fachada async** (`a2s/asyncapi.py`): es exactamente eso — una fachada.
El núcleo sigue siendo síncrono con hilos (decisión razonada); await no
convierte esto en un servidor de 10k conexiones (el handler HTTP sigue
siendo `http.server`): es ergonomía de integración, no escala.

## 16. Agent Control Plane (v1.9): industrial no significa mágicamente enterprise

La GUI nueva es un **control plane local de un solo proceso**. Usa HTML/CSS/JS
empaquetado, API `http.server` y SSE; no usa CDN ni un backend de pago.

| Sí implementado | Límite honesto |
|---|---|
| Mission control con parámetros acotados | Una misión simultánea por instancia |
| Parada cooperativa | No interrumpe una syscall; espera el timeout del paso activo |
| Topología y preview SORL sin llamada real | Los factores son heurísticos, no una garantía de calidad futura |
| CSP, deny framing, nosniff, SameSite y control de Origin | HTTP plano; al exponer usa `--auth` y reverse proxy TLS |
| Assets relativos y responsive | No se certificó todavía WCAG con lector de pantalla real |
| Radar, fichas y `a2s audit` | El radar depende de disponibilidad/cuota pública de GitHub |

`--public` sin `--auth` sigue siendo deliberadamente peligroso: cualquier
cliente con acceso podría lanzar una misión. El CLI lo advierte, pero no lo
prohíbe para conservar escenarios de laboratorio aislado. La opción segura es
localhost (default) o `--public --auth` detrás de un proxy.

### 16.1. Cierre de la regresión de misiones completas

Los tres tests antes gated en v1.8.2 volvieron a pasar repetidamente tras
corregir el ciclo de vida del mini-shell: ahora espera **todos** los procesos de
un pipeline, cierra sus pipes y mata/recolecta el pipeline ante timeout. Se
eliminó `A2S_RUN_SLOW_MISSIONS`; las misiones completas forman parte de la suite
por defecto y no quedan skips ocultos.

Esto es evidencia de correlación fuerte, no una afirmación causal absoluta: el
problema previo dependía del entorno reconstruido y no se obtuvo un core dump.
El test de regresión y la ausencia de `ResourceWarning` son el control futuro.

## 17. Radar OSS y primera integración OmniRoute (v1.9; base npm desde v1.13)

`a2s scout` no instala soluciones. Lee metadatos públicos, exige una licencia
SPDX de la allowlist, filtra por el modelo de permisos y persiste la procedencia.
El campo `code_executed: false` es un contrato comprobado por tests.

Límites:

- una licencia declarada por GitHub puede estar mal; revisión humana antes de
  copiar código;
- estrellas y frescura no prueban seguridad;
- el resumen por descripción no sustituye una auditoría del repositorio;
- proyectos `NOASSERTION`/`UNKNOWN` se rechazan aunque parezcan abiertos;
- el catálogo semilla envejece y debe refrescarse con `a2s scout`;
- buscar más proyectos aumenta el conjunto de ideas, no la capacidad por sí
  sola: solo un experimento verificado autoriza una mejora.

Desde v1.13 la **distribución npm** declara OmniRoute `3.8.49` como dependencia
fijada. El launcher lo arranca bajo demanda en loopback y registra su endpoint
en SORL; `auto` es la ruta base y ya no exige `--provider`. La ejecución Python
directa sigue pudiendo descubrir un gateway existente o usar
`A2S_OMNIROUTE_URL`.

Esto no convierte un servicio externo en cómputo local: no se instala un LLM,
pero las rutas keyless de OmniRoute necesitan red y están sujetas a la
disponibilidad y términos de sus upstreams. Si no responden, A²S degrada al
núcleo heurístico. OmniRoute tiene una superficie y un árbol npm sustanciales;
su `postinstall` oficial prepara binarios nativos. La dependencia directa es
exacta y el checkout captura su integridad, pero una actualización requiere la
misma revisión de supply chain que cualquier dependencia.
`A2S_OMNIROUTE=off` elimina el arranque automático.

## 18. Distribución npm (v1.10, ampliada en v1.13)

El paquete `a2s-agent-control-plane` hace que A²S sea instalable mediante npm,
pero el núcleo sigue ejecutándose en Python. Node solo lanza el núcleo y
supervisa el gateway; no duplica seguridad, memoria ni planificación.

| Hay | No hay |
|---|---|
| Comandos npm globales `a2s` y `a2s-control-plane` | Python embebido dentro de Node |
| Detección de Python ≥3.9 y `A2S_PYTHON` | Descarga automática de intérpretes o modelos LLM |
| OmniRoute exacto como dependencia npm | Garantía de red o de disponibilidad de cada upstream keyless |
| Arranque daemon en `127.0.0.1:20128` + detección reutilizable | Sondeo automático de hosts remotos |
| SORL `auto` + fallback heurístico | Necesidad de elegir proveedor para el uso normal |
| Zipapp ejecutable con Python del host | Binario nativo único sin prerrequisitos |
| E2E de instalación aislada en Linux | Certificación manual firmada en cada SO |
| Matriz CI configurada para Linux/macOS/Windows | Resultado remoto hasta que GitHub ejecute el workflow |

`npm run build` no publica nada. `npm run release:local` deja artefactos locales
en `artifacts/`; `npm publish` requiere autenticación npm y es una acción
separada del operador. A²S no añade un hook propio de instalación, pero npm sí
ejecuta el `postinstall` declarado por OmniRoute: una instalación funcional no
debe ocultarlo con `--ignore-scripts`. Python solo se ejecuta cuando el operador
invoca `a2s`.

## 19. Protocolo Adaptativo Aegis (v1.15): omnimodal no significa universal

`aegis_protocol.py` aporta una capa de decisión reproducible delante del chat y
del planner. La mejora real es **selección y trazabilidad**, no una ampliación
mágica de las herramientas instaladas.

| Sí hay | No hay |
|---|---|
| Clasificación multi-etiqueta de seis familias de necesidad | Comprensión semántica perfecta de cualquier frase |
| Catálogo explícito de análisis, investigación, cálculo, creación, visualización y recuperación | Activación indiscriminada de todos los modos en cada mensaje |
| Contexto reciente del chat y prompt especializado por petición | Ventana de contexto ilimitada o memoria total infalible |
| Fuente/fecha exigidas para hechos actuales | Garantía de que internet, el upstream o dos fuentes estén disponibles |
| Herramientas candidatas inyectadas al planner | Garantía de que una herramienta candidata será ejecutable con los permisos actuales |
| Perfil en SSE, timeline, ledger e informe final | Prueba de corrección por el solo hecho de registrar el perfil |
| Resumen de método, evidencia y criterios | Chain-of-thought privado, tokens internos o deliberación oculta |
| ASCII/Mermaid/Markdown como visualización textual | Generador nativo de imágenes, audio o vídeo dentro del core stdlib |
| Alternativas legítimas y degradación honesta | Acceso a sistemas, cuentas, datos o cómputo no concedidos |

La selección por palabras clave es deliberadamente auditable y funciona sin
LLM, pero tiene falsos positivos y negativos. `a2s protocol "..." --json`
permite inspeccionarla antes de una misión. Cuando el resultado dependa de una
matemática, fuente o artefacto, el criterio fuerte sigue siendo el mismo de todo
A²S: **evidencia reproducible y verificador de misión**. Una lista de
capacidades activadas no sustituye esa prueba.

El sistema descarta bloques `<think>...</think>` emitidos por un upstream antes
de persistir o mostrar el texto. Esto reduce una vía común de exposición, pero
no puede demostrar cómo razona internamente un proveedor remoto. Por eso el
contrato solicita únicamente un resumen externo de enfoque; no intenta capturar
ni auditar estados internos del modelo.
