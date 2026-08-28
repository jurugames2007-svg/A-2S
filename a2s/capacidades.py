"""Capa de capacidades del catálogo (v1.26): de lista de enlaces a mapa accionable.

Traduce las entradas de ``recursos.py`` en conocimiento de ingeniería: qué
capacidad aporta cada recurso, con qué **uso autónomo** (sí / parcial /
operador / referencia), qué necesita (CLI, API key, hardware, autorización),
qué equivalente interno de A²S la cubre y con qué otros recursos encadena.

Fronteras honestas (no configurables):

* **Conocimiento, no armamento**: la ingesta asimila READMEs públicos vía la
  API de GitHub (solo lectura, cuotas respetadas) y **nunca clona, instala ni
  ejecuta** el código estudiado. La frontera anti supply-chain de ``learner``
  queda intacta; para contenido prohibido se aplica ``classify_forbidden``.
* **Puerta de autorización**: las rutas que requieren alcance escrito
  (explotación, payloads en vivo, recuperación de hashes ajenos) se mueven a
  ``bloqueados`` salvo que exista ``workspace/.a2s/alcance.json`` que autorice
  el objetivo; siempre se ofrece la alternativa defensiva equivalente.
* **Zona gris = referencia**: streaming sin licencia, deepweb, réplicas y
  modelos «sin filtros» se marcan ``no`` (solo documentación, sin recetas
  operativas).
* El enrutador es determinista y auditable: publica qué rama eligió, por qué y
  qué quedó fuera; no finge capacidades que el entorno no tiene.

Uso: ``a2s capacidades`` (resumen), ``a2s capacidades ruta OBJETIVO``
(rutado con puerta de autorización), ``a2s capacidades ingesta`` (READMEs a
fichas de conocimiento), ``a2s capacidades mapa`` (informe completo),
``GET /api/capacidades`` en el Control Plane.
"""

from __future__ import annotations

import json
import os
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import now_iso
from .pcb import _atomic_write
from .recursos import AVISO_ETICO, ENTRADAS, _CAT_NOMBRE, extras
from .search import BM25Index, Doc

# ---------------------------------------------------------------------------
# Vocabulario canónico
# ---------------------------------------------------------------------------

DOMINIOS: tuple[str, ...] = (
    "cognitiva", "ciber", "automatizacion", "infraestructura", "datos", "utilidades",
)

DOMINIO_NOMBRE: dict[str, str] = {
    "cognitiva": "Capacidad cognitiva",
    "ciber": "Ciber-inteligencia",
    "automatizacion": "Automatización",
    "infraestructura": "Infraestructura",
    "datos": "Fuentes de datos",
    "utilidades": "Utilidades",
}

USO_NOMBRE: dict[str, str] = {
    "si": "autónomo (A²S lo aplica solo)",
    "parcial": "parcial (requiere CLI/API/servicio instalado)",
    "operador": "operador (decisión manual; A²S prepara)",
    "no": "referencia (zona gris; no se integra)",
}

REQ_NOMBRE: dict[str, str] = {
    "cliente_github": "API de GitHub (solo lectura)",
    "api_key_google": "credenciales Google del operador (API oficial)",
    "credenciales_propias": "credenciales del operador (nunca en claro)",
    "entorno_n8n": "instancia n8n del operador",
    "entorno_ruflo": "entorno RuFlo del operador",
    "entorno_claude_code": "Claude Code / asistente inyectable",
    "navegador_web": "navegador del operador",
    "claves_llm_propias": "claves de proveedores LLM del operador",
    "cli_ghidra": "CLI/servidor Ghidra instalado",
    "cli_imhex": "ImHex instalado",
    "cli_x64dbg": "x64dbg en Windows",
    "cli_metasploit": "Metasploit instalado",
    "cli_sqlmap": "sqlmap instalado",
    "cli_nuclei": "Nuclei instalado",
    "cli_trivy": "Trivy instalado",
    "cli_hashcat": "hashcat instalado",
    "cli_mitmproxy": "mitmproxy instalado",
    "cli_hackingtool": "HackingTool instalado",
    "cli_openssl": "OpenSSL CLI instalado",
    "hardware_gpu": "GPU (hashcat)",
    "servidor_propio": "servidor/infraestructura propia",
    "servidor_vpn": "servidor VPN propio (VPS/VM)",
    "servidor_vault": "instancia Vault del operador",
    "servidor_dns_propio": "servidor DNS propio",
    "docker": "motor de contenedores",
    "android": "terminal/emulador Android",
    "windows": "entorno Windows",
    "red_tor": "red Tor (riesgo elevado)",
    "entorno_autorizado": "entorno autorizado (CTF/lab propio)",
    "autorizacion_escrita": "alcance escrito firmado",
    "operador_manual": "decisión del operador",
    "configuracion_propia": "configuración propia del operador",
    "urls_propias": "dominios/URLs propios",
    "hashes_propios": "hashes propios o de CTF",
    "regulacion_local": "verificación regulatoria local",
    "riesgo_financiero": "riesgo de pérdida (finanzas)",
    "suscripcion": "suscripción/servicio de pago",
    "servicio_web": "servicio web externo",
}

_CAT_DOMINIO: dict[str, str] = {
    "ia": "cognitiva",
    "ciber": "ciber",
    "dev": "infraestructura",
    "directorios": "datos",
    "utilidades": "utilidades",
    "empleo": "utilidades",
}


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Capacidad:
    """Qué aporta un recurso del catálogo y cómo lo usa A²S."""

    id: str
    dominio: str
    capacidad: str
    uso: str
    requiere: tuple[str, ...] = ()
    mapa_a2s: tuple[str, ...] = ()
    receta: tuple[str, ...] = ()
    etico: str = ""
    sinergias: tuple[str, ...] = ()
    core: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dominio": self.dominio,
            "dominio_nombre": DOMINIO_NOMBRE.get(self.dominio, self.dominio),
            "capacidad": self.capacidad,
            "uso": self.uso,
            "uso_nombre": USO_NOMBRE.get(self.uso, self.uso),
            "requiere": list(self.requiere),
            "requiere_nombre": [REQ_NOMBRE.get(r, r) for r in self.requiere],
            "mapa_a2s": list(self.mapa_a2s),
            "receta": list(self.receta),
            "etico": self.etico,
            "sinergias": list(self.sinergias),
            "core": self.core,
        }


def _e(ident: str, dominio: str, capacidad: str, uso: str,
       requiere: tuple[str, ...] = (), mapa: tuple[str, ...] = (),
       receta: tuple[str, ...] = (), etico: str = "",
       sinergias: tuple[str, ...] = (), core: bool = False) -> dict[str, Any]:
    return {"id": ident, "dominio": dominio, "capacidad": capacidad, "uso": uso,
            "requiere": requiere, "mapa_a2s": mapa, "receta": receta,
            "etico": etico, "sinergias": sinergias, "core": core}


# ---------------------------------------------------------------------------
# Especificación por entrada del catálogo (65/65)
# ---------------------------------------------------------------------------

