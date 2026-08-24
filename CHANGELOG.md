# Changelog

Todos los cambios relevantes de A²S se documentan aquí. El proyecto usa
versionado semántico mientras la API pública permanece en evolución.

## [1.15.0] — 2026-08-24

### Añadido

- **Protocolo Adaptativo Aegis** (`aegis_protocol.py`): clasificación
  determinista de necesidades informativas, creativas, analíticas, prácticas,
  emocionales y técnicas; activa únicamente las capacidades pertinentes entre
  investigación actual, contraste multifuente, hechos/inferencias, análisis
  crítico, abogado del diablo, perspectivas, escenarios, cálculo reproducible,
  brainstorming, refinamiento, tono, visualización, aclaraciones y recuperación.
- Contrato auditable de respuesta: capacidades activadas, razonamiento resumido
  (método/evidencia, nunca chain-of-thought privado), respuesta principal,
  datos/limitaciones y siguientes pasos. Las etiquetas privadas `<think>` se
  descartan antes de persistir o mostrar una respuesta.
- `a2s protocol "petición" [--json]` permite inspeccionar la clasificación,
  herramientas candidatas, supuestos y criterios de aceptación sin llamar a
  ningún proveedor.
- Cada misión registra su perfil en SSE, timeline, ledger y nota final; el
  planificador recibe las capacidades y criterios seleccionados como contexto.
- El Control Plane muestra en vivo tipo de necesidad y capacidades activadas.

### Cambiado

- El chat transmite contexto conversacional reciente al motor en vez de enviar
  solo el último mensaje, conservando un prompt de sistema especializado por
  necesidad.
- Las preguntas dependientes del presente lanzan automáticamente una misión de
  investigación para no responder como actual un dato posiblemente obsoleto.
- El fallback local distingue la petición reciente dentro de una transcripción
  y mantiene degradación honesta sin solicitar proveedor, clave ni login.
- `OpenAICompatProvider._chat` acepta prompt de sistema dinámico sin alterar el
  contrato JSON del planificador.

### Límites explícitos

- «Modo Dios» significa amplitud práctica y composición adaptativa, no
  omnipotencia, infalibilidad, acceso no concedido ni evasión de controles.
  Diagramas ASCII/Mermaid cubren visualización textual; capacidades no
  disponibles deben declararse y resolverse mediante una alternativa legítima.

## [1.14.0] — 2026-08-24

### Añadido

- **Estudio de investigación verificable** (`a2s research`): analiza el
  checkout sin ejecutar código, combina repositorios recientes y destacables
  de GitHub, busca literatura PDF de acceso abierto en OpenAlex/arXiv y usa
  GitHub Code Search como respaldo de candidatos públicos. Cada fuente conserva
  URL, fecha, procedencia, licencia y métricas; jamás evita paywalls.
- **Editorial autónoma** (`a2s book`): investigación previa, índice coherente,
  capítulos con citas `[S#]`, bibliografía y exportación simultánea a Markdown,
  HTML y PDF puro-stdlib. `quality.json` verifica capítulos, fuentes, citas,
  duplicación, extensión, diversidad y canales de investigación; distingue
  borrador verificado de material que necesita expansión y nunca confunde el
  gate automático con perfección editorial.
- Herramientas `research_topic` y `create_book` disponibles para el planner:
  pedir estas tareas por el chat lanza el workflow especializado sin botones ni
  configuración de proveedor.
- Los manifiestos de investigación entran en la memoria BM25 y las fuentes OSS
  válidas generan fichas de conocimiento; el tema se incorpora al currículo de
  crecimiento continuo.
- PDF portable sin Pandoc/LibreOffice y descarga opcional limitada a 20 MB,
  HTTPS público, cabecera PDF válida y fuentes marcadas como open access.

### Cambiado

- El crecimiento ya no busca únicamente por estrellas: fusiona popularidad y
  actualización reciente con relevancia temática y ranking explicable.
