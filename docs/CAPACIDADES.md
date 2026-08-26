# Capa de capacidades del catálogo (v1.26)

> Cómo la lista de 65 URLs del operador se convirtió en un **mapa accionable**:
> para cada fuente —qué capacidad aporta, con qué uso autónomo, qué necesita,
> qué equivalente interno de A²S la cubre, cómo encadena y cuándo se bloquea—.
> Determinista, stdlib puro y auditable: no finge capacidades que el entorno no
> tiene.

---

## 1. De listado a ingeniería (Fase 1–2)

`a2s/recursos.py` ya catalogaba las fuentes (referencia y estudio, sin
ejecución). `a2s/capacidades.py` añade la **semántica** por entrada:

| Campo | Qué significa |
|---|---|
| `dominio` | Categoría funcional: cognitiva, ciber, automatización, infraestructura, datos, utilidades |
| `capacidad` | Verbo de capacidad (p. ej. `reconocimiento_web`, `reversing_binario`, `prompt_engineering`) |
| `uso` | `si` autónomo · `parcial` (requiere CLI/API/servicio) · `operador` (decisión manual) · `no` (zona gris: solo referencia) |
| `requiere` | Dependencias canónicas (CLI Ghidra/ImHex/Trivy/Nuclei, API key Google, GPU, servidor propio, alcance escrito…) |
| `mapa_a2s` | Equivalente interno: `tools.fetch_url`, `plugin.forensics_extra`, `plugin.crypto_tools`, `plugin.repo_audit`, `learner.GitHubClient`, `search.BM25Index`, `provider_pool`, `aegis_protocol`… |
| `receta` | 2–4 pasos de uso, consumibles por el planificador |
| `etico` | Nota de frontera por recurso |
| `sinergias` | Qué otros recursos encadenan después |
| `core` | 1 de las 15 fuentes de mayor apalancamiento |

Cobertura **65/65** verificada por test: ninguna entrada puede quedar sin
capacidad, receta o nota ética. Los recursos propios del operador
(`a2s recursos add`) reciben un registro genérico de dominio derivado.

### Completitud real del listado

El mensaje del operador declaraba «63 únicos». Recuento real de URLs únicas:
**65**. Faltaban tres en el catálogo:

- `github.com/anthropics/courses` — espejo oficial de los cursos (se añade
  como entrada propia).
- `github.com/ShadowHackrs/gmail-account-creator` — se añade con marca
  `advertido` y receta restringida: **solo la API oficial de Google sobre la
  cuenta principal del operador**; nunca creación masiva ni saltos de ToS.
- `github.com/lahirusanjika/Worm-GPT` — el repo real se localiza (antes la
  entrada tenía URL vacía); queda como referencia documental, no integrado.

## 2. Extracción de valor (Fase 3)

**Para repos de código:** la ingesta asimila **texto** (README, metadatos,
licencia) vía la API de GitHub con el cliente existente (`GitHubClient`:
ventanas de cuota locales + `Retry-After` del servidor respetado, token del
operador opcional). Cada fuente produce una ficha de conocimiento
(`cap-<id>` en `workspace/.a2s/knowledge/`) con resumen extractivo stdlib,
receta y estado persistido en `.a2s/capacidades/ingesta.json`.

Frontera dura (no configurable): **nunca se clona, instala ni ejecuta el
código estudiado**. Los READMEs pasan por `classify_forbidden` (modelo de
permisos); el contenido que casa con un patrón prohibido queda `revisar` —
la ficha se conserva (el material es público) pero **no se auto-aplica** y
queda para revisión del operador, con el motivo registrado.

**Para herramientas web:** uso `operador` — A²S prepara (fetch público con
`--allow-host`, resúmenes, check de enlaces) y el operador decide; nunca se
automatizan servicios de pago, finanzas de riesgo ni zonas grises.

**Para cursos/conocimiento:** las técnicas se convierten en fichas y en
directivas internas (p. ej. los 4 principios de Karpathy en el contrato
Aegis).

### 15 core (prioridad de integración)

`agency-agents`, `book-secret-knowledge`, `claude-courses`, `cyberchef`,
`ghidra`, `karpathy-skills`, `n8n-workflows`, `openssl`, `osint4all`,
`real-world-llm-apps`, `ruflo`, `system-prompts-leaks`, `trivy`, `vault`,
`web-check`.

