"""Consejo informado: legal, médico y financiero. No es ejercicio profesional."""

from __future__ import annotations

import os
from typing import Any, Optional

from .control import StopToken
from .finder import fold
from .models import now_iso

DISCLAIMER = (
    "A²S no es abogado, no es médico y no es asesor financiero licenciado. "
    "Esto es información general para orientarte. Un profesional colegiado "
    "en tu jurisdicción debe revisar cualquier decisión que te afecte."
)


def domain_of(topic: str) -> str:
    text = fold(topic)
    if any(w in text for w in ("medico", "salud", "sintoma", "dolor", "fiebre",
                               "receta", "diagnostico", "urgencia")):
        return "medical"
    if any(w in text for w in ("abogado", "legal", "demanda", "contrato",
                               "juicio", "derecho", "denuncia")):
        return "legal"
    return "finance"


def advise(workspace: str, topic: str,
           stop: Optional[StopToken] = None) -> dict[str, Any]:
    if stop:
        stop.raise_if_set()
    domain = domain_of(topic)
    body = {
        "legal": _legal(topic),
        "medical": _medical(topic),
        "finance": _finance(topic),
    }[domain]
    title = {"legal": "Orientación legal (no es un abogado)",
             "medical": "Orientación de salud (no es un médico)",
             "finance": "Orientación financiera (no es un asesor)" }[domain]
    md = f"# {title}\n\n> {DISCLAIMER}\n\nEncargo: {topic}\n\n{body}\n"
    folder = os.path.join(os.path.abspath(workspace), "counsel")
    os.makedirs(folder, exist_ok=True)
    name = f"{domain}.md"
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    return {"status": "counsel_note", "domain": domain, "title": title,
            "disclaimer": True, "artifacts": [f"counsel/{name}"]}


def _legal(topic: str) -> str:
    return (
        "## Mapa de proceso\n\n"
        "1. Conserva documentos con fecha (contratos, mensajes, boletas).\n"
        "2. Escribe una cronología de hechos, no de opiniones.\n"
        "3. Identifica la jurisdicción (país, región, fuero).\n"
        "4. Busca asistencia jurídica gratuita o colegio de abogados local.\n"
        "5. No firmes cesiones ni acuerdos bajo presión sin lectura.\n\n"
        "## Lo que A²S no hace\n\n"
        "- No te representa ante un tribunal.\n"
        "- No redacta un contrato vinculante como si fuera tu letrado.\n"
        "- No evite plazos legales: un profesional debe calcularlos.\n\n"
        f"Tema pedido: {topic}. Úsalo como lista de preparación para la cita.\n"
    )


def _medical(topic: str) -> str:
    return (
        "## Primeros pasos generales\n\n"
        "1. Si hay dolor de pecho, ahogo, hemorragia, desmayo, confusión "
        "aguda o sospecha de ACV: llama al servicio de urgencias ahora.\n"
        "2. Anota inicio, intensidad, fiebre, medicamentos y alergias.\n"
        "3. No inicies ni suspendas fármacos recetados por un chat.\n"
        "4. Acude a un profesional de salud de tu red local.\n\n"
        "## Lo que A²S no hace\n\n"
        "- No diagnostica.\n"
        "- No receta.\n"
        "- No sustituye una urgencia ni un examen físico.\n\n"
        f"Tema pedido: {topic}. Esta nota solo ordena preguntas para el médico.\n"
    )


def _finance(topic: str) -> str:
    return (
        "## Presupuesto mínimo\n\n"
        "1. Lista ingresos netos del mes.\n"
        "2. Separa fijos (arriendo, servicios) de variables.\n"
        "3. Reserva un colchón de 1 mes antes de cualquier apuesta.\n"
        "4. Desconfía de rendimientos garantizados y de quien pida tu semilla.\n"
        "5. Un producto financiero se entiende o no se compra.\n\n"
        "## Lo que A²S no hace\n\n"
        "- No opera tu banco ni tu bróker.\n"
        "- No genera wallets ni claves privadas.\n"
        "- No promete rentabilidad.\n\n"
        f"Tema pedido: {topic}.\n"
    )