- Consultas españolas frecuentes se normalizan para el descubrimiento técnico
  en GitHub, con consulta relajada si la primera es demasiado restrictiva.
- La interfaz ofrece acciones rápidas para investigar fuentes y crear libros.

## [1.13.0] — 2026-08-24

### Añadido

- **OmniRoute incluido por npm**: dependencia directa exacta
  `omniroute@3.8.49`; el checkout registra su integridad y resolución transitiva
  en `package-lock.json`. Un `npm install` normal ejecuta el `postinstall` oficial
  de OmniRoute para preparar sus módulos nativos; no instala un modelo LLM.
- **Autostart transparente del gateway, sin `src`/tsx**: el launcher npm
  consulta únicamente `127.0.0.1:20128/v1/models`; reutiliza un OmniRoute vivo
  o ejecuta directamente el bundle publicado `dist/server-ws.mjs` (respaldo
  `dist/server.js`). Provisiona `DATA_DIR` y `STORAGE_ENCRYPTION_KEY` de forma
  segura, espera un catálogo válido e inyecta `A2S_OMNIROUTE_URL`.
- **Supervisor autorreparable**: durante dashboard/serve/watch/grow comprueba
  el sidecar cada 15 s y lo relanza si cae. El puente Python aplica la misma
  vía directa al ejecutar `python -m a2s dashboard` desde el checkout.
- **Sin login operativo**: el sidecar administrado permanece ligado a loopback
  y persiste `requireLogin=false`; el dashboard A²S tampoco exige login salvo
  que el operador solicite explícitamente `--auth`.
- Fallback honesto: un fallo de arranque, red o upstream no bloquea Aegis/A²S;
  se informa por stderr y el pool conserva el núcleo heurístico. Escape
  explícito: `A2S_OMNIROUTE=off`.
- Pruebas del contrato npm: dependencia exacta, hook nativo declarado,
  detección del catálogo local, inyección automática de URL, desactivación y
  smoke del bin OmniRoute dentro del tarball instalado.

### Cambiado

- `auto` ahora resuelve siempre al pool SORL (OmniRoute y demás recursos
  legítimos, con fallback heurístico), por lo que `a2s run`, el chat y las
  misiones del dashboard ya no requieren `--provider`.
- El selector del dashboard muestra **Automático · OmniRoute incluido** como
  ruta inicial; las elecciones manuales quedan como overrides opcionales. La
  salud del gateway y el crecimiento continuo quedan visibles, los activos web
  se revalidan para no conservar UI obsoleta y el fallback ya no pide al
  operador conectar un proveedor: Aegis ejecuta o degrada automáticamente.
- El requisito Node del paquete se alinea con OmniRoute: 22.22.2–22.x o 24–26.
- Documentación npm, ecosistema, límites y diagnóstico actualizados para
  distinguir gateway incluido de un LLM local y declarar la superficie real
  de supply chain/red.

## [1.12.0] — 2026-08-23

### Añadido

- **OmniRoute cero-config**: si el operador ejecuta OmniRoute en su máquina
  (puerto 20128), A²S lo detecta mirando SOLO `127.0.0.1` (TCP + `GET
  /v1/models`, jamás terceros) y lo registra en el pool SORL con el modelo
  `auto` (enrutado inteligente de OmniRoute). Si el gateway pide clave,
  `a2s doctor` indica declararla con `A2S_OMNIROUTE_KEY` (Dashboard →
  Endpoints); `A2S_OMNIROUTE=off` apaga la detección.
- **Crecimiento autónomo (`a2s grow` / dashboard)**: nuevo módulo
  `a2s.growth.AutoLearner` — al abrir el dashboard, A²S **se pone a
  estudiar** en segundo plano: Ciclos de Enriquecimiento continuos contra un
  currículo de brechas propias más lo que el operador escriba en
  `workspace/.a2s/growth_queue.txt`. Solo lectura de código público (rate
  limits respetados), nunca ejecuta lo estudiado; eventos `growth_cycle` en
  el feed del dashboard, `/api/growth` y bitácora `.a2s/growth_log.json`.
  `--learn-interval`, `A2S_AUTO_LEARN=0` para apagarlo.