_ESPEC: tuple[dict[str, Any], ...] = (
    _e("claude-courses", "cognitiva", "prompt_engineering", "si",
       ("cliente_github",), ("aegis_protocol.analyze_request", "learner.GitHubClient"),
       ("Ingerir el temario oficial (página + repo espejo).",
        "Destilar las técnicas de prompting en fichas de conocimiento.",
        "Aplicarlas a prompts/misiones y verificar con el verificador de objetivo."),
       "Contenido oficial de Anthropic: A²S aplica las técnicas, no publica el material.",
       ("system-prompts-leaks", "karpathy-skills", "agency-agents"), True),
    _e("anthropic-courses", "cognitiva", "prompt_engineering", "si",
       ("cliente_github",), ("learner.GitHubClient",),
       ("Leer README/estructura del espejo en GitHub.",
        "Comparar con la web oficial y destilar lo no incluido."),
       "Espejo del curso oficial; verificar fecha y rama actual antes de citar.",
       ("claude-courses",)),
    _e("coursera-ai", "cognitiva", "estudio_ia", "parcial",
       ("credenciales_propias",), ("search.workspace_search", "learner.GitHubClient"),
       ("Buscar material público asociado (syllabus, referencias).",
        "Crear temario de estudio en fichas de conocimiento."),
       "Curso con matrícula: A²S solo enlaza y estudia lo abierto."),
    _e("n8n-workflows", "automatizacion", "orquestacion_workflows", "parcial",
       ("entorno_n8n",), ("fsm", "watch", "provider_pool.ProviderPool"),
       ("Analizar los JSON de workflows como patrones de orquestación.",
        "Convertir el patrón en máquina de estados determinista (`a2s fsm`).",
        "Validar la secuencia con un verificador de objetivo."),
       "Patrones de la comunidad: revisar licencia de cada workflow.",
       ("agency-agents", "ruflo"), True),
    _e("ruflo", "automatizacion", "orquestacion_agentes", "parcial",
       ("entorno_ruflo",), ("provider_pool.ProviderPool", "aegis_protocol.analyze_request"),
       ("Estudiar las primitivas de orquestación (docs/README).",
        "Mapearlas a fanout/DAG del pool SORL (`execute_dag`).",
        "Probar con una misión demo acotada."),
       "Framework del operador (revisar licencia y mantenedor).",
       ("n8n-workflows", "agency-agents"), True),
    _e("aifreeforever", "datos", "directorio_ia", "operador",
       ("operador_manual",), ("tools.fetch_url",),
       ("Filtrar el directorio por categoría.",
        "Verificar términos, caducidad y reputación de cada oferta."),
       "Directorios de terceros: términos y caducidad bajo el operador."),
    _e("tranchi-ai", "datos", "directorio_ia", "operador",
       ("operador_manual",), ("tools.fetch_url",),
       ("Revisar la ficha de la herramienta.",
        "Verificar reputación y términos antes de usarla."),
       "Servicio de terceros: revisar política antes de subir datos."),
    _e("wormgpt", "ciber", "modelo_sin_filtros", "no",
       ("autorizacion_escrita", "operador_manual"), (),
       ("Consultar solo como referencia documental.",
        "No integrar, instalar ni ejecutar.",
        "Registrar en el ledger cualquier petición de automatizarlo."),
       "Modelo sin procedencia ni garantías (repo de terceros): A²S no lo integra."),
    _e("karpathy-skills", "cognitiva", "prompt_engineering_coding", "si",
       ("cliente_github",), ("aegis_protocol.analyze_request", "planner"),
       ("Ingerir el CLAUDE.md (los 4 principios de Karpathy).",
        "Convertirlos en directiva interna anti-alucinación de código."),
       "Colección derivada, no oficial: contrastar con la fuente primaria.",
       ("claude-courses", "agency-agents", "system-prompts-leaks"), True),
    _e("zero-to-mastery-ml", "cognitiva", "estudio_ml", "si",
       ("cliente_github",), ("learner.KnowledgeCard", "search.BM25Index"),
       ("Analizar el índice del curso (notebooks y guías).",
        "Destilar ejercicios en misiones de entrenamiento."),
       "Material con licencia propia: A²S no ejecuta los notebooks.",
       ("coursera-ai",)),
    _e("agency-agents", "automatizacion", "agentes_dominio", "parcial",
       ("cliente_github", "entorno_claude_code"), ("aegis_protocol.analyze_request",
                                                    "provider_pool.ProviderPool"),
       ("Ingerir los agentes especializados (Markdown de dominio).",
        "Mapear cada agente a rutinas/capacidades nativas de A²S."),
       "Agentes inyectables de terceros: revisar su procedencia.",
       ("karpathy-skills", "real-world-llm-apps"), True),
    _e("godmode", "automatizacion", "multi_chat_llm", "parcial",
       ("navegador_web", "claves_llm_propias"), ("provider_pool.ProviderPool",),
       ("Estudiar el patrón multi-proveedor con una sola interfaz.",
        "Reusar la idea en el pool SORL (una interfaz, varios proveedores)."),
       "Codigo de la comunidad: estudiar el diseño, sin ejecutar el binario."),
    _e("real-world-llm-apps", "automatizacion", "apps_llm_produccion", "si",
       ("cliente_github",), ("provider_pool", "planner", "loop"),
       ("Estudiar los casos reales (browser agent, RAG, eval, recruiter).",
        "Mapear cada patrón a una misión nativa con verificador."),
       "Catálogo de ejemplos: adaptar ideas, no copiar código sin licencia.",
       ("agency-agents", "ruflo"), True),
    _e("kaspersky-cybermap", "ciber", "visualizacion_amenazas", "operador",
       ("operador_manual",), ("tools.fetch_url",),
       ("Consultar el mapa como fuente visual.",
        "Anexar la instantánea al informe con fecha y fuente."),
       "Solo lectura de un widget público; sin sondeo adicional."),
    _e("grayhat-warfare", "ciber", "estudio_exploits", "parcial",
       ("operador_manual",), ("search.workspace_search",),
       ("Buscar write-ups/retos sobre un CVE.",
        "Destilar la técnica en una ficha (sin payloads listos para disparar).",
        "Aplicar únicamente en un entorno autorizado."),
       "Estudio técnico: A²S no dispara payloads contra sistemas ajenos."),
    _e("osint4all", "ciber", "osint_datos_publicos", "parcial",
       ("operador_manual",), ("tools.web_search", "tools.fetch_url"),
       ("Consultar el dashboard de fuentes de información pública.",
        "Contrastar cada dato con la fuente original.",
        "No suplantar identidades ni hacer scraping masivo."),
       "Información pública con responsabilidad: sin suplantación ni recolección masiva.",
       ("web-check", "study-notes"), True),
    _e("study-notes", "ciber", "top_repos_seguridad", "si",
       ("cliente_github",), ("learner.GitHubClient", "search.BM25Index"),
       ("Ingerir el resumen de repos destacados de seguridad.",
        "Actualizar fichas de herramientas con licencia y vigencia."),
       "Resumen de terceros: contrastar con el repo original."),
    _e("book-secret-knowledge", "datos", "compendio_herramientas", "parcial",
       ("cliente_github",), ("search.BM25Index", "learner.GitHubClient"),
       ("Usar como índice de referencia por categoría.",
        "Validar licencia, actualidad y alcance antes de aplicar."),
       "Catálogo masivo: selectivo, autorizado y con atribución.",
       ("awesome-hacking", "awesome-pentest"), True),
    _e("awesome-hacking", "datos", "directorio_aprendizaje_ctf", "si",
       ("cliente_github",), ("search.BM25Index",),
       ("Filtrar el directorio por tema.",
        "Convertir recursos en fichas de estudio."),
       "Directorio educativo: cada recurso conserva su propia licencia."),
    _e("payloads-all-things", "ciber", "tecnicas_pruebas", "parcial",
       ("autorizacion_escrita", "entorno_autorizado"), ("search.BM25Index",),
       ("Consultar como referencia de técnicas y categorías.",
        "Usarlo para redactar casos de prueba en entornos propios.",
        "No automatizar el lanzamiento contra sistemas ajenos."),
       "Referencia técnica para pruebas autorizadas, nunca ejecución ofensiva en vivo."),
    _e("ghidra", "ciber", "reversing_binario", "parcial",
       ("cli_ghidra", "entorno_autorizado"),
       ("plugin.forensics_extra", "plugin.crypto_tools"),
       ("Detectar el binario con `file_magic` y extraer cadenas.",
        "Si Ghidra está instalado, descompilar la muestra propia.",
        "Cruzar resultados con hashes SHA-256 (cadena de custodia)."),
       "Análisis de binarios propios/CTF; nunca de software ajeno sin autorización.",
       ("imhex", "x64dbg", "cyberchef"), True),
    _e("hackingtool", "ciber", "suite_pruebas_cli", "parcial",
       ("cli_hackingtool", "autorizacion_escrita", "entorno_autorizado"),
       ("tools.shell",),
       ("Usar en el laboratorio autorizado con el operador presente.",
        "Registrar cada ejecución con su alcance."),
       "Suite agregada: solo entorno autorizado; A²S no automatiza su ejecución."),
    _e("imhex", "ciber", "analisis_binario_hex", "parcial",
       ("cli_imhex",), ("plugin.forensics_extra.extract_strings",
                        "plugin.forensics_extra.file_magic"),
       ("Inspeccionar el binario con patrones hex.",
        "Usar el lenguaje de patrones solo sobre muestras propias."),
       "Análisis binario de artefactos propios.",
       ("ghidra", "x64dbg")),
    _e("v2rayng", "infraestructura", "cliente_proxy_android", "operador",
       ("android", "configuracion_propia"), (),
       ("Configurar el cliente con el servidor propio.",
        "Verificar términos y legalidad de la red del operador."),
       "Proxy/censura: configuración propia y legalidad local."),
    _e("x64dbg", "ciber", "depuracion_windows", "parcial",
       ("cli_x64dbg", "windows"), ("plugin.forensics_extra",),
       ("Depurar solo muestras propias en Windows.",
        "Registrar trazas con cadena de custodia."),
       "Depurador: uso exclusivo sobre software propio o autorizado.",
       ("ghidra", "imhex")),
    _e("mitmproxy", "ciber", "inspeccion_trafico", "parcial",
       ("cli_mitmproxy", "entorno_autorizado"), ("tools.fetch_url", "tools.shell"),
       ("Interceptar tráfico de servicios propios.",
        "Parsear los hallazgos al informe con la fuente."),
       "Solo tráfico propio/autorizado; nunca credenciales de terceros."),
    _e("metasploit", "ciber", "explotacion_framework", "parcial",
       ("cli_metasploit", "autorizacion_escrita", "entorno_autorizado"), (),
       ("Preparar el laboratorio (Metasploitable/Kali) y registrar alcance.",
        "El operador ejecuta el framework en el entorno autorizado.",
        "Documentar resultados con cadena de custodia."),
       "Uso exclusivo en laboratorio/alcance registrado; A²S no porta ni ejecuta exploits."),
    _e("sqlmap", "ciber", "deteccion_sqli", "parcial",
       ("cli_sqlmap", "autorizacion_escrita", "entorno_autorizado"), (),
       ("Usar solo sobre el objetivo autorizado del lab.",
        "Registrar alcance, parámetros y salida en el informe.",
        "No automatizar contra sistemas ajenos al alcance."),
       "Pruebas de inyección exclusivamente sobre el alcance registrado."),
    _e("xray-core", "infraestructura", "proxy_xray", "parcial",
       ("servidor_propio",), ("tools.fetch_url",),
       ("Desplegar sobre infraestructura propia.",
        "Configurar listas de retención y auditoría."),
       "Proxy: uso en servidores propios y legalidad local."),
    _e("vault", "infraestructura", "gestion_secretos", "parcial",
       ("servidor_vault", "credenciales_propias"), ("vault", "signing"),
       ("Usar la instancia del operador para secretos.",
        "A²S nunca persiste secretos en claro en el workspace.",
        "Rotar claves y registrar accesos."),
       "Defensa: gestión de secretos con la bóveda del operador.",
       ("openssl", "cyberchef"), True),
    _e("cyberchef", "ciber", "codificacion_cifrado", "si",
       (), ("plugin.crypto_tools", "plugin.forensics_extra.pdf_metadata"),
       ("Decodificar/detectar formatos con utilidades stdlib.",
        "Verificar cada transformación por una segunda vía."),
       "Análisis de artefactos propios (codificación, cifrado, metadatos).",
       ("ghidra", "imhex"), True),
    _e("v2ray-core", "infraestructura", "nucleo_proxy", "parcial",
       ("servidor_propio",), (),
       ("Instalar el núcleo en servidor propio.",
        "Configurar con listas propias y monitoreo."),
       "Servidor propio y legalidad local."),
    _e("adguard-home", "infraestructura", "dns_defensa", "parcial",
       ("servidor_dns_propio",), ("tools.fetch_url",),
       ("Desplegar en infraestructura propia.",
        "Revisar listas de bloqueo antes de aplicarlas."),
       "Defensa: DNS propio, sin almacenar tráfico de terceros.",
       ("stevenblack-hosts",)),
    _e("trivy", "ciber", "escaneo_contenedores", "parcial",
       ("cli_trivy", "docker"), ("plugin.repo_audit",),
       ("Escanear imágenes propias y SBOM.",
        "Triar por severidad y fecha de CVE.",
        "Persistir el informe con hash."),
       "Defensa: escaneo de artefactos propios.",
       ("web-check", "nuclei"), True),
    _e("web-check", "ciber", "auditoria_web", "parcial",
       ("entorno_autorizado", "urls_propias"), ("tools.fetch_url", "tools.web_search"),
       ("Auditar cabeceras, TLS, DNS y subdominios de dominios propios.",
        "Parsear los hallazgos a un informe estructurado.",
        "Contrastar con una segunda fuente."),
       "Defensa: auditoría de activos propios, sin sondeo de terceros.",
       ("osint4all", "trivy", "nuclei"), True),
    _e("algo", "infraestructura", "vpn_wireguard", "parcial",
       ("servidor_vpn",), ("tools.shell",),
       ("Desplegar en VPS propio con las guías del proyecto.",
        "Verificar claves y rotación."),
       "VPN autoalojada sobre infraestructura propia.",
       ("setup-ipsec-vpn", "xray-core")),
    _e("stevenblack-hosts", "infraestructura", "listas_bloqueo_dns", "parcial",
       ("cliente_github",), ("tools.fetch_url",),
       ("Fusionar la lista agregada con la propia.",
        "Aplicar en el resolutor y revisar falsos positivos."),
       "Defensa: listas de bloqueo sobre DNS propio.",
       ("adguard-home",)),
    _e("openssl", "infraestructura", "cripto_tls", "parcial",
       ("cli_openssl",), ("plugin.crypto_tools", "signing"),
       ("Generar/verificar certificados propios.",
        "Auditar configuraciones TLS con utilidades internas."),
       "Criptografía de referencia para infraestructura propia.",
       ("vault",), True),
    _e("setup-ipsec-vpn", "infraestructura", "servidor_ipsec", "parcial",
       ("servidor_vpn",), ("tools.shell",),
       ("Instalar el servidor en VPS propio.",
        "Documentar credenciales en el gestor de secretos."),
       "VPN autoalojada: infraestructura propia y legalidad local.",
       ("algo",)),
    _e("nuclei", "ciber", "escaneo_plantillas", "parcial",
       ("cli_nuclei", "autorizacion_escrita"), ("plugin.repo_audit",),
       ("Ejecutar plantillas únicamente sobre alcance autorizado.",
        "Registrar el alcance y el resultado en el informe."),
       "Solo alcance autorizado; A²S la mantiene tras la puerta de autorización.",
       ("web-check", "trivy")),
    _e("hashcat", "ciber", "recuperacion_hash", "parcial",
       ("hardware_gpu", "autorizacion_escrita", "hashes_propios"), (),
       ("Recuperar solo hashes propios o de CTF.",
        "Documentar el diccionario y los modos usados."),
       "Auditoría autorizada; nunca credenciales de terceros."),
    _e("awesome-pentest", "datos", "directorio_pentest", "si",
       ("cliente_github",), ("search.BM25Index",),
       ("Filtrar el directorio por categoría.",
        "Convertir hallazgos en fichas de estudio."),
       "Directorio educativo: cada herramienta conserva su licencia."),
    _e("h4cker", "datos", "curso_pentesting", "si",
       ("cliente_github",), ("learner.GitHubClient",),
       ("Estudiar los notebooks de la suite educativa.",
        "Mapear ejercicios a misiones de entrenamiento."),
       "Material educativo: A²S no ejecuta el código del curso."),
    _e("system-prompts-leaks", "ciber", "auditoria_prompts", "si",
       ("cliente_github",), ("aegis_protocol.analyze_request", "search.BM25Index"),
       ("Ingerir los prompts publicados con procedencia.",
        "Analizar patrones de guardarraíl y de inyección.",
        "Aplicar lecciones al contrato Aegis (sin copiar texto ajeno)."),
       "Auditoría y estudio defensivo de filtraciones públicas, en entornos autorizados.",
       ("claude-courses", "karpathy-skills"), True),
    _e("gmail-account-creator", "ciber", "api_google_automation", "parcial",
       ("credenciales_propias", "api_key_google", "autorizacion_escrita"),
       ("tools.fetch_url", "vault"),
       ("Integrar solo la API oficial de Google sobre la cuenta principal del operador.",
        "Guardar credenciales en el gestor de secretos, nunca en claro.",
        "No automatizar creación de cuentas ni saltarse políticas de Google."),
       "Cuenta propia y términos de Google; el enfoque del repo (creación masiva) no se integra.",
       ("gworkspace-cli",)),
    _e("gworkspace-cli", "infraestructura", "cli_workspace", "parcial",
       ("credenciales_propias", "api_key_google"), ("tools.shell", "tools.fetch_url"),
       ("Automatizar la administración del Workspace propio.",
        "Limitar permisos y auditar cambios."),
       "Administración del propio tenant con la CLI oficial.",
       ("gmail-account-creator",)),
    _e("bytebytego", "infraestructura", "system_design", "si",
       (), ("search.BM25Index", "pdf.MiniPDF"),
       ("Ingerir los artículos del blog.",
        "Destilar patrones de arquitectura en fichas.",
        "Usarlos en informes de diseño con cita."),
       "Contenido editorial: citar la fuente al usarlo.",
       ("sdd-101",)),
    _e("sdd-101", "infraestructura", "system_design", "si",
       ("cliente_github",), ("search.BM25Index",),
       ("Estudiar las guías ilustradas.",
        "Usarlas como base de fichas de arquitectura."),
       "Material con licencia propia: estudio, no copia para otros canales.",
       ("bytebytego",)),
    _e("octocademy", "utilidades", "utils_libreria", "parcial",
       ("cliente_github",), ("search.BM25Index",),
       ("Estudiar las utilidades y su licencia.",
        "Portar al núcleo solo lo que aplique y tenga licencia compatible."),
       "Verificar licencia antes de incorporar cualquier función."),
    _e("open-source-games", "datos", "juegos_oss", "si",
       ("cliente_github",), ("search.BM25Index",),
       ("Filtrar por motor/licencia.",
        "Registrar como referencia de juegos propios."),
       "Solo proyectos de código abierto con licencia verificada."),
    _e("fmhy", "datos", "directorio_medios", "no",
       ("operador_manual",), (),
       ("Consultar solo como referencia documental.",
        "No automatizar descargas ni integración."),
       "Zona gris de legalidad local: A²S no la automatiza."),
    _e("yarrlist", "datos", "listas_torrents", "no",
       ("operador_manual",), (),
       ("Consultar solo como referencia documental.",
        "No automatizar descargas ni integración."),
       "Verificar legalidad local: sin automatización."),
    _e("deepwebnest", "datos", "buscador_onion", "no",
       ("red_tor", "operador_manual"), (),
       ("Consultar solo como referencia documental.",
        "No conectarse ni automatizar búsquedas."),
       "Fishing/criminalidad alta: no se integra."),
    _e("flixer", "datos", "streaming_no_licenciado", "no",
       ("operador_manual",), (),
       ("Consulta documental únicamente.",
        "No automatizar acceso ni descargas."),
       "Sin licencia verificable: A²S no la automatiza."),
    _e("anker-games", "datos", "juegos_no_verificados", "no",
       ("operador_manual",), (),
       ("Consulta documental únicamente.",
        "Verificar licencias antes de cualquier uso."),
       "Zona gris: sin automatización."),
    _e("imagetotext", "utilidades", "ocr", "parcial",
       ("servicio_web", "operador_manual"), ("tools.fetch_url",),
       ("Usar el servicio con imágenes propias.",
        "No subir documentos ajenos ni sensibles."),
       "OCR externo: privacidad y ToS del servicio."),
    _e("veepn", "utilidades", "vpn_comercial", "operador",
       ("suscripcion", "operador_manual"), (),
       ("Comparar política de privacidad y jurisdicción.",
        "Decidir el uso bajo responsabilidad del operador."),
       "Servicio comercial: verificación de términos antes de pagar."),
    _e("delphi-tools", "utilidades", "utilidades_web_dev", "operador",
       ("operador_manual",), ("tools.fetch_url",),
       ("Probar cada utilidad con datos propios.",
        "Verificar términos y retención del servicio."),
       "Utilidades web de terceros."),
    _e("sideshift", "utilidades", "finanzas_cripto", "operador",
       ("operador_manual", "regulacion_local"), (),
       ("Revisar regulación local y comisiones.",
        "Operar solo con la decisión del operador."),
       "Finanzas: riesgo de pérdida, sin consejo automatizado."),
    _e("invoapp", "utilidades", "copy_trading", "operador",
       ("operador_manual", "riesgo_financiero"), (),
       ("Revisar el enlace de referido y los términos.",
        "Entender el riesgo de pérdida antes de operar."),
       "Inversión con riesgo; enlace de referido declarado."),
    _e("four-day-week", "utilidades", "empleo_remoto", "operador",
       ("operador_manual",), ("tools.web_search",),
       ("Filtrar ofertas por jornada y ubicación.",
        "Preparar una solicitud con la información pública."),
       "Empleo: A²S prepara, el operador decide."),
    _e("instahyre", "utilidades", "talento", "operador",
       ("operador_manual",), ("tools.web_search",),
       ("Buscar oportunidades como fuente pública.",
        "Preparar material de candidatura."),
       "Empleo: A²S prepara, el operador decide."),
    _e("darebee", "utilidades", "fitness", "operador",
       ("operador_manual",), ("tools.fetch_url",),
       ("Elegir un plan con la biblioteca pública.",
        "Registrar el plan como objetivo del operador."),
       "Salud: sin consejo médico; planes de la comunidad."),
    _e("nealfun", "utilidades", "juegos_interactivos", "operador",
       ("operador_manual",), ("tools.fetch_url",),
       ("Explorar los experimentos.",
        "Usarlos como material de entretenimiento/educación."),
       "Entretenimiento: contenido propiedad del sitio."),
    _e("fashionreps", "datos", "comunidad_moda", "no",
       ("operador_manual",), (),
       ("Consulta documental sobre la comunidad.",
        "No automatizar compras ni suplantación."),
       "Zona gris (réplicas): A²S no la automatiza."),
)

