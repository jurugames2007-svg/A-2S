"""SORL — Sistema de Orquestación de Recursos Legítimos (``provider_pool``).

Meta-proveedor que agrega **los recursos a los que el operador tiene derecho
de uso** (claves propias, free tiers dentro de sus términos, modelos locales)
detrás de una única interfaz ``BaseProvider``. Para el resto de A²S es un
proveedor más; internamente planifica, distribuye y agrega.

Filosofía (frontera de diseño, no configurable):

* **Orquestación, no expropiación.** El pool solo contiene endpoints
  configurados por el operador o descubiertos por variables de entorno
  (*claves que el operador posee*). No descubre, sondea ni usa endpoints de
  terceros sin autorización.
* **Los límites se respetan, no se evaden.** Un ``429 Too Many Requests`` es
  una señal de estado: el endpoint entra en cuarentena durante el tiempo que
  indica ``Retry-After`` (o backoff exponencial) y la carga migra a otro
  recurso autorizado del pool. No hay rotación de IPs, falsificación de
  cabeceras ni ningún mecanismo para eludir controles de terceros.
* **Nunca se rinde.** Si todos los endpoints fallan, degrada al núcleo
  heurístico determinista (igual que ``OpenAICompatProvider``).

Componentes (ver plan SORL):

* ``RateWindow``      — ventana deslizante de cuota por endpoint (rpm).
* ``EndpointState``   — cuarentena (429) y circuit breaker (fallos).
* ``Telemetry``       — métricas por endpoint (p50/p95, éxito, coste) en
                        JSONL + snapshot recargable: el bucle
                        Ejecutar → Medir → Aprender → Optimizar.
* ``TaskScheduler``   — estrategias round_robin / cost_first / speed_first /
                        multi_objective (función de utilidad ponderada con
                        penalización por riesgo de agotar cuota).
* ``ProviderPool``    — meta-proveedor con failover, ``fanout`` (map paralelo)
                        y ``execute_dag`` (grafo de tareas con dependencias).
"""

from __future__ import annotations

import atexit
import email.utils
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import now_iso
from .providers import SYSTEM_PROMPT, BaseProvider, HeuristicProvider, _extract_json

# --------------------------------------------------------------------------
# Configuración de endpoints
# --------------------------------------------------------------------------

TIERS = ("free", "cheap", "paid")          # orden de preferencia por coste
TIER_COST_SCORE = {"free": 1.0, "cheap": 0.55, "paid": 0.15}
# Coste estimado por 1K tokens (prompt+completado) usado solo para telemetría.
TIER_EST_COST_1K = {"free": 0.0, "cheap": 0.0006, "paid": 0.006}


@dataclass
class PoolEndpoint:
    """Un recurso legítimo del pool (endpoint OpenAI-compatible o heurístico)."""
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""
    cost_tier: str = "cheap"             # free | cheap | paid
    quality: float = 0.8                 # aptitud esperada (0..1) del modelo
    rpm: int = 0                         # límite de peticiones/minuto (0 = sin límite conocido)
    timeout: int = 90                    # segundos por petición
    capabilities: tuple[str, ...] = ()   # etiquetas: plan, code, summarize, fast…
    role: str = "member"                 # member | fallback_only
    extra_headers: dict[str, str] = field(default_factory=dict)
    disabled_reason: str = ""            # p.ej. "${VAR} sin definir"

    @property
    def active(self) -> bool:
        return not self.disabled_reason

    @property
    def tier_index(self) -> int:
        return TIERS.index(self.cost_tier) if self.cost_tier in TIERS else len(TIERS)

    @property
    def cost_score(self) -> float:
        return TIER_COST_SCORE.get(self.cost_tier, 0.3)

    @property
    def est_cost_1k(self) -> float:
        return TIER_EST_COST_1K.get(self.cost_tier, 0.001)

    def matches(self, kind: str) -> float:
        """Afinidad (0..1) del endpoint para un tipo de tarea."""
        if not self.capabilities:
            return self.quality
        if not kind or kind in self.capabilities or "general" in self.capabilities:
            return self.quality
        return 0.5 * self.quality          # puede hacerlo, no es su especialidad


_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: str) -> Optional[str]:
    """Expande ``${VAR}`` en un valor de configuración. None si la var no existe."""
    if value is None:
        return None
    out, missing = value, False
    for var in _ENV_RE.findall(value):
        env = os.environ.get(var)
        if env is None:
            missing = True
        else:
            out = out.replace("${" + var + "}", env)
    return None if missing else out


# --------------------------------------------------------------------------
# Estado por endpoint: cuota, cuarentena y circuit breaker
# --------------------------------------------------------------------------

class RateWindow:
    """Ventana deslizante de rpm. ``try_acquire`` consume un hueco o falla."""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self._hits: deque[float] = deque()

    def try_acquire(self, now: Optional[float] = None) -> bool:
        if self.rpm <= 0:
            return True
        now = time.monotonic() if now is None else now
        self._prune(now)
        if len(self._hits) >= self.rpm:
            return False
        self._hits.append(now)
        return True

    def seconds_until_slot(self, now: Optional[float] = None) -> float:
        if self.rpm <= 0:
            return 0.0
        now = time.monotonic() if now is None else now
        self._prune(now)
        if len(self._hits) < self.rpm:
            return 0.0
        return max(0.0, self._hits[0] + 60.0 - now)

    def used(self) -> int:
        self._prune(time.monotonic())
        return len(self._hits)

    def _prune(self, now: float) -> None:
        while self._hits and self._hits[0] <= now - 60.0:
            self._hits.popleft()


