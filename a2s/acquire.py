"""Obtención honesta de obras de dominio público (Project Gutenberg).

Nunca descarga El Principito ni otras obras protegidas. Solo HTTPS, hosts
conocidos y un catálogo o una ficha de Gutendex con identificador numérico.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .finder import fold
from .literary import is_principito

ALLOWED_HOSTS = frozenset({
    "gutendex.com", "www.gutenberg.org", "gutenberg.org",
    "www.gutenberg.net",
})
MAX_BYTES = 1_800_000
USER_AGENT = "A2S/1.17 (+public-domain reader; +https://www.gutenberg.org)"

# (claves plegadas, id Gutenberg, título de cortesía)
CATALOG: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (("quijote", "cervantes", "don quixote"), 2000, "Don Quijote de la Mancha"),
    (("odisea", "odyssey"), 1727, "The Odyssey"),
    (("iliada", "iliad"), 2199, "The Iliad"),
    (("hamlet",), 1524, "Hamlet"),
    (("orgullo y prejuicio", "pride and prejudice"), 1342, "Pride and Prejudice"),
    (("frankenstein",), 84, "Frankenstein"),
    (("dracula",), 345, "Dracula"),
    (("moby dick", "moby-dick"), 2701, "Moby Dick"),
    (("alicia en el pais", "alice in wonderland", "alice's adventures"), 11,
     "Alice's Adventures in Wonderland"),
    (("robinson crusoe",), 521, "Robinson Crusoe"),
    (("sherlock", "estudio en escarlata"), 1661, "The Adventures of Sherlock Holmes"),
    (("tom sawyer",), 74, "The Adventures of Tom Sawyer"),
)


Transport = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]


def match_catalog(topic: str) -> Optional[tuple[int, str]]:
    text = fold(topic)
    for keys, gid, title in CATALOG:
        if any(key in text for key in keys):
            return gid, title
    return None


def can_obtain(topic: str) -> bool:
    if is_principito(topic):
        return False
    return match_catalog(topic) is not None


def fetch_public_domain(topic: str, transport: Optional[Transport] = None,
                        max_chars: int = 120_000) -> dict[str, Any]:
    """Devuelve texto de dominio público o un rechazo explícito."""
    if is_principito(topic):
        return {
            "status": "refused_copyright",
            "reason": ("El Principito no se descarga: companion original, "
                       "no la novela protegida en varios territorios."),
        }
    hit = match_catalog(topic)
    if hit is None:
        return {"status": "not_public_domain",
                "reason": "no está en el catálogo de dominio público de A²S"}
    gid, title = hit
    getter = transport or _default_transport
    text, url, err = _download_text(gid, getter)
    if not text:
        return {"status": "unavailable", "reason": err or "sin texto",
                "gutenberg_id": gid, "title": title}
    clean = _strip_gutenberg(text)
    full_len = len(clean)
    excerpt = clean[:max(4000, max_chars)]
    return {
        "status": "obtained",
        "title": title,
        "gutenberg_id": gid,
        "source_url": url,
        "license": "Project Gutenberg public domain (US)",
        "text": excerpt,
        "full_chars": full_len,
        "truncated": full_len > len(excerpt),
    }


def _download_text(gid: int, transport: Transport
                   ) -> tuple[str, str, str]:
    urls = (
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-8.txt",
    )
    last = "sin candidatos"
    for url in urls:
        try:
            code, _headers, blob = transport(url, {"User-Agent": USER_AGENT})
        except Exception as exc:  # noqa: BLE001 — se prueba el siguiente espejo
            last = f"{type(exc).__name__}: {exc}"
            continue
        if code != 200 or not blob:
            last = f"HTTP {code} en {url}"
            continue
        text = blob[:MAX_BYTES].decode("utf-8", errors="replace")
        if len(text) < 400:
            last = "respuesta demasiado corta"
            continue
        return text, url, ""
    return "", "", last


def _default_transport(url: str, headers: dict[str, str]
                       ) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("solo https")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host no permitido: {host}")
    req = Request(url, headers=headers)
    with urlopen(req, timeout=25) as resp:  # noqa: S310 — host allowlist
        return resp.status, dict(resp.headers), resp.read(MAX_BYTES + 1)


def _strip_gutenberg(text: str) -> str:
    start = re.search(r"\*\*\*\s*START OF", text)
    end = re.search(r"\*\*\*\s*END OF", text)
    body = text
    if start:
        body = text[start.end():]
        nl = body.find("\n")
        if 0 <= nl < 80:
            body = body[nl + 1:]
    if end:
        body = body[:end.start()]
    return body.strip() or text.strip()


def to_markdown(title: str, text: str, meta: dict[str, Any]) -> str:
    note = (
        f"> Fuente: Project Gutenberg #{meta.get('gutenberg_id')} · "
        f"{meta.get('source_url', '')}. Dominio público en EE.UU. "
        "A²S no altera el texto salvo recorte de cabecera PG y tope de maquetación."
    )
    if meta.get("truncated"):
        note += (f" El texto completo tiene {meta.get('full_chars')} caracteres; "
                 "este volumen maquetado es un extracto fiel. El .txt guarda más.")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    lines = [f"# {title}", "", note, "", "## Texto"]
    for para in paras:
        compact = re.sub(r"\s+", " ", para)
        lines.extend(["", compact])
    return "\n".join(lines) + "\n"