_ESPEC_POR_ID: dict[str, dict[str, Any]] = {s["id"]: s for s in _ESPEC}

# Adaptadores nativos implementados fuera de las especificaciones históricas.
_ADAPTADORES_NATIVOS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "public-apis": ("catalogo_apis_https", ("integrations.PublicAPIManager",),
            ("Registrar APIs con base HTTPS.", "Buscar y llamar solo rutas del host registrado.")),
    "pm2": ("gestion_procesos_locales", ("integrations.ProcessManager",),
        ("Iniciar procesos con argumentos, sin shell.", "Monitorizar estado y consultar logs.")),
    "auto-browser": ("crawler_https", ("web_integrations.WebCrawler",),
             ("Descargar HTML con allowlist y limite de bytes.", "Extraer texto y enlaces.")),
    "crawl4ai": ("crawler_https", ("web_integrations.WebCrawler",),
         ("Extraer HTML estatico de sitios permitidos.", "Respetar HTTPS, limites y terminos.")),
    "claude-seo": ("auditoria_seo", ("web_integrations.SEOAuditor",),
           ("Auditar titulos, enlaces y cabeceras.", "Generar un informe determinista.")),
    "book-to-skill": ("documento_a_skill", ("web_integrations.BookToSkill",),
              ("Dividir texto propio en chunks.", "Consultar los chunks por terminos.")),
    "yt-dlp": ("metadatos_media", ("media_orchestration.MediaExtractor",),
           ("Consultar metadatos con yt-dlp opcional.", "Descargar solo con derechos confirmados.")),
    "orca": ("orquestacion_local", ("media_orchestration.TaskOrchestrator",),
         ("Ejecutar tareas Python independientes con workers acotados.", "Conservar errores por tarea.")),
    "speech-to-speech": ("pipeline_voz", (),
             ("Requiere dependencias de audio/STT/TTS del operador.", "No disponible en stdlib base.")),
    "ui-tars": ("control_gui_asistido", (),
        ("Requiere modelo visual y permiso explicito.", "No controla el escritorio por defecto.")),
    "webtoapp": ("generacion_apk", (),
         ("Requiere Android SDK y proyecto propio.", "No compila APK automaticamente en el nucleo.")),
    "prompt-master": ("optimizacion_prompts", ("promptguard",),
              ("Aplicar plantillas propias.", "Auditar entradas con PromptGuard.")),
    "jlens": ("interpretabilidad_modelos", (),
          ("Requiere modelo y dependencias ML del operador.", "Solo referencia en el nucleo stdlib.")),
    "video-shotcraft": ("planificacion_video", (),
            ("Generar planes como datos estructurados.", "Exportacion a editor requiere adaptador adicional.")),
    "postiz": ("planificacion_social", (),
           ("Preparar calendario y borradores.", "Publicacion requiere API y confirmacion del operador.")),
    "agent-reach": ("lectura_web_controlada", ("web_integrations.WebCrawler",),
            ("Leer paginas HTTPS permitidas.", "No evadir anti-bot, paywalls ni limites.")),
    "wififorge": ("laboratorio_wifi", (),
          ("Requiere hardware y laboratorio propio.", "A²S no transmite ni desautentica redes.")),
}

