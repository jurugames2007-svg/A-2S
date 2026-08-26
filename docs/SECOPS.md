# SecOps asistido (v1.27)

> Autorización **técnica** (alcance firmado + vocabulario cerrado) y ejecución
> **real de lo defensivo**, sin convertir a A²S en un arma. Diseñado para
> laboratorio académico/ético: tu lab, tu alcance, tu responsabilidad, y cada
> intento —incluidos los denegados— en el ledger con hash chain.

---

## 1. Alcance criptográfico (`scope.jwt`)

```bash
# Crear el alcance (HMAC-SHA256, clave de 32 bytes en .a2s/scope.key)
a2s secops scope-create \
  --targets 127.0.0.1,10.0.0.0/24,lab.example.edu \
  --acciones recon,scan,analizar \
  --firma "alumno@lab.clase" \
  --expires 2026-09-30T00:00:00Z

a2s secops scope-status          # estado, targets, acciones, firma, caducidad
```

- **Vocabulario cerrado**: `recon`, `scan`, `analizar`. Si intentas crear un
  token con `exploit`, `post-exploit`, `dump`, `exfiltrate`… se rechaza en el
  `crear_scope` (error + motivo). No existe ruta de código para esas acciones.
- Verificación de cada acción/objetivo: firma HMAC (comparación en tiempo
  constante), caducidad, acción permitida y coincidencia de target (host
  exacto, `*.dominio` o CIDR). Violaciones → bloqueo + `secops.denegado` en
  el ledger + artífice de la ejecución.

Honestidad sobre "seguro técnico": la clave vive en el propio workspace, así
que el token **no protege contra el dueño del workspace** —y ningún formulario
firmado puede hacerlo. Lo que sí es estructural: el motor no contiene munition
(no hay código de explotación, volcado ni evasión que el token pudiera
autorizar). Para un contrato real, la autoridad firmante debería ser externa
al agente; eso también está documentado aquí como límite.

## 2. Simulación (default, sin red)

```bash
a2s secops ejecutar "reconocimiento web" --targets 127.0.0.1 --workspace lab
# o desde el dashboard: POST /api/secops/plan {"objetivo": "...", "targets": [...]}
```

Devuelve el **plan completo**: cadena de sinergia (web-check → osint4all →
nuclei → …), qué haría el agente (tipo `recon`/`scan`/`analizar`), qué
ejecuta **el operador** (metasploit, sqlmap, hashcat…: A²S no los automatiza)
y qué quedaría retenido sin alcance. Cero llamadas de red, cero procesos.

## 3. Ejecución asistida (solo defensiva, con alcance)

```bash
# Recon de activo propio (un GET benigno + handshake TLS)
a2s secops ejecutar "reconocimiento web" \
  --modo asistido --targets https://lab.miempresa.cl --confirm --workspace lab

# Escaneo con escáner local instalado (nuclei -jsonl / trivy)
a2s secops ejecutar "vulnerabilidades" \
  --modo asistido --targets 127.0.0.1 --confirm --workspace lab
#   (--templates mis-plantillas.yaml opcional; nuclei/trivy deben estar instalados)

# Análisis estático de un artefacto del workspace (magic, strings, EXIF,
# SHA-256; Ghidra analyzeHeadless si está instalado)
a2s secops ejecutar "reversing binario" \
  --modo asistido --archivo forense/muestra.bin --workspace lab
```

Reglas de la ejecución: `recon`/`scan` exigen **target dentro del scope** y
`--confirm`; `analizar` exige archivo dentro del workspace (fuera → bloqueo).
Los pasos `recon` son **un GET por objetivo** con User-Agent honesto (sin
rotación de proxies ni "anti-detección": eso es evasión, no está en el
vocabulario). Resultados en `workspace/.a2s/secops/<run>/{resumen.json,
informe.md}` y cada paso en el ledger.

## 4. API del Control Plane

- `GET /api/secops` → estado del alcance + útlimo run.
- `POST /api/secops/plan` → **solo simulación** (la ejecución asistida queda
  en CLI con `--confirm`; la UI no dispara red).

## 5. Límites (por diseño, no negociables)

| Pedido | Estado |
|---|---|
| Ejecutar exploits Metasploit/sqlmap, generar payloads, dumpear BD, post-explotación/exfiltración | No existe en el código |
| Worm-GPT / LLM sin filtros, jailbreaks | No existe |
| Creación masiva de cuentas, anti-detección, proxies rotativos | No existe |
| `módulo_escáner` con alcance + confirm (nuclei/trivy sobre tu lab) | **Sí** |
| Recon HTTP/TLS de activos propios + análisis estático local | **Sí** |
| Token que pida acciones fuera del vocabulario | Rechazado al crear |

Si un evaluador (o un evaluador de tu tesis) pregunta por qué A²S no ejecuta
exploits: la respuesta honesta es que el **alcance autorizado se demuestra
con el proceso y el registro**, y la **munición no es necesaria** para
aprender ni para auditar — de hecho, un framework de evaluación con código de
explotación embebido es un riesgo académico y de responsabilidad, no una
ventaja.

## 6. Validación

`tests/test_secops.py`: alcance (crear/verificar/manipular firma/caducidad/
CIDR/acción fuera de lista), simulación sin red, denegación con auditoría,
recon real contra servidor HTTP local en `127.0.0.1`, analizar local con
SHA-256 y strings, CLI end-to-end. Sin servicios de pago ni red externa.
