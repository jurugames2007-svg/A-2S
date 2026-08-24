"""Protocolo adaptativo de capacidades para Aegis.

Traduce el llamado «Modo Dios» a ingeniería verificable: clasifica la necesidad,
activa únicamente capacidades aplicables, fija criterios de aceptación y deja
una justificación auditable. No promete omnipotencia ni expone cadenas privadas
de razonamiento; publica un resumen de método, evidencia, límites y próximos
pasos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .models import now_iso


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    purpose: str
    tools: tuple[str, ...] = ()


CATALOG: dict[str, Capability] = {
    "structured_analysis": Capability(
        "structured_analysis", "Análisis estructurado",
        "descomponer la necesidad y sintetizar una respuesta; se muestra un resumen, no pensamiento privado"),
    "devils_advocate": Capability(
        "devils_advocate", "Abogado del diablo",
        "buscar supuestos frágiles, contraejemplos y motivos por los que una conclusión podría fallar"),
    "multiple_perspectives": Capability(
        "multiple_perspectives", "Múltiples perspectivas",
        "comparar al menos tres enfoques cuando haya decisiones o diseño"),
    "predictive_scenarios": Capability(
        "predictive_scenarios", "Escenarios si/entonces",
        "hacer explícitas consecuencias, riesgos y condiciones futuras"),
    "current_research": Capability(
        "current_research", "Investigación actualizada",
        "consultar fuentes públicas cuando la respuesta dependa del estado actual",
        ("research_topic", "web_search", "fetch_url")),
    "multi_source_verify": Capability(
        "multi_source_verify", "Verificación multifuente",
        "contrastar hechos importantes y registrar procedencia y fecha",
        ("research_topic",)),
    "facts_vs_analysis": Capability(
        "facts_vs_analysis", "Hechos separados de análisis",
        "distinguir evidencia recuperada, inferencias y opiniones"),
    "math_precision": Capability(
        "math_precision", "Cálculo reproducible",
        "calcular con herramientas y hacer una segunda comprobación independiente",
        ("python_exec",)),
    "data_visualization": Capability(
        "data_visualization", "Datos estructurados",
        "presentar cantidades mediante tablas, listas o diagramas apropiados"),
    "brainstorm": Capability(
        "brainstorm", "Brainstorming con selección",
        "generar hasta diez alternativas diversas y elegir mediante criterios explícitos"),
    "iterative_refinement": Capability(
        "iterative_refinement", "Refinamiento V1→V2→V3",
        "criticar y mejorar el borrador en iteraciones verificables"),
    "tone_adaptation": Capability(
        "tone_adaptation", "Tono adaptativo",
        "ajustar registro, ejemplos, analogías y nivel técnico a la audiencia"),
    "visual_explanation": Capability(
        "visual_explanation", "Visualización ASCII/Mermaid",
        "usar diagramas textuales cuando aclaren estructura, flujo o arquitectura"),
    "multimodal_route": Capability(
        "multimodal_route", "Ruta de salida omnimodal",
        "producir el medio solicitado con herramientas registradas o entregar una alternativa útil (guion, storyboard, SVG/diagrama o especificación) sin fingir generación nativa"),
    "clarification": Capability(
        "clarification", "Aclaración dirigida",
        "preguntar solo por ambigüedades que cambien materialmente el resultado"),
    "autonomous_execution": Capability(
        "autonomous_execution", "Ejecución autónoma",
        "convertir la petición en una misión, producir artefactos y comprobarlos"),
    "recovery_ladder": Capability(
        "recovery_ladder", "Recuperación por alternativas",
        "reintentar, reparametrizar, cambiar herramienta, dividir y replanificar"),
    "limitations": Capability(
        "limitations", "Límites y confianza explícitos",
        "declarar lo no verificado y evitar presentar aproximaciones como hechos"),
    "next_steps": Capability(
        "next_steps", "Próximos pasos",
        "proponer continuaciones concretas y priorizadas"),
    "empathy": Capability(
        "empathy", "Empatía contextual",
        "responder con cuidado antes de convertir una necesidad emocional en una tarea"),
    "security_scope": Capability(
        "security_scope", "Alcance y permisos",
        "usar solo datos, sistemas y recursos autorizados; ofrecer alternativas legítimas"),
}


_TYPE_KEYWORDS = {
    "informativa": ("que es", "explica", "informacion", "datos", "quien", "cuando",
                    "donde", "resumen", "comparar", "estado", "noticias"),
    "creativa": ("crea", "escribe", "imagina", "ideas", "libro", "historia", "disena",
                 "poema", "guion", "nombre", "brainstorm"),
    "analitica": ("analiza", "evalua", "compara", "decide", "causa", "riesgo",
                  "estrategia", "diagnostica", "por que", "predice"),
    "practica": ("haz", "ejecuta", "construye", "implementa", "corrige", "pasos",
                 "guia", "configura", "descarga", "genera"),
    "emocional": ("siento", "triste", "ansiedad", "miedo", "solo", "frustrado",
                   "apoyo", "escuchame", "emocional"),
    "tecnica": ("codigo", "api", "repositorio", "bug", "error", "arquitectura",
                "algoritmo", "python", "javascript", "servidor", "base de datos",
                "seguridad", "pdf", "llm", "modelo"),
}

_CURRENT_MARKERS = ("hoy", "actual", "actualizado", "reciente", "ultimo", "ultima",
                    "2025", "2026", "noticias", "precio", "version", "estado")
_MATH_MARKERS = ("calcula", "cuanto", "porcentaje", "promedio", "convertir", "conversion",
                 "suma", "resta", "multiplica", "divide", "ecuacion", "probabilidad",
                 "temperatura", "moneda", "unidades")
_DECISION_MARKERS = ("opciones", "alternativas", "mejor", "elegir", "decidir", "diseno",
                     "estrategia", "enfoque", "arquitectura")
_PREDICTIVE_MARKERS = ("futuro", "predice", "escenario", "riesgo", "impacto", "si ",
                       "podria", "consecuencia")
_VISUAL_MARKERS = ("diagrama", "visual", "tabla", "grafico", "mermaid", "arquitectura",
                   "flujo", "mapa", "imagen", "ilustracion", "logo", "fotografia")
_MODALITY_MARKERS = {
    "código": ("codigo", "script", "programa", "api", "html", "css", "sql"),
    "documento": ("documento", "informe", "libro", "pdf", "manual", "presentacion"),
    "datos": ("datos", "dataset", "csv", "json", "tabla", "grafico"),
    "imagen": ("imagen", "ilustracion", "logo", "fotografia", "svg"),
    "audio": ("audio", "voz", "podcast", "narracion"),
    "video": ("video", "animacion", "storyboard"),
}
_ACTION_MARKERS = ("haz", "crea", "genera", "ejecuta", "implementa", "corrige", "analiza",
                   "investiga", "busca", "construye", "escribe", "descarga", "audita")
_SOCIAL_MARKERS = ("hola", "buenas", "gracias", "como estas", "que tal")


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(char for char in value
                   if unicodedata.category(char) != "Mn")


def _has_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


@dataclass
class ProtocolDecision:
    request: str
    need_types: list[str]
    capabilities: list[Capability]
    acceptance_criteria: list[str]
    clarification_questions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    reference_at: str = field(default_factory=now_iso)
    social_only: bool = False

    @property
    def capability_ids(self) -> list[str]:
        return [capability.id for capability in self.capabilities]

    @property
    def tool_candidates(self) -> list[str]:
        seen = []
        for capability in self.capabilities:
            for tool in capability.tools:
                if tool not in seen:
                    seen.append(tool)
        return seen

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tool_candidates"] = self.tool_candidates
        return data

    def rationale_summary(self) -> str:
        types = ", ".join(self.need_types)
        return (f"Clasifiqué la solicitud como {types}. Activé solo los modos que aportan "
                "evidencia o mejoran el resultado; las conclusiones se contrastan con los "
                "criterios declarados, sin revelar razonamiento interno privado.")

    def planner_context(self) -> str:
        capabilities = ", ".join(capability.label for capability in self.capabilities)
        criteria = "\n".join(f"- {criterion}" for criterion in self.acceptance_criteria)
        questions = "\n".join(f"- {question}" for question in self.clarification_questions)
        assumptions = "\n".join(f"- {item}" for item in self.assumptions)
        return (
            "[PROTOCOLO ADAPTATIVO AEGIS]\n"
            f"Tipos de necesidad: {', '.join(self.need_types)}\n"
            f"Capacidades activadas: {capabilities}\n"
            f"Herramientas candidatas: {', '.join(self.tool_candidates) or 'selección del planner'}\n"
            f"Criterios de aceptación:\n{criteria}\n"
            + (f"Preguntas no bloqueantes:\n{questions}\n" if questions else "")
            + (f"Supuestos explícitos:\n{assumptions}\n" if assumptions else "")
            + "No expongas chain-of-thought. Registra evidencia, decisiones y límites observables."
        )

    def system_prompt(self) -> str:
        checklist = "\n".join(
            f"✅ {capability.label}: {capability.purpose}"
            for capability in self.capabilities)
        return (
            "Eres Aegis, el asistente autónomo de A²S. Mantén conversación coherente usando "
            "el historial proporcionado. No inventes resultados ni capacidades. Si una acción "
            "requiere misión, indícalo brevemente y deja que el orquestador la ejecute.\n\n"
            f"Necesidad detectada: {', '.join(self.need_types)}. Fecha de referencia: "
            f"{self.reference_at}.\nCapacidades aplicables:\n{checklist}\n\n"
            "No reveles cadenas privadas de pensamiento, deliberaciones internas ni tokens. En "
            "[RAZONAMIENTO RESUMIDO] explica solo método, evidencia y criterios en 2-3 líneas. "
            "Distingue hechos verificados, inferencias y opiniones. Para datos actuales exige "
            "fuente y fecha. No afirmes precisión absoluta, omnipotencia ni éxito sin evidencia. Conserva el "
            "modelo de permisos y ofrece una alternativa legítima cuando algo no sea posible.\n\n"
            "Para solicitudes sustantivas responde con estas secciones: [CAPACIDADES ACTIVADAS], "
            "[RAZONAMIENTO RESUMIDO], [RESPUESTA PRINCIPAL], [DATOS ADICIONALES], "
            "[SIGUIENTES PASOS]. Para saludo o agradecimiento responde de forma natural."
        )


def analyze_request(request: str) -> ProtocolDecision:
    """Selecciona capacidades por señales observables; no usa un LLM."""
    raw = " ".join((request or "").split())
    text = _normalize(raw)
    scores = {need: sum(marker in text for marker in markers)
              for need, markers in _TYPE_KEYWORDS.items()}
    need_types = [need for need, score in scores.items() if score > 0]
    if not need_types:
        need_types = ["informativa"]
    social_only = len(text.split()) <= 5 and _has_any(text, _SOCIAL_MARKERS)
    selected = ["structured_analysis", "limitations", "next_steps"]

    if _has_any(text, _DECISION_MARKERS) or "analitica" in need_types:
        selected += ["devils_advocate", "multiple_perspectives"]
    if _has_any(text, _PREDICTIVE_MARKERS):
        selected.append("predictive_scenarios")
    if _has_any(text, _CURRENT_MARKERS):
        selected += ["current_research", "multi_source_verify", "facts_vs_analysis"]
    elif "informativa" in need_types or "tecnica" in need_types:
        selected.append("facts_vs_analysis")
    if _has_any(text, _MATH_MARKERS) or re.search(r"\d\s*[%+*/=-]", text):
        selected += ["math_precision", "data_visualization"]
    if "creativa" in need_types:
        selected += ["brainstorm", "iterative_refinement", "tone_adaptation"]
    if _has_any(text, _VISUAL_MARKERS):
        selected += ["visual_explanation", "data_visualization"]
    if any(_has_any(text, markers) for name, markers in _MODALITY_MARKERS.items()
           if name in ("imagen", "audio", "video")):
        selected.append("multimodal_route")
    if _has_any(text, _ACTION_MARKERS) or "practica" in need_types:
        selected += ["autonomous_execution", "recovery_ladder"]
    if "emocional" in need_types:
        selected.insert(0, "empathy")
    if any(word in text for word in ("privado", "cuenta", "credencial", "sistema ajeno",
                                     "seguridad", "permiso")):
        selected.append("security_scope")

    questions, assumptions = _ambiguity(raw, text, need_types)
    if questions:
        selected.append("clarification")
    selected = list(dict.fromkeys(selected))
    if social_only:
        selected = [item for item in selected
                    if item in ("empathy", "limitations", "next_steps")]
        if not selected:
            selected = ["tone_adaptation"]

    criteria = _acceptance_criteria(need_types, selected)
    return ProtocolDecision(
        request=raw, need_types=need_types,
        capabilities=[CATALOG[item] for item in selected],
        acceptance_criteria=criteria, clarification_questions=questions,
        assumptions=assumptions, social_only=social_only)


def _ambiguity(raw: str, normalized: str,
               need_types: list[str]) -> tuple[list[str], list[str]]:
    questions = []
    assumptions = []
    vague = len(normalized.split()) < 4 or normalized in {
        "hazlo", "mejoralo", "arreglalo", "crea esto", "analiza esto", "ayudame"}
    if vague and not _has_any(normalized, _SOCIAL_MARKERS):
        questions.append("¿Cuál es el resultado final concreto y cómo sabremos que está correcto?")
    if "creativa" in need_types and not any(word in normalized for word in
                                             ("profesional", "casual", "tecnico", "poetico")):
        assumptions.append("Usaré tono profesional y claro salvo que indiques otra audiencia.")
    if _has_any(normalized, _CURRENT_MARKERS):
        assumptions.append("Los datos actuales solo se tratarán como verificados si incluyen fuente y fecha.")
    if "practica" in need_types:
        assumptions.append("Procederé con valores seguros y reversibles cuando falte un detalle no crítico.")
    return questions, assumptions


def _acceptance_criteria(need_types: list[str], selected: list[str]) -> list[str]:
    criteria = [
        "La respuesta o artefacto aborda directamente la necesidad detectada.",
        "Hechos, inferencias y límites quedan diferenciados.",
    ]
    if "current_research" in selected:
        criteria.append("Los datos dependientes del tiempo incluyen fuente y fecha de consulta.")
    if "multi_source_verify" in selected:
        criteria.append("Las afirmaciones importantes se contrastan con dos fuentes cuando estén disponibles.")
    if "math_precision" in selected:
        criteria.append("Los cálculos se reproducen y se verifican por una segunda vía.")
    if "creativa" in need_types:
        criteria.append("Se comparan alternativas y el borrador final supera una revisión iterativa.")
    if "autonomous_execution" in selected:
        criteria.append("Los artefactos existen, pueden abrirse y pasan sus verificadores específicos.")
    return criteria


def format_response(main: str, decision: ProtocolDecision,
                    additional: str = "", next_steps: list[str] | None = None) -> str:
    """Aplica el contrato visible sin fabricar ni retransmitir razonamiento privado."""
    text = (main or "").strip()
    # Algunos motores emiten deliberación privada en etiquetas auxiliares a
    # pesar del prompt. El contrato Aegis las descarta antes de persistir o UI.
    text = re.sub(r"<think(?:\s[^>]*)?>[\s\S]*?</think>", "", text,
                  flags=re.IGNORECASE).strip()
    if not text:
        text = "No se obtuvo una respuesta principal verificable de la ruta seleccionada."
    if decision.social_only:
        return text
    required = ("[CAPACIDADES ACTIVADAS]", "[RAZONAMIENTO RESUMIDO]",
                "[RESPUESTA PRINCIPAL]", "[DATOS ADICIONALES]",
                "[SIGUIENTES PASOS]")
    if all(section in text for section in required):
        return text
    capabilities = "\n".join(f"- ✅ {capability.label}"
                              for capability in decision.capabilities)
    if additional.strip():
        data = additional.strip()
    else:
        data_parts = [
            f"Fecha de referencia: {decision.reference_at}.",
            "Lo no respaldado por una fuente o artefacto se considera análisis, no hecho verificado.",
        ]
        if decision.assumptions:
            data_parts.append("Supuestos: " + " ".join(decision.assumptions))
        if decision.clarification_questions:
            data_parts.append("Aclaración útil: " + " ".join(
                decision.clarification_questions))
        data = " ".join(data_parts)
    steps = next_steps or [
        *(decision.clarification_questions[:1]),
        "Confirma o ajusta el criterio de éxito si quieres una ejecución autónoma.",
        "Pide evidencia, archivos o una segunda revisión para profundizar.",
    ]
    return (
        f"[CAPACIDADES ACTIVADAS]\n{capabilities}\n\n"
        f"[RAZONAMIENTO RESUMIDO]\n{decision.rationale_summary()}\n\n"
        f"[RESPUESTA PRINCIPAL]\n{text}\n\n"
        f"[DATOS ADICIONALES]\n{data}\n\n"
        "[SIGUIENTES PASOS]\n" + "\n".join(f"{index}. {step}"
                                                  for index, step in enumerate(steps, 1))
    )
