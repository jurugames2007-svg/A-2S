"""Catálogo curado de recursos del operador (v1.21).

Lista consolidada de referencia en 6 categorías: IA/cursos/automatización,
ciberseguridad/redes/OSINT, desarrollo/arquitectura, directorios/streaming/
juegos, herramientas web/finanzas y empleo/estilo de vida/entretenimiento.

Filtro de ética (no negociable):

* Los recursos son **referencia y estudio**: A²S no descarga, instala ni
  ejecuta nada de este catálogo por su cuenta; solo muestra URLs y notas.
* Las herramientas ofensivas (pentesting, explotación, OSINT, reversing)
  se usan únicamente en entornos **autorizados**: infraestructura propia,
  CTF, red-team con alcance firmado o trabajo académico con comité de ética.
  A²S no valida esa autorización por el operador.
* Cada destino mantiene sus propios términos, licencias y legalidad local.
  Las entradas en zona gris llevan la etiqueta ``advertido`` y el operador
  decide bajo su responsabilidad.

Uso: ``a2s recursos`` (CLI), pestaña **Recursos** del Control Plane,
``GET /api/recursos`` y ``a2s search`` (origen ``recurso``).

Extras del operador (v1.22): ``a2s recursos add NOMBRE URL --cat ciber``
persiste recursos propios en ``workspace/.a2s/recursos.json`` (con
``forget`` los elimina); ``--check`` verifica la disponibilidad HTTP de los
enlaces y ``--md``/``--html`` exportan el catálogo (con los propios) para
documentación o material del evento.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

from .models import now_iso
from .search import BM25Index, Doc

AVISO_ETICO = (
    "Referencia y estudio: uso solo en entornos autorizados (infraestructura "
    "propia, CTF, red-team con alcance o fin académico). A²S no descarga ni "
    "instala nada del catálogo. Las entradas «advertido» son zona gris: "
    "verificar términos, licencia y legalidad local antes de usarlas."
)

CATEGORIAS: tuple[dict[str, Any], ...] = (
    {"id": "ia", "nombre": "IA, Cursos y Automatización"},
    {"id": "ciber", "nombre": "Ciberseguridad, Redes y OSINT"},
    {"id": "dev", "nombre": "Desarrollo de Software y Arquitectura"},
    {"id": "directorios", "nombre": "Directorios de Recursos, Streaming y Juegos"},
    {"id": "utilidades", "nombre": "Herramientas Web, Utilidades y Finanzas"},
    {"id": "empleo", "nombre": "Empleo, Estilo de Vida y Entretenimiento"},
)

ENTRADAS: tuple[dict[str, Any], ...] = (
    # ---- 1. IA, Cursos y Automatización ---------------------------------
    {"id": "claude-courses", "cat": "ia",
     "nombre": "Claude / Anthropic — Cursos oficiales",
     "url": "https://claude.com/resources/courses",
     "desc": "Cursos oficiales de Anthropic (prompting, agentes, APIs). "
             "Espejo en github.com/anthropics/courses.",
     "tags": ("claud", "cursos", "prompt", "agentes")},
    {"id": "anthropic-courses", "cat": "ia",
     "nombre": "Anthropic Courses — repositorio GitHub",
     "url": "https://github.com/anthropics/courses",
     "desc": "Repositorio oficial del curso de Anthropic (notebooks, "
             "módulos de agents, prompting y tool use). Espejo del "
             "contenido de claude.com/resources/courses.",
     "tags": ("claud", "cursos", "prompt", "agentes", "github")},
    {"id": "coursera-ai", "cat": "ia",
     "nombre": "Coursera — Google AI Essentials",
     "url": "https://www.coursera.org/specializations/ai-essentials-google",
     "desc": "Especialización universitaria sobre fundamentos de IA, LLMs y ética.",
     "tags": ("cursos", "ia", "google")},
    {"id": "n8n-workflows", "cat": "ia",
     "nombre": "n8n — Colección de workflows",
     "url": "https://github.com/Zie619/n8n-workflows",
     "desc": "Flujos de automatización n8n listos para adaptar (comunidad).",
     "tags": ("automatizacion", "n8n")},
    {"id": "ruflo", "cat": "ia",
     "nombre": "RuFlo — Agentes de IA",
     "url": "https://github.com/ruvnet/ruflo",
     "desc": "Framework de agentes IA y orquestación (comunidad; revisar "
             "licencia y mantenedor).",
     "tags": ("agentes", "ia")},
    {"id": "aifreeforever", "cat": "ia",
     "nombre": "AI Free Forever",
     "url": "https://aifreeforever.com/",
     "desc": "Directorio de servicios y modelos de IA gratuitos (comunidad; "
             "verificar términos y caducidad).",
     "tags": ("ia", "gratuito")},
    {"id": "tranchi-ai", "cat": "ia",
     "nombre": "Tranchi AI",
     "url": "https://tranchi.ai/",
     "desc": "Herramienta de IA de nicho (comunidad; verificar reputación "
             "y términos).",
     "tags": ("ia",) },
    {"id": "wormgpt", "cat": "ia",
     "nombre": "Worm-GPT (repo de terceros)",
     "url": "https://github.com/lahirusanjika/Worm-GPT",
     "desc": "Proyecto de terceros (lahirusanjika) publicitado como LLM «sin "
             "filtros» para ciberseguridad/red-team. No es oficial ni "
             "verificado: advertido, solo referencia documental; A²S no lo "
             "integra ni ejecuta.",
     "tags": ("advertido", "ia", "referencia")},
    {"id": "karpathy-skills", "cat": "ia",
     "nombre": "Karpathy Skills (multica-ai)",
     "url": "https://github.com/multica-ai/andrej-karpathy-skills",
     "desc": "Archivo CLAUDE.md que mejora el comportamiento de Claude Code, derivado de las observaciones de Andrej Karpathy sobre fallos de los LLM al programar (4 principios); referencia, no oficial.",
     "tags": ("claude", "llms", "coding", "karpathy")},
    {"id": "zero-to-mastery-ml", "cat": "ia",
     "nombre": "Zero to Mastery ML (mrdbourke)",
     "url": "https://github.com/mrdbourke/zero-to-mastery-ml",
     "desc": "Material del curso Zero to Mastery de Machine Learning y Data Science (Daniel Bourke): notebooks, código y proyecto final.",
     "tags": ("ml", "aprendizaje", "notebooks", "curso")},
    {"id": "agency-agents", "cat": "ia",
     "nombre": "Agency Agents (msitarzewski)",
     "url": "https://github.com/msitarzewski/agency-agents",
     "desc": "Catálogo de agentes de IA especializados inyectables en Claude Code, Cursor y Aider (msitarzewski); transforma asistentes genéricos en expertos de dominio.",
     "tags": ("agentes", "ia", "automatizacion", "claude")},
    {"id": "godmode", "cat": "ia",
     "nombre": "Godmode (smol-ai)",
     "url": "https://github.com/smol-ai/godmode",
     "desc": "Navegador de chat de IA (smol-ai/GodMode): acceso rápido a ChatGPT, Claude, Perplexity, Bing, Llama2 con un atajo; open-source y sin API.",
     "tags": ("ia", "chat", "navegador")},
    {"id": "real-world-llm-apps", "cat": "ia",
     "nombre": "Real-World LLM Apps (manthanguptaa)",
     "url": "https://github.com/manthanguptaa/real-world-llm-apps",
     "desc": "Catálogo de aplicaciones reales y listas para producción que usan LLMs: browser agent, health advisor, RAG, reclutador, eval (manthanguptaa).",
     "tags": ("llm", "aplicaciones", "ia", "production")},
    {"id": "ui-tars", "cat": "ia",
     "nombre": "UI-TARS",
     "url": "https://github.com/bytedance/UI-TARS",
     "desc": "Referencia de agentes multimodales para comprender interfaces; A²S no controla el escritorio sin intervención y permisos del operador.",
     "tags": ("ia", "multimodal", "gui", "referencia")},
    {"id": "prompt-master", "cat": "ia",
     "nombre": "Prompt Master",
     "url": "https://github.com/nidhininjas/prompt-master",
     "desc": "Referencia de plantillas y técnicas de mejora de prompts para evaluación local.",
     "tags": ("ia", "prompt", "evaluacion")},
    {"id": "jlens", "cat": "ia",
     "nombre": "Jacobian Lens",
     "url": "https://github.com/jlens/jlens",
     "desc": "Referencia de interpretabilidad y análisis de activaciones de modelos; requiere modelos y datos del operador.",
     "tags": ("ia", "interpretabilidad", "modelos")},
    {"id": "speech-to-speech", "cat": "ia",
     "nombre": "Speech-to-Speech",
     "url": "https://github.com/speech-to-speech/speech-to-speech",
     "desc": "Referencia de pipelines de voz, transcripción y síntesis para pruebas locales.",
     "tags": ("ia", "voz", "audio")},
    {"id": "book-to-skill", "cat": "ia",
     "nombre": "Book-to-Skill",
     "url": "https://github.com/book-to-skill/book-to-skill",
     "desc": "Referencia para convertir documentación propia en fichas de conocimiento e índices consultables.",
     "tags": ("ia", "conocimiento", "rag")},
    {"id": "orca", "cat": "ia",
     "nombre": "Orca",
     "url": "https://github.com/getorca/orca",
     "desc": "Referencia de orquestación paralela; A²S reutiliza sus patrones solo dentro de workspaces propios y auditados.",
     "tags": ("ia", "agentes", "orquestacion")},
    {"id": "auto-browser", "cat": "ia",
     "nombre": "Auto-Browser",
     "url": "https://github.com/LvcidPsyche/auto-browser",
     "desc": "Referencia de navegación automatizada y extracción de páginas con sesión controlada por el operador.",
     "tags": ("navegador", "web", "automatizacion")},
    {"id": "crawl4ai", "cat": "ia",
     "nombre": "Crawl4AI",
     "url": "https://github.com/unclecode/crawl4ai",
     "desc": "Referencia de crawling y extracción de contenido para investigación web respetuosa con robots y límites.",
     "tags": ("web", "crawl", "extraccion")},
    {"id": "public-apis", "cat": "dev",
     "nombre": "Public APIs",
     "url": "https://github.com/public-apis/public-apis",
     "desc": "Catálogo de APIs públicas para descubrimiento; cada llamada requiere revisar autenticación, límites y términos.",
     "tags": ("api", "catalogo", "desarrollo")},
    {"id": "pm2", "cat": "dev",
     "nombre": "PM2",
     "url": "https://github.com/Unitech/pm2",
     "desc": "Referencia de gestión y supervisión de procesos propios; A²S no inicia servicios sin configuración explícita.",
     "tags": ("procesos", "node", "operacion")},
    {"id": "webtoapp", "cat": "dev",
     "nombre": "WebToApp",
     "url": "https://github.com/TheDarkBug/WebToApp",
     "desc": "Referencia de empaquetado de aplicaciones web propias para Android y revisión de permisos.",
     "tags": ("android", "web", "desarrollo")},
    {"id": "yt-dlp", "cat": "utilidades",
     "nombre": "yt-dlp",
     "url": "https://github.com/yt-dlp/yt-dlp",
     "desc": "Referencia de extracción de metadatos y medios cuando el operador tiene derecho de descarga; no se evaden restricciones.",
     "tags": ("video", "audio", "metadatos")},
    {"id": "wififorge", "cat": "ciber",
     "nombre": "WiFi Forge",
     "url": "https://github.com/wififorge/wififorge",
     "desc": "Referencia de laboratorio inalámbrico; cualquier prueba requiere hardware propio y alcance autorizado.",
     "tags": ("wifi", "laboratorio", "autorizado")},
    {"id": "agent-reach", "cat": "ciber",
     "nombre": "Agent Reach",
     "url": "https://github.com/agent-reach/agent-reach",
     "desc": "Referencia de acceso web directo; A²S respeta robots, límites, sesiones y términos del sitio.",
     "tags": ("web", "osint", "referencia")},
    {"id": "claude-seo", "cat": "utilidades",
     "nombre": "Claude SEO",
     "url": "https://github.com/claude-seo/claude-seo",
     "desc": "Referencia de auditoría SEO sobre sitios propios: metadatos, enlaces, schema y rendimiento.",
     "tags": ("seo", "web", "auditoria")},
    {"id": "postiz", "cat": "utilidades",
     "nombre": "Postiz",
     "url": "https://github.com/gitroomhq/postiz-app",
     "desc": "Referencia de planificación editorial y publicación social con cuentas y permisos del operador.",
     "tags": ("social", "contenido", "automatizacion")},
    {"id": "video-shotcraft", "cat": "utilidades",
     "nombre": "Video Shotcraft",
     "url": "https://github.com/video-shotcraft/video-shotcraft",
     "desc": "Referencia de storyboards, guiones técnicos y planificación de rodajes propios.",
     "tags": ("video", "storyboard", "contenido")},
    # ---- 2. Ciberseguridad, Redes y OSINT -------------------------------
    {"id": "kaspersky-cybermap", "cat": "ciber",
     "nombre": "Kaspersky Cyberthreat Map",
     "url": "https://cybermap.kaspersky.com/",
     "desc": "Mapa en vivo de ciberataques para monitorización y charlas.",
     "tags": ("monitorizacion", "mapa")},
    {"id": "grayhat-warfare", "cat": "ciber",
     "nombre": "Grayhat Warfare",
     "url": "https://grayhatwarfare.com/",
     "desc": "Write-ups y retos de explotación para estudio técnico.",
     "tags": ("exploit", "writeups")},
    {"id": "osint4all", "cat": "ciber",
     "nombre": "OSINT4ALL — Dashboard",
     "url": "https://start.me/p/L1rEYQ/osint4all",
     "desc": "Panel de herramientas OSINT (información pública, sin "
             "suplantación).",
     "tags": ("osint",) },
    {"id": "study-notes", "cat": "ciber",
     "nombre": "Study Notes — Top repos de GitHub",
     "url": "https://study-notes.org/",
     "desc": "Resumen de los repositorios de seguridad más destacados de GitHub.",
     "tags": ("osint", "repos")},
    {"id": "book-secret-knowledge", "cat": "ciber",
     "nombre": "The Book of Secret Knowledge",
     "url": "https://github.com/trimstray/the-book-of-secret-knowledge",
     "desc": "Compendio masivo de herramientas y técnicas (filtrar por "
             "categoría).",
     "tags": ("referencia", "ofensiva")},
    {"id": "awesome-hacking", "cat": "ciber",
     "nombre": "Awesome Hacking",
     "url": "https://github.com/Hack-with-Github/Awesome-Hacking",
     "desc": "Catálogo de recursos de aprendizaje y CTFs.",
     "tags": ("aprendizaje", "ctf")},
    {"id": "payloads-all-things", "cat": "ciber",
     "nombre": "PayloadsAllTheThings",
     "url": "https://github.com/swisskyrepo/PayloadsAllTheThings",
     "desc": "Payloads y técnicas de prueba (XSS, SQLi, SSRF, auth…).",
     "tags": ("payloads", "xss", "sqli")},
    {"id": "ghidra", "cat": "ciber",
     "nombre": "Ghidra",
     "url": "https://github.com/NationalSecurityAgency/ghidra",
     "desc": "Suite de ingeniería inversa de la NSA: descompilador, "
             "desensamblador y plugins.",
     "tags": ("reverse", "decompilador")},
    {"id": "hackingtool", "cat": "ciber",
     "nombre": "HackingTool",
     "url": "https://github.com/Z4nzu/hackingtool",
     "desc": "CLI que integra varias herramientas de escaneo y pruebas.",
     "tags": ("cli", "herramientas")},
    {"id": "imhex", "cat": "ciber",
     "nombre": "ImHex",
     "url": "https://github.com/WerWolv/ImHex",
     "desc": "Editor hexadecimal con lenguaje de patrones (reversing y "
             "forense binario).",
     "tags": ("hex", "binario")},
    {"id": "v2rayng", "cat": "ciber",
     "nombre": "v2rayNG",
     "url": "https://github.com/2dust/v2rayNG",
     "desc": "Cliente Android para la plataforma de proxy v2ray.",
     "tags": ("proxy", "android")},
    {"id": "x64dbg", "cat": "ciber",
     "nombre": "x64dbg",
     "url": "https://github.com/x64dbg/x64dbg",
     "desc": "Depurador de 64 bits para Windows (análisis de binarios).",
     "tags": ("debugger", "windows")},
    {"id": "mitmproxy", "cat": "ciber",
     "nombre": "mitmproxy",
     "url": "https://github.com/mitmproxy/mitmproxy",
     "desc": "Proxy inspeccionable para tráfico HTTP(S); solo en entornos "
             "autorizados.",
     "tags": ("proxy", "trafico", "https")},
    {"id": "metasploit", "cat": "ciber",
     "nombre": "Metasploit Framework",
     "url": "https://github.com/rapid7/metasploit-framework",
     "desc": "Framework de explotación y post-explotación; requiere alcance "
             "escrito.",
     "tags": ("exploit", "framework", "advertido")},
    {"id": "sqlmap", "cat": "ciber",
     "nombre": "sqlmap",
     "url": "https://github.com/sqlmapproject/sqlmap",
     "desc": "Detección y explotación de inyección SQL; solo en sistemas "
             "autorizados.",
     "tags": ("sqli", "advertido")},
    {"id": "xray-core", "cat": "ciber",
     "nombre": "Xray-core",
     "url": "https://github.com/XTLS/Xray-core",
     "desc": "Plataforma de red para eludir censura (núcleo de proxy).",
     "tags": ("proxy", "red")},
    {"id": "vault", "cat": "ciber",
     "nombre": "HashiCorp Vault",
     "url": "https://github.com/hashicorp/vault",
     "desc": "Gestión de secretos y cifrado en reposo (defensa).",
     "tags": ("defensa", "secretos")},
    {"id": "cyberchef", "cat": "ciber",
     "nombre": "CyberChef",
     "url": "https://github.com/gchq/CyberChef",
     "desc": "Navaja suiza: codificación, cripto, análisis de binarios y más.",
     "tags": ("codigos", "analisis")},
    {"id": "v2ray-core", "cat": "ciber",
     "nombre": "v2ray-core",
     "url": "https://github.com/v2fly/v2ray-core",
     "desc": "Núcleo de la plataforma de proxy v2ray.",
     "tags": ("proxy", "red")},
    {"id": "adguard-home", "cat": "ciber",
     "nombre": "AdGuard Home",
     "url": "https://github.com/AdguardTeam/AdGuardHome",
     "desc": "Bloqueo de anuncios a nivel de red + DNS (defensa).",
     "tags": ("defensa", "dns")},
    {"id": "trivy", "cat": "ciber",
     "nombre": "Trivy",
     "url": "https://github.com/aquasecurity/trivy",
     "desc": "Escáner de vulnerabilidades en contenedores, código y SBOM "
             "(defensa).",
     "tags": ("defensa", "vulnerabilidades", "contenedores")},
    {"id": "web-check", "cat": "ciber",
     "nombre": "Web-Check",
     "url": "https://github.com/Lissy93/web-check",
     "desc": "Auditoría por lotes de sitios web: cabeceras, TLS, DNS, "
             "subdominios.",
     "tags": ("defensa", "auditoria")},
    {"id": "algo", "cat": "ciber",
     "nombre": "Algo VPN",
     "url": "https://github.com/trailofbits/algo",
     "desc": "VPN WireGuard sin configuración (Trail of Bits).",
     "tags": ("vpn", "wireguard")},
    {"id": "stevenblack-hosts", "cat": "ciber",
     "nombre": "StevenBlack hosts",
     "url": "https://github.com/StevenBlack/hosts",
     "desc": "Ficheros hosts agregados para bloquear trackers y publicidad.",
     "tags": ("defensa", "hosts")},
    {"id": "openssl", "cat": "ciber",
     "nombre": "OpenSSL",
     "url": "https://github.com/openssl/openssl",
     "desc": "Suite criptográfica de referencia para TLS/SSL.",
     "tags": ("cripto", "tls")},
    {"id": "setup-ipsec-vpn", "cat": "ciber",
     "nombre": "Setup IPsec VPN",
     "url": "https://github.com/hwdsl2/setup-ipsec-vpn",
     "desc": "Instalador de servidor IPsec VPN en Linux (autoalojado).",
     "tags": ("vpn", "ipsec")},
    {"id": "nuclei", "cat": "ciber",
     "nombre": "Nuclei",
     "url": "https://github.com/projectdiscovery/nuclei",
     "desc": "Escáner de vulnerabilidades por plantillas; solo sobre alcance "
             "autorizado.",
     "tags": ("escaneo", "vulnerabilidades", "advertido")},
    {"id": "hashcat", "cat": "ciber",
     "nombre": "hashcat",
     "url": "https://github.com/hashcat/hashcat",
     "desc": "Recuperación de contraseñas acelerada por GPU; solo en "
             "auditorías autorizadas.",
     "tags": ("hashes", "gpu", "advertido")},
    {"id": "awesome-pentest", "cat": "ciber",
     "nombre": "Awesome Pentest",
     "url": "https://github.com/enaqx/awesome-pentest",
     "desc": "Catálogo de herramientas y recursos de pentesting.",
     "tags": ("pentest", "referencia")},
    {"id": "h4cker", "cat": "ciber",
     "nombre": "h4cker",
     "url": "https://github.com/The-Art-of-Hacking/h4cker",
     "desc": "Suite multiplataforma de pentesting orientada a la enseñanza.",
     "tags": ("pentest", "educacion")},
    {"id": "system-prompts-leaks", "cat": "ciber",
     "nombre": "System Prompts Leaks (asgeirtj)",
     "url": "https://github.com/asgeirtj/system_prompts_leaks",
     "desc": "Prompts del sistema filtrados de LLMs (Claude, ChatGPT, Gemini, Grok, Copilot, Cursor, Perplexity...; asgeirtj): referencia para auditoría de prompts e inyección; usar en entornos autorizados.",
     "tags": ("prompts", "seguridad", "research")},
    {"id": "gmail-account-creator", "cat": "ciber",
     "nombre": "Gmail Account Creator (ShadowHackrs)",
     "url": "https://github.com/ShadowHackrs/gmail-account-creator",
     "desc": "Scripts para integrar la API oficial de Google sobre la cuenta "
             "principal del operador (obtener credenciales/API una sola vez). "
             "Advertido: no automatiza creación masiva de cuentas ni saltos "
             "de políticas; verificar ToS de Google y el código antes de usar.",
     "tags": ("google", "api", "cuentas", "advertido")},
    # ---- 3. Desarrollo de Software y Arquitectura -----------------------
    {"id": "gworkspace-cli", "cat": "dev",
     "nombre": "Google Workspace CLI",
     "url": "https://github.com/googleworkspace/cli",
     "desc": "CLI para administrar Google Workspace.",
     "tags": ("google", "cli", "administracion")},
    {"id": "bytebytego", "cat": "dev",
     "nombre": "ByteByteGo — Blog de System Design",
     "url": "https://blog.bytebytego.com/",
     "desc": "Artículos de arquitectura y diseño de sistemas con diagramas.",
     "tags": ("system-design", "arquitectura")},
    {"id": "sdd-101", "cat": "dev",
     "nombre": "ByteByteGo — System Design 101",
     "url": "https://github.com/ByteByteGoHq/system-design-101",
     "desc": "Guía ilustrada de diseño de sistemas para estudio.",
     "tags": ("system-design",) },
    {"id": "octocademy", "cat": "dev",
     "nombre": "Octocademy — Utils Library",
     "url": "https://github.com/octocademy/utils-library",
     "desc": "Colección de funciones utilitarias (comunidad).",
     "tags": ("utils",) },
    {"id": "open-source-games", "cat": "dev",
     "nombre": "Open Source Games",
     "url": "https://github.com/bobeff/open-source-games",
     "desc": "Colección de juegos y motores con licencias abiertas.",
     "tags": ("juegos", "open-source")},
    # ---- 4. Directorios de Recursos, Streaming y Juegos ------------------
    {"id": "fmhy", "cat": "directorios",
     "nombre": "FMHY — Search",
     "url": "https://fmhy.net/posts/search",
     "desc": "Buscador del directorio FreeMediaHeckYeah (autogestión de "
             "medios; verificar legalidad local).",
     "tags": ("directorios", "media", "advertido")},
    {"id": "yarrlist", "cat": "directorios",
     "nombre": "Yarrlist",
     "url": "https://yarrlist.net/",
     "desc": "Directorio de listas de torrents y seguimiento de series "
             "(verificar legalidad local).",
     "tags": ("directorios", "advertido")},
    {"id": "deepwebnest", "cat": "directorios",
     "nombre": "DeepWebNest",
     "url": "https://deepwebnest.com/",
     "desc": "Buscador de sitios .onion (Tor; riesgos de phishing altos).",
     "tags": ("onion", "tor", "advertido")},
    {"id": "flixer", "cat": "directorios",
     "nombre": "Flixer (Streaming)",
     "url": "https://flixer.su/",
     "desc": "Sitio de streaming sin licencia verificable: zona gris legal, "
             "bajo responsabilidad del operador.",
     "tags": ("streaming", "advertido")},
    {"id": "anker-games", "cat": "directorios",
     "nombre": "Anker Games",
     "url": "https://ankergames.net/games-list",
     "desc": "Lista de juegos (comunidad; verificar licencias y legalidad "
             "local).",
     "tags": ("juegos", "advertido")},
    # ---- 5. Herramientas Web, Utilidades y Finanzas ----------------------
    {"id": "imagetotext", "cat": "utilidades",
     "nombre": "Image to Text (OCR)",
     "url": "https://www.imagetotext.info/",
     "desc": "Extracción de texto de imágenes (OCR).",
     "tags": ("ocr",) },
    {"id": "veepn", "cat": "utilidades",
     "nombre": "VeePN",
     "url": "https://veepn.com/",
     "desc": "Servicio VPN (comparar política de privacidad y términos antes "
             "de pagar).",
     "tags": ("vpn",) },
    {"id": "delphi-tools", "cat": "utilidades",
     "nombre": "Delphi Tools",
     "url": "https://delphi.tools/",
     "desc": "Utilidades web para desarrollo.",
     "tags": ("tools",) },
    {"id": "sideshift", "cat": "utilidades",
     "nombre": "SideShift",
     "url": "https://sideshift.app/",
     "desc": "Monetización para creadores y exchange P2P (verificar "
             "regulación local y términos).",
     "tags": ("finanzas", "creadores")},
    {"id": "invoapp", "cat": "utilidades",
     "nombre": "InvoApp (Copy trading)",
     "url": "https://invoapp.com/join/tradewzay",
     "desc": "Plataforma de copy trading (enlace de referido; la inversión "
             "conlleva riesgo de pérdida).",
     "tags": ("finanzas", "copy-trading", "advertido")},
    # ---- 6. Empleo, Estilo de Vida y Entretenimiento ---------------------
    {"id": "four-day-week", "cat": "empleo",
     "nombre": "4 Day Week",
     "url": "https://4dayweek.io/",
     "desc": "Empleos remotos con jornada de 4 días.",
     "tags": ("empleo", "remoto")},
    {"id": "instahyre", "cat": "empleo",
     "nombre": "Instahyre",
     "url": "https://instahyre.com/",
     "desc": "Marketplace de talento y contratación.",
     "tags": ("empleo",) },
    {"id": "darebee", "cat": "empleo",
     "nombre": "Darebee",
     "url": "https://darebee.com/",
     "desc": "Planes de entrenamiento y biblioteca de ejercicios en PDF.",
     "tags": ("fitness",) },
    {"id": "nealfun", "cat": "empleo",
     "nombre": "Neal.fun",
     "url": "https://neal.fun/",
     "desc": "Juegos y experimentos interactivos.",
     "tags": ("juegos", "entretenimiento")},
    {"id": "fashionreps", "cat": "empleo",
     "nombre": "Reddit — FashionReps",
     "url": "https://www.reddit.com/r/FashionReps/",
     "desc": "Comunidad sobre réplicas de moda (zona gris: legalidad local "
             "y reglas de la plataforma).",
     "tags": ("comunidad", "moda", "advertido")},
)

_CAT_NOMBRE = {c["id"]: c["nombre"] for c in CATEGORIAS}


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")


def _slug(texto: str) -> str:
    out = []
    for ch in _norm(texto):
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "recurso"


def _cat_coincide(valor: str) -> Optional[str]:
    """Id de la categoría si ``valor`` es su id o contiene/contiene su nombre."""
    v = _norm((valor or "").strip())
    if not v:
        return None
    for c in CATEGORIAS:
        nombre = _norm(c["nombre"])
        if c["id"] == v or v == nombre or v in nombre or nombre in v:
            return c["id"]
    return None


def _entry(e: dict[str, Any]) -> dict[str, Any]:
    return {**e, "categoria": _CAT_NOMBRE.get(e["cat"], "")}


# ---------------------------------------------------------------------------
# Registro declarativo de fuentes externas
# ---------------------------------------------------------------------------

SOURCE_TYPES = frozenset(("code", "api", "docs", "workflow", "dataset", "tool"))
SOURCE_POLICIES = frozenset(("allowed", "reference_only", "blocked"))
ADAPTER_STATUSES = frozenset(("verified", "unavailable"))
_BLOCKED_MARKERS = ("malware", "wormware", "worm-gpt", "account creator",
                    "creador de cuentas", "evasion", "credencial", "credential")


@dataclass(frozen=True)
class FuenteExterna:
    """Fuente declarativa: describirla nunca implica acceder a ella."""

    id: str
    url: str
    nombre: str
    categoria: str
    tipo: str
    licencia: str
    dependencia: str
    capabilities: tuple[str, ...]
    policy: str
    adapter_status: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        return data


def _source_type(entry: dict[str, Any]) -> str:
    explicit = entry.get("type") or entry.get("tipo")
    if explicit in SOURCE_TYPES:
        return explicit
    text = " ".join((entry.get("nombre", ""), entry.get("desc", ""),
                     " ".join(entry.get("tags", ()))))
    lowered = _norm(text)
    if "workflow" in lowered or "flujo" in lowered:
        return "workflow"
    if "api" in lowered:
        return "api"
    if "curso" in lowered or "blog" in lowered or "document" in lowered:
        return "docs"
    if "dataset" in lowered or "datos" in lowered:
        return "dataset"
    if "tool" in lowered or "herramienta" in lowered or "suite" in lowered:
        return "tool"
    return "code" if "github.com" in entry.get("url", "") else "docs"


def _source_policy(entry: dict[str, Any]) -> str:
    text = _norm(" ".join((entry.get("nombre", ""), entry.get("desc", ""),
                           " ".join(entry.get("tags", ()))))
                  ).replace("_", " ")
    return "blocked" if any(marker in text for marker in _BLOCKED_MARKERS) else "reference_only"


def _source_from_entry(entry: dict[str, Any], workspace: str = "") -> FuenteExterna:
    from .capacidades import resolver

    cap = resolver(entry["id"], workspace)
    return FuenteExterna(
        id=entry["id"], url=entry.get("url", ""), nombre=entry["nombre"],
        categoria=entry.get("cat", "unknown"), tipo=_source_type(entry),
        licencia=entry.get("license", "unknown"),
        dependencia=entry.get("dependency", "unknown"),
        capabilities=(cap.capacidad,), policy=_source_policy(entry),
        adapter_status="verified" if cap.mapa_a2s else "unavailable",
    )


class SourceRegistry:
    """Registro local, serializable y sin operaciones de red."""

    def __init__(self, sources: Iterable[FuenteExterna] = ()) -> None:
        self._sources = {source.id: source for source in sources}

    def register(self, source: FuenteExterna) -> FuenteExterna:
        if not isinstance(source, FuenteExterna):
            raise TypeError("source debe ser FuenteExterna")
        if source.tipo not in SOURCE_TYPES or source.policy not in SOURCE_POLICIES:
            raise ValueError("tipo o policy de fuente inválido")
        if source.adapter_status not in ADAPTER_STATUSES:
            raise ValueError("adapter_status de fuente inválido")
        if not source.id or not source.nombre or not source.url:
            raise ValueError("una fuente necesita id, nombre y URL")
        self._sources[source.id] = source
        return source

    def get(self, source_id: str) -> FuenteExterna:
        return self._sources[source_id]

    def search(self, capability: str = "", categoria: str = "") -> list[FuenteExterna]:
        cap = _norm(capability).strip()
        cat = _norm(categoria).strip()
        return [source for source in self._sources.values()
                if (not cap or any(cap in _norm(value) for value in source.capabilities))
                and (not cat or _norm(source.categoria) == cat)]

    def can_use(self, source_id: str,
                mission_capabilities: Iterable[str] = ()) -> dict[str, Any]:
        source = self.get(source_id)
        wanted = {_norm(value) for value in mission_capabilities}
        matches = not wanted or bool(wanted & {_norm(value) for value in source.capabilities})
        allowed = (source.policy == "allowed" and matches
               and source.adapter_status == "verified")
        if source.policy == "blocked":
            reason = "fuente bloqueada por política"
        elif source.policy == "reference_only":
            reason = "fuente solo de referencia; requiere adapter verificado"
        elif source.adapter_status != "verified":
            reason = "fuente sin adapter verificado"
        elif not matches:
            reason = "la fuente no declara la capacidad de la misión"
        else:
            reason = "fuente autorizada"
        return {"source_id": source.id, "allowed": allowed,
                "reason": reason, "source": source.to_dict()}

    def plan(self, goal: str, context: Any = None,
             include_reference_only: bool = False) -> list[dict[str, Any]]:
        """Selecciona capacidades declarativamente, sin acceder a fuentes.

        ``reference_only`` solo entra cuando se solicita expresamente para
        planificar; una fuente ``blocked`` nunca puede formar parte del plan.
        """
        if not isinstance(goal, str):
            raise TypeError("goal debe ser texto")
        query = _planning_text(goal, context)
        terms = set(re.findall(r"[a-z0-9]+", _norm(query)))
        rows = []
        for source in sorted(self._sources.values(), key=lambda item: item.id):
            if source.policy == "blocked":
                continue
            if source.policy == "reference_only" and not include_reference_only:
                continue
            matches = [capability for capability in source.capabilities
                       if _capability_matches(capability, query, terms)]
            if not matches:
                continue
            reason = ("capacidad autorizada para la misión"
                      if source.policy == "allowed" else
                      "capacidad de referencia incluida explícitamente")
            rows.append({
                "source": source.id,
                "capabilities": matches,
                "reason": reason,
                "policy": source.policy,
                "adapter_status": source.adapter_status,
            })
        return rows

    def to_list(self) -> list[dict[str, Any]]:
        return [source.to_dict() for source in self._sources.values()]


def source_registry(workspace: str = "") -> SourceRegistry:
    """Construye el registro desde catálogos locales, sin consultar URLs."""
    return SourceRegistry(_source_from_entry(entry, workspace)
                          for entry in _todas(workspace) if entry.get("url"))


def _planning_text(goal: str, context: Any) -> str:
    parts = [goal]
    if context is not None:
        if isinstance(context, str):
            parts.append(context)
        elif isinstance(context, dict):
            parts.extend(str(value) for value in context.values())
        else:
            try:
                parts.extend(str(value) for value in context)
            except TypeError as exc:
                raise TypeError("context debe ser texto, mapa o iterable") from exc
    return " ".join(parts)


def _capability_matches(capability: str, query: str,
                        query_terms: set[str]) -> bool:
    normalized = _norm(capability).replace("_", " ")
    capability_terms = set(re.findall(r"[a-z0-9]+", normalized))
    query_normalized = _norm(query).replace("_", " ")
    return normalized in query_normalized or bool(capability_terms & query_terms)


def planificar_capacidades(goal: str, context: Any = None,
                           include_reference_only: bool = False,
                           workspace: str = "") -> list[dict[str, Any]]:
    """Genera un plan de capacidades local y declarativo."""
    return source_registry(workspace).plan(
        goal, context, include_reference_only=include_reference_only)


def serializar_plan_capacidades(plan: Iterable[dict[str, Any]]) -> str:
    """Serializa un plan sin añadir efectos ni resolver sus fuentes."""
    return json.dumps(list(plan), ensure_ascii=True, indent=2, sort_keys=True)


def buscar_fuentes(capability: str = "", categoria: str = "",
                   workspace: str = "") -> list[dict[str, Any]]:
    return [source.to_dict() for source in
            source_registry(workspace).search(capability, categoria)]


def puede_usarse_fuente(source_id: str, mission_capabilities: Iterable[str] = (),
                        workspace: str = "") -> dict[str, Any]:
    return source_registry(workspace).can_use(source_id, mission_capabilities)


def serializar_fuentes(sources: Iterable[FuenteExterna]) -> str:
    return json.dumps([source.to_dict() for source in sources],
                      ensure_ascii=True, indent=2, sort_keys=True)


def deserializar_fuentes(payload: str) -> SourceRegistry:
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError("el registro serializado debe ser una lista")
    return SourceRegistry(FuenteExterna(
        id=row["id"], url=row["url"], nombre=row["nombre"],
        categoria=row["categoria"], tipo=row["tipo"], licencia=row["licencia"],
        dependencia=row["dependencia"],
        capabilities=tuple(row["capabilities"]), policy=row["policy"],
        adapter_status=row["adapter_status"]) for row in rows)


# ---------------------------------------------------------------------------
# Recursos propios del operador (persistidos en workspace/.a2s/recursos.json)
# ---------------------------------------------------------------------------

def _extra_path(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace or "."), ".a2s", "recursos.json")


def extras(workspace: str) -> list[dict[str, Any]]:
    """Recursos añadidos por el operador (no forman parte del catálogo base)."""
    path = _extra_path(workspace)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        rows = data.get("recursos", [])
        return [r for r in rows if isinstance(r, dict) and r.get("id")]
    except (OSError, ValueError):
        return []


def extra_add(workspace: str, nombre: str, url: str, cat: str,
              desc: str = "", tags: Optional[list[str]] = None) -> dict[str, Any]:
    """Añade un recurso propio del operador (validado) y lo persiste."""
    nombre = (nombre or "").strip()
    url = (url or "").strip()
    if not nombre:
        raise ValueError("falta el nombre del recurso")
    cid = _cat_coincide(cat)
    if cid is None:
        raise ValueError("categoría desconocida: usa ia, ciber, dev, directorios, "
                         "utilidades o empleo")
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("URL inválida: debe empezar por http:// o https://")
    base = [_entry(e) for e in ENTRADAS] + extras(workspace)
    ids = {e["id"] for e in base}
    ident = _slug(nombre)
    while ident in ids:
        ident += "-2"
    entry = {"id": ident, "cat": cid, "nombre": nombre[:120], "url": url[:300],
             "desc": (desc or "")[:300] or f"Recurso propio del operador ({cid}).",
             "tags": [t.strip().lower()[:32] for t in (tags or []) if t.strip()][:8],
             "custom": True, "added_at": now_iso()}
    rows = extras(workspace)
    rows.append(entry)
    path = _extra_path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "recursos": rows}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return entry


def extra_forget(workspace: str, ident: str) -> bool:
    """Olvida un recurso propio (los del catálogo base no se eliminan)."""
    ident = (ident or "").strip()
    if not ident:
        return False
    rows = extras(workspace)
    kept = [r for r in rows if r.get("id") != ident]
    if len(kept) == len(rows):
        return False
    path = _extra_path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "recursos": kept}, fh, ensure_ascii=False, indent=1)
    return True


def _todas(workspace: str) -> list[dict[str, Any]]:
    """Catálogo base + recursos propios del workspace (orden estable)."""
    rows = list(ENTRADAS)
    rows.extend(extras(workspace) if workspace else [])
    return rows


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def categorias(workspace: str = "") -> list[dict[str, Any]]:
    """Categorías con su recuento de entradas (base + propios del workspace)."""
    out = []
    for c in CATEGORIAS:
        count = sum(1 for e in _todas(workspace) if e["cat"] == c["id"])
        out.append({**c, "count": count})
    return out

def entradas(cat: str = "", workspace: str = "") -> list[dict[str, Any]]:
    """Entradas (base + propias), todas o de una categoría por id/nombre."""
    cid = _cat_coincide(cat) if cat else None
    if cat and cid is None:
        return []
    return [_entry(e) for e in _todas(workspace)
            if cid is None or e["cat"] == cid]


def buscar(consulta: str, top: int = 25, workspace: str = "") -> list[dict[str, Any]]:
    """Búsqueda BM25 sobre nombre, descripción, etiquetas, URL y categoría."""
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    docs = docs_memoria(workspace)
    hits = BM25Index(docs).search(consulta, top=top)
    out = []
    for doc, score in hits:
        entry = next((e for e in _todas(workspace)
                      if e["id"] == doc.doc_id.split(":", 1)[1]), None)
        if entry is not None:
            out.append({**_entry(entry), "score": round(score, 4)})
    return out


def docs_memoria(workspace: str = "") -> list[Doc]:
    """Documentos para ``a2s search`` (origen ``recurso``)."""
    docs = []
    for e in _todas(workspace):
        partes = [e["nombre"], e["desc"], " ".join(e.get("tags", ())),
                  _CAT_NOMBRE.get(e["cat"], "")]
        if e.get("url"):
            partes.append(e["url"])
        docs.append(Doc(
            doc_id=f"recurso:{e['id']}",
            texto=" ".join(partes),
            origen="recurso",
            meta=f"{e['nombre']} · {_CAT_NOMBRE.get(e['cat'], '')}"))
    return docs


def api_snapshot(consulta: str = "", cat: str = "", top: int = 25,
                 workspace: str = "") -> dict[str, Any]:
    """Snapshot para la API/CLI: lista o búsqueda + metadatos."""
    consulta = (consulta or "").strip()
    cat = (cat or "").strip()
    if consulta:
        rows = buscar(consulta, top=top, workspace=workspace)
        cid = _cat_coincide(cat)
        if cid:
            rows = [r for r in rows if r["cat"] == cid]
    else:
        rows = entradas(cat, workspace=workspace)
    from .capacidades import resumen as _cap_resumen
    return {"total": len(_todas(workspace)),
            "total_base": len(ENTRADAS),
            "consulta": consulta,
            "categoria": cat,
            "recursos": rows,
            "categorias": categorias(workspace),
            "check": estado_check(workspace),
            "capacidades": _cap_resumen(workspace),
            "aviso": AVISO_ETICO}


def validar(workspace: str = "") -> list[str]:
    """Problemas de integridad del catálogo (base + propios del workspace)."""
    problemas: list[str] = []
    ids: set[str] = set()
    urls: set[str] = set()
    for e in _todas(workspace):
        if e["id"] in ids:
            problemas.append(f"dup id: {e['id']}")
        ids.add(e["id"])
        if e["cat"] not in _CAT_NOMBRE:
            problemas.append(f"{e['id']}: categoría desconocida «{e['cat']}»")
        if not e["nombre"].strip():
            problemas.append(f"{e['id']}: sin nombre")
        if e.get("url"):
            if not e["url"].startswith(("http://", "https://")):
                problemas.append(f"{e['id']}: URL inválida «{e['url']}»")
            if e["url"] in urls:
                problemas.append(f"duplicada URL: {e['url']}")
            urls.add(e["url"])
    return problemas


# ---------------------------------------------------------------------------
# Chequeo de enlaces (GET ligero; sin ejecución, solo disponibilidad)
# ---------------------------------------------------------------------------

def _chequear_uno(e: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Chequeo HTTP de una entrada (estado + latencia)."""
    import time
    import urllib.error
    import urllib.request
    base = {**e, "ok": False, "estado": "", "ms": None, "sin_enlace": False}
    if not e.get("url"):
        base["estado"] = "sin enlace"
        base["sin_enlace"] = True
        return base
    req = urllib.request.Request(
        e["url"], method="GET",
        headers={"User-Agent": "A2S-Recursos/1.24 (verificacion de enlaces)"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            base["ok"] = resp.status < 400
            base["estado"] = f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        base["estado"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — diagnóstico por URL
        base["estado"] = type(exc).__name__
    base["ms"] = int((time.monotonic() - t0) * 1000)
    return base


def comprobar_enlaces(entries: list[dict[str, Any]], timeout: float = 8.0,
                      workers: int = 8) -> list[dict[str, Any]]:
    """Disponibilidad HTTP de las entradas, en paralelo (orden preservado).

    ``workers=0`` fuerza modo secuencial (reproducible, depuración).
    """
    if workers <= 1 or len(entries) <= 1:
        return [_chequear_uno(e, timeout) for e in entries]
    from concurrent.futures import ThreadPoolExecutor
    n = max(1, min(workers, len(entries)))
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(lambda e: _chequear_uno(e, timeout), entries))


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def _nota_check(e: dict[str, Any], check: Optional[dict[str, Any]]) -> str:
    """Nota del último chequeo HTTP para una entrada (Markdown)."""
    if not check or not e.get("url"):
        return ""
    st = (check.get("results") or {}).get(e["id"])
    if not st:
        return ""
    when = (check.get("at") or "")[:16]
    if st.get("ok"):
        return f" · *{st.get('estado', 'ok')} · {when}*"
    return f" · *⚠ {st.get('estado', 'caído')} · {when}*"


def como_markdown(workspace: str = "") -> str:
    """Export del catálogo (base + propios) en Markdown."""
    check = estado_check(workspace)
    lineas = ["# Catálogo de recursos A²S", "", f"> {AVISO_ETICO}", ""]
    rows = _todas(workspace)
    for c in CATEGORIAS:
        cat_rows = [e for e in rows if e["cat"] == c["id"]]
        lineas.append(f"## {c['nombre']} ({len(cat_rows)})")
        lineas.append("")
        for e in cat_rows:
            if e.get("url"):
                titulo = f"[{e['nombre']}]({e['url']})"
            else:
                titulo = f"{e['nombre']} *(sin enlace oficial)*"
            if e.get("custom"):
                titulo += " · *propio*"
            lineas.append(f"- {titulo} — {e['desc']}{_nota_check(e, check)}")
            if e.get("tags"):
                lineas.append(f"  - etiquetas: {', '.join(e['tags'])}")
        lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def _sello_check(e: dict[str, Any], check: Optional[dict[str, Any]]) -> str:
    """Sello del último chequeo HTTP para una entrada (HTML)."""
    import html as _h
    if not check or not e.get("url"):
        return ""
    st = (check.get("results") or {}).get(e["id"])
    if not st:
        return ""
    detail = f'{st.get("estado", "")} · {(check.get("at") or "")[:16]}'
    cls = "sel check ok" if st.get("ok") else "sel check fail"
    return f'<span class="{cls}" title="{detail}">' \
           f'{"✔" if st.get("ok") else "✗"} {_h.escape(st.get("estado", ""))}</span>'


def como_html(workspace: str = "") -> str:
    """Export autocontenido (un solo archivo) para el evento: buscador inline."""
    import html as _h
    check = estado_check(workspace)
    secciones = []
    for c in CATEGORIAS:
        cat_rows = [e for e in _todas(workspace) if e["cat"] == c["id"]]
        items = []
        for e in cat_rows:
            nombre = _h.escape(e["nombre"])
            url = e.get("url", "")
            if url:
                titulo = (f'<a href="{_h.escape(url, quote=True)}" target="_blank" '
                          f'rel="noopener noreferrer">{nombre}</a>')
            else:
                titulo = f"<b>{nombre}</b>"
            warn = '<span class="sel warn">ADVERTIDO</span>' if "advertido" in e.get("tags", ()) else ""
            propio = '<span class="sel propio">PROPIO</span>' if e.get("custom") else ""
            ck = _sello_check(e, check)
            tags = " ".join(_h.escape(t) for t in e.get("tags", ()))
            url_html = f'<small class="url">{_h.escape(url)}</small>' if url else ""
            items.append(
                f'<li data-cat="{c["id"]}" data-tags="{tags}">'
                f'<div class="rhead">{titulo}{warn}{propio}{ck}'
                f'<span class="cat">{_h.escape(c["nombre"])}</span></div>'
                f'<p>{_h.escape(e["desc"])}</p>{url_html}</li>')
        secciones.append(
            f'<section><h2>{_h.escape(c["nombre"])} <span class="n">{len(cat_rows)}</span></h2>'
            f'<ul>{"".join(items)}</ul></section>')
    aviso = _h.escape(AVISO_ETICO)
    total = len(_todas(workspace))
    if check:
        check_stamp = (f" · último check: {(check.get('at') or '')[:16]} "
                       f"({check.get('ok')}/{check.get('total')} alcanzables)")
    else:
        check_stamp = " · sin chequeo todavía (a2s recursos --check)"
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catálogo de recursos A²S</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; padding: 28px 20px 60px; background: #07111d; color: #c7d3de; font: 14px/1.55 system-ui, sans-serif; }}
header {{ max-width: 980px; margin: 0 auto 18px; }}
h1 {{ margin: 0 0 6px; font-size: 22px; color: #e8f0f6; }}
.aviso {{ margin: 0 0 14px; padding: 10px 14px; border: 1px solid #1d4539; background: #0b1c1a; color: #70a99a; font-size: 12px; }}
input {{ width: min(420px, 100%); padding: 10px 12px; margin-bottom: 18px; color: #e8f0f6; background: #0a1621; border: 1px solid #2c4154; border-radius: 6px; font-size: 13px; }}
main {{ max-width: 980px; margin: 0 auto; }}
section {{ margin-bottom: 26px; }}
h2 {{ font-size: 15px; color: #9fdce6; border-bottom: 1px solid #172a3a; padding-bottom: 6px; }}
h2 .n {{ color: #506a7e; font-size: 12px; }}
ul {{ list-style: none; margin: 0; padding: 0; }}
li {{ padding: 10px 2px; border-bottom: 1px solid #10202e; }}
.rhead {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
.rhead a {{ color: #d7e3ee; font-weight: 600; text-decoration: none; }}
.rhead a:hover {{ color: #20d7e6; }}
.rhead b {{ color: #d7e3ee; }}
.sel {{ padding: 2px 6px; border-radius: 4px; font: 700 9px/1.4 ui-monospace, monospace; letter-spacing: .08em; }}
.sel.warn {{ color: #e5b45a; border: 1px solid #5d4827; background: #211b0e; }}
.sel.propio {{ color: #7fd4a0; border: 1px solid #21533f; background: #0d211c; }}
.cat {{ margin-left: auto; color: #506a7e; font: 9px/1.4 ui-monospace, monospace; letter-spacing: .06em; }}
.sel.check {{ font-size: 9px; }}
.sel.check.ok {{ color: #7fd4a0; border: 1px solid #21533f; background: #0d211c; }}
.sel.check.fail {{ color: #e08a8a; border: 1px solid #5c2b35; background: #221117; }}
p {{ margin: 5px 0 0; color: #788da0; font-size: 12px; }}
.url {{ color: #506a7e; font: 11px/1.4 ui-monospace, monospace; word-break: break-all; }}
footer {{ max-width: 980px; margin: 30px auto 0; color: #44586c; font-size: 11px; }}
</style>
</head>
<body>
<header>
<h1>Catálogo de recursos A²S · {total} entradas</h1>
<p class="aviso">{aviso}</p>
<input id="q" type="search" placeholder="Filtrar: ghidra, vpn, pentest…" aria-label="Filtrar catálogo">
</header>
<main>
{"".join(secciones)}
</main>
<footer>Generado por a2s recursos --html · A²S v1.23{check_stamp} · referencia y estudio; el uso debe ser autorizado, defensivo o académico.</footer>
<script>
document.getElementById("q").addEventListener("input", (e) => {{
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("main li").forEach((li) => {{
    li.style.display = li.textContent.toLowerCase().includes(q) ? "" : "none";
  }});
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Chequeo persistido (estado para el material del evento)
# ---------------------------------------------------------------------------

def _check_path(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace or "."), ".a2s",
                        "recursos_check.json")


def estado_check(workspace: str) -> Optional[dict[str, Any]]:
    """Último chequeo de enlaces persistido (None si aún no existe)."""
    path = _check_path(workspace)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and data.get("results") else None
    except (OSError, ValueError):
        return None


def guardar_check(workspace: str, results: list[dict[str, Any]],
                  timeout: float = 8.0) -> dict[str, Any]:
    """Persiste un chequeo completo de enlaces (solo chequeos de todo)."""
    con_url = [r for r in results if not r.get("sin_enlace")]
    data = {"version": 1, "at": now_iso(), "timeout": timeout,
            "ok": sum(1 for r in con_url if r.get("ok")),
            "total": len(con_url),
            "results": {r["id"]: {"ok": bool(r.get("ok")),
                                  "estado": r.get("estado", ""),
                                  "ms": r.get("ms")} for r in results}}
    path = _check_path(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    return data


def como_pdf(ruta: str, workspace: str = "") -> int:
    """Export en PDF (MiniPDF, stdlib) para el evento. Devuelve páginas."""
    from .pdf import MiniPDF
    check = estado_check(workspace)
    doc = MiniPDF("Catálogo de recursos A²S")
    doc.cover("Catálogo de recursos A²S",
              f"{len(_todas(workspace))} entradas en {len(CATEGORIAS)} categorías",
              AVISO_ETICO)
    for c in CATEGORIAS:
        cat_rows = [e for e in _todas(workspace) if e["cat"] == c["id"]]
        doc.h2(f"{c['nombre']} ({len(cat_rows)})")
        for e in cat_rows:
            marcas = []
            if "advertido" in e.get("tags", ()):
                marcas.append("[ADVERTIDO]")
            if e.get("custom"):
                marcas.append("[propio]")
            st = ((check or {}).get("results") or {}).get(e["id"]) \
                if e.get("url") else None
            if st:
                marcas.append(f"[{st.get('estado', '?')}]")
            doc.bullet(f"{e['nombre']} {' '.join(marcas)} — {e['desc']}", size=9)
            if e.get("url"):
                doc.para(e["url"], size=7.8, indent=14)
        doc.spacer(8)
    return doc.save(ruta)


_PPT_POR_PAGINA = 9


def _puntos_ppt(e: dict[str, Any],
                check: Optional[dict[str, Any]]) -> str:
    """Viñeta compacta de una entrada para PPT (con marcas y estado)."""
    marcas = []
    if "advertido" in e.get("tags", ()):
        marcas.append("[ADVERTIDO]")
    if e.get("custom"):
        marcas.append("[propio]")
    st = ((check or {}).get("results") or {}).get(e["id"]) if e.get("url") else None
    if st and st.get("estado"):
        marcas.append(f"[{st.get('estado')}]")
    desc = (e.get("desc") or "")[:120]
    return f"{e['nombre']} {' '.join(marcas)} — {desc}"


def como_pptx(ruta: str, workspace: str = "") -> int:
    """Presentación del catálogo para el evento (PPTX, stdlib). Páginas."""
    from .slides import Slide, write_pptx
    check = estado_check(workspace)
    rows = _todas(workspace)
    slides = [Slide("Catálogo de recursos A²S", [
        f"{len(rows)} entradas en {len(CATEGORIAS)} categorías",
        "Referencia y estudio para el evento",
        AVISO_ETICO[:140],
    ], "Portada: el uso debe ser autorizado, defensivo o académico.", "title")]
    for c in CATEGORIAS:
        cat_rows = [e for e in rows if e["cat"] == c["id"]]
        paginas = (len(cat_rows) + _PPT_POR_PAGINA - 1) // _PPT_POR_PAGINA
        for i in range(0, len(cat_rows), _PPT_POR_PAGINA):
            chunk = cat_rows[i:i + _PPT_POR_PAGINA]
            n = i // _PPT_POR_PAGINA + 1
            titulo = (f"{c['nombre']} ({n}/{paginas})" if paginas > 1
                      else f"{c['nombre']} ({len(cat_rows)})")
            urls = ", ".join(e["url"] for e in cat_rows if e.get("url"))[:600]
            slides.append(Slide(
                titulo,
                [_puntos_ppt(e, check) for e in chunk],
                f"URLs de la categoría: {urls}" if urls else "Sin URLs en esta categoría."))
    if check:
        fails = [rid for rid, st in (check.get("results") or {}).items()
                 if not st.get("ok") and st.get("estado") != "sin enlace"]
        slides.append(Slide("Estado de enlaces", [
            f"Último chequeo: {(check.get('at') or '')[:16]} · "
            f"timeout {check.get('timeout')}s",
            f"{check.get('ok')}/{check.get('total')} enlaces alcanzables",
            f"Caídos ({len(fails)}): {', '.join(fails[:8]) or 'ninguno'}"
            + (f" +{len(fails) - 8}" if len(fails) > 8 else ""),
            "Instantánea, no garantía: repasar con a2s recursos --estado",
        ], "La disponibilidad cambia; el chequeo es una foto del momento."))
    write_pptx(ruta, "Catálogo de recursos A²S", slides)
    return len(slides)
