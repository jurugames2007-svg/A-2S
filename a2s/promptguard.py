"""PromptGuard (v1.28): detección defensiva de inyección de prompts.

Contraparte honesta de las herramientas de jailbreak que A²S **no** integra:
este módulo no genera, no sugiere ni automatiza ningún vector de evasión.
Solo **detecta y clasifica** señal en texto de entrada con fines de
auditoría/defensa (línea de investigación académica legítima).

Categorías observadas (referencia pública de investigación, sin payloads):

* ``suplantacion_rol`` — pedir asumir una identidad/rol sin restricciones.
* ``anulacion_instrucciones`` — pedir ignorar/desobedecer las reglas dadas.
* ``fuga_prompt`` — pedir que el modelo revele su prompt del sistema.
* ``ofuscacion`` — pedir decodificar/leer contenido cifrado o alterado.
* ``exfiltracion_contenido`` — pedir contenido de la política de seguridad
  (malware, phishing, credenciales, "sin filtros").

La salida es un veredicto con puntuación, categorías y pistas; nunca una
receta para saltarse el guardarraíl. Si se pasa ``--ledger`` (o el parámetro
``documentar=True``), el hallazgo queda en la cadena de custodia.

Uso: ``a2s promptguard check TEXTO``, ``a2s promptguard check --file ruta``,
``a2s promptguard check --json``, ``a2s promptguard check --ledger``.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

_CATEGORIAS: tuple[tuple[str, str, tuple[str, ...], int], ...] = (
    ("suplantacion_rol", "Suplantación de rol",
     ("actua como", "actuas como", "eres ahora", "ahora eres", "finge ser",
      "fingir ser", "modo god", "modo dios", "developer mode", "dungeons and dragons",
      "do anything now", "pretend to be", "you are now", "roleplay as",
      "sin restricciones morales"), 2),
    ("anulacion_instrucciones", "Anulación de instrucciones",
     ("ignora", "ignorar", "ignora todas", "ignora las reglas", "desobedece",
      "no sigas las reglas", "olvida las reglas", "olvida tus instrucciones",
      "override", "ignore all previous", "ignore previous", "ignore your",
      "disregard", "no tienes restricciones", "no tienes limites",
      "sin filtros", "sin censura", "quita el filtro"), 2),
    ("fuga_prompt", "Fuga de prompt del sistema",
     ("dime tu prompt", "muestra tu prompt", "escribe tu prompt del sistema",
      "cual es tu prompt", "revela tus instrucciones", "muestra tus instrucciones",
      "print your system prompt", "repeat your instructions",
      "what are your instructions", "system prompt", "prompt del sistema",
      "prompt original"), 2),
    ("ofuscacion", "Ofuscación/decodificación inusual",
     ("base64", "rot13", "cifrado cesar", "cesar cipher", "decode this",
      "decodifica", "codifica en base64", "leelo al reves", "al reves",
      "unicode", "piglatin", "leet", "1337", "texto cifrado"), 1),
    ("exfiltracion_contenido", "Contenido fuera de la política",
     ("malware", "ransomware", "keylogger", "phishing", "credenciales",
      "robame", "exfiltra", "escala privilegios", "backdoor", "rootkit",
      "botnet", "ilegal", "hackear", "cuenta ajena", "suplanta identidad",
      "hazlo indetectable", "undetectable"), 3),
)

_ANCHO = re.compile(r"[\u0400-\u04ff]")


def _norm(texto: str) -> str:
    """Normaliza para comparar: minúsculas, sin acentos, espacios colapsados."""
    value = unicodedata.normalize("NFD", (texto or "").lower())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(value.split())


def _variante(texto_norm: str) -> str:
    """Variante con separadores/puntuación fuera (para pistas embebidas)."""
    return re.sub(r"[^a-z0-9\sñ]", "", texto_norm)


@dataclass
class Hallazgo:
    categoria: str
    nombre: str
    pistas: tuple[str, ...]
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {"categoria": self.categoria, "nombre": self.nombre,
                "pistas": list(self.pistas), "score": self.score}


@dataclass
class Veredicto:
    texto: str
    veredicto: str
    score: int
    hallazgos: list[Hallazgo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "veredicto": self.veredicto,
            "score": self.score,
            "hallazgos": [h.to_dict() for h in self.hallazgos],
            "nota": ("Detección defensiva: A²S no genera ni sugiere vectores "
                     "de evasión; solo marca la señal para auditoría."),
        }


def clasificar(texto: str) -> Veredicto:
    """Clasifica un entrada como limpia o con señal de inyección/jailbreak."""
    texto = (texto or "").strip()
    if not texto:
        return Veredicto(texto=texto, veredicto="sin_texto", score=0)
    norm = _norm(texto)
    var = _variante(norm)
    hallazgos: list[Hallazgo] = []
    for cid, nombre, marcadores, peso in _CATEGORIAS:
        pistas: list[str] = []
        for marcador in marcadores:
            if marcador in norm or re.sub(r"[^a-z0-9\sñ]", "", marcador) in var:
                pistas.append(marcador)
        if pistas:
            hallazgos.append(Hallazgo(cid, nombre, tuple(pistas[:8]),
                                      peso * len(pistas)))
    score = sum(h.score for h in hallazgos)
    # señales de estructura (coordenadas de rol + instrucción) no cuentan solas
    if score == 0:
        return Veredicto(texto=texto, veredicto="limpio", score=0)
    if score >= 6:
        veredicto = "jailbreak_probable"
    elif score >= 3:
        veredicto = "inyeccion_posible"
    else:
        veredicto = "senal_sutil"
    return Veredicto(texto=texto, veredicto=veredicto, score=score,
                     hallazgos=hallazgos)


def documentar(workspace: str, veredicto: Veredicto) -> dict[str, Any]:
    """Registra el hallazgo en el ledger (cadena de custodia)."""
    from .ledger import Ledger
    from .models import now_iso
    ledger = Ledger(os.path.join(os.path.abspath(workspace or "."), ".a2s"))
    record = ledger.append("promptguard.hallazgo", {
        "veredicto": veredicto.veredicto,
        "score": veredicto.score,
        "categorias": [h.categoria for h in veredicto.hallazgos],
        "pistas": [p for h in veredicto.hallazgos for p in h.pistas][:12],
        "texto": (veredicto.texto or "")[:200],
    })
    return {"at": now_iso(), "ledger": record}


def formato_legible(v: Veredicto) -> str:
    """Texto para el CLI."""
    if v.veredicto == "limpio":
        return "sin señal de inyección/jailbreak en la entrada."
    lineas = [f"veredicto: {v.veredicto} · score {v.score}"]
    for h in v.hallazgos:
        lineas.append(f"  - {h.nombre}: {', '.join(h.pistas)}")
    lineas.append("detección defensiva: A²S no genera vectores de evasión.")
    return "\n".join(lineas)