@dataclass
class EndpointState:
    """Estado mutable de un endpoint (protegido por el lock del pool)."""
    cooldown_until: float = 0.0          # cuarentena por 429/503 (respeta Retry-After)
    consecutive_429: int = 0
    consecutive_failures: int = 0        # fallos no-429 ( circuit breaker)
    circuit_trips: int = 0
    circuit_open_until: float = 0.0
    last_error: str = ""

    def in_cooldown(self, now: float) -> bool:
        return now < self.cooldown_until

    def circuit_open(self, now: float) -> bool:
        return now < self.circuit_open_until

    def quarantine(self, seconds: float, now: float, reason: str) -> None:
        self.cooldown_until = max(self.cooldown_until, now + max(0.0, seconds))
        self.last_error = reason

    def record_success(self) -> None:
        self.consecutive_429 = 0
        self.consecutive_failures = 0
        self.last_error = ""

    def record_failure(self, reason: str, now: float,
                       threshold: int = 3, base_backoff: float = 30.0) -> None:
        self.consecutive_failures += 1
        self.last_error = reason
        if self.consecutive_failures >= threshold:
            self.circuit_trips += 1
            backoff = min(300.0, base_backoff * (2 ** (self.circuit_trips - 1)))
            self.circuit_open_until = now + backoff
            self.consecutive_failures = 0     # media apertura: permitir una sonda


# --------------------------------------------------------------------------
# Telemetría: la memoria del sistema (JSONL + snapshot, sin dependencias)
# --------------------------------------------------------------------------

DEFAULT_WEIGHTS = {"speed": 0.25, "cost": 0.40, "reliability": 0.15,
                   "capability": 0.15, "quota_risk": 0.05}