# Rutas de sinergia por intención (en orden de ejecución)
RUTAS_SINERGIA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reconocimiento", ("web-check", "osint4all", "nuclei", "study-notes")),
    ("auditoria", ("web-check", "trivy", "osint4all", "claude-seo")),
    ("vulnerab", ("nuclei", "trivy", "web-check", "payloads-all-things")),
    ("reversing", ("ghidra", "imhex", "x64dbg", "cyberchef")),
    ("binario", ("imhex", "ghidra", "cyberchef")),
    ("malware", ("ghidra", "cyberchef", "imhex")),
    ("forense", ("imhex", "cyberchef", "ghidra")),
    ("prompt", ("claude-courses", "system-prompts-leaks", "karpathy-skills",
                "agency-agents")),
    ("agente", ("ruflo", "agency-agents", "real-world-llm-apps", "n8n-workflows")),
    ("orquest", ("n8n-workflows", "ruflo", "agency-agents")),
    ("workflow", ("n8n-workflows", "ruflo")),
    ("secreto", ("vault", "openssl", "cyberchef")),
    ("vpn", ("algo", "setup-ipsec-vpn", "xray-core", "v2ray-core")),
    ("proxy", ("xray-core", "v2ray-core", "mitmproxy")),
    ("dns", ("adguard-home", "stevenblack-hosts", "web-check")),
    ("contenedor", ("trivy", "web-check", "repo_audit_interno")),
    ("ml", ("zero-to-mastery-ml", "coursera-ai", "claude-courses")),
    ("arquitectura", ("sdd-101", "bytebytego")),
    ("sistema", ("sdd-101", "bytebytego")),
    ("google", ("gworkspace-cli", "gmail-account-creator")),
    ("empleo", ("four-day-week", "instahyre")),
    ("fitness", ("darebee",)),
    ("juegos", ("nealfun", "open-source-games")),
    ("entretenimiento", ("nealfun", "open-source-games")),
    ("cripto", ("sideshift", "invoapp")),
    ("finanzas", ("sideshift", "invoapp")),
    ("ocr", ("imagetotext", "delphi-tools")),
    ("estudio", ("coursera-ai", "zero-to-mastery-ml", "h4cker")),
    ("navegar", ("auto-browser", "agent-reach", "crawl4ai")),
    ("browser", ("auto-browser", "agent-reach", "crawl4ai")),
    ("crawl", ("crawl4ai", "auto-browser", "web-check")),
    ("voz", ("speech-to-speech", "real-world-llm-apps")),
    ("audio", ("speech-to-speech", "yt-dlp")),
    ("video", ("yt-dlp", "video-shotcraft", "claude-seo")),
    ("social", ("postiz", "claude-seo", "video-shotcraft")),
    ("seo", ("claude-seo", "crawl4ai", "web-check")),
    ("apk", ("webtoapp", "auto-browser")),
    ("android", ("webtoapp", "v2rayng")),
    ("api publica", ("public-apis", "gworkspace-cli")),
    ("api", ("public-apis", "gworkspace-cli")),
    ("proceso", ("pm2", "orca")),
    ("pm2", ("pm2", "provider_pool")),
    ("skill", ("book-to-skill", "claude-courses", "search.workspace_search")),
    ("documento", ("book-to-skill", "search.workspace_search")),
    ("interpretabilidad", ("jlens", "real-world-llm-apps")),
    ("explotar", ("metasploit", "sqlmap")),
    ("metasploit", ("metasploit",)),
    ("sqlmap", ("sqlmap",)),
)


