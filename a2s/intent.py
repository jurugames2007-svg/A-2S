"""Clasificador de intención del operador (chat vs acción vs parada).

Determinista, sin red y sin LLM. El chat lo usa para NO lanzar una misión
de 10 minutos cuando el operador solo quiere hablar, buscar o detener.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


_STOP = (
    "para", "parado", "detente", "detente", "deten", "detén", "stop",
    "cancela", "cancelar", "abortar", "aborta", "interrumpe", "interrumpir",
    "basta", "ya esta", "ya está", "corta", "kill",
)
_STATUS = (
    "que haces", "qué haces", "estado", "status", "como vas", "cómo vas",
    "progreso", "avance", "que esta pasando", "qué está pasando",
)
_SEARCH = (
    "busca", "buscar", "encuentra", "encontrar", "search", "find",
    "repositorios", "repositorio", "repos", "github", "radar",
)
_CREATE = (
    "crea", "crear", "genera", "generar", "escribe", "escribir",
    "construye", "hazme", "haz un", "produce", "redacta", "compone",
    "disena", "disenar", "arma",
)
_BOOK = ("libro", "book", "ebook", "manual", "dossier", "novela", "cuento")
_CHAT_ONLY = (
    "hola", "buenas", "hey", "hello", "hi ", "gracias", "thanks",
    "como estas", "cómo estás", "que tal", "qué tal", "ayuda", "help",
    "que puedes", "qué puedes", "quien eres", "quién eres",
)


_SLIDES = (
    "ppt", "pptx", "powerpoint", "presentacion", "diapositiva",
    "diapositivas", "slides", "deck",
)
_OBTAIN = (
    "obtener", "obten", "descarga", "descargar", "gutenberg",
    "dominio publico", "public domain",
)


def wants_slides(text: str) -> bool:
    folded = _fold(text)
    return any(re.search(rf"\b{re.escape(w)}\b", folded) for w in _SLIDES)


def wants_obtain(text: str) -> bool:
    folded = _fold(text)
    return any(w in folded for w in _OBTAIN)


_STEWARD = (
    "escritorio", "ordenar", "ordena", "renombrar", "renombra", "mover archivo",
    "limpia", "limpiar", "icono", "iconos", "personalizar", "animar",
    "mayordomo",
)
_MACRO = ("macro", "macros")
_CODEGEN = ("programa", "programas", "script python", "genera un programa",
            "generar un programa", "codigo fuente")
_HARDWARE = ("bios", "overclock", "gpu", "tarjeta de video", "tarjeta grafica",
             "optimizar cpu", "optimiza la cpu", "flashear")
_VAULT = ("wallet", "billetera", "seed phrase", "semilla", "clave privada",
          "crear cuenta", "crea una cuenta")
_COUNSEL_L = ("abogado", "legal", "demanda", "contrato", "juicio")
_COUNSEL_M = ("medico", "médico", "sintoma", "síntoma", "diagnostico",
              "receta", "fiebre", "dolor")
_HORIZON = ("oportunidad de trabajo", "oportunidades de trabajo",
            "busca empleo", "buscar empleo", "trabaja por mi",
            "trabajar por el usuario", "oportunidad financiera")


def wants_steward(text: str) -> bool:
    folded = _fold(text)
    return any(w in folded for w in _STEWARD)


@dataclass(frozen=True)
class Intent:
    kind: str          # chat | stop | status | search | create | mission | ...
    topic: str
    wants_book: bool = False
    wants_slides: bool = False
    wants_obtain: bool = False
    confidence: float = 1.0


def classify_intent(text: str) -> Intent:
    raw = (text or "").strip()
    if not raw:
        return Intent("chat", "")
    folded = _fold(raw)
    early = _early_intent(raw, folded)
    if early:
        return early
    special = _special_intent(raw, folded)
    if special:
        return special
    return _make_intent(raw, folded)


def _early_intent(raw: str, folded: str) -> Optional[Intent]:
    padded = f" {folded} "
    if folded in _STOP or folded.rstrip("!.") in _STOP:
        return Intent("stop", raw, confidence=0.95)
    if any(f" {w} " in padded for w in _STOP) and len(raw.split()) <= 4:
        return Intent("stop", raw, confidence=0.95)
    if any(w in folded for w in _STATUS) and len(raw) < 80:
        return Intent("status", raw, confidence=0.9)
    if len(raw) < 60 and any(re.search(rf"\b{re.escape(_fold(w))}\b", folded)
                             for w in _CHAT_ONLY):
        return Intent("chat", raw, confidence=0.85)
    return None


def _special_intent(raw: str, folded: str) -> Optional[Intent]:
    table = (
        (_VAULT, "vault", 0.93),
        (_HARDWARE, "hardware", 0.9),
        (_MACRO, "macro", 0.88),
        (_COUNSEL_L + _COUNSEL_M, "counsel", 0.88),
        (_HORIZON, "horizon", 0.86),
        (_CODEGEN, "codegen", 0.86),
    )
    for keys, kind, conf in table:
        if any(w in folded for w in keys):
            return Intent(kind, raw, confidence=conf)
    if wants_steward(raw):
        return Intent("steward", raw, confidence=0.88)
    return None


def _make_intent(raw: str, folded: str) -> Intent:
    slides = wants_slides(raw)
    obtain = wants_obtain(raw)
    wants_book = any(w in folded for w in _BOOK) or obtain
    if any(re.search(rf"\b{re.escape(w)}\b", folded) for w in _SEARCH):
        topic = _strip_verbs(raw, _SEARCH)
        return Intent("search", topic or raw, confidence=0.9)
    if any(re.search(rf"\b{re.escape(w)}\b", folded) for w in _CREATE):
        topic = _strip_verbs(raw, _CREATE + _SLIDES + _OBTAIN)
        return Intent("create", topic or raw, wants_book=wants_book,
                      wants_slides=slides, wants_obtain=obtain,
                      confidence=0.88)
    if slides or obtain or wants_book:
        return Intent("create", raw, wants_book=wants_book or obtain,
                      wants_slides=slides, wants_obtain=obtain,
                      confidence=0.8)
    if len(raw) > 24 and any(w in folded for w in (
            "analiza", "audita", "investiga", "ejecuta", "lanza",
            "repara", "optimiza", "implementa")):
        return Intent("mission", raw, confidence=0.75)
    return Intent("chat", raw, confidence=0.6)


def _strip_verbs(text: str, verbs: tuple[str, ...]) -> str:
    out = text
    for verb in verbs:
        out = re.sub(rf"\b{re.escape(verb)}\b", " ", out, flags=re.I)
    out = re.sub(r"\b(un|una|el|la|los|las|de|del|sobre|por|favor|me|porfa)\b",
                 " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip(" .,:;")