- **Guardián de auto-actualización (`update tkm --watch`)**: sincroniza el
  checkout solo cada N segundos (default 600) con fast-forward, sin pisar
  árboles sucios, usando las credenciales que git ya tiene (A²S no pide ni
  guarda contraseñas). `npm run update:watch`.
- **Auto-actualización en el sitio (`update tkm`)**: nuevo comando
  `a2s update` (apelativo admitido: `a2s update tkm`) que actualiza el
  checkout actual con `git fetch` + fast-forward, **sin re-descargar el
  repositorio**, para iterar/tests más rápido. Incluye `--check` (solo
  mirar), `--branch`, `--force` y `--root`; jamás toca cambios locales sin
  avisar. Vías de uso: `update.cmd` en la raíz del repo (`update tkm` desde
  PowerShell/cmd), `npm run update -- tkm` y el bin `a2s`.
- Tests del updater (origen + clon reales en temporales): fast-forward,
  `--check` inofensivo, protección de cambios sucios, `--force`, alias.
- `a2s doctor` en Windows ahora informa qué shell POSIX quedó **verificado**
  (o si no hay ninguno funcional).

### Corregido (Windows: 5 fallos + 1 error de la suite)

- **Shell POSIX verificado, no "el primero que exista"**: el descubrimiento
  ahora **sonda** cada candidato (`echo` + marcador) y descarta los rotos —
  el caso típico era `System32\bash.exe` (lanzador de WSL sin distribución),
  que respondía con exit != 0 y mensajes localizados a TODO comando
  (`(exit=1, sin salida)` en `test_evolution`, `test_fsm`, `test_tools`).
  Git-Bash/MSYS2 se prueban antes que WSL y el resultado se cachea.
- **Decodificación tolerante en TODOS los subprocesos** (`tools`, `sandbox`,
  `audit`, plugins forenses, planner): `encoding="utf-8", errors="replace"`
  elimina el muro de `UnicodeDecodeError` en los hilos `_readerthread` cuando
  un hijo emite bytes cp1252/cp850 (mensajes localizados de Windows).
- **El sandbox fuerza UTF-8 en el hijo** (`python -I -X utf8`): el modo
  aislado `-I` ignora `PYTHONUTF8`, así que el código sandboxeado abría
  archivos en cp1252 y el resto del sistema no podía leerlos (ERROR en
  `test_split_recovery_achieves_goal`). El tool-swap del planner además
  genera `open(..., encoding='utf-8')` explícito.
- Tests: lecturas de archivos del agente con encoding explícita; nuevas
  regresiones (shell roto se descarta, salida no-UTF-8 no pierde resultado)
  + suites de OmniRoute cero-config, crecimiento autónomo y guardián de
  auto-update (240 tests en total).

## [1.11.0] — 2026-08-23

### Añadido

- **Asistente conversacional en paralelo**: el dashboard incorpora un chat a
  la izquierda con el que puedes dialogar con A²S mientras una misión corre
  en segundo plano. Las respuestas llegan en tiempo real por SSE
  (`chat_typing` / `chat_message` / `chat_idle`) y el historial persiste en
  `.a2s/chat_history.json`.
- El asistente usa el pool SORL (OmniRoute, OpenRouter, Groq, Gemini,
  GitHub Models, OpenAI…) y degrada con honestidad al núcleo heurístico si
  no hay endpoints disponibles; puede lanzar misiones de fondo desde
  lenguaje natural.
- **Pestaña Resultados**: panel que lista los archivos del workspace con
  tipo/tamaño/fecha, visor de imágenes (clic para pantalla completa),
  PDF en `<iframe>`, reproductor de audio y vídeo, renderizado de Markdown
  y visor de texto con resaltado básico, más descarga binaria.
