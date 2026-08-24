"""Asistente conversacional en paralelo a las misiones.

El ``ChatManager`` mantiene una conversación con el operador y se ejecuta en
su propio hilo, por lo que se puede hablar con el agente **mientras una
misión está corriendo**. Usa el mismo proveedor de razonamiento que el núcleo
(pool SORL / OmniRoute / OpenAI / heurístico) y comparte su telemetría y
failover: si un endpoint satura, la conversación migra a otro recurso
autorizado sin que el operador lo note.

Diseño:

* Historial persistido en ``workspace/.a2s/chat_history.json``.
* Cada respuesta se calcula en un hilo daemon: la API responde inmediatamente
  y el texto llega vía SSE (evento ``chat_message`` / ``chat_typing``).
* El chat puede **lanzar misiones** de fondo y seguir conversando: cuando el
  operador pide una acción ("genera un informe", "crea una imagen",
  "analiza el repo"), el asistente dispara la misión y la conversación
  continúa; los artefactos que produzca aparecen en el panel de resultados.
* Respuestas en prosa natural (no JSON): el prompt de sistema cambia respecto
  al del planificador para que el asistente dialogue, no que emita planes.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable, Optional

from .config import Config
from .models import now_iso
from .providers import BaseProvider, HeuristicProvider, OpenAICompatProvider

# Prompt del asistente: prosa, en español, orientado a ayudar.
ASSISTANT_SYSTEM_PROMPT = (
    "Eres Aegis, el asistente autónomo de A²S. Dialogas en español de forma "
    "clara, técnica pero cercana. Puedes explicar qué está haciendo el agente, "
    "resumir resultados, proponer próximos pasos y, cuando el operador lo pide, "
    "lanzar misiones de fondo (un planificador separado las ejecuta). No inventes "
    "archivos ni resultados: si no sabes algo, dilo. Cuando el operador te pida "
    "producir algo (un informe, código, una imagen, analizar el workspace), "
    "respóndele que vas a lanzar una misión para hacerlo y descríbela en una línea. "
    "Mantén las respuestas concisas y accionables."
)


def _prose_chat(provider: BaseProvider, messages: list[dict[str, str]],
                max_tokens: int = 900) -> str:
    """Llama al proveedor en modo *prosa* (no JSON estructurado).

    Aprovecha el transporte existente de cada proveedor: el pool SORL ya tiene
    ``chat()``; ``OpenAICompatProvider`` expone ``_chat``; el núcleo heurístico
    tiene un asistente determinista de respaldo que nunca falla.
    """
    # 1) Pool SORL / OmniRoute / cualquier proveedor con chat(prose).
    chat = getattr(provider, "chat", None)
    if callable(chat):
        try:
            out = chat(messages[-1]["content"], kind="general",
                       max_tokens=max_tokens, system=ASSISTANT_SYSTEM_PROMPT)
            if out:
                return out.strip()
        except Exception:  # noqa: BLE001 — el asistente nunca muere
            pass

    # 2) OpenAI-compatible (reutiliza _chat, que ya hace failover al heurístico).
    if isinstance(provider, OpenAICompatProvider):
        try:
            return provider._chat(messages[-1]["content"],
                                  max_tokens=max_tokens).strip()
        except Exception:  # noqa: BLE001
            return HeuristicAssistant().reply(messages)

    # 3) Heurístico local / cualquier otro: respaldo determinista.
    if isinstance(provider, HeuristicProvider) or provider is None:
        return HeuristicAssistant().reply(messages)

    generic = getattr(provider, "_chat", None)
    if callable(generic):
        try:
            return generic(messages[-1]["content"],
                           max_tokens=max_tokens).strip()
        except Exception:  # noqa: BLE001
            pass
    return HeuristicAssistant().reply(messages)


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    lines = []
    for m in messages[-10:]:
        role = "Operador" if m["role"] == "user" else "Aegis"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)


class HeuristicAssistant:
    """Respaldo determinista: responde sin red ni claves, nunca lanza excepción.

    No es un LLM: reconoce intención por palabras clave y da una respuesta
    útil. Garantiza que el chat *siempre* funcione, incluso con todos los
    endpoints del pool caídos (igual que el núcleo heurístico del planificador).
    """

    GREETINGS = ("hola", "buenas", "qué tal", "que tal", "buenos días",
                 "buenas tardes", "buenas noches", "hey", "saludos")
    STATUS_WORDS = ("qué haces", "que haces", "estado", "status", "cómo vas",
                    "como vas", "qué está pasando", "avance", "progreso")
    HELP_WORDS = ("ayuda", "qué puedes", "que puedes", "comandos", "help",
                  "cómo funcionas", "como funcionas")
    THANKS = ("gracias", "thanks", "te agradezco", "perfecto", "genial", "ok")
    WELLBEING = ("cómo estás", "como estas", "cómo te encuentras",
                 "como te encuentras", "todo bien")

    def reply(self, messages: list[dict[str, str]]) -> str:
        text = (messages[-1]["content"] if messages else "").lower().strip()
        if any(g in text for g in self.GREETINGS):
            return ("Hola. Soy Aegis, el asistente autónomo de A²S. Puedo ejecutar "
                    "misiones en segundo plano, explicarte qué está pasando y "
                    "mostrarte los resultados. Dime qué objetivo quieres perseguir.")
        if any(w in text for w in self.WELLBEING):
            return ("Estoy operativo y listo para trabajar. El núcleo local sigue "
                    "activo incluso si una ruta externa falla, y OmniRoute se "
                    "supervisa y recupera automáticamente. ¿Qué hacemos?")
        if any(w in text for w in self.HELP_WORDS):
            return ("Puedo: (1) lanzar automáticamente una misión con un objetivo "
                    "verificable, (2) contarte el estado de la misión en curso, "
                    "(3) mostrarte los artefactos que haya producido y (4) charlar "
                    "sobre el proyecto mientras trabajo. Escríbeme en lenguaje "
                    "natural qué necesitas; yo elijo la ruta y me ocupo del resto.")
        if any(w in text for w in self.STATUS_WORDS):
            return ("Para ver el estado en vivo revisa el panel de telemetría: "
                    "ahí aparece cada paso, evaluación y replanificación. "
                    "Si hay una misión corriendo, sus eventos se transmiten en "
                    "tiempo real por SSE.")
        if any(w in text for w in self.THANKS):
            return "A ti. ¿Algo más en lo que pueda ayudarte?"
        if any(w in text for w in ("lanza", "ejecuta", "genera", "crea", "haz",
                                    "analiza", "produce", "construye", "escribe")):
            return ("Entendido. Lo ejecutaré como una misión autónoma en segundo "
                    "plano y publicaré aquí el avance y los resultados. No necesitas "
                    "elegir proveedor ni pulsar otro botón.")
        if text.endswith("?"):
            return ("Buena pregunta. Estoy operativo con el núcleo local y usaré "
                    "OmniRoute automáticamente cuando esté disponible. Si necesitas "
                    "una respuesta basada en evidencia del workspace o de la web, "
                    "pídeme que la investigue y lanzaré la misión por ti.")
        return ("Te he entendido. Aegis selecciona la mejor ruta disponible de forma "
                "automática; si una ruta falla, continúa con el núcleo local. Puedes "
                "pedirme directamente que investigue, analice, cree o ejecute algo.")


class ChatManager:
    """Conversación persistente con respuestas en segundo plano."""

    MAX_HISTORY = 80
    MAX_MESSAGE = 8000

    def __init__(self, hub: Any, workspace: str,
                 get_provider: Callable[[], BaseProvider],
                 launch_mission: Optional[Callable[[str, dict[str, Any]],
                                                   tuple[bool, str]]] = None,
                 get_state: Optional[Callable[[], dict[str, Any]]] = None):
        self.hub = hub
        self.workspace = os.path.abspath(workspace)
        self._get_provider = get_provider
        self._launch_mission = launch_mission
        self._get_state = get_state
        self._lock = threading.Lock()
        self.history: list[dict[str, Any]] = []
        self.busy = False
        self._path = os.path.join(self.workspace, ".a2s", "chat_history.json")
        self._load()

    # -- persistencia --------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            loaded = data.get("history", [])[-self.MAX_HISTORY:]
            # Migración de UX: no revivir tras una actualización el antiguo
            # fallback que delegaba al operador «conecta un proveedor».
            legacy = ("No tengo un LLM conectado", "Conecta un proveedor",
                      "conecta un proveedor")
            self.history = [message for message in loaded
                            if not (message.get("role") == "assistant" and
                                    any(marker in message.get("content", "")
                                        for marker in legacy))]
            if len(self.history) != len(loaded):
                self._save()
        except (OSError, json.JSONDecodeError):
            self.history = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"history": self.history[-self.MAX_HISTORY:]},
                          fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self._path)
        except OSError:
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"busy": self.busy, "history": list(self.history)}

    # -- publicación de eventos ---------------------------------------------
    def _publish(self, event: str, **data: Any) -> None:
        self.hub.publish({"event": event, "at": now_iso(), **data})

    # -- intención de lanzar misión -----------------------------------------
    _MISSION_VERBS = ("lanza", "ejecuta", "genera", "crea", "construye",
                      "haz", "analiza", "produce", "escribe", "descarga",
                      "investiga", "busca", "audita", "revisa")

    def _wants_mission(self, text: str) -> bool:
        low = text.lower()
        return any(f" {v} " in f" {low} " for v in self._MISSION_VERBS) and \
            len(text) > 12

    # -- API principal -------------------------------------------------------
    def send(self, text: str) -> tuple[bool, str]:
        text = (text or "").strip()
        if not text:
            return False, "mensaje vacío"
        if len(text) > self.MAX_MESSAGE:
            return False, f"máximo {self.MAX_MESSAGE} caracteres"
        with self._lock:
            if self.busy:
                return False, "estoy respondiendo todavía; espera un momento"
            self.busy = True
            self.history.append({"role": "user", "content": text,
                                  "at": now_iso()})
            self._save()

        wants_mission = self._wants_mission(text)
        threading.Thread(target=self._respond, name="a2s-chat",
                         args=(text, wants_mission), daemon=True).start()
        return True, "ok"

    def _respond(self, user_text: str, wants_mission: bool) -> None:
        self._publish("chat_typing")
        reply = ""
        try:
            provider = self._get_provider()
            context = self._context_block()
            convo = [*self.history[:-1][-12:]]
            if context:
                convo = [{"role": "system", "content": context}] + convo
            convo.append({"role": "user", "content": user_text})
            reply = _prose_chat(provider, convo) or "No tengo respuesta en este momento."

            # Si el operador pide acción y hay lanzador disponible, abrimos misión.
            mission_id = None
            if wants_mission and self._launch_mission is not None:
                ok, msg = self._launch_mission(user_text, {})
                if ok:
                    mission_id = "background"
                    reply += (f"\n\nHe lanzado la misión en segundo plano "
                              f"({msg}). Ve siguiendo el flujo en el panel de "
                              f"telemetría; te mostraré los archivos que produzca "
                              f"en Resultados.")
                else:
                    reply += f"\n\n(No pude lanzar la misión ahora mismo: {msg}.)"

            with self._lock:
                self.history.append({"role": "assistant", "content": reply,
                                     "at": now_iso(), "mission_id": mission_id})
                self._save()
            self._publish("chat_message", role="assistant", content=reply,
                          mission_id=mission_id)
        except Exception as exc:  # noqa: BLE001 — el chat no rompe el servicio
            fallback = ("Perdona, he tenido un problema generando la respuesta "
                        f"({type(exc).__name__}: {exc}). Sigo aquí; inténtalo de nuevo.")
            with self._lock:
                self.history.append({"role": "assistant", "content": fallback,
                                     "at": now_iso(), "error": True})
                self._save()
            self._publish("chat_message", role="assistant", content=fallback,
                          error=True)
        finally:
            with self._lock:
                self.busy = False
            self._publish("chat_idle")

    def _context_block(self) -> str:
        """Fragmento de contexto vivo para el LLM: estado de la misión."""
        if self._get_state is None:
            return ""
        try:
            st = self._get_state()
        except Exception:  # noqa: BLE001
            return ""
        parts = []
        if st.get("running"):
            parts.append("Hay una misión EN CURSO en este momento.")
        else:
            report = st.get("report")
            if report:
                parts.append(
                    f"La última misión terminó con éxito={report.get('success')} "
                    f"tras {report.get('iterations', 0)} iteraciones "
                    f"({report.get('wall_seconds', 0)}s).")
        it = st.get("iterations", 0)
        if it:
            parts.append(f"Iteraciones totales de esta sesión: {it}.")
        if not parts:
            return "No hay ninguna misión activa ni previa en el workspace."
        return " ".join(parts)

    def clear(self) -> None:
        with self._lock:
            self.history = []
            self._save()
        self._publish("chat_cleared")
