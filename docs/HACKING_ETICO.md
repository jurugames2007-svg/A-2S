# Hacking ético y fines académicos con A²S (v1.26)

> Este documento define el **flujo autorizado** del catálogo: cómo un
> estudiante, investigador o red-teamer con alcance usa A²S para estudio y
> práctica, qué queda habilitado, qué queda bloqueado y —sin rodeos— por qué.

## 1. Flujo académico en 3 pasos

```bash
# 1) Registra el marco (auditable, queda en workspace/.a2s/alcance.json)
a2s capacidades --alcance --perfil lab \
  --nota "DVWA y Metasploitable en VM local (clase de la U)"

# 2) Enruta tu objetivo con el perfil
a2s capacidades --ruta "reconocimiento web" --perfil lab
#    → pasos: web-check, osint4all, study-notes
#    → ahora NUCLEI pasa de «bloqueado» a «habilitado»
#      (sigue exigiendo alcance en el CLI de Nuclei; A²S no lo dispara solo)

# 3) Ingiera el material de estudio (solo READMEs, nunca ejecuta código)
a2s capacidades --ingesta --solo payloads-all-things,ghidra,web-check
```

Perfiles disponibles: `ctf` (HTB/THM/VulnHub), `lab` (Metasploitable, DVWA,
Juice Shop, Kali), `propio` (infraestructura/datos/binarios propios),
`universidad` (laboratorio académico con autorización docente/comité). El
perfil **no se auto-declara al enrutar**: el archivo de alcance debe existir
antes; si no, la ruta queda retenida con el motivo exacto.

## 2. Qué queda habilitado para estudio autorizado

| Área | Recursos del catálogo | Cómo lo usa A²S |
|---|---|---|
| Reconocimiento | web-check, osint4all, study-notes | auditoría de activos/dominios propios o del laboratorio; datos públicos contrastados |
| Escaneo | nuclei, trivy, web-check | plantillas sobre el alcance registrado; SBOM/imágenes propias |
| Reversing/forense | ghidra, imhex, x64dbg, cyberchef | análisis de binarios propios o de reto; equivalente interno: `file_magic`, `strings`, EXIF, hashes |
| Cripto/secretos | vault, openssl, cyberchef | gestión de secretos del operador, firmas HMAC, certificados propios |
| Automatización | n8n, ruflo, agency-agents, real-world-llm-apps | patrones → máquinas de estado / DAG del pool SORL |
| Prompting | claude-courses, karpathy-skills, system-prompts-leaks, agency-agents | fichas y contrato Aegis; auditoría defensiva de prompts |
| Estudio ML/arquitectura | ZTM ML, ByteByteGo, SDD-101, h4cker | fichas de conocimiento, misiones de entrenamiento |

## 3. Lo que se ejecuta en tu lab (no dentro del agente) y lo que no

1. **Exploits/payloads de Metasploit, sqlmap o PayloadsAllTheThings: se
   ejecutan en TU laboratorio, no dentro de A²S.** Con el alcance
   registrado (`--perfil lab/ctf/propio/universidad`) el enrutador los
   reconoce como eslabones de la cadena (`sqlmap`, `metasploit`, `nuclei`,
   `hashcat`, `hackingtool` entran en `pasos` con uso `parcial` y su
   requerimiento `autorizacion_escrita` cubierto). A²S no porta ni ejecuta
   su código: el diseño anti supply-chain y stdlib puro se mantienen, la
   ejecución la hace **el operador** en el entorno autorizado, y A²S deja
   el registro, el alcance y la verificación. El valor académico del método
   (reconocimiento → análisis → informe) se conserva íntegro.
2. **Worm-GPT / LLMs «sin filtros».** Estudiar su existencia está en el
   catálogo; integrarlo no aporta a la investigación (sin procedencia
   verificable) y sí riesgo.
3. **Automatización masiva de cuentas de Google (gmail-account-creator).**
   La integración legítima es la API oficial sobre tu cuenta principal
   (receta documentada); la creación de cuentas en masa incumple ToS y no
   es «ética» por contexto académico.
4. **Zonas grises** (streaming sin licencia, deepweb, réplicas): se estudian
   como referencia; no se automatizan.

## 4. Qué ganas frente a «copiar y pegar código»

- **Pipeline con cadena de custodia**: cada paso queda en el ledger encadenado
  por SHA-256; el informe final es verificable (`a2s verify`).
- **Puerta explícita**: tu alcance queda escrito, fechado y consultable
  (`a2s capacidades --alcance`); es la evidencia de que la práctica estuvo
  autorizada.
- **Conocimiento con fuente**: fichas con licencia, repo y resumen
  (`a2s search --origen ficha`), citables en la tesis.
- **Sin dependencias arbitrarias**: stdlib puro; el sandbox y la lista
  blanca de shell siguen activos cuando corres tus propios laboratorios.

## 5. Recordatorio de legalidad local

El alcance académico no convierte en legal un objetivo ajeno sin
autorización (ni en un país las pruebas en infraestructura de terceros
suben el riesgo legal). Los entornos recomendados son los que ya están
pensados para esto: HTB/THM/VulnHub/Metasploitable/DVWA/OWASP Juice Shop,
VM local, o infraestructura con contrato de pruebas firmado. A²S registra
el alcance, pero quien responde es el operador.