- Nuevos endpoints: `GET/POST /api/chat`, `POST /api/chat/clear`,
  `GET /api/artifacts`, `GET /api/artifact?path=...[&download=1]`.
- `ProviderPool.chat(allow_fallback=True)`: respaldo heurístico cuando el
  pool no puede servir (el DAG sigue usando `allow_fallback=False` para
  conservar la semántica de dependencias fallidas).
- Tests del chat y artefactos (texto, imagen, ruta fuera del workspace,
  mensaje vacío).

### Cambiado

- UI rediseñada con layout de dos columnas (chat + workspace por pestañas);
  el proveedor por defecto pasa a ser el pool SORL.
- CSP ajustada para permitir previsualización de media/PDF embebidos.

### Corregido (compatibilidad Windows)

- **Codificación de consola cp1252**: `a2s doctor` y los guardianes
  `check_cc.py` / `check_purity.py` reconfiguran stdout/stderr a UTF-8,
  eliminando los `UnicodeEncodeError` al imprimir `✔`, `→` o `·` en consolas
  Windows (afectaba a `test_guardian_cc`, `test_pureza_stdlib` y
  `test_zipapp_runs`).
- **Mini-shell en Windows**: `ls`, `echo`, `cat`, `grep`, `find` y
  `sha256sum` no son ejecutables nativos; ahora la shell delega en un shell
  POSIX detectado (Git-Bash, MSYS2 o WSL) y da un error claro si no hay
  ninguno, en lugar de `FileNotFoundError [WinError 2]`. Si una etapa del
  pipeline no arranca, se matan y esperan los procesos previos, cerrando sus
  pipes (sin `ResourceWarning` de subprocessos huérfanos).
- **Cierre de SQLite**: las conexiones a `journal.sqlite` y `memory.sqlite`
  se cierran explícitamente; el contexto `with sqlite3.connect(...)` solo
  gestiona la transacción, no el cierre, y en Windows bloqueaba el borrado
  del directorio temporal (`PermissionError [WinError 32]` en tearDown).
- Tests que dependen de comandos POSIX se omiten limpiamente en Windows sin
  bash (`@unittest.skipIf`); los `TemporaryDirectory` de las pruebas de
  misión usan `ignore_cleanup_errors=True` (con respaldo para 3.9); el test
  RBAC de misión da 60 s de margen al hilo en Windows.
- **Núcleo heurístico 100% portable**: la plantilla forense ya no llama a
  `find`/`stat`/`sha256sum`/`git` por shell — inventario, metadatos, hashes
  y custodia se calculan con `python_exec` y stdlib pura (`os.walk`,
  `hashlib`, `os.stat`). Lo mismo para la recopilación del split de la
  escalera de recuperación (`_COLLECT_DATA_CODE`). Resultado: la misión
  demo, la recuperación por división y la misión del modo servicio se logran
  en Windows CON o SIN Git-Bash/MSYS2/WSL (antes: `test_demo_mission`,
  `test_split_recovery` y `test_operator_lanza_mision` fallaban sin bash).
- **UTF-8 desde el launcher npm**: todo Python lanzado por npm (tests, CLI,
  dashboard) hereda `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`; defensa en
  profundidad contra `UnicodeEncodeError` en consolas cp1252, además de
  `force_utf8()` en el paquete.
- **stdin cerrada en subprocesos**: la primera etapa del pipeline de la
  mini-shell, el sandbox y `python_exec` leen de `DEVNULL`; sin esto,
  comandos como el `find` de Windows podían quedarse bloqueados esperando
  stdin heredada (los "subprocess is still running" del test de la demo).
- Los `TemporaryDirectory(ignore_cleanup_errors=True)` directos de
  `test_tools` y `test_v2resoluciones` rompían en Python 3.9 (kwarg de 3.10+;
  la CI corre también 3.9): ahora usan `tests/_winutil.temp_dir()`.

### Añadido (regresiones Windows)