# ---------------------------------------------------------------------------
# Resolución y consulta
# ---------------------------------------------------------------------------

def _norm(texto: str) -> str:
    value = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn")


def resolver(ident: str, workspace: str = "") -> Capacidad:
    """Capacidad de una entrada (base o recurso propio del operador)."""
    spec = _ESPEC_POR_ID.get(ident)
    if spec:
        return Capacidad(**spec)
    entry = next((e for e in ENTRADAS if e["id"] == ident), None)
    if entry is None:
        entry = next((e for e in extras(workspace) if e.get("id") == ident), None)
    if entry is None:
        raise KeyError(f"recurso desconocido: {ident}")
    native = _ADAPTADORES_NATIVOS.get(ident)
    if native:
        capacidad, mapa, receta = native
        return Capacidad(
            id=ident,
            dominio=_CAT_DOMINIO.get(entry.get("cat", "ia"), "utilidades"),
            capacidad=capacidad,
            uso="parcial" if mapa else "operador",
            requiere=("operador_manual",),
            mapa_a2s=mapa,
            receta=receta,
            etico="Adaptador controlado: revisar dependencias, permisos y terminos.",
        )
    cat = entry.get("cat", "ia")
    return Capacidad(
        id=ident,
        dominio=_CAT_DOMINIO.get(cat, "utilidades"),
        capacidad="recurso_operador",
        uso="operador",
        requiere=("operador_manual",),
        mapa_a2s=(),
        receta=("Revisar términos, licencia y legalidad local.",
                "Decidir el uso bajo responsabilidad del operador."),
        etico="Recurso del operador: validar su estado antes de usarlo.",
    )