class Telemetry:
    """Métricas por endpoint, persistidas en ``workspace/.a2s/pool/``.

    El scheduler recarga el snapshot al iniciar: latencias y tasas de éxito
    aprendidas en ejecuciones anteriores alimentan la planificación, y el
    sistema **aprende el rpm real** de cada endpoint (cuando un proveedor
    satura antes de lo declarado, el pool se auto-limita) más un micro-ajuste
    acotado de los pesos del scheduler. Es heurística acumulativa, no
    reentrenamiento: documentado en LIMITACIONES.md §10.3.
    """

    def __init__(self, directory: Optional[str] = None) -> None:
        self.directory = directory
        self.calls: dict[str, dict[str, Any]] = {}   # endpoint → agregados
        self.learned_rpm: dict[str, int] = {}        # endpoint → rpm efectivo observado
        self.weight_suggestions: dict[str, float] = {}  # micro-ajustes sugeridos
        self.clean_since_429: dict[str, int] = {}    # éxitos seguidos sin 429 (sesión)
        self._fh = None
        self._snapshots = 0
        if directory:
            os.makedirs(directory, exist_ok=True)
            self._load_snapshot()

    # -- registro ----------------------------------------------------------

    def record(self, endpoint: str, *, ok: bool, latency: float, kind: str = "",
               status: Optional[int] = None, retry_after: Optional[float] = None,
               tokens: int = 0, est_cost: float = 0.0) -> None:
        agg = self.calls.setdefault(endpoint, {
            "total": 0, "ok": 0, "rate_limited": 0, "errors": 0,
            "latencies": deque(maxlen=200), "tokens": 0, "est_cost": 0.0,
            "kinds": {},
        })
        agg["total"] += 1
        agg["ok"] += int(ok)
        if status == 429:
            agg["rate_limited"] += 1
        elif not ok:
            agg["errors"] += 1
        if ok:
            agg["latencies"].append(latency)
        agg["tokens"] += tokens
        agg["est_cost"] += est_cost
        if kind:
            agg["kinds"][kind] = agg["kinds"].get(kind, 0) + 1
        if ok:
            self.clean_since_429[endpoint] = self.clean_since_429.get(endpoint, 0) + 1
        elif status == 429:
            self.clean_since_429[endpoint] = 0
        self._append_jsonl({
            "t": now_iso(), "endpoint": endpoint, "kind": kind, "ok": ok,
            "latency": round(latency, 3), "status": status,
            "retry_after": retry_after, "tokens": tokens,
            "est_cost": round(est_cost, 6),
        })
        self._snapshots += 1
        if self._snapshots % 25 == 0:
            self.save_snapshot()

    # -- consultas ---------------------------------------------------------

    def success_rate(self, endpoint: str) -> Optional[float]:
        """Tasa de éxito EXCLUYENDO 429s: la saturación no es falta de
        fiabilidad del endpoint (la gestiona la cuarentena y el riesgo de
        cuota); aquí se mide "¿funciona cuando estamos dentro de cuota?"."""
        agg = self.calls.get(endpoint)
        if not agg:
            return None
        denom = agg["ok"] + agg["errors"]
        if denom < 3:
            return None                       # sin datos suficientes
        return agg["ok"] / denom

    def latency(self, endpoint: str, pct: float = 0.5) -> Optional[float]:
        agg = self.calls.get(endpoint)
        if not agg or not agg["latencies"]:
            return None
        data = sorted(agg["latencies"])
        idx = min(len(data) - 1, int(pct * len(data)))
        return data[idx]

    def summary(self) -> dict[str, Any]:
        out = {}
        for name, agg in self.calls.items():
            ok_plus_err = agg["ok"] + agg["errors"]
            out[name] = {
                "total": agg["total"], "ok": agg["ok"],
                "rate_limited": agg["rate_limited"], "errors": agg["errors"],
                # éxito = funciona dentro de cuota (429s excluidos: saturación
                # ≠ fallo; la gestiona la cuarentena y el riesgo de cuota)
                "success_rate": (agg["ok"] / ok_plus_err) if ok_plus_err >= 3 else None,
                "p50_ms": None if self.latency(name) is None else round(self.latency(name) * 1000),
                "p95_ms": None if self.latency(name, .95) is None else round(self.latency(name, .95) * 1000),
                "tokens": agg["tokens"], "est_cost": round(agg["est_cost"], 4),
            }
        return out

    # -- aprendizaje (rpm real observado + micro-ajuste de pesos) ------------

    def note_rate_limit_hit(self, endpoint: str, window_used: int) -> None:
        """El proveedor saturó con menos peticiones de las declaradas: aprende
        el rpm efectivo (80% de lo observado) para auto-limitarse antes."""
        cand = max(1, int(window_used * 0.8))
        cur = self.learned_rpm.get(endpoint)
        self.learned_rpm[endpoint] = cand if cur is None else max(1, min(cur, cand))

    def _tune_weights(self) -> None:
        """Micro-ajuste ACOTADO de pesos del scheduler según lo observado.

        Heurística simple y conservadora (no gradiente): si hubo muchas
        saturaciones → más peso al riesgo de cuota y menos al coste; si hubo
        muchos errores → más peso a la fiabilidad. Los ajustes persisten y se
        aplican solo si el operador NO fijó pesos explícitos.
        """
        total = sum(a["total"] for a in self.calls.values())
        if total < 10:
            return
        rl = sum(a["rate_limited"] for a in self.calls.values())
        errs = sum(a["errors"] for a in self.calls.values())
        sug = dict(self.weight_suggestions)

        def get(key: str) -> float:
            return sug.get(key, DEFAULT_WEIGHTS[key])

        changed = False
        if rl / total > 0.05:
            new = min(0.30, get("quota_risk") + 0.05)
            if new != get("quota_risk"):
                sug["quota_risk"], changed = new, True
            new_cost = max(0.05, get("cost") - 0.05)
            if new_cost != get("cost"):
                sug["cost"], changed = new_cost, True
        if errs / total > 0.10:
            new = min(0.35, get("reliability") + 0.05)
            if new != get("reliability"):
                sug["reliability"], changed = new, True
            new_speed = max(0.05, get("speed") - 0.05)
            if new_speed != get("speed"):
                sug["speed"], changed = new_speed, True
        if changed:
            self.weight_suggestions = sug

    def effective_rpm(self, endpoint: str, configured: int) -> int:
        """rpm a usar: el aprendido (si existe y es más conservador)."""
        learned = self.learned_rpm.get(endpoint)
        if learned is None:
            return configured
        if configured <= 0:
            return learned               # declarado ilimitado pero saturó
        return min(configured, learned)

    # -- persistencia --------------------------------------------------------

    def _path(self, name: str) -> Optional[str]:
        return os.path.join(self.directory, name) if self.directory else None

    def _append_jsonl(self, entry: dict[str, Any]) -> None:
        path = self._path("telemetry.jsonl")
        if not path:
            return
        if self._fh is None:
            self._fh = open(path, "a", encoding="utf-8")
        self._fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fh.flush()

    def save_snapshot(self, configured_rpm: Optional[dict[str, int]] = None) -> None:
        path = self._path("state.json")
        if not path:
            return
        self._tune_weights()
        # Recuperación gradual del rpm aprendido: tras ≥20 éxitos seguidos sin
        # saturación, se le devuelve +1 rpm (hasta el configurado). Si vuelve a
        # saturar, note_rate_limit_hit lo baja de nuevo — homeostasis.
        for name in list(self.learned_rpm):
            cfg = (configured_rpm or {}).get(name, 0)
            if self.clean_since_429.get(name, 0) >= 20 and (cfg <= 0 or self.learned_rpm[name] < cfg):
                self.learned_rpm[name] += 1
                if cfg > 0:
                    self.learned_rpm[name] = min(self.learned_rpm[name], cfg)
        snap = {"saved_at": now_iso(), "endpoints": {},
                "learned_rpm": self.learned_rpm,
                "weights": self.weight_suggestions}
        for name, agg in self.calls.items():
            lat = sorted(agg["latencies"])
            snap["endpoints"][name] = {
                "total": agg["total"], "ok": agg["ok"],
                "rate_limited": agg["rate_limited"], "errors": agg["errors"],
                "p50": lat[len(lat) // 2] if lat else None,
                "p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else None,
                "tokens": agg["tokens"], "est_cost": agg["est_cost"],
                "kinds": agg["kinds"],
            }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def _load_snapshot(self) -> None:
        path = self._path("state.json")
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                snap = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        for name, data in snap.get("endpoints", {}).items():
            agg = self.calls.setdefault(name, {
                "total": 0, "ok": 0, "rate_limited": 0, "errors": 0,
                "latencies": deque(maxlen=200), "tokens": 0, "est_cost": 0.0,
                "kinds": {},
            })
            agg["total"] = int(data.get("total", 0))
            agg["ok"] = int(data.get("ok", 0))
            agg["rate_limited"] = int(data.get("rate_limited", 0))
            agg["errors"] = int(data.get("errors", 0))
            if data.get("p50") is not None:
                agg["latencies"].append(float(data["p50"]))
            if data.get("p95") is not None:
                agg["latencies"].append(float(data["p95"]))
            agg["tokens"] = int(data.get("tokens", 0))
            agg["est_cost"] = float(data.get("est_cost", 0.0))
            agg["kinds"] = dict(data.get("kinds", {}))
        self.learned_rpm = {k: int(v) for k, v in snap.get("learned_rpm", {}).items()}
        self.weight_suggestions = {k: float(v) for k, v in snap.get("weights", {}).items()}

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


# --------------------------------------------------------------------------
# Scheduler: decide qué endpoint ejecuta cada tarea
# --------------------------------------------------------------------------

class TaskScheduler:
    """Asignación multi-criterio de tareas a endpoints disponibles.

    Un endpoint es *elegible* si: está activo, no está en cuarentena por 429,
    no tiene el circuit abierto y le queda hueco en su ventana de rpm.
    """

    def __init__(self, strategy: str = "multi_objective",
                 weights: Optional[dict[str, float]] = None) -> None:
        self.strategy = strategy
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self._rr = 0

    def eligible(self, endpoints: list[tuple[PoolEndpoint, EndpointState, RateWindow]],
                 kind: str, now: float, include_fallback: bool = False,
                 ) -> list[tuple[PoolEndpoint, EndpointState, RateWindow]]:
        out = []
        members = []
        for ep, st, win in endpoints:
            if not ep.active:
                continue
            if ep.role == "fallback_only" and not include_fallback:
                continue
            if st.in_cooldown(now) or st.circuit_open(now):
                continue
            members.append((ep, st, win))
        # El fallback heurístico solo entra si no hay ningún miembro utilizable
        # (con hueco de cuota) — garantiza que el pool nunca se rinde.
        with_quota = [t for t in members if t[0].role != "fallback_only"
                      and t[2].try_acquire(now)]
        if with_quota:
            out = with_quota
        elif include_fallback:
            out = members
        return out

    def pick(self, endpoints: list[tuple[PoolEndpoint, EndpointState, RateWindow]],
             kind: str = "general", exclude: Optional[set[str]] = None,
             now: Optional[float] = None) -> Optional[tuple[PoolEndpoint, EndpointState, RateWindow]]:
        """Elige (y reserva cuota para) el mejor endpoint; None si no hay."""
        now = time.monotonic() if now is None else now
        exclude = exclude or set()
        cands = [t for t in self.eligible(endpoints, kind, now) if t[0].name not in exclude]
        if not cands:
            # último recurso: fallback heurístico (sin cuota HTTP que reservar)
            fb = [t for t in endpoints if t[0].role == "fallback_only" and t[0].active
                  and t[0].name not in exclude and not t[1].circuit_open(now)]
            return fb[0] if fb else None
        s = self.strategy
        if s == "round_robin":
            cands.sort(key=lambda t: t[0].name)
            chosen = cands[self._rr % len(cands)]
            self._rr += 1
            return chosen
        if s == "cost_first":
            return min(cands, key=lambda t: (t[0].tier_index,
                                             self._latency(t[0].name) or 9e9))
        if s == "speed_first":
            return min(cands, key=lambda t: self._latency(t[0].name) or 9e9)
        return min(cands, key=lambda t: -self._utility(t, kind))

    # -- función de utilidad multi-objetivo ----------------------------------

    def _latency(self, name: str) -> Optional[float]:
        return self.telemetry.latency(name) if self.telemetry else None

    telemetry: Optional[Telemetry] = None

    def _utility(self, triple: tuple[PoolEndpoint, EndpointState, RateWindow],
                 kind: str) -> float:
        ep, _st, win = triple
        w = self.weights
        p50 = self._latency(ep.name)
        speed = 1.0 - min((p50 or 2.5) / 5.0, 1.0)       # 0s→1.0, ≥5s→0
        rel = self.telemetry.success_rate(ep.name) if self.telemetry else None
        reliability = 0.8 if rel is None else rel
        capability = ep.matches(kind)
        quota_risk = (win.used() / ep.rpm) if ep.rpm > 0 else 0.0
        return (w["speed"] * speed + w["cost"] * ep.cost_score
                + w["reliability"] * reliability + w["capability"] * capability
                - w["quota_risk"] * quota_risk)


# --------------------------------------------------------------------------
# El pool: meta-proveedor con failover, fanout y DAG
# --------------------------------------------------------------------------

_Transport = Callable[[PoolEndpoint, dict[str, Any]], dict[str, Any]]


class ProviderPool(BaseProvider):
    """Meta-proveedor SORL. Para A²S es un ``BaseProvider``; internamente
    orquesta N endpoints legítimos con cuotas, failover y agregación."""

    name = "pool"

    def __init__(self, endpoints: Optional[list[PoolEndpoint]] = None,
                 strategy: str = "multi_objective",
                 weights: Optional[dict[str, float]] = None,
                 workspace: Optional[str] = None,
                 max_parallel: int = 8,
                 transport: Optional[_Transport] = None,
                 verbose: bool = False) -> None:
        self.endpoints: list[PoolEndpoint] = endpoints or []
        if not any(e.role == "fallback_only" for e in self.endpoints):
            self.endpoints.append(PoolEndpoint(
                name="heuristic", base_url="", model="",
                cost_tier="free", quality=0.3, rpm=0, role="fallback_only"))
        self.fallback = HeuristicProvider()
        self.max_parallel = max(1, max_parallel)
        self.verbose = verbose
        self._transport = transport
        self._lock = threading.RLock()
        self._states = {e.name: EndpointState() for e in self.endpoints}
        tel_dir = os.path.join(os.path.abspath(workspace), ".a2s", "pool") if workspace else None
        self.telemetry = Telemetry(tel_dir)
        # rpm efectivo: si ejecuciones anteriores aprendieron que un endpoint
        # satura antes de lo declarado, auto-limitarse desde el arranque.
        self._windows = {e.name: RateWindow(self.telemetry.effective_rpm(e.name, e.rpm))
                         for e in self.endpoints}
        self.scheduler = TaskScheduler(strategy, weights)
        self.scheduler.telemetry = self.telemetry
        # Micro-ajuste de pesos aprendido: solo si el operador no fijó pesos.
        if weights is None and self.telemetry.weight_suggestions:
            self.scheduler.weights.update(self.telemetry.weight_suggestions)
        self._triples = [(e, self._states[e.name], self._windows[e.name])
                         for e in self.endpoints]
        # Persistir el aprendizaje aunque el proceso termine sin close()
        # (misiones normales, kill del supervisor, etc.).
        atexit.register(self.close)

    # -- triples activos ----------------------------------------------------

    def _active(self) -> list[tuple[PoolEndpoint, EndpointState, RateWindow]]:
        return [t for t in self._triples if t[0].active]

    # -- ejecución de una petición chat con failover --------------------------

    def _chat(self, messages: list[dict[str, str]], kind: str = "general",
              max_tokens: int = 1500, model_override: str = "") -> tuple[Optional[str], str]:
        """Devuelve (contenido, endpoint_que_lo_sirvió). (None, razón) si todos fallan."""
        tried: set[str] = set()
        attempts = len(self._active()) + 1
        for _ in range(max(1, attempts)):
            with self._lock:
                picked = self.scheduler.pick(self._triples, kind=kind, exclude=tried)
            if picked is None:
                break
            ep, st, _win = picked
            if ep.role == "fallback_only":
                return None, "fallback"
            tried.add(ep.name)
            content, err = self._call_once(ep, st, messages, kind, max_tokens, model_override)
            if content is not None:
                return content, ep.name
            with self._lock:
                remaining = [t for t in self._active()
                             if t[0].name not in tried and t[0].role != "fallback_only"]
                if not remaining:
                    # Todos los miembros útiles están saturados o caídos: si el
                    # reintento más cercano es razonable, esperar respetando el
                    # límite (Retry-After); nunca reintentar en caliente.
                    now = time.monotonic()
                    waits = [self._windows[t[0].name].seconds_until_slot(now)
                             for t in self._active() if t[0].role != "fallback_only"]
                    cooldowns = [self._states[t[0].name].cooldown_until - now
                                 for t in self._active() if t[0].role != "fallback_only"]
                    wait = min([w for w in waits + cooldowns if w > 0] or [0.0])
                    if 0 < wait <= 45:
                        if self.verbose:
                            print(f"[A²S-pool] ⏳ todos los miembros saturados; esperando "
                                  f"{wait:.0f}s (se respeta Retry-After) y reintento",
                                  flush=True)
                        time.sleep(wait + 0.05)
                        tried.clear()
                        continue
                    break               # nada disponible y la espera es demasiado larga
            # quedan endpoints sin probar: el bucle continúa con el siguiente
        return None, "exhausted"

    def _call_once(self, ep: PoolEndpoint, st: EndpointState,
                   messages: list[dict[str, str]], kind: str,
                   max_tokens: int, model_override: str) -> tuple[Optional[str], str]:
        payload = {
            "model": model_override or ep.model,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        t0 = time.monotonic()
        status: Optional[int] = None
        retry_after: Optional[float] = None
        tokens = 0
        try:
            data = self._send(ep, payload)
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            tokens = int(usage.get("prompt_tokens", 0) or 0) + \
                int(usage.get("completion_tokens", 0) or 0)
            latency = time.monotonic() - t0
            with self._lock:
                st.record_success()
                self.telemetry.record(ep.name, ok=True, latency=latency, kind=kind,
                                      tokens=tokens,
                                      est_cost=tokens / 1000.0 * ep.est_cost_1k)
            return content, ""
        except urllib.error.HTTPError as exc:
            status = exc.code
            retry_after = _parse_retry_after(exc.headers)
            latency = time.monotonic() - t0
            reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, KeyError, ValueError,
                json.JSONDecodeError, RuntimeError) as exc:
            latency = time.monotonic() - t0
            reason = f"{type(exc).__name__}: {str(exc)[:120]}"
        with self._lock:
            now = time.monotonic()
            self.telemetry.record(ep.name, ok=False, latency=latency, kind=kind,
                                  status=status, retry_after=retry_after)
            if status == 429 or status == 503:
                # Saturación del proveedor: cuarentena por Retry-After o backoff
                # exponencial (se RESPETA el límite; la carga migra a otro
                # recurso autorizado — nunca reintentos en caliente).
                st.consecutive_429 += 1
                backoff = retry_after if retry_after is not None else \
                    min(300.0, 5.0 * (2 ** (st.consecutive_429 - 1)))
                st.quarantine(backoff, now, f"HTTP {status} (cuarentena {backoff:.0f}s)")
                # Aprendizaje: el rpm declarado era optimista → aprender el real.
                if status == 429:
                    self.telemetry.note_rate_limit_hit(ep.name,
                                                       self._windows[ep.name].used())
                if self.verbose:
                    print(f"[A²S-pool] ◐ {ep.name}: HTTP {status} → cuarentena "
                          f"{backoff:.0f}s (se respeta el límite; la carga migra)",
                          flush=True)
                return None, "saturated"
            st.record_failure(reason, now)
            if self.verbose:
                print(f"[A²S-pool] ✗ {ep.name}: {reason}", flush=True)
            return None, "failed"

    def _send(self, ep: PoolEndpoint, payload: dict[str, Any]) -> dict[str, Any]:
        """Transporte HTTP real (o inyectado para tests)."""
        if self._transport is not None:
            return self._transport(ep, payload)
        headers = {"Content-Type": "application/json"}
        if ep.api_key:
            headers["Authorization"] = f"Bearer {ep.api_key}"
        headers.update(ep.extra_headers)
        req = urllib.request.Request(
            f"{ep.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=ep.timeout) as resp:
            return json.loads(resp.read().decode())

    # -- interfaz BaseProvider ------------------------------------------------

    def _structured(self, prompt: str, kind: str, fallback_obj: dict[str, Any],
                    max_tokens: int = 1500) -> dict[str, Any]:
        raw, served_by = self._chat(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            kind=kind, max_tokens=max_tokens)
        if raw is not None:
            obj = _extract_json(raw)
            if obj is not None:
                obj.setdefault("pool_provider", served_by)
                return obj
            fallback_obj["llm_fallback_reason"] = "respuesta sin JSON válido"
            return fallback_obj
        fallback_obj["llm_fallback_reason"] = "pool sin endpoints disponibles"
        return fallback_obj

    def plan(self, goal: str, context: str, tools: str, variant: int = 0) -> dict[str, Any]:
        prompt = (
            f"OBJETIVO: {goal}\n\nCONTEXTO:\n{context}\n\nHERRAMIENTAS:\n{tools}\n\n"
            f"Ronda de planificación: {variant}. Si variante > 0, el enfoque anterior "
            "falló: propón un plan DISTINTO.\n"
            'Devuelve JSON: {"strategy": str, "steps": [{"id": str, "goal": str, '
            '"approach": str, "tool": str, "params": dict, "success_criteria": [str], '
            '"depends_on": [str]}]}. Planifica pasos ejecutables con las herramientas '
            "disponibles para lograr el objetivo."
        )
        fallback = self.fallback.plan(goal, context, tools, variant=variant)
        obj = self._structured(prompt, "plan", fallback)
        if not isinstance(obj.get("steps"), list) or not obj["steps"]:
            return fallback
        return obj

    def reparameterize(self, goal: str, failed: str, history: str, tools: str) -> dict[str, Any]:
        prompt = (
            f"Un paso del plan falló.\nOBJETIVO: {goal}\nFALLO:\n{failed}\n"
            f"HISTORIAL RECIENTE:\n{history}\nHERRAMIENTAS:\n{tools}\n"
            'Devuelve JSON: {"strategy": str, "change": str, "new_params_hint": str}. '
            "Propón un enfoque DIFERENTE (reparametrización), nunca el mismo."
        )
        return self._structured(prompt, "reparam",
                                self.fallback.reparameterize(goal, failed, history, tools))

    def evaluate(self, step_goal: str, observation: str, criteria: str) -> dict[str, Any]:
        prompt = (
            f"Evalúa si el paso logró su objetivo.\nPASO: {step_goal}\n"
            f"CRITERIOS: {criteria}\nOBSERVACIÓN:\n{observation[:3000]}\n"
            'Devuelve JSON: {"score": float(0..1), "verdict": "success|failed|blocked", '
            '"reason": str}. blocked = imposible con el enfoque actual; failed = '
            "intento fallido pero reparametrizable."
        )
        fallback = self.fallback.evaluate(step_goal, observation, criteria)
        obj = self._structured(prompt, "evaluate", fallback, max_tokens=400)
        if obj.get("verdict") not in ("success", "failed", "blocked"):
            return fallback
        return obj

    def goal_check(self, goal: str, summary: str) -> tuple[bool, str]:
        prompt = (
            f"OBJETIVO: {goal}\nEVIDENCIA RECOPILADA:\n{summary[:3000]}\n"
            'Devuelve JSON: {"achieved": bool, "reason": str}. Sé estricto: solo '
            "true si el objetivo está realmente cumplido."
        )
        raw, served_by = self._chat(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            kind="goal_check", max_tokens=200)
        if raw is not None:
            obj = _extract_json(raw)
            if obj is not None and isinstance(obj.get("achieved"), bool):
                return obj["achieved"], str(obj.get("reason", ""))
        return self.fallback.goal_check(goal, summary)

    # -- ejecución distribuida: fanout (map) y DAG -----------------------------

    def chat(self, prompt: str, kind: str = "general", max_tokens: int = 1000,
             system: str = SYSTEM_PROMPT) -> Optional[str]:
        """Petición chat directa contra el pool (para herramientas externas)."""
        content, _ = self._chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": prompt}],
            kind=kind, max_tokens=max_tokens)
        return content

    def fanout(self, prompts: list[str], kind: str = "general",
               max_tokens: int = 1000, max_parallel: Optional[int] = None,
               progress: Optional[Callable[[int, int], None]] = None,
               ) -> list[Optional[str]]:
        """Map paralelo sobre el pool: N subtareas independientes repartidas
        entre los endpoints disponibles respetando las cuotas de cada uno."""
        tasks = [{"id": f"fan-{i}", "prompt": p, "kind": kind,
                  "max_tokens": max_tokens} for i, p in enumerate(prompts)]
        result = self.execute_dag(tasks, max_parallel=max_parallel)
        return [result["results"][t["id"]] for t in tasks]

    def execute_dag(self, tasks: list[dict[str, Any]],
                    aggregate: Optional[Callable[[dict[str, Any]], Any]] = None,
                    max_parallel: Optional[int] = None) -> dict[str, Any]:
        """Ejecuta un grafo de tareas (DAG) con dependencias.

        Cada tarea: ``{"id": str, "prompt": str, "depends_on": [str],
        "kind"?: str, "max_tokens"?: int}``. Las tareas se ejecutan por olas
        topológicas en paralelo; cada una usa el failover del pool. Si una
        tarea falla, sus dependientes se marcan ``skipped`` (honestidad ante
        fallos, coherente con LIMITACIONES.md).
        """
        ids = {t["id"] for t in tasks}
        deps = {t["id"]: list(t.get("depends_on", [])) for t in tasks}
        for tid, dl in deps.items():
            for d in dl:
                if d not in ids:
                    raise ValueError(f"tarea {tid}: dependencia desconocida {d}")
        # Orden topológico por olas (Kahn) + detección de ciclos.
        indeg = {tid: len(dl) for tid, dl in deps.items()}
        wave = [tid for tid, d in indeg.items() if d == 0]
        order: list[list[str]] = []
        seen: set[str] = set()
        while wave:
            order.append(sorted(wave))
            seen.update(wave)
            nxt: list[str] = []
            for tid in wave:
                for other, dl in deps.items():
                    if tid in dl:
                        indeg[other] -= 1
                        if indeg[other] == 0:
                            nxt.append(other)
            wave = nxt
        if len(seen) != len(ids):
            cyclic = sorted(ids - seen)
            raise ValueError(f"ciclo detectado en el DAG: {cyclic}")
        by_id = {t["id"]: t for t in tasks}
        results: dict[str, Optional[str]] = {}
        failed: set[str] = set()
        max_par = max_parallel or self.max_parallel
        for batch in order:
            runnable = [by_id[tid] for tid in batch
                        if not any(d in failed for d in deps[tid])]
            skipped = [tid for tid in batch if tid not in {t["id"] for t in runnable}]
            for tid in skipped:
                results[tid] = None
                failed.add(tid)
            if not runnable:
                continue
            with ThreadPoolExecutor(max_workers=min(max_par, len(runnable))) as pool:
                futs = {pool.submit(self.chat, t["prompt"], t.get("kind", "general"),
                                    t.get("max_tokens", 1000)): t["id"] for t in runnable}
                for fut in as_completed(futs):
                    tid = futs[fut]
                    try:
                        results[tid] = fut.result()
                    except Exception as exc:  # noqa: BLE001 — tarea aislada
                        results[tid] = None
                    if results[tid] is None:
                        failed.add(tid)
        out = {"results": results, "failed": sorted(failed),
               "executed": len(results) - len(failed), "total": len(tasks)}
        if aggregate is not None:
            # el agregador recibe el resumen completo (results + failed) para
            # poder decidir qué hacer con las tareas sin resultado
            out["aggregate"] = aggregate(out)
        return out

    # -- estado ----------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        eps = []
        with self._lock:
            for ep, st, win in self._triples:
                eps.append({
                    "name": ep.name, "base_url": ep.base_url, "model": ep.model,
                    "role": ep.role, "cost_tier": ep.cost_tier, "rpm": ep.rpm,
                    "rpm_effective": win.rpm,
                    "rpm_learned": self.telemetry.learned_rpm.get(ep.name),
                    "active": ep.active, "disabled_reason": ep.disabled_reason,
                    "cooldown_remaining_s": max(0.0, round(st.cooldown_until - now, 1)),
                    "circuit_open": st.circuit_open(now),
                    "consecutive_failures": st.consecutive_failures,
                    "last_error": st.last_error,
                    "window_used": win.used(),
                })
        tel = self.telemetry.summary()
        for e in eps:
            e.update(tel.get(e["name"], {}))
        totals = {
            "endpoints_active": sum(1 for e in eps if e["active"] and e["role"] == "member"),
            "endpoints_saturated": sum(1 for e in eps if e["cooldown_remaining_s"] > 0),
            "total_calls": sum(t.get("total", 0) for t in tel.values()),
            "total_ok": sum(t.get("ok", 0) for t in tel.values()),
            "est_cost": round(sum(t.get("est_cost", 0.0) for t in tel.values()), 4),
        }
        return {"strategy": self.scheduler.strategy,
                "weights": self.scheduler.weights,
                "endpoints": eps, "totals": totals}

    def close(self) -> None:
        with self._lock:
            try:
                self.telemetry.save_snapshot(
                    configured_rpm={e.name: e.rpm for e in self.endpoints})
            except OSError:
                pass        # p.ej. workspace volátil eliminado antes del exit
            self.telemetry.close()


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _parse_retry_after(headers: Any) -> Optional[float]:
    """``Retry-After`` en segundos (int o HTTP-date); None si ausente/inválido."""
    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After")
    except Exception:  # noqa: BLE001 — headers de excepción variables
        return None
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(raw)
            return max(0.0, when.timestamp() - time.time())
        except (ValueError, TypeError):
            return None


def _local_ollama_alive(host: str = "127.0.0.1", port: int = 11434,
                        timeout: float = 0.4) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


def discover_endpoints_from_env(include_local: bool = True) -> list[PoolEndpoint]:
    """Descubre endpoints LEGÍTIMOS: solo los cuya clave posee el operador.

    No sondea servicios de terceros: lee variables de entorno del entorno del
    operador y construye endpoints OpenAI-compatibles conocidos.
    """
    eps: list[PoolEndpoint] = []

    def add(name: str, base_url: str, key: str, model: str, tier: str,
            rpm: int, quality: float, caps: tuple[str, ...] = (),
            timeout: int = 90, extra: Optional[dict[str, str]] = None) -> None:
        eps.append(PoolEndpoint(
            name=name, base_url=base_url, api_key=key, model=model,
            cost_tier=tier, quality=quality, rpm=rpm, timeout=timeout,
            capabilities=caps, extra_headers=extra or {}))

    groq = os.environ.get("GROQ_API_KEY")
    if groq:
        add("groq", "https://api.groq.com/openai/v1", groq,
            os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
            "free", rpm=25, quality=0.8, caps=("fast", "general"), timeout=60)
    gemini = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
              or os.environ.get("GOOGLE_AI_API_KEY"))
    if gemini:
        add("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
            gemini, os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            "free", rpm=10, quality=0.9, caps=("plan", "summarize", "general"))
    github = os.environ.get("GITHUB_MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if github:
        add("github-models", "https://models.github.ai/inference", github,
            os.environ.get("GITHUB_MODELS_MODEL", "OpenAI/gpt-4o-mini"),
            "free", rpm=14, quality=0.85, caps=("plan", "code", "general"))
    openrouter = os.environ.get("OPENROUTER_API_KEY")
    if openrouter:
        add("openrouter", "https://openrouter.ai/api/v1", openrouter,
            os.environ.get("OPENROUTER_MODEL",
                           "meta-llama/llama-3.1-8b-instruct:free"),
            "cheap", rpm=15, quality=0.75, caps=("general",),
            extra={"X-Title": "A2S-agent"})
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        add("openai", os.environ.get("A2S_LLM_BASE_URL",
                                     "https://api.openai.com/v1").rstrip("/"),
            openai_key, os.environ.get("A2S_LLM_MODEL", "gpt-4o-mini"),
            "paid", rpm=60, quality=1.0,
            caps=("plan", "evaluate", "code", "general"))
    if include_local and _local_ollama_alive():
        add("ollama-local", "http://127.0.0.1:11434/v1", "ollama",
            os.environ.get("A2S_OLLAMA_MODEL", "llama3.2"),
            "free", rpm=0, quality=0.75, caps=("general", "summarize"),
            timeout=180)
    return eps


def endpoints_from_config(path: str) -> tuple[list[PoolEndpoint], dict[str, Any]]:
    """Carga el pool desde JSON (ver ``examples/pool.example.json``).

    Soporta expansión ``${VAR}`` en cualquier valor de cadena; si una variable
    requerida (p.ej. una api_key) no existe, el endpoint queda desactivado con
    su motivo — visible en ``a2s pool-status``.
    """
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    eps: list[PoolEndpoint] = []
    for raw in cfg.get("endpoints", []):
        api_key = raw.get("api_key", "")
        if "${" in api_key:
            expanded = _expand_env(api_key)
            disabled = "" if expanded is not None else f"{api_key} sin definir"
            api_key = expanded or ""
        else:
            disabled = ""
        eps.append(PoolEndpoint(
            name=raw["name"],
            base_url=raw.get("base_url", ""),
            api_key=api_key,
            model=raw.get("model", raw.get("models", [""])[0] if raw.get("models") else ""),
            cost_tier=raw.get("cost_tier", "cheap"),
            quality=float(raw.get("quality", 0.8)),
            rpm=int(raw.get("rpm", 0)),
            timeout=int(raw.get("timeout", 90)),
            capabilities=tuple(raw.get("capabilities", ())),
            role=raw.get("role", "member"),
            extra_headers=dict(raw.get("extra_headers", {})),
            disabled_reason=disabled,
        ))
    return eps, cfg


def build_pool_provider(config: Any = None) -> ProviderPool:
    """Fábrica usada por ``get_provider("pool")``.

    Orden de resolución: JSON explícito (``--pool-config`` / A2S_POOL_CONFIG)
    → ``workspace/.a2s/pool.json`` → descubrimiento por variables de entorno.
    """
    strategy = getattr(config, "pool_strategy", None) or os.environ.get(
        "A2S_POOL_STRATEGY", "multi_objective")
    workspace = getattr(config, "workspace", None) or "workspace"
    max_parallel = getattr(config, "pool_max_parallel", None) or int(
        os.environ.get("A2S_POOL_MAX_PARALLEL", "8"))
    verbose = not getattr(config, "quiet", False)

    cfg_path = (getattr(config, "pool_config", None)
                or os.environ.get("A2S_POOL_CONFIG")
                or os.path.join(workspace, ".a2s", "pool.json"))
    endpoints: list[PoolEndpoint] = []
    weights = None
    if os.path.isfile(cfg_path):
        endpoints, cfg = endpoints_from_config(cfg_path)
        strategy = cfg.get("strategy", strategy)
        weights = cfg.get("weights", weights)
        max_parallel = int(cfg.get("max_parallel", max_parallel))
        source = cfg_path
    else:
        endpoints = discover_endpoints_from_env()
        source = "variables de entorno (claves del operador)"
    pool = ProviderPool(endpoints, strategy=strategy, weights=weights,
                        workspace=workspace, max_parallel=max_parallel,
                        verbose=verbose)
    if verbose:
        active = [e.name for e in endpoints if e.active]
        print(f"[A²S] ⚙ pool SORL ({source}): {len(active)} endpoint(s) "
              f"activo(s): {', '.join(active) or '(solo fallback heurístico)'}; "
              f"estrategia={strategy}", flush=True)
    return pool