Integraciones internas reales (ya existentes, ahora mapeadas): análisis
estático de binarios (`forensics_extra`), hash/HMAC (`crypto_tools`),
auditoría de repos (`repo_audit`), puente DFIR (`forensic_tools`), estudio
de repos (`learner`), memoria BM25 (`search`), orquestación (`provider_pool`,
`fsm`, `watch`), bóveda sin secretos (`vault`), firma de resultados
(`signing`).

## 3. Sinergias (Fase 4)

Cadenas declaradas en `RUTAS_SINERGIA` (intención → eslabones):

- `reconocimiento` → web-check → osint4all → nuclei (con puerta) → study-notes
- `vulnerabilidades` → nuclei → trivy → web-check → payloads-all-things
- `reversing` → ghidra → imhex → x64dbg → cyberchef
- `prompt` → claude-courses → system-prompts-leaks → karpathy-skills → agency-agents
- `orquestación` → n8n-workflows → ruflo → agency-agents → real-world-llm-apps
- `secretos` → vault → openssl → cyberchef
- `vpn/proxy/DNS` → algo → setup-ipsec-vpn → xray-core → adguard-home → stevenblack-hosts
- `google` → gworkspace-cli → gmail-account-creator
- `empleo`, `fitness`, `juegos`, `cripto/finanzas`, `ocr`, `estudio`…

El fallback es búsqueda BM25 sobre el texto sintetizado de cada capacidad
(capacidad + dominio + requisitos + receta + etiquetas), así las intenciones
no declaradas tampoco quedan muertas.

## 4. Sistema de decisión (Fase 5)

```
a2s capacidades ruta "reconocimiento web"
```

Devuelve `pasos` (habilitados, con por-qué, requisitos y equivalente A²S),
`bloqueados` (motivo), estado de `autorizacion` y **sugerencia defensiva**.
Ejemplos de salida real:

- `reconocimiento web` → pasos: web-check, osint4all, study-notes ·
  bloqueado: nuclei («requiere alcance escrito…») · sugerencia: web-check +
  trivy + repo_audit sobre activos propios.
- `reversing binario` → ghidra, imhex, x64dbg, cyberchef (ninguno requiere
  alcance escrito: análisis de muestras propias).
- `explotar con metasploit sqlmap` → ambos retenidos («uso ofensivo:
  requiere alcance escrito firmado»); sugerencia defensiva.
- `streaming flixer` → retenido («zona gris/referencia»).

### Puerta de autorización

`a2s capacidades ruta` lee `workspace/.a2s/alcance.json`:

```json
{
  "autorizado": true,
  "hosts": ["*"],
  "nota": "red-team propio con alcance firmado (2026-08)"
}
```

Solo con alcance válido (y cobertura del host o contexto CTF/lab propio) se
liberan los eslabones con `autorizacion_escrita` (nuclei, hashcat, etc.).
Sin archivo, la ruta ofensiva queda bloqueada y se publica la alternativa.
Los recursos `no` (zona gris: deepweb, streaming sin licencia, Worm-GPT,
réplicas) **nunca** se liberan: son documentación.

## 5. Comandos

```
a2s capacidades                      # resumen (dominios, usos, core, ingesta)
a2s capacidades --core               # las 15 fuentes core
a2s capacidades --ruta "recon web"   # enrutador con puerta de autorización
a2s capacidades --ruta ... --json    # contrato JSON completo
a2s capacidades --mapa [-|RUTA]      # informe Markdown completo
a2s capacidades --ingesta --calls 40 [--solo ghidra,cyberchef] [--refresh]
a2s recursos --md                    # catálogo de siempre (ahora 65 entradas)
```

Control Plane: `GET /api/capacidades` (resumen)
y `GET /api/capacidades?objetivo=reconocimiento%20web` (ruta); en la
pestaña **Recursos** hay barra de capacidades + campo «Enrutar objetivo».

## 6. Límites honestos

- La ingesta solo ve READMEs públicos; los 24 recursos externos no GitHub se
  registran como `referencia`.
- Sin `GITHUB_TOKEN` el límite de la API es ~2 lecturas/min: la ingesta
  completa es reanudable; con token del operador (~30/min) se completa en
  pocos minutos.
- El enrutador es determinista (no LLM): cubre las intenciones declaradas y
  cae a BM25 para el resto; la puerta de ética es explícita y auditable.
- A²S **no** porta exploits ni payloads ejecutables, ni automatiza zonas
  grises, ni integra modelos sin procedencia. Lo que sí hace: análisis
  defensivo de artefactos propios, orquestación con recursos legítimos del
  operador y conocimiento destilado con fuente y licencia.
