"""Clasificador de intención del operador (chat vs acción vs parada).

Determinista, sin red y sin LLM. El chat lo usa para NO lanzar una misión
de 10 minutos cuando el operador solo quiere hablar, buscar o detener.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


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


@dataclass(frozen=True)
class Intent:
    kind: str          # chat | stop | status | search | create | mission
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
    padded = f" {folded} "

    if any(f" {w} " in padded or folded == w for w in _STOP):
        if len(raw) < 80:
            return Intent("stop", raw, confidence=0.95)

    if any(w in folded for w in _STATUS) and len(raw) < 80:
        return Intent("status", raw, confidence=0.9)

    if any(w in folded for w in _CHAT_ONLY) and len(raw) < 60:
        return Intent("chat", raw, confidence=0.85)

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
