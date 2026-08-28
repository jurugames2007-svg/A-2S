"""Integraciones web locales: crawling respetuoso, SEO y fichas de texto."""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Optional


@dataclass
class PageSnapshot:
    url: str
    status: int
    title: str
    text: str
    links: list[str]
    headers: dict[str, str]


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)


class WebCrawler:
    """Descarga y analiza HTML, sin automatizar evasión ni formularios."""

    def __init__(self, allow_hosts: Optional[list[str]] = None,
                 max_bytes: int = 200_000, timeout: int = 20) -> None:
        self.allow_hosts = {host.lower().lstrip(".") for host in (allow_hosts or [])}
        self.max_bytes = max(1_000, max_bytes)
        self.timeout = max(1, min(120, timeout))

    def _allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            return False
        if not self.allow_hosts:
            return True
        host = (parsed.hostname or "").lower()
        return host in self.allow_hosts or any(host.endswith("." + item) for item in self.allow_hosts)

    def fetch(self, url: str) -> PageSnapshot:
        if not self._allowed(url):
            raise PermissionError("URL fuera de la allowlist HTTPS")
        request = urllib.request.Request(url, headers={"User-Agent": "A2S/1.28 (+research)"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read(self.max_bytes + 1)
            status = int(response.status)
            headers = {str(k): str(v) for k, v in response.headers.items()}
            final_url = response.geturl()
        if len(body) > self.max_bytes:
            body = body[:self.max_bytes]
        parser = _PageParser()
        parser.feed(body.decode("utf-8", "replace"))
        base = final_url
        links = []
        for link in parser.links:
            absolute = urllib.parse.urljoin(base, html.unescape(link))
            if urllib.parse.urlparse(absolute).scheme in ("http", "https"):
                links.append(absolute)
        return PageSnapshot(final_url, status, " ".join(parser.title_parts),
                            " ".join(parser.text_parts), sorted(set(links)), headers)


class SEOAuditor:
    """Auditoria SEO determinista de una instantanea HTML."""

    def audit(self, page: PageSnapshot) -> dict[str, Any]:
        title_length = len(page.title)
        text = page.text
        return {
            "url": page.url,
            "status": page.status,
            "title": page.title,
            "title_length": title_length,
            "title_ok": 30 <= title_length <= 60,
            "word_count": len(re.findall(r"\b[\w'-]+\b", text)),
            "links": len(page.links),
            "security_headers": {
                "content_security_policy": bool(page.headers.get("Content-Security-Policy")),
                "strict_transport_security": bool(page.headers.get("Strict-Transport-Security")),
                "x_content_type_options": bool(page.headers.get("X-Content-Type-Options")),
            },
        }


class BookToSkill:
    """Convierte texto propio en una ficha modular consultable."""

    def convert(self, text: str, name: str, chunk_size: int = 1200) -> dict[str, Any]:
        text = (text or "").strip()
        name = (name or "").strip()
        if not text or not name:
            raise ValueError("texto y nombre son obligatorios")
        if chunk_size < 100:
            raise ValueError("chunk_size minimo: 100")
        words = text.split()
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        return {"name": name, "version": "1.0.0", "chunks": chunks,
                "words": len(words), "source": "operator-provided"}

    def query(self, skill: dict[str, Any], query: str, top: int = 3) -> list[str]:
        terms = set(re.findall(r"\w{3,}", (query or "").lower()))
        ranked = sorted(skill.get("chunks", []),
                        key=lambda chunk: sum(term in chunk.lower() for term in terms),
                        reverse=True)
        return ranked[:max(1, top)]