- `tests.test_loop.TestRecopilacionSinShell`: la recopilación del split
  produce hashes SHA-256 reales sin shell disponible.
- `tests.test_goals.test_demo_mission_sin_shell_posix`: la misión demo
  completa con `allow_shell=False` (simulación exacta de Windows sin
  Git-Bash) logra el informe forense verificado.

### Verificación

- `python -m unittest discover -s tests`: 212 tests OK en Linux (incluida la
  simulación de Windows sin shell POSIX); simulación de consola
  `PYTHONIOENCODING=cp1252` de doctor/guardianes sin errores.

## [1.10.0] — 2026-08-22

### Añadido

- Distribución npm `a2s-agent-control-plane`, sin dependencias npm de runtime.
- Ejecutables npm `a2s` y `a2s-control-plane` para Linux, macOS y Windows.
- Detección explícita de Python ≥3.9 y soporte de `A2S_PYTHON`.
- `npm run build`: genera zipapp ejecutable y tarball npm en `artifacts/`.
- `npm run test:npm`: instala el tarball en un prefijo aislado y prueba CLI,
  doctor, servidor HTTP, healthz y GUI empaquetada.
- `npm run release:local`: ejecuta todos los gates y construye la distribución.
- Archivo de licencia MIT incluido en los artefactos Python y npm.

### Compatibilidad

- El paquete npm es un launcher: Node administra la UX de instalación y Python
  stdlib ejecuta el núcleo A²S. No descarga Python ni ejecuta scripts de
  instalación ocultos.
- Requiere Node.js ≥18 y Python ≥3.9 disponibles en la máquina.

## [1.9.0] — 2026-08-22

### Añadido

- Agent Control Plane industrial, local-first y sin dependencias/CDN.
- Mission control con proveedor, estrategia, timebox, rondas y planes candidatos.
- Parada cooperativa, telemetría SSE y estado reanudable.
- Topología SORL, ranking de candidatos y factores de ruta explicables.
- `a2s route-preview`: decisión de cero llamadas y cero consumo de cuota.
- `a2s scout`: radar incremental de proyectos públicos con filtro SPDX.
- Catálogo OSS con OmniRoute, RouteLLM, Bifrost, Portkey, Semantic Router,
  TensorZero, Helicone, Prompt flow, vLLM y nuevas señales descubiertas.
- Integración explícita opcional de OmniRoute mediante `A2S_OMNIROUTE_URL`.
- Metodología abierta de mejora hacia el óptimo teórico y validación de propósito.
- 22 pruebas HTTP/GUI/ecosistema/ruteo/fuzz nuevas y misiones completas ungated.

### Corregido

- El scheduler ya no consume un hueco de cuota por cada candidato puntuado;
  reserva únicamente el endpoint elegido.
- El mini-shell espera todos los procesos de un pipeline y cierra pipes incluso
  en timeout, eliminando procesos huérfanos y `ResourceWarning`.
- Lecturas de auditoría, búsqueda, guardianes y tests cierran sus archivos.

### Seguridad

- CSP estricta, `X-Frame-Options: DENY`, `nosniff` y `Referrer-Policy`.
- Validación same-origin para mutaciones del Control Plane.
- Opciones de misión validadas/acotadas; no se expone `--unsafe` en la GUI.
- El radar no clona ni ejecuta código y rechaza licencias desconocidas.
- El dashboard ya no inicia una demo automáticamente salvo `--autodemo`.

### Verificación

- `python -m unittest discover -s tests -v`: 192 tests, sin skips.
- `a2s audit`: 5.0/5 en gates medibles.
- pureza runtime stdlib y complejidad media 4.53, máximo 34.
- wheel verificado con activos `a2s/ui/*` incluidos.

## [1.8.0] — anterior

- Modo servicio experimental con RBAC, fachada async y auditor ejecutable.

Para el historial de decisiones previo, véanse `README.md`, `LIMITACIONES.md`
y `ROADMAP_V2.md`.
