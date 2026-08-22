"""Ciclo de Enriquecimiento (CE) — aprender de repos públicos hasta ser capaz.

La versión LEGÍTIMA de "enriquecerse buscando en GitHub": estudio de código
público como **conocimiento**, no como recurso que expropiar.

Qué hace::

    problema → intento → [fallo] → detectar brecha de conocimiento
            → buscar repos públicos (API de GitHub, clave del OPERADOR)
            → estudiar READMEs (resumen via pool SORL o extractivo stdlib)
            → destilar FICHAS DE CONOCIMIENTO (fuente + licencia + cómo usar)
            → reinyectar el conocimiento en la planificación → reintentar
            → repetir hasta que el VERIFICADOR del objetivo pase (o presupuesto agotado)

Fronteras de diseño (no configurables):

* **Solo lectura de código público** con la clave del operador; se respetan
  los rate limits de la API (``Retry-After`` incluido). No se descubre ni
  sondea ningún endpoint ajeno — la línea anti-SORD sigue intacta.
* **Nunca se ejecuta código de los repos estudiados**: se asimila texto
  (ideas, APIs, recetas), no binarios. El supply-chain no se toca.
* **"Sentirse capaz" = verificación**: el criterio de parada es el verificador
  del objetivo, no una sensación. La confianza se reporta como evidencia
  (fichas aplicadas, ciclos, brechas perseguidas), nunca como promesa.
* Cada contenido pasa por el **modelo de permisos** (``classify_forbidden``):
  un README que describa conductas prohibidas se rechaza y queda registrado.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from .config import classify_forbidden
from .models import now_iso
from .provider_pool import ProviderPool, RateWindow

GITHUB_API = "https://api.github.com"


# --------------------------------------------------------------------------
# Cliente de la API de GitHub (solo lectura, rate limits respetados)
# --------------------------------------------------------------------------

class BudgetExhausted(RuntimeError):
    """Presupuesto de API o de tiempo agotado: parada honesta."""


@dataclass
class RepoHit:
    full_name: str
    html_url: str
    description: str = ""
    stars: int = 0
    language: str = ""
    license: str = ""
    updated_at: str = ""


class GitHubClient:
    """Búsqueda y lectura en GitHub con cuota auto-impuesta (conservadora).

    Ventanas: 20 búsquedas/min autenticado (límite real 30) y 10 sin token
    (límite real 10); lecturas de README: 30/min autenticado, 2 sin token.
    Un 403/429 con ``Retry-After`` se RESPETA (espera acotada) — nunca se
    reintenta en caliente ni se evade el límite.
    """

    def __init__(self, token: Optional[str] = None,
                 transport: Optional[Callable[[str, dict], tuple[int, dict, bytes]]] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None,
                 max_calls: int = 60) -> None:
        self.token = (token or os.environ.get("GITHUB_TOKEN")
                      or os.environ.get("GH_TOKEN") or "").strip()
        self.authed = bool(self.token)
        self.search_window = RateWindow(20 if self.authed else 8)
        self.core_window = RateWindow(30 if self.authed else 2)
        self._calls = 0
        self.max_calls = max_calls
        self._transport = transport          # (url, headers) → (status, headers, body)
        self._sleep = sleep_fn or time.sleep
        self.last_rate_info: dict[str, Any] = {}

    # -- bajo nivel ----------------------------------------------------------

    def _headers(self, accept: str) -> dict[str, str]:
        h = {"User-Agent": "A2S-learner/1.5 (+autonomous study; read-only)",
             "Accept": accept}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _get(self, path_or_url: str, accept: str,
             window: RateWindow) -> tuple[int, dict, bytes]:
        url = path_or_url if path_or_url.startswith("http") else GITHUB_API + path_or_url
        waited_server_limit = False
        for _ in range(3):
            self._calls += 1
            if self._calls > self.max_calls:
                raise BudgetExhausted(
                    f"presupuesto de API agotado ({self.max_calls} llamadas)")
            if not window.try_acquire():
                wait = window.seconds_until_slot()
                if wait > 30:
                    raise BudgetExhausted(f"cuota de API local agotada ({wait:.0f}s)")
                self._sleep(min(wait + 0.05, 30.0))    # respetar la ventana propia
                continue
            status, headers, body = self._request(url, accept)
            if status in (403, 429):
                remaining = str(headers.get("X-RateLimit-Remaining",
                                            headers.get("x-ratelimit-remaining", "1")))
                retry_after = headers.get("Retry-After", headers.get("retry-after"))
                if remaining != "0" and not retry_after:
                    return status, headers, body       # 403 de otro tipo (permisos)
                # rate limit DEL SERVIDOR: se respeta (espera acotada, 1 reintento)
                if waited_server_limit:
                    raise BudgetExhausted("rate limit de GitHub persiste tras esperar")
                try:
                    wait = float(retry_after) if retry_after else 60.0
                except ValueError:
                    wait = 60.0
                if wait > 60:
                    raise BudgetExhausted(f"rate limit de GitHub: espera {wait:.0f}s")
                self._sleep(min(wait, 60.0))
                waited_server_limit = True
                continue
            return status, headers, body
        raise BudgetExhausted("sin hueco de cuota tras esperar")

    def _request(self, url: str, accept: str) -> tuple[int, dict, bytes]:
        if self._transport is not None:
            return self._transport(url, self._headers(accept))
        req = urllib.request.Request(url, headers=self._headers(accept))
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(2000)
            except Exception:  # noqa: BLE001
                pass
            return exc.code, dict(exc.headers or {}), body

    # -- API pública -----------------------------------------------------------

    def search_repositories(self, query: str, per_page: int = 5,
                            language: str = "") -> list[RepoHit]:
        q = urllib.parse.quote(query)
        if language:
            q = urllib.parse.quote(f"{query} language:{language}")
        status, headers, body = self._get(
            f"{GITHUB_API}/search/repositories?q={q}&sort=stars"
            f"&order=desc&per_page={per_page}", "application/vnd.github+json",
            self.search_window)
        if status != 200:
            return []
        data = json.loads(body.decode("utf-8", "replace"))
        hits = []
        for it in data.get("items", [])[:per_page]:
            hits.append(RepoHit(
                full_name=it.get("full_name", ""),
                html_url=it.get("html_url", ""),
                description=(it.get("description") or "")[:300],
                stars=int(it.get("stargazers_count", 0) or 0),
                language=it.get("language") or "",
                license=((it.get("license") or {}).get("spdx_id") or "desconocida"),
                updated_at=(it.get("updated_at") or "")[:10]))
        self.last_rate_info = {"search_remaining": headers.get(
            "X-RateLimit-Remaining", "?")}
        return hits

    def fetch_readme(self, full_name: str, max_bytes: int = 60_000) -> str:
        status, headers, body = self._get(
            f"{GITHUB_API}/repos/{urllib.parse.quote(full_name)}/readme",
            "application/vnd.github.raw", self.core_window)
        if status != 200:
            return ""
        if self._transport is None and body[:1] == b"{":
            # alguna configuración devuelve JSON con base64
            try:
                body = base64.b64decode(json.loads(body.decode()).get("content", ""))
            except Exception:  # noqa: BLE001
                return ""
        return body[:max_bytes].decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Fichas de conocimiento
# --------------------------------------------------------------------------

@dataclass
class KnowledgeCard:
    """Conocimiento destilado de un repo público: fuente, licencia, receta."""
    id: str
    topic: str
    query: str
    repo: str
    url: str
    license: str
    summary: str
    recipe: str                      # "cómo se usa" en 3-6 pasos
    snippet: str = ""                # extracto citado (máx ~500 chars)
    stars: int = 0
    created_at: str = field(default_factory=now_iso)
    used: int = 0
    wins: int = 0

    @property
    def win_rate(self) -> float:
        return (self.wins / self.used) if self.used else 0.0

    def to_text(self, with_snippet: bool = True) -> str:
        out = (f"### {self.repo} (★{self.stars}, licencia {self.license}) — {self.topic}\n"
               f"{self.summary}\nUso: {self.recipe}\nFuente: {self.url}")
        if with_snippet and self.snippet:
            out += f"\nExtracto: {self.snippet}"
        return out


def _cards_dir(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), ".a2s", "knowledge")


def save_card(card: KnowledgeCard, workspace: str) -> str:
    d = _cards_dir(workspace)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, card.id + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(card), fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def load_cards(workspace: str) -> list[KnowledgeCard]:
    d = _cards_dir(workspace)
    out: list[KnowledgeCard] = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                out.append(KnowledgeCard(**json.load(fh)))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return out


# --------------------------------------------------------------------------
# Resumen extractivo (stdlib, sin LLM) y detección de brecha heurística
# --------------------------------------------------------------------------

_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def extractive_summary(text: str, max_sents: int = 5, max_chars: int = 600) -> str:
    """Resumen pobre-pero-honesto: primeras frases + cabeceras de sección."""
    if not text:
        return ""
    headers = [ln.strip("# ").strip() for ln in text.splitlines()
               if ln.startswith("#") and 3 < len(ln.strip()) < 80][:6]
    sents = [s.strip() for s in _SENT_RE.split(text.replace("\n", " ")) if s.strip()]
    body = " ".join(sents[:max_sents])[:max_chars]
    return (" · ".join(h for h in headers if h) + "\n" + body).strip()


_STOP = set("""de la el los las un una y o en para con como por que se su al del
the a an of to for with how using python library tool error errors exception
traceback module named import failed failure type code sin no desconozco""".split())

_TECH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[_.-][A-Za-z0-9]+)+$")


def _is_tech_token(tok: str) -> bool:
    """Identificador técnico: EXIF, PIL, CamelCase, snake_case, kebab-case."""
    if tok.isupper() and 2 <= len(tok) <= 12:
        return True                                  # EXIF, PIL, HTTP…
    if _TECH_RE.match(tok):
        return True                                  # exif_py, exif-py, pkg.name
    return any(ch.isupper() for ch in tok[1:])       # CamelCase


def gap_query_heuristic(goal: str, failures: str) -> str:
    """Extrae una consulta de brecha sin LLM: términos clave del objetivo más
    los IDENTIFICADORES TÉCNICOS del fallo (EXIF, PIL, CamelCase…). Las
    palabras genéricas del error ("Error", "module named") no buscan nada en
    GitHub y se descartan."""
    def keywords(text: str, n: int) -> list[str]:
        words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑ_][A-Za-z0-9_\-]{2,}", text or "")
        seen, out = set(), []
        for w in words:
            lw = w.lower()
            if lw in _STOP or lw in seen:
                continue
            seen.add(lw)
            out.append(w)
        return out[:n]

    goal_keys = keywords(goal, 4)
    tech = [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.\-]{1,20}", failures or "")
            if _is_tech_token(t) and t.lower() not in {g.lower() for g in goal_keys}]
    parts = goal_keys + tech[:3]
    return " ".join(parts) if parts else goal.strip()[:60]


def _frescura(iso: str, vida_media_dias: float = 180.0) -> float:
    """Peso de frescura exponencial: hoy=1.0, media vida a `vida_media_dias`."""
    try:
        t = time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return 0.5
    dias = max(0.0, (time.time() - t) / 86400.0)
    return math.exp(-dias / vida_media_dias)


# --------------------------------------------------------------------------
# El Ciclo de Enriquecimiento
# --------------------------------------------------------------------------

class Learner:
    """Busca, estudia y destila conocimiento público hasta que el verificador
    del objetivo pasa (o se agota el presupuesto). Nunca ejecuta lo estudiado."""

    def __init__(self, workspace: str,
                 pool: Optional[ProviderPool] = None,
                 github: Optional[GitHubClient] = None,
                 repos_per_cycle: int = 4) -> None:
        self.workspace = workspace
        self.pool = pool
        self.github = github or GitHubClient()
        self.repos_per_cycle = repos_per_cycle
        self.cards: list[KnowledgeCard] = load_cards(workspace)
        self.cycle_log: list[dict[str, Any]] = []

    # -- estudiar ------------------------------------------------------------

    def _summarize_many(self, query: str, readmes: list[tuple[RepoHit, str]],
                        ) -> list[tuple[RepoHit, str, str]]:
        """[(repo, resumen, receta)] — con pool SORL (fanout) o extractivo."""
        if self.pool is not None and readmes:
            prompts = [
                f"Estudia el README de {r.full_name} para resolver: «{query}».\n"
                f"README (truncado):\n{text[:4000]}\n"
                'Devuelve JSON: {"summary": "qué es y qué aporta (2-3 frases)", '
                '"recipe": "cómo usarlo en 3-6 pasos concretos", '
                '"snippet": "extracto literal ≤400 chars"}'
                for r, text in readmes]
            results = self.pool.fanout(prompts, kind="summarize", max_tokens=500)
            out = []
            for (r, text), res in zip(readmes, results):
                if res:
                    obj = None
                    try:
                        m = re.search(r"\{.*\}", res, re.S)
                        obj = json.loads(m.group(0)) if m else None
                    except json.JSONDecodeError:
                        obj = None
                    if isinstance(obj, dict) and obj.get("summary"):
                        out.append((r, str(obj.get("summary", ""))[:600],
                                    str(obj.get("recipe", ""))[:600]))
                        continue
                out.append((r, extractive_summary(text),
                            "leer la documentación del repositorio (sin LLM)"))
            return out
        return [(r, extractive_summary(t),
                 "leer la documentación del repositorio (sin LLM)")
                for r, t in readmes]

    def research(self, query: str, topic: str = "") -> list[KnowledgeCard]:
        """Busca repos para la brecha, los estudia y guarda fichas nuevas."""
        topic = topic or query[:40]
        hits = self.github.search_repositories(query, per_page=self.repos_per_cycle)
        readmes: list[tuple[RepoHit, str]] = []
        for h in hits:
            text = self.github.fetch_readme(h.full_name)
            if text:
                readmes.append((h, text))
        new_cards: list[KnowledgeCard] = []
        for i, (hit, summary, recipe) in enumerate(self._summarize_many(query, readmes)):
            blob = f"{hit.description}\n{summary}\n{recipe}"
            if reason := classify_forbidden(blob):
                self.cycle_log.append({"at": now_iso(), "rejected": hit.full_name,
                                       "reason": reason})
                continue                     # modelo de permisos: no se asimila
            card = KnowledgeCard(
                id=f"card-{abs(hash((query, hit.full_name))) % 10**10}",
                topic=topic, query=query, repo=hit.full_name, url=hit.html_url,
                license=hit.license, summary=summary, recipe=recipe,
                snippet=summary[:400], stars=hit.stars)
            known = {c.repo for c in self.cards}
            if hit.full_name in known:
                continue
            save_card(card, self.workspace)
            self.cards.append(card)
            new_cards.append(card)
        return new_cards

    # -- unlearning: poda de fichas perdedoras ---------------------------------

    def prune(self, min_used: int = 5, max_win: float = 0.2,
              min_dias: int = 90) -> list[str]:
        """Olvida lo que demostró no servir: ficha con uso suficiente, win-rate
        bajo y edad mínima se borra (archivo y memoria). Devuelve los repos
        olvidados. La poda NUNCA borra fichas nuevas (sin uso aún)."""
        olvidadas = []
        for c in list(self.cards):
            if c.used >= min_used and c.win_rate <= max_win:
                try:
                    t = time.mktime(time.strptime(c.created_at, "%Y-%m-%dT%H:%M:%SZ"))
                    if (time.time() - t) / 86400.0 < min_dias:
                        continue
                except ValueError:
                    pass
                self.cards.remove(c)
                path = os.path.join(_cards_dir(self.workspace), c.id + ".json")
                try:
                    os.remove(path)
                except OSError:
                    pass
                olvidadas.append(c.repo)
        return olvidadas

    # -- reinyectar ------------------------------------------------------------

    def knowledge_context(self, max_cards: int = 4,
                          topic_like: str = "") -> str:
        """Bloque de conocimiento para inyectar en la planificación."""
        cards = self.cards
        if topic_like:
            tl = topic_like.lower()
            cards = sorted(
                self.cards,
                # win-rate decaído por frescura: lo viejo pierde prioridad
                key=lambda c: (c.win_rate * _frescura(c.created_at),
                               tl in c.topic.lower() or tl in c.query.lower()),
                reverse=True)
        if not cards:
            return ""
        top = cards[:max_cards]
        for c in top:
            c.used += 1
        body = "\n\n".join(c.to_text() for c in top)
        return (f"[CONOCIMIENTO ASIMILADO de repos públicos — {len(top)} fichas "
                f"de {len(self.cards)}; nunca ejecutes código de las fuentes, "
                f"usa las recetas como guía]\n{body}")

    def mark_result(self, won: bool, max_cards: int = 4) -> None:
        """Atribuye el resultado a las fichas inyectadas en el último ciclo."""
        for c in self.cards[-max_cards:]:
            if c.used > c.wins:
                c.wins += int(won)
        for c in self.cards:
            save_card(c, self.workspace)

    # -- el loop ----------------------------------------------------------------

    def detect_gap(self, goal: str, failures: str) -> str:
        if self.pool is not None:
            res = self.pool.chat(
                f"OBJETIVO: {goal}\n\nFALLOS RECIENTES:\n{failures[:1500]}\n\n"
                "Formula UNA consulta corta de búsqueda en GitHub (solo "
                "términos clave, sin comillas) para el conocimiento que falta.",
                kind="general", max_tokens=60,
                system="Responde solo con la consulta de búsqueda, nada más.")
            if res and res.strip():
                return res.strip().strip('"')[:120]
        return gap_query_heuristic(goal, failures)

    def enrich_until_capable(
            self, goal: str,
            attempt: Callable[[str], Any],
            verifier: Callable[[Any], bool],
            max_cycles: int = 3,
            on_cycle: Optional[Callable[[int, dict[str, Any]], None]] = None,
            failures_of: Optional[Callable[[Any], str]] = None,
    ) -> dict[str, Any]:
        """Ciclo: intentar → [fallar] → detectar brecha → estudiar → reintentar.

        Parada honesta: el ``verifier`` del objetivo pasa (capaz ✔) o se
        agota ``max_cycles`` (informe con lo aprendido y las brechas quedan
        persistidas para la siguiente ejecución).
        """
        report: dict[str, Any] = {"goal": goal, "cycles": [], "capable": False,
                                  "cards_total": len(self.cards), "at": now_iso()}
        for cycle in range(1, max_cycles + 1):
            knowledge = self.knowledge_context(topic_like=goal)
            result = attempt(knowledge)
            won = bool(verifier(result))
            self.mark_result(won)
            info = {"cycle": cycle, "won": won,
                    "cards_before": report["cards_total"],
                    "knowledge_cards": knowledge.count("###")}
            self.cycle_log.append({"at": now_iso(), **info})
            report["cycles"].append(info)
            report["last_result"] = result
            report["cards_total"] = len(self.cards)
            if on_cycle:
                on_cycle(cycle, info)
            if won:
                report["capable"] = True
                report["confidence"] = self._confidence(won_cycles=cycle)
                return report
            failures = failures_of(result) if failures_of else ""
            gap = self.detect_gap(goal, failures or "fallo sin detalle")
            info["gap_query"] = gap
            try:
                new = self.research(gap)
                info["new_cards"] = [c.repo for c in new]
            except BudgetExhausted as exc:
                info["budget_stop"] = str(exc)
                report["cycles"][-1] = info
                break
            report["cards_total"] = len(self.cards)
        report["confidence"] = self._confidence(won_cycles=0)
        return report

    def _confidence(self, won_cycles: int) -> str:
        """Evidencia, no sensación: qué se aplicó y con qué resultado."""
        used = sum(c.used for c in self.cards)
        wins = sum(c.wins for c in self.cards)
        if won_cycles:
            return (f"verificado: objetivo cumplido en {won_cycles} ciclo(s) "
                    f"con {used} aplicaciones de fichas ({wins} con éxito)")
        return (f"NO verificado: presupuesto agotado con {len(self.cards)} fichas "
                f"asimiladas ({used} aplicaciones); las fichas persisten y la "
                f"siguiente ejecución parte con ellas")