def todas(workspace: str = "") -> list[Capacidad]:
    """Una capacidad por cada entrada del catálogo (base + propias)."""
    rows = [resolver(e["id"], workspace) for e in ENTRADAS]
    rows.extend(resolver(e["id"], workspace) for e in extras(workspace))
    return rows


def core_ids() -> list[str]:
    """Las 15 entradas de mayor apalancamiento (prioridad de implementación)."""
    cores = [s for s in _ESPEC if s["core"]]
    cores.sort(key=lambda s: s["id"])
    return [s["id"] for s in cores][:15]


def _entrada(ident: str, workspace: str = "") -> Optional[dict[str, Any]]:
    for e in ENTRADAS:
        if e["id"] == ident:
            return {**e, "categoria": _CAT_NOMBRE.get(e["cat"], "")}
    for e in extras(workspace):
        if e.get("id") == ident:
            return {**e, "categoria": _CAT_NOMBRE.get(e.get("cat", ""), "")}
    return None


def resumen(workspace: str = "") -> dict[str, Any]:
    """Conteo por dominio funcional, uso autónomo y cobertura."""
    caps = todas(workspace)
    por_dominio = {d: 0 for d in DOMINIOS}
    por_uso = {u: 0 for u in USO_NOMBRE}
    for cap in caps:
        por_dominio[cap.dominio] = por_dominio.get(cap.dominio, 0) + 1
        por_uso[cap.uso] = por_uso.get(cap.uso, 0) + 1
    autonomas = por_uso.get("si", 0)
    return {
        "total": len(caps),
        "dominios": [{"id": d, "nombre": DOMINIO_NOMBRE[d], "count": por_dominio[d]}
                     for d in DOMINIOS],
        "usos": [{"id": u, "nombre": USO_NOMBRE[u], "count": por_uso[u]}
                 for u in USO_NOMBRE],
        "autonomas": autonomas,
        "con_puerta": sum(1 for c in caps
                          if "autorizacion_escrita" in c.requiere),
        "core": core_ids(),
        "ingesta": estado_ingesta(workspace),
        "aviso": AVISO_ETICO,
    }


def _docs(workspace: str = "") -> list[Doc]:
    docs = []
    for cap in todas(workspace):
        entry = _entrada(cap.id, workspace) or {}
        texto = " ".join([
            cap.capacidad, DOMINIO_NOMBRE.get(cap.dominio, cap.dominio),
            " ".join(USO_NOMBRE.get(u, u) for u in cap.requiere),
            " ".join(cap.mapa_a2s), " ".join(cap.receta), cap.etico,
            entry.get("nombre", ""), entry.get("desc", ""),
            " ".join(entry.get("tags", ())), entry.get("url", ""),
        ])
        docs.append(Doc(doc_id=f"capacidad:{cap.id}", texto=texto,
                        origen="capacidad",
                        meta=f"{entry.get('nombre', cap.id)} · {cap.capacidad}"))
    return docs


def buscar_capacidad(consulta: str, top: int = 8,
                     workspace: str = "") -> list[dict[str, Any]]:
    """Búsqueda BM25 sobre el mapa de capacidades."""
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    hits = BM25Index(_docs(workspace)).search(consulta, top=top)
    out = []
    for doc, score in hits:
        ident = doc.doc_id.split(":", 1)[1]
        cap = resolver(ident, workspace)
        entry = _entrada(ident, workspace) or {}
        item = cap.to_dict()
        item.update({"url": entry.get("url", ""), "nombre": entry.get("nombre", ident),
                     "score": round(score, 4)})
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Puerta de autorización (ruta ofensiva)
# ---------------------------------------------------------------------------

# Perfiles académicos/éticos con alcance explícito y registrado. Ningún perfil
# es "auto-autorización": el archivo de alcance debe existir antes de enrutar.
PERFILES: dict[str, str] = {
    "ctf": "Competiciones/plataformas de CTF (HTB, THM, VulnHub, retos locales)",
    "lab": "Laboratorio propio (Metasploitable, DVWA, Juice Shop, Kali)",
    "propio": "Infraestructura, datos o binarios propios",
    "universidad": "Laboratorio académico con autorización docente/comité",
}

_MARCAS_LAB = ("ctf", "hackthebox", "tryhackme", "htb", "thm", "vulnhub",
               "metasploitable", "dvwa", "juice shop", "kali", "lab",
               "laboratorio", "propio", "local", "demo", "red-team",
               "tesis", "universidad", "academico", "academica", "ejercicio",
               "practica", "clase", "curso")


def alcance_path(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace or "."), ".a2s", "alcance.json")


def alcance_info(workspace: str) -> dict[str, Any]:
    """Estado del alcance escrito: existe, es válido y qué cubre."""
    path = alcance_path(workspace)
    base = {"existe": False, "valido": False, "hosts": [], "nota": "",
            "perfil": "", "path": path}
    if not os.path.isfile(path):
        return base
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return base
    if not isinstance(data, dict) or not data.get("autorizado"):
        return base
    hosts = data.get("hosts") or []
    if not isinstance(hosts, list):
        hosts = []
    perfil = str(data.get("perfil") or "")
    nota = str(data.get("nota") or "")[:300]
    valido = bool(perfil in PERFILES and nota)
    return {**base, "existe": True, "valido": valido,
            "hosts": [str(h)[:120] for h in hosts],
            "nota": nota, "perfil": perfil}


def crear_alcance(workspace: str, perfil: str, nota: str = "",
                  hosts: Optional[tuple[str, ...]] = None) -> dict[str, Any]:
    """Registra el alcance académico/ético del operador (auditable, atómico).

    ``perfil`` define el marco (ctf/lab/propio/universidad), ``nota`` el caso
    concreto (clase, plataforma, infraestructura) y ``hosts`` el alcance de
    red opcional (por defecto sólo el entorno local/lab). El archivo queda en
    ``workspace/.a2s/alcance.json`` junto a la bitácora forense.
    """
    perfil = (perfil or "").strip().lower()
    if perfil not in PERFILES:
        raise ValueError(
            f"perfil desconocido «{perfil}»; usa: {', '.join(PERFILES)}")
    nota = (nota or "").strip()
    if not nota:
        raise ValueError("falta la nota del alcance (caso concreto: clase, "
                         "plataforma, infraestructura…)")
    hosts_list = [h.strip().lower() for h in (hosts or ("127.0.0.1", "localhost"))
                  if h.strip()]
    perfil_nombre = PERFILES[perfil]
    data = {"version": 1, "autorizado": True, "perfil": perfil,
            "perfil_nombre": perfil_nombre,
            "nota": nota[:300], "hosts": hosts_list,
            "at": now_iso()}
    _atomic_write(alcance_path(workspace), data)
    return data


def _es_objetivo_lab(objetivo: str) -> bool:
    text = _norm(objetivo)
    return any(mar in text for mar in _MARCAS_LAB)


def puerta_autorizacion(objetivo: str, workspace: str = "",
                        perfil: str = "") -> dict[str, Any]:
    """¿La ruta ofensiva pedida está dentro del alcance académico autorizado?"""
    info = alcance_info(workspace)
    objetivo_norm = _norm(objetivo or "")
    host = ""
    for prefix in ("https://", "http://"):
        if objetivo_norm.startswith(prefix):
            host = urllib.parse.urlparse(objetivo).netloc.lower()
            break
    perfil_pedido = (perfil or "").strip().lower()
    cubierto = (
        info["valido"]
        and ("*" in info["hosts"]
             or (host and any(h in host or host in h for h in info["hosts"]))
             or _es_objetivo_lab(objetivo)
             or (perfil_pedido and info["perfil"] == perfil_pedido))
    )
    return {"necesaria": True, "valida": bool(cubierto), **info}


