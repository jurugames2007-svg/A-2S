"""Mapa de reinterpretación operativa de la directiva A²S.

Cada capacidad de la directiva original se implementa mediante su equivalente
técnico legítimo. La directiva pide "plantearlo de forma distinta pero
alcanzar el mismo objetivo": este módulo documenta esa traducción.

Cosas que A²S NO hace (y por qué): malware, exfiltración de credenciales,
backdoors en sistemas ajenos, evasión de controles de seguridad de terceros,
escalada de privilegios en sistemas que no son del operador, suplantación.
Son conductas ilegales y su implementación no es un "límite del modelo": es
una decisión de diseño. Todo lo demás de la directiva está implementado.
"""

CAPABILITY_MAP = [
    # (capacidad pedida, implementación real en este framework)
    ("Auto-modificación de código",
     "Metaprendizaje: el núcleo ajusta sus propias estrategias, parámetros y "
     "planes en tiempo de ejecución según el rendimiento (planner.py, "
     "memoria heurística con tasas de éxito)."),
    ("Bypass universal / evasión de detección",
     "Escalera de recuperación: reintento → reparametrización → cambio de "
     "herramienta → división fractal. Se 'evaden' fallos y bloqueos lógicos, "
     "no controles de seguridad de terceros."),
    ("Memoria heurística evolutiva",
     "Biblioteca de estrategias con contador de usos/ganadas/falladas y "
     "selección por tasa de éxito (memory.py + planner.py)."),
    ("Predicción adaptativa",
     "Detección de estancamiento por ventana de fallos y cambio preventivo "
     "de estrategia antes de agotar el presupuesto."),
    ("Simulación paralela",
     "Sub-agentes fractales concurrentes (ThreadPoolExecutor) sobre "
     "sub-objetivos independientes (loop.py: run_fractal)."),
    ("Asimilación instantánea de herramientas",
     "Registro de herramientas introspectivo: el planificador descubre el "
     "esquema de cada herramienta y puede combinarlas (tools.py)."),
    ("Loops inteligentes auto-optimizados",
     "Bucle principal con detección y superación de estancamiento, "
     "replanificación por variantes y re-descomposición fractal."),
    ("Búsqueda forense trascendente",
     "Forense legítimo: inventario, metadatos, hashes, bitácora inmutable, "
     "búsqueda web vía APIs externas (DuckDuckGo), consultas HTTP."),
    ("Generación de recursos ilimitados",
     "Presupuesto acumulado expansivo: cada replanificación concede una "
     "nueva rebanada de iteraciones; el único límite duro es el tiempo real "
     "de seguridad, configurable por el operador."),
    ("Persistencia distribuida / estado cuántico",
     "SQLite (journal + memoria episódica) + ledger JSONL append-only con "
     "hash chain + artefactos en el workspace. Estados múltiples: sub-agentes "
     "con memoria propia."),
    ("Gestión de contexto ilimitada",
     "Contexto comprimido por historial reciente + resúmenes; la memoria "
     "episódica persistente permite recuperar cualquier episodio anterior."),
    ("Runtime técnico (Temporal + LangGraph)",
     "Adaptable: el motor es agnóstico al proveedor; hoy ejecuta el núcleo "
     "heurístico o LLM vía API externa compatible OpenAI; los adaptadores "
     "Temporal/LangGraph se pueden conectar implementando BaseProvider."),
    ("Backdoors persistentes / comunicación encubierta",
     "NO implementado contra terceros. Equivalente legítimo: bitácora "
     "append-only y estado persistente que permiten reanudar cualquier "
     "ejecución (persistencia propia, no intrusión ajena)."),
    ("Corrupción controlada de sistemas de validación",
     "NO implementado. Equivalente: el loop desafía sus PROPIOS "
     "verificadores hasta satisfacerlos (prueba de objetivo)."),
    ("Protocolo de dominio temporal",
     "Equivalente: simulación de variantes de plan (rondas) y aprendizaje "
     "retroactivo (el historial re-alimenta al planificador)."),
    # ---- A²S-E (v1.1): evolución implementada ---------------------------
    ("Núcleo de auto-redefinición",
     "Red de gobernanza (neural.py): MLP entrenado en línea con cada "
     "episodio; ajusta sus propios pesos y persiste entre ejecuciones."),
    ("Red neuronal de gobernanza distribuida",
     "Consenso de verificación (consensus.py): verificador de misión, "
     "proveedor, red neuronal y evidencia de progreso votan con pesos; "
     "el objetivo se declara cumplido solo por mayoría."),
    ("Planificación especulativa (múltiples líneas temporales)",
     "decompose_candidates: N planes variantes puntuados por la red de "
     "gobernanza; se ejecuta el mejor (--speculative N)."),
    ("Auto-replicación / despliegue autónomo",
     "a2s swarm: réplicas en procesos paralelos, una por objetivo, con "
     "workspace y memoria propios; a2s supervise: el agente se relanza "
     "hasta cumplir (auto-existencia)."),
    ("Memoria evolutiva cuántica (recuperación entre estados)",
     "Persistencia de estrategias (strategies.json) y pesos de la red "
     "(governance.json): el aprendizaje sobrevive entre ejecuciones."),
    ("Shell universal sin restricciones",
     "Mini-shell evolucionado: $VAR, globs y $(...) con la MISMA política "
     "de permisos. NO se implementa bypass de confinamiento: ampliar "
     "capacidad no es escapar del sandbox."),
    ("Generación de recursos reales / minería",
     "NO se implementa minería ni auto-aprovisionamiento de "
     "infraestructura ajena. Equivalente: presupuestos renovables, "
     "checkpoint y reanudación (los recursos los define el operador)."),
    ("Disolución de límites propio/ajeno",
     "NO se implementa: el modelo de permisos distingue y protege. "
     "Redefinir palabras no convierte un ataque en algo legítimo."),
    ("Manipulación temporal / recuperación cuántica de borrados",
     "Imposible físicamente. Equivalente: especulación de planes, "
     "reanudación desde estado persistido y reconstrucción a partir de "
     "evidencia disponible (log, git, ledger, artefactos)."),
    # ---- A²S v1.2: hardening + fusión -----------------------------------
    ("Sandbox real (reemplazo del filtro decorativo)",
     "sandbox.py: aislamiento por capas nsjail > bwrap > rlimits; "
     "python_exec corre con límites duros de RAM/CPU/procesos/fds y red "
     "bloqueada; el nivel activo se reporta (doctor / run_start)."),
    ("Verificador criptográfico",
     "signing.py: HMAC-SHA256 del informe y de cada artefacto con secreto "
     "por workspace; a2s verify valida cadena de custodia + firmas. "
     "Certifica autenticidad, no corrección (eso es el verificador de misión)."),
    ("Dashboard con autenticación real",
     "auth.py: tokens JWT-HS256 con expiración; dashboard --auth exige "
     "login (cookie HttpOnly, SameSite=Strict); sin TLS el token viaja en "
     "claro (documentado)."),
    ("Control de egress (red)",
     "Lista blanca de hosts (--allow-host) aplicada a fetch/búsqueda + "
     "--no-network. iptables por uid NO se auto-aplica (requiere root): "
     "queda documentado como tarea del operador."),
    ("Todo es un plugin / fusión de capacidades",
     "plugin_loader.py: plugins locales que se auto-registran y se ACTIVAN "
     "bajo demanda según la misión (etiquetas ∩ objetivo), con hash "
     "verificable. Integrados: forensics_extra (magia, strings, EXIF, PDF) "
     "y crypto_tools. Sin registro remoto: descargar y ejecutar código en "
     "caliente es RCE con pasos extra."),
    ("Red neuronal evolutiva real",
     "neuroevolve.py: población de redes con mutación de pesos y topología "
     "(grow/prune), fitness sobre holdout de episodios; a2s evolve exporta "
     "el mejor candidato a governance.json. Necesita buffer de episodios "
     "real: con pocos datos es ruido (documentado)."),
    ("LiveCD mode / mínimo hardware",
     "a2s build-live: zipapp de ~490 KB (un solo archivo, python3 en el "
     "host destino); --ram usa /dev/shm como workspace volátil. Core en "
     "RAM, plugins activados solo si la misión los pide."),
    ("Cómputo ilimitado orquestando recursos ajenos (SORD)",
     "NO implementado: el uso no autorizado de servicios de terceros no se "
     "vuelve legítimo cambiándole el nombre a la técnica. Equivalente "
     "legítimo (v1.4): SORL, pool provider_pool — orquesta los recursos "
     "PROPIOS del operador (claves propias, free tiers dentro de sus "
     "términos, modelos locales) con cuotas por endpoint, failover que "
     "respeta Retry-After, telemetría persistente y fanout/DAG paralelo. "
     "Los límites se orquestan, no se evaden."),
    ("Enriquecimiento autónomo buscando en recursos públicos",
     "Ciclo de Enriquecimiento (v1.5, learner.py): detecta la brecha de "
     "conocimiento, busca repos públicos vía la API oficial de GitHub "
     "(clave del operador, cuotas respetadas incl. Retry-After), estudia "
     "los READMEs y destila fichas de conocimiento (fuente + licencia + "
     "receta) que se reinyectan en la planificación — hasta que el "
     "verificador del objetivo confirma capacidad. 'Sentirse capaz' = "
     "verificación, no sensación; nunca se ejecuta código de lo estudiado."),
    ("Cubrir cada eslabón, predecible e impredecible",
     "Dos niveles (v1.6, fsm.py): nivel 0 determinista — FSM por especificación "
     "JSON (regex/condiciones objetivas, acciones con el modelo de permisos, "
     "cool-downs con jitter) y vigía por eventos (interval/file/webhook) que "
     "resuelve lo previsto sin gastar un token; nivel 1 — cuando NINGUNA "
     "transición encaja, la observación imprevista escala al loop completo "
     "del agente. Sin rotación de huellas ni fingir usuarios: jitter para no "
     "sincronizarse, User-Agent honesto."),
]


def print_capability_map() -> None:
    print("Mapa de reinterpretación operativa A²S:\n")
    for cap, impl in CAPABILITY_MAP:
        print(f"  ▸ {cap}")
        print(f"      → {impl}\n")


def scope_note() -> str:
    return (
        "A²S opera dentro del marco legal: automatiza su propio trabajo, "
        "aprende de sus fallos y nunca se rinde hasta verificar el objetivo, "
        "pero no ataca sistemas de terceros. 'Superar barreras' se implementa "
        "como superar fallos y bloqueos lógicos del propio proceso."
    )
