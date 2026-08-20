"""A²S — Agente Autónomo Supremo (interfaz pública).

Framework de agente autónomo con loops auto-optimizados, superación de
estancamiento, memoria jerárquica, metaprendizaje por rendimiento, sub-agentes
fractales y registro forense con cadena de custodia digital.

Opera con dos motores de razonamiento intercambiables (más el pool SORL):

* ``HeuristicProvider``  — núcleo heurístico determinista (sin red, sin claves).
* ``OpenAICompatProvider`` — LLM vía API externa compatible con OpenAI
  (``OPENAI_API_KEY`` + ``A2S_LLM_BASE_URL`` opcional), sin consumo de recursos
  locales de cómputo.
* ``ProviderPool`` (SORL) — meta-proveedor que orquesta **los recursos
  legítimos del operador** (claves propias, free tiers dentro de sus términos,
  modelos locales) con cuotas por endpoint, failover que respeta
  ``Retry-After``, telemetría persistente y fanout/DAG paralelo
  (``--provider pool``).

Uso rápido::

    python -m a2s run "objetivo aquí"
    python -m a2s demo
    python -m a2s pool-status
    python -m a2s dashboard --port 8000
"""

__version__ = "1.5.0"
__all__ = ["__version__"]

from .loop import AgentLoop, run_goal
from .memory import MemoryHub
from .providers import HeuristicProvider, OpenAICompatProvider, get_provider
from .provider_pool import ProviderPool