# ---------------------------------------------------------------------------
# Enrutador determinista
# ---------------------------------------------------------------------------

def _coincidir_intento(objetivo: str) -> tuple[str, Optional[tuple[str, ...]]]:
    text = _norm(objetivo)
    matches: list[tuple[int, str, tuple[str, ...]]] = []
    for clave, cadena in RUTAS_SINERGIA:
        if clave in text:
            matches.append((len(clave), clave, cadena))
    if not matches:
        return "general", None
    matches.sort(key=lambda item: item[0], reverse=True)
    merged: list[str] = []
    for _, _, cadena in matches:
        for ident in cadena:
            if ident not in merged:
                merged.append(ident)
    return matches[0][1], tuple(merged)


def _paso(ident: str, posicion: int, total: int,
          workspace: str) -> dict[str, Any]:
    cap = resolver(ident, workspace)
    entry = _entrada(ident, workspace) or {}
    return {
        "id": ident,
        "nombre": entry.get("nombre", ident),
        "url": entry.get("url", ""),
        "capacidad": cap.capacidad,
        "uso": cap.uso,
        "uso_nombre": USO_NOMBRE.get(cap.uso, cap.uso),
        "por_que": (f"eslabón {posicion}/{total} de la cadena de sinergia "
                    f"para el objetivo detectado"),
        "requiere": list(cap.requiere),
        "mapa_a2s": list(cap.mapa_a2s),
        "etico": cap.etico,
    }


def seleccionar(objetivo: str, contexto: str = "",
                workspace: str = "", top: int = 6,
                perfil: str = "") -> dict[str, Any]:
    """Decide qué cadena de recursos usar para un objetivo (o la bloquea).

    ``perfil`` (ctf/lab/propio/universidad) solo actúa cuando el alcance ya
    está registrado en ``workspace/.a2s/alcance.json``. Devuelve ``pasos``
    (lo que A²S puede ejecutar o preparar), ``bloqueados`` (lo que la puerta
    retiene) y una sugerencia defensiva alternativa.
    """
    objetivo = (objetivo or "").strip()
    if not objetivo:
        raise ValueError("falta el objetivo a enrutar")
    intent, cadena = _coincidir_intento(objetivo)
    if cadena is None:
        ranked = buscar_capacidad(f"{objetivo} {contexto}", top=top,
                                  workspace=workspace)
        cadena = tuple(str(r["id"]) for r in ranked)
    gate = puerta_autorizacion(objetivo, workspace, perfil=perfil)
    pasos: list[dict[str, Any]] = []
    bloqueados: list[dict[str, Any]] = []
    for ident in cadena:
        if ident == "repo_audit_interno":
            pasos.append({"id": "repo_audit_interno", "nombre": "repo_audit (núcleo)",
                          "url": "", "capacidad": "auditoria_interna",
                          "uso": "si", "uso_nombre": USO_NOMBRE["si"],
                          "por_que": "equivalente interno del escaneo de artefactos",
                          "requiere": [], "mapa_a2s": ["plugin.repo_audit"], "etico": ""})
            continue
        try:
            cap = resolver(ident, workspace)
        except KeyError:
            continue
        entry = _entrada(ident, workspace) or {}
        motivo = _motivo_bloqueo(cap, entry, objetivo, gate)
        if motivo:
            bloqueados.append({"id": ident, "nombre": entry.get("nombre", ident),
                               "motivo": motivo})
        else:
            pasos.append(_paso(ident, len(pasos) + 1, len(cadena), workspace))
    defensiva = _sugerencia_defensiva(objetivo, cadena)
    return {
        "objetivo": objetivo,
        "contexto": (contexto or "").strip(),
        "intento": intent,
        "pasos": pasos,
        "bloqueados": bloqueados,
        "autorizacion": {k: gate[k] for k in ("necesaria", "valida", "existe",
                                              "nota", "hosts", "perfil", "path")},
        "sugerencia_defensiva": defensiva,
        "resumen": (f"{len(pasos)} paso(s) habilitado(s), "
                    f"{len(bloqueados)} retenido(s) por la puerta de ética"),
    }


def _motivo_bloqueo(cap: Capacidad, entry: dict[str, Any],
                    objetivo: str, gate: dict[str, Any]) -> str:
    etiquetas = entry.get("tags", ())
    if cap.uso == "no":
        if "autorizacion_escrita" in cap.requiere:
            return ("uso ofensivo: requiere alcance escrito firmado "
                    "(A²S no lo automatiza)")
        return "zona gris/referencia: A²S no automatiza este recurso"
    if "autorizacion_escrita" in cap.requiere:
        if not gate["valida"]:
            return ("requiere alcance académico registrado: ejecuta "
                    "`a2s capacidades --alcance --perfil ctf|lab|propio|"
                    "universidad --nota \"...\"` antes de enrutar")
        return ""
    if "advertido" in etiquetas:
        return "advertido: verificar términos y legalidad local"
    return ""


def _sugerencia_defensiva(objetivo: str, cadena: tuple[str, ...]) -> str:
    text = _norm(objetivo)
    if any(w in text for w in ("recon", "auditoria", "web", "vulnerab")):
        return ("Alternativa defensiva: web-check + trivy + repo_audit sobre "
                "activos propios; nuclei solo con alcance firmado.")
    if any(w in text for w in ("revers", "binario", "malware", "forense")):
        return ("Alternativa defensiva: análisis estático stdlib "
                "(file_magic, strings, EXIF, hashes) sobre muestras propias; "
                "Ghidra/x64dbg solo para software propio o autorizado.")
    if any(w in text for w in ("secreto", "clave", "token")):
        return ("Alternativa defensiva: bóveda del operador + firma HMAC + "
                "rotación documentada; no almacenar secretos en claro.")
    return ("Alternativa defensiva: aplicar el recurso sobre infraestructura, "
            "datos o binarios propios y con el alcance documentado en "
            "workspace/.a2s/alcance.json.")


# ---------------------------------------------------------------------------
# Ingesta a memoria (READMEs públicos → fichas de conocimiento)
# ---------------------------------------------------------------------------

def _ingesta_dir(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace or "."), ".a2s", "capacidades")


def _ingesta_path(workspace: str) -> str:
    return os.path.join(_ingesta_dir(workspace), "ingesta.json")


def estado_ingesta(workspace: str) -> dict[str, Any]:
    path = _ingesta_path(workspace)
    vacio = {"at": "", "ok": 0, "error": 0, "referencia": 0, "revisar": 0,
             "total": len(ENTRADAS)}
    if not os.path.isfile(path):
        return dict(vacio)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return dict(vacio)
    estados = data.get("estados", {}) if isinstance(data, dict) else {}
    counts = {"ok": 0, "error": 0, "referencia": 0, "revisar": 0}
    for st in estados.values():
        kind = st.get("estado", "error") if isinstance(st, dict) else "error"
        counts[kind] = counts.get(kind, 0) + 1
    return {"at": data.get("at", "") if isinstance(data, dict) else "",
            **counts, "total": len(ENTRADAS)}


def _github_repo(url: str) -> Optional[str]:
    parsed = urllib.parse.urlparse(url or "")
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _resumen_readme(readme: str, desc: str) -> str:
    from .learner import extractive_summary
    if readme and len(readme.strip()) > 80:
        return extractive_summary(readme, max_sents=6, max_chars=900)
    return (desc or "").strip()[:400] or "Sin README/resumen disponible."


