"""Asistente conversacional en paralelo a las misiones.

El operador puede hablar, buscar, crear y detener mientras una misión corre.
Las peticiones se encolan: nunca se rechazan por «estoy respondiendo».
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Optional

from .aegis_protocol import ProtocolDecision, analyze_request, format_response
from .control import RequestInbox, acquire
from .intent import classify_intent
from .models import now_iso
from .providers import BaseProvider, HeuristicProvider, OpenAICompatProvider

ASSISTANT_SYSTEM_PROMPT = analyze_request(
    "Explica de forma verificable qué puede hacer Aegis").system_prompt()


def _prose_chat(provider: BaseProvider, messages: list[dict[str, str]],
                max_tokens: int = 900,
                decision: Optional[ProtocolDecision] = None) -> str:
    last_user = next((message.get("content", "") for message in reversed(messages)
                      if message.get("role") == "user"), "")
    decision = decision or analyze_request(last_user)
    system_prompt = decision.system_prompt()
    conversation_prompt = _messages_to_prompt(messages)

    def finish(output: str) -> str:
        return format_response(output.strip(), decision)

    chat = getattr(provider, "chat", None)
    if callable(chat):
        try:
            out = chat(conversation_prompt, kind="general",
                       max_tokens=max_tokens, system=system_prompt)
            if out:
                return finish(out)
        except Exception:
            pass
    if isinstance(provider, OpenAICompatProvider):
        try:
            out = provider._chat(conversation_prompt, max_tokens=max_tokens,
                                 system=system_prompt)
            return finish(out)
        except Exception:
            return finish(HeuristicAssistant().reply(messages))
    if isinstance(provider, HeuristicProvider) or provider is None:
        return finish(HeuristicAssistant().reply(messages))
    generic = getattr(provider, "_chat", None)
    if callable(generic):
        try:
            out = generic(conversation_prompt, max_tokens=max_tokens,
                          system=system_prompt)
            return finish(out)
        except Exception:
            pass
    return finish(HeuristicAssistant().reply(messages))


def _create_reply(kind: str, ok: bool, msg: str, slides: bool) -> str:
    if not ok:
        return f"No pude encolar el trabajo: {msg}."
    if kind == "vault":
        return (f"No genero wallets ni cuentas ajenas ({msg}). "
                "Dejé la política en Resultados. La semilla la creas tú, offline.")
    if kind == "hardware":
        return (f"Diagnóstico de solo lectura encolado ({msg}). "
                "No flasheo BIOS ni overclockeo.")
    if kind == "counsel":
        return (f"Preparo una nota de orientación ({msg}). "
                "No soy médico ni abogado: es información para tu cita.")
    if kind == "steward":
        return (f"Ordeno el workspace A²S ({msg}), no el escritorio del sistema. "
                "Hay deshacer. Puedes decir «para».")
    if kind == "horizon":
        return (f"Armo un brief de oportunidades públicas ({msg}). "
                "No postulo en tu nombre.")
    if slides:
        return (f"Diseño la presentación en vivo ({msg}). "
                "Verás el proceso en Operaciones.")
    return (f"Empiezo en segundo plano ({msg}). "
            "Puedes hablar o decir «para». El resultado sale en Resultados.")


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    lines = []
    for message in messages[-12:]:
        role = {"user": "Operador", "assistant": "Aegis",
                "system": "Contexto verificable"}.get(message.get("role"), "Contexto")
        content = str(message.get("content", ""))[:6000]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


class HeuristicAssistant:
    """Respaldo determinista: responde sin red ni claves, nunca lanza."""

    GREETINGS = ("hola", "buenas", "qué tal", "que tal", "buenos días",
                 "buenas tardes", "buenas noches", "hey", "saludos", "hello", "hi")
    STATUS_WORDS = ("qué haces", "que haces", "estado", "status", "cómo vas",
                    "como vas", "qué está pasando", "avance", "progreso")
    HELP_WORDS = ("ayuda", "qué puedes", "que puedes", "comandos", "help",
                  "cómo funcionas", "como funcionas")
    THANKS = ("gracias", "thanks", "te agradezco", "perfecto", "genial", "ok")
    WELLBEING = ("cómo estás", "como estas", "cómo te encuentras",
                 "como te encuentras", "todo bien")
    RESOURCE_WORDS = ("recurso", "recursos", "catálogo", "catalogo",
                      "dónde aprend", "donde aprend", "curso de", "cursos de",
                      "herramientas para", "dónde encuentro", "donde encuentro")

    def reply(self, messages: list[dict[str, str]]) -> str:
        text = (messages[-1]["content"] if messages else "").strip()
        if "Operador:" in text:
            text = text.rsplit("Operador:", 1)[-1]
        text = text.lower().strip()
        if any(g in text for g in self.GREETINGS):
            return ("Hola. Soy Aegis. Puedes hablarme mientras corro una misión: "
                    "pídeme que busque repositorios, que cree un libro o un "
                    "informe, o que detenga lo que está en curso. Dime el objetivo.")
        if any(w in text for w in self.WELLBEING):
            return ("Estoy operativo y listo para trabajar. El núcleo local sigue "
                    "activo incluso si una ruta externa falla, y OmniRoute se "
                    "recupera automáticamente. Puedes interrumpirme cuando quieras. "
                    "¿Qué hacemos?")
        if any(w in text for w in self.HELP_WORDS):
            return ("Puedo: (1) conversar en paralelo a una misión, (2) buscar "
                    "repositorios por palabra clave en español o inglés, "
                    "(3) crear libros, PPT y programas locales, (4) ordenar el "
                    "workspace con macros y limpieza segura, (5) orientar en "
                    "legal/salud/finanzas sin sustituir a un profesional, "
                    "(6) briefs de empleo públicos (sin crear cuentas ni wallets) "
                    "y (7) detener o lanzar una misión larga. "
                    "Escríbeme en lenguaje natural; yo elijo la ruta automáticamente.")
        if any(w in text for w in self.STATUS_WORDS):
            return ("Revisa el panel de telemetría para el detalle en vivo. "
                    "Si hay una misión o un trabajo de creación, también te lo "
                    "cuento aquí. Puedes decir «para» para interrumpir.")
        if any(w in text for w in self.THANKS):
            return "A ti. ¿Sigo con otra cosa o detengo lo que está corriendo?"
        if any(w in text for w in self.RESOURCE_WORDS):
            return self._reply_recursos(text)
        if any(w in text for w in ("lanza", "ejecuta", "genera", "crea", "haz",
                                    "analiza", "produce", "construye", "escribe",
                                    "busca")):
            return ("Entendido. Lo ejecuto en segundo plano y sigo disponible "
                    "para hablar, buscar o detener. No necesitas otro botón.")
        if text.endswith("?"):
            return ("Buena pregunta. Si necesitas evidencia del workspace o de "
                    "repositorios, pídemelo y lo busco yo. Si quieres un "
                    "artefacto, dilo: lo creo y te aviso.")
        return ("Te he entendido. Puedes pedirme que investigue, cree, busque "
                "o detenga; si una ruta falla, continúo con el núcleo local.")

    def _reply_recursos(self, text: str) -> str:
        """Responde con entradas del catálogo curado (a2s recursos)."""
        from .recursos import buscar
        rows = buscar(text, top=3)
        if not rows:
            return ("Lo busco en mi catálogo curado (57 entradas en 6 categorías: "
                    "IA y cursos, ciberseguridad, desarrollo, directorios, "
                    "utilidades, empleo). Pruébame con «ghidra», «vpn» o "
                    "«pentest», o abre la pestaña Recursos del panel.")
        lineas = ["En el catálogo:"]
        for r in rows:
            lineas.append(f"• {r['nombre']} — {r['url'] or 'sin enlace'}")
        lineas.append("Completo en la pestaña Recursos. Filtro de ética: uso solo "
                      "autorizado, defensivo o académico.")
        return "\n".join(lineas)


class ChatManager:
    """Conversación persistente. Inbox siempre acepta. Worker único."""

    MAX_HISTORY = 80
    MAX_MESSAGE = 8000

    def __init__(self, hub: Any, workspace: str,
                 get_provider: Callable[[], BaseProvider],
                 launch_mission: Optional[Callable[[str, dict[str, Any]],
                                                   tuple[bool, str]]] = None,
                 get_state: Optional[Callable[[], dict[str, Any]]] = None,
                 stop_all: Optional[Callable[[], tuple[bool, str]]] = None,
                 run_search: Optional[Callable[[str], dict[str, Any]]] = None,
                 run_create: Optional[Callable[[str, dict[str, Any]],
                                               tuple[bool, str]]] = None):
        self.hub = hub
        self.workspace = os.path.abspath(workspace)
        self._get_provider = get_provider
        self._launch_mission = launch_mission
        self._get_state = get_state
        self._stop_all = stop_all
        self._run_search = run_search
        self._run_create = run_create
        self._lock = threading.Lock()
        self.history: list[dict[str, Any]] = []
        self.busy = False
        self.last_protocol: Optional[dict[str, Any]] = None
        self._path = os.path.join(self.workspace, ".a2s", "chat_history.json")
        self.inbox = RequestInbox(maxsize=200)
        self._worker_started = False
        self._wake = threading.Event()
        self._load()
        self._ensure_worker()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            loaded = data.get("history", [])[-self.MAX_HISTORY:]
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
        if not acquire(self._lock, 1.0):
            return {"busy": self.busy, "history": [], "protocol": self.last_protocol,
                    "inbox": self.inbox.snapshot()}
        try:
            return {"busy": self.busy, "history": list(self.history),
                    "protocol": self.last_protocol,
                    "inbox": self.inbox.snapshot()}
        finally:
            self._lock.release()

    def _publish(self, event: str, **data: Any) -> None:
        self.hub.publish({"event": event, "at": now_iso(), **data})

    def _ensure_worker(self) -> None:
        if self._worker_started:
            return
        self._worker_started = True
        threading.Thread(target=self._worker, name="a2s-chat-worker",
                         daemon=True).start()

    def send(self, text: str) -> tuple[bool, str]:
        text = (text or "").strip()
        if not text:
            return False, "mensaje vacío"
        if len(text) > self.MAX_MESSAGE:
            return False, f"máximo {self.MAX_MESSAGE} caracteres"
        if not acquire(self._lock, 1.0):
            # Aunque el candado falle, la petición no se pierde: se encola.
            self.inbox.put({"text": text, "at": now_iso()})
            self._wake.set()
            return True, "queued"
        try:
            self.history.append({"role": "user", "content": text, "at": now_iso()})
            self._save()
        finally:
            self._lock.release()
        ok, msg = self.inbox.put({"text": text, "at": now_iso()})
        self._wake.set()
        return ok, msg if ok else msg

    def _worker(self) -> None:
        while True:
            item = self.inbox.get(timeout=0.5)
            if item is None:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            try:
                self._respond(str(item.get("text") or ""))
            except Exception as exc:  # noqa: BLE001
                self._fail(f"El worker del chat recuperó un error: {type(exc).__name__}: {exc}")
            finally:
                self.inbox.task_done()

    def _fail(self, message: str) -> None:
        if acquire(self._lock, 1.0):
            try:
                self.history.append({"role": "assistant", "content": message,
                                     "at": now_iso(), "error": True})
                self._save()
            finally:
                self._lock.release()
        self._publish("chat_message", role="assistant", content=message, error=True)
        self._publish("chat_idle")

    def _respond(self, user_text: str) -> None:
        if not user_text:
            return
        if acquire(self._lock, 1.0):
            try:
                self.busy = True
            finally:
                self._lock.release()
        self._publish("chat_typing")
        decision = analyze_request(user_text)
        protocol = decision.to_dict()
        if acquire(self._lock, 1.0):
            try:
                self.last_protocol = protocol
            finally:
                self._lock.release()
        self._publish("capability_protocol", protocol=protocol)
        intent = classify_intent(user_text)
        reply = ""
        mission_id = None
        try:
            if intent.kind == "stop" and self._stop_all is not None:
                ok, msg = self._stop_all()
                reply = (f"Parada solicitada: {msg}." if ok
                         else f"No había nada que cortar ({msg}). "
                              "Sigo escuchando.")
            elif intent.kind == "resume":
                reply = self._resume_reply()
            elif intent.kind == "status":
                reply = self._status_reply()
            elif intent.kind == "search" and self._run_search is not None:
                report = self._run_search(intent.topic or user_text)
                from .finder import format_search
                reply = format_search(report)
            elif intent.kind in {"create", "steward", "counsel", "horizon",
                                 "hardware", "vault", "macro", "codegen"} \
                    and self._run_create is not None:
                options = {
                    "book": intent.wants_book,
                    "slides": intent.wants_slides,
                    "obtain": intent.wants_obtain,
                }
                if intent.kind != "create":
                    options["kind"] = intent.kind
                ok, msg = self._run_create(intent.topic or user_text, options)
                reply = _create_reply(intent.kind, ok, msg, intent.wants_slides)
            else:
                provider = self._get_provider()
                context = self._context_block()
                if acquire(self._lock, 1.0):
                    try:
                        convo = [*self.history[:-1][-12:]]
                    finally:
                        self._lock.release()
                else:
                    convo = []
                if context:
                    convo = [{"role": "system", "content": context}] + convo
                convo.append({"role": "user", "content": user_text})
                reply = (_prose_chat(provider, convo, decision=decision)
                         or "No tengo respuesta en este momento.")
                if intent.kind == "mission" and self._launch_mission is not None:
                    ok, msg = self._launch_mission(user_text, {})
                    if ok:
                        mission_id = "background"
                        reply += (f"\n\nHe lanzado la misión en segundo plano "
                                  f"({msg}). Sigo aquí para conversar, buscar o parar.")
                    else:
                        reply += (f"\n\nNo lancé otra misión exclusiva ({msg}). "
                                  "Si quieres, dime «para» y relanzamos, o "
                                  "pídeme crear/buscar en paralelo.")

            if acquire(self._lock, 1.0):
                try:
                    self.history.append({"role": "assistant", "content": reply,
                                         "at": now_iso(), "mission_id": mission_id,
                                         "protocol": protocol,
                                         "intent": intent.kind})
                    self._save()
                finally:
                    self._lock.release()
            self._publish("chat_message", role="assistant", content=reply,
                          mission_id=mission_id, intent=intent.kind)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"Perdona, falló la respuesta ({type(exc).__name__}: {exc}). "
                       "Sigo escuchando.")
            return
        finally:
            if acquire(self._lock, 1.0):
                try:
                    self.busy = False
                finally:
                    self._lock.release()
            self._publish("chat_idle")

    def _resume_reply(self) -> str:
        try:
            from .kernel import Kernel
            kernel = Kernel.open(self.workspace)
            restored = kernel.resume_all()
            snap = kernel.snapshot()
            return (f"PCB activo: {snap['applied']} mejoras aplicadas. "
                    f"Reanudé {len(restored)} trabajo(s). "
                    f"ready={snap['ready']} running={snap['running']} "
                    f"parked={snap['parked']} blocked={snap['blocked']}. "
                    "Si se corta, el journal queda en .a2s/pcb/.")
        except Exception as exc:
            return f"No pude leer el PCB ({type(exc).__name__}: {exc})."

    def _status_reply(self) -> str:
        if self._get_state is None:
            return "No tengo un snapshot ahora mismo, pero el chat está vivo."
        try:
            st = self._get_state()
        except Exception as exc:
            return f"No pude leer el estado ({type(exc).__name__})."
        if st.get("running"):
            return (f"Hay una misión en curso desde {st.get('started_at') or '?'}. "
                    f"Iteraciones: {st.get('iterations', 0)}. "
                    "Puedes seguir hablándome o decir «para».")
        report = st.get("report")
        if report:
            return (f"La última misión terminó success={report.get('success')} "
                    f"tras {report.get('iterations', 0)} iteraciones "
                    f"({report.get('wall_seconds', 0)}s). ¿Creamos algo o buscamos?")
        jobs = st.get("jobs") or []
        live = [j for j in jobs if j.get("alive")]
        if live:
            kinds = ", ".join(j.get("kind", "?") for j in live)
            return f"No hay misión exclusiva, pero hay trabajos laterales: {kinds}."
        return "Estoy idle. Dime qué crear, buscar o ejecutar."

    def _context_block(self) -> str:
        if self._get_state is None:
            return ""
        try:
            st = self._get_state()
        except Exception:
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
        inbox = self.inbox.snapshot()
        if inbox["queued"]:
            parts.append(f"Hay {inbox['queued']} mensaje(s) más en la bandeja.")
        if not parts:
            return "No hay ninguna misión activa ni previa en el workspace."
        return " ".join(parts)

    def clear(self) -> None:
        if acquire(self._lock, 1.0):
            try:
                self.history = []
                self.last_protocol = None
                self._save()
            finally:
                self._lock.release()
        self._publish("chat_cleared")
