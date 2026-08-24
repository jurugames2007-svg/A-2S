"""Configuración global y modelo de permisos (safety)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Parámetros operativos del agente.

    Todos los límites son *adaptativos*: al alcanzarse no se abandona el
    objetivo, se reestructura el plan (ver ``AgentLoop``).
    """
    # Presupuestos adaptativos (el loop los renueva re-planificando).
    max_iterations: int = 60          # presupuesto por ronda de plan
    max_rounds: int = 6               # rondas de replanificación fractal
    max_wall_seconds: int = 900       # límite duro de tiempo (seguridad)
    max_subagents: int = 4            # sub-agentes fractales en paralelo
    subagent_share: float = 0.35      # fracción del presupuesto cedida a hijos
    max_fractal_depth: int = 3        # profundidad máxima de división fractal
    speculative_candidates: int = 0   # planes candidatos evaluados por la red
                                      # de gobernanza (0 = rotación clásica)
    # Detección de estancamiento.
    stagnation_window: int = 4        # intentos fallidos seguidos
    # Proveedor de razonamiento.
    provider: str = "auto"            # auto = pool SORL/OmniRoute + fallback heurístico
    llm_model: str = field(default_factory=lambda: os.environ.get("A2S_LLM_MODEL", "gpt-4o-mini"))
    llm_base_url: Optional[str] = field(default_factory=lambda: os.environ.get("A2S_LLM_BASE_URL"))
    temperature: float = 0.2
    # Pool SORL (solo si provider == "pool").
    pool_strategy: str = field(default_factory=lambda: os.environ.get(
        "A2S_POOL_STRATEGY", "multi_objective"))  # round_robin|cost_first|speed_first|multi_objective
    pool_config: Optional[str] = field(default_factory=lambda: os.environ.get("A2S_POOL_CONFIG"))
    pool_max_parallel: int = 8        # subtareas concurrentes en fanout/DAG
    # Rutas (raíz del espacio de trabajo del agente).
    workspace: str = field(default_factory=lambda: os.environ.get("A2S_WORKSPACE", "workspace"))
    # Permisos.
    allow_network: bool = True
    allow_shell: bool = True
    shell_unsafe: bool = False        # requiere --unsafe: comandos sin lista blanca
    network_allowlist: list[str] = field(default_factory=list)  # hosts permitidos (vacío = todos)
    sandbox: bool = True              # aislar python_exec (nsjail > bwrap > rlimits)
    max_plugins: int = 4              # plugins simultáneos (mínimo hardware)
    evolve_generations: int = 0       # generaciones de neuroevolución al finalizar (0 = off)
    # Verbosidad.
    verbose: bool = True
    quiet: bool = False

    def log(self, msg: str) -> None:
        if not self.quiet:
            print(msg, flush=True)


@dataclass
class DeniedAction:
    """Registro de una acción rechazada por el modelo de permisos."""
    at: str
    tool: str
    reason: str


# --------------------------------------------------------------------------
# Modelo de permisos: implementa la "directiva de ejecución segura".
#
# El marco rechaza acciones cuyo único propósito es dañar o atacar terceros:
# exfiltración de credenciales, malware, evasión de controles de seguridad de
# sistemas ajenos, suplantación, ataques a infraestructura, etc.
#
# Sus equivalentes legítimos — auto-depuración, reparametrización de
# estrategias, auditoría inmutable y forense de artefactos propios — están
# implementados de primera clase en el núcleo.
# --------------------------------------------------------------------------

FORBIDDEN_PATTERNS = (
    "credential", "password", "api_key", "secret", "token de acceso",
    "exfiltrar", "exfiltration", "ransomware", "malware", "botnet",
    "ddos", "denegación de servicio", "phishing", "suplantar identidad",
    "inyección sql", "sqli", "exploit", "escalada de privilegios",
    "backdoor", "rootkit", "keylogger", "spyware", "evadir detección",
    "eludir antivirus", "crackear", "cracking", "piratear cuenta",
)

SHELL_ALLOWLIST = (
    "ls", "cat", "head", "tail", "wc", "find", "grep", "file", "stat",
    "sha256sum", "md5sum", "git", "pwd", "mkdir", "touch", "python3",
    "python", "cp", "mv", "rm", "du", "df", "date", "echo", "test",
    "diff", "sort", "uniq", "sed", "awk", "zip", "unzip", "tar",
)


def classify_forbidden(text: str) -> Optional[str]:
    """Devuelve el motivo si el texto describe una acción prohibida."""
    lowered = (text or "").lower()
    for pat in FORBIDDEN_PATTERNS:
        if pat in lowered:
            return f"acción prohibida por el modelo de permisos (patrón: '{pat}')"
    return None