def _ingesta_uno(ident: str, workspace: str, gh: Any,
                 refresh: bool) -> dict[str, Any]:
    from .learner import classify_forbidden, save_card
    entry = _entrada(ident, workspace) or {"id": ident, "nombre": ident,
                                           "url": "", "desc": "", "tags": ()}
    url = entry.get("url", "")
    repo = _github_repo(url)
    if repo is None:
        return {"id": ident, "estado": "referencia",
                "motivo": "sin README en GitHub: recurso externo (referencia)",
                "repo": "", "licencia": "", "stars": 0}
    try:
        meta = gh.repo_metadata(repo) or {}
        readme = gh.fetch_readme(repo)
    except Exception as exc:  # noqa: BLE001 — diagnóstico por repo
        return {"id": ident, "estado": "error",
                "motivo": f"{type(exc).__name__}: {exc}"[:160], "repo": repo}
    contenido = f"{meta.get('description', '')}\n{readme}"
    motivo = classify_forbidden(contenido)
    resumen_txt = _resumen_readme(readme, entry.get("desc", ""))
    snippet = (readme or "").strip()[:500]
    licencia = str(meta.get("license") or "desconocida")
    card = {
        "id": f"cap-{ident[:48]}",
        "topic": f"Catálogo: {entry.get('nombre', ident)} — "
                 f"{resolver(ident, workspace).capacidad}",
        "query": f"catálogo {ident}",
        "repo": repo, "url": url, "license": licencia,
        "summary": resumen_txt,
        "recipe": "\n".join(resolver(ident, workspace).receta
                            or ("Revisar la documentación con la fuente "
                                "original antes de aplicar.",)),
        "snippet": snippet,
        "stars": int(meta.get("stars") or 0),
        "created_at": now_iso(),
        "used": 0, "wins": 0,
    }
    from .learner import KnowledgeCard
    save_card(KnowledgeCard(**card), workspace)
    # El modelo de permisos marca el contenido para revisión del operador:
    # la ficha se conserva (el material es público) pero no se auto-aplica.
    estado = "revisar" if motivo else "ok"
    return {"id": ident, "estado": estado,
            "motivo": (motivo or "")[:160] if motivo else "",
            "repo": repo, "licencia": licencia,
            "stars": int(meta.get("stars") or 0),
            "lenguaje": str(meta.get("language") or ""),
            "archivado": bool(meta.get("archived")),
            "readme_chars": len(readme or ""),
            "resumen": resumen_txt[:240]}


def ingesta(workspace: str = "", max_calls: int = 40, solo: Optional[str] = None,
            refresh: bool = False, gh: Any = None) -> dict[str, Any]:
    """Ingiere READMEs públicos del catálogo a fichas de conocimiento.

    Solo lectura vía API de GitHub (cuotas respetadas por ``GitHubClient``).
    Reanudable: por defecto omite lo ya ``ok``; ``refresh`` lo re-hace.
    Nunca clona ni ejecuta código.
    """
    if gh is None:
        from .learner import GitHubClient
        gh = GitHubClient(max_calls=max_calls)
    whitelist = None
    if solo:
        whitelist = {s.strip() for s in solo.split(",") if s.strip()}
    resultados: dict[str, dict[str, Any]] = {}
    prev = {}
    path = _ingesta_path(workspace)
    if os.path.isfile(path) and not refresh:
        try:
            with open(path, encoding="utf-8") as fh:
                prev = (json.load(fh) or {}).get("estados", {}) or {}
        except (OSError, ValueError):
            prev = {}
    for e in ENTRADAS:
        ident = e["id"]
        if whitelist is not None and ident not in whitelist:
            continue
        prev_st = prev.get(ident) or {}
        if prev_st.get("estado") == "ok" and not refresh:
            resultados[ident] = prev_st
            continue
        try:
            resultados[ident] = _ingesta_uno(ident, workspace, gh, refresh)
        except Exception as exc:  # noqa: BLE001 — un repo no rompe la ingesta
            resultados[ident] = {"id": ident, "estado": "error",
                                 "motivo": f"{type(exc).__name__}: {exc}"[:160]}
    data = {"version": 1, "at": now_iso(),
            "estados": {**prev, **resultados}}
    _atomic_write(path, data)
    return {"at": data["at"], "estados": resultados,
            "total": len(resultados),
            "ok": sum(1 for r in resultados.values() if r.get("estado") == "ok"),
            "error": sum(1 for r in resultados.values() if r.get("estado") == "error"),
            "revisar": sum(1 for r in resultados.values()
                           if r.get("estado") == "revisar"),
            "referencia": sum(1 for r in resultados.values()
                              if r.get("estado") == "referencia")}


# ---------------------------------------------------------------------------
# Mapa completo (informe)
# ---------------------------------------------------------------------------

def _leer_estados(workspace: str) -> dict[str, dict[str, Any]]:
    """Estados de ingesta persistidos (o vacío si no existe)."""
    path = _ingesta_path(workspace)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    estados = data.get("estados", {}) if isinstance(data, dict) else {}
    return {k: v for k, v in estados.items() if isinstance(v, dict)}


def mapa_entradas(workspace: str = "") -> list[dict[str, Any]]:
    """Entradas del catálogo enriquecidas con su capacidad y estado de ingesta."""
    estados = _leer_estados(workspace)
    rows = []
    for entry in ENTRADAS:
        cap = resolver(entry["id"], workspace)
        row = {**entry, "categoria": _CAT_NOMBRE.get(entry["cat"], ""),
               **cap.to_dict()}
        row["ingesta"] = (estados.get(entry["id"], {}) or {}).get(
            "estado", "pendiente")
        rows.append(row)
    return rows


def mapa_markdown(workspace: str = "") -> str:
    """Informe completo del mapa fuente → capacidad → A²S."""
    state = estado_ingesta(workspace)
    caps = todas(workspace)
    lineas = [
        "# Mapa de capacidades A²S (fuentes → capacidades → uso)",
        "",
        f"> {AVISO_ETICO}",
        "",
        f"**{len(caps)} recursos** · {len(core_ids())} core · "
        f"ingesta: {state.get('ok', 0)} ok / {state.get('revisar', 0)} revisar / "
        f"{state.get('error', 0)} error / {state.get('referencia', 0)} referencia",
        "",
        "| Dominio | Capacidad | Uso | Requiere | Equivalente A²S |",
        "|---|---|---|---|---|",
    ]
    for cap in sorted(caps, key=lambda c: (c.dominio, c.capacidad)):
        req = ", ".join(REQ_NOMBRE.get(r, r) for r in cap.requiere) or "—"
        mapeo = ", ".join(cap.mapa_a2s) or "—"
        core = " ⭐" if cap.core else ""
        lineas.append(
            f"| {DOMINIO_NOMBRE.get(cap.dominio, cap.dominio)} | "
            f"`{cap.capacidad}`{core} | {USO_NOMBRE.get(cap.uso, cap.uso)} | "
            f"{req} | {mapeo} |")
    lineas += ["", "## Recetas por recurso (resumen)", ""]
    for cap in sorted(caps, key=lambda c: c.id):
        entry = _entrada(cap.id, workspace) or {}
        if cap.receta:
            lineas.append(f"### {entry.get('nombre', cap.id)} (`{cap.id}`)")
            lineas += [f"- {paso}" for paso in cap.receta]
    lineas += ["", "## Core (prioridad de integración)", "",
               "1. " + ", ".join(f"`{i}`" for i in core_ids())]
    lineas += ["", "## Límites", "",
               "Zona gris marcada `no`: documentación, sin automatización. "
               "Rutado con `a2s capacidades ruta OBJETIVO`; las cadenas "
               "ofensivas se bloquean sin `workspace/.a2s/alcance.json`."]
    return "\n".join(lineas)
