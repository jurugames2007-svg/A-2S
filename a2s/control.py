"""Control de concurrencia: parada, inbox y trabajos laterales.

Contrato anti-deadlock (no negociable):

1. Nunca invertir el orden de candados: ``jobs`` → ``mission`` → ``chat``.
2. Nunca retener un candado mientras se llama a red, proveedor o herramienta.
3. Los candados se adquieren con timeout; si expiran, se degrada, no se espera
   eternamente.
4. Las colas usan ``queue.Queue`` (ya es thread-safe). ``put_nowait`` en el
   hub SSE: un cliente lento no bloquea al productor.
5. Chat y misión NUNCA comparten la misma instancia de proveedor.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any, Callable, Optional

from .models import now_iso


class StopToken:
    """Señal cooperativa de parada. Comprobable desde cualquier hilo."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason = ""
        self.set_at = ""

    def set(self, reason: str = "operator") -> None:
        self.reason = reason or "operator"
        self.set_at = now_iso()
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def clear(self) -> None:
        self.reason = ""
        self.set_at = ""
        self._event.clear()

    def raise_if_set(self) -> None:
        if self._event.is_set():
            raise InterruptedError(self.reason or "parada solicitada")


class RequestInbox:
    """Bandeja de peticiones que NUNCA rechaza por 'ocupado'.

    El HTTP handler solo encola (O(1)). Un único worker procesa en orden.
    Capacidad alta: si se llena, se descarta el más antiguo (nunca deadlock).
    """

    def __init__(self, maxsize: int = 200) -> None:
        self._q: queue.Queue = queue.Queue(maxsize=max(8, maxsize))
        self.accepted = 0
        self.dropped = 0
        self._lock = threading.Lock()

    def put(self, item: Any) -> tuple[bool, str]:
        with self._lock:
            self.accepted += 1
        try:
            self._q.put_nowait(item)
            return True, "queued"
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.task_done()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(item)
                with self._lock:
                    self.dropped += 1
                return True, "queued_after_drop"
            except queue.Full:
                return False, "inbox saturada"

    def get(self, timeout: float = 0.4) -> Any:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def task_done(self) -> None:
        try:
            self._q.task_done()
        except ValueError:
            pass

    def qsize(self) -> int:
        return self._q.qsize()

    def snapshot(self) -> dict[str, Any]:
        return {"queued": self.qsize(), "accepted": self.accepted,
                "dropped": self.dropped}


class JobSupervisor:
    """Trabajos laterales (buscar, crear) en paralelo a la misión y al chat."""

    MAX_JOBS = 4

    def __init__(self, publish: Optional[Callable[[dict[str, Any]], None]] = None):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._publish = publish

    def submit(self, kind: str, fn: Callable[..., Any],
               payload: Optional[dict[str, Any]] = None) -> tuple[bool, str]:
        token = StopToken()
        job_id = f"job-{uuid.uuid4().hex[:10]}"
        acquired = self._lock.acquire(timeout=1.0)
        if not acquired:
            return False, "supervisor ocupado (timeout de candado)"
        try:
            live = [j for j in self._jobs.values() if j["alive"]]
            if len(live) >= self.MAX_JOBS:
                return False, f"ya hay {len(live)} trabajos en curso"
            self._jobs[job_id] = {
                "id": job_id, "kind": kind, "alive": True,
                "started_at": now_iso(), "ended_at": "",
                "ok": None, "result": None, "error": "",
                "token": token, "payload": payload or {},
            }
        finally:
            self._lock.release()

        def worker() -> None:
            ok, result, error = False, None, ""
            try:
                result = fn(token)
                ok = True
            except InterruptedError as exc:
                error = str(exc) or "interrumpido"
            except Exception as exc:  # noqa: BLE001 — el supervisor no muere
                error = f"{type(exc).__name__}: {exc}"
            acquired_end = self._lock.acquire(timeout=2.0)
            try:
                rec = self._jobs.get(job_id)
                if rec is not None:
                    rec["alive"] = False
                    rec["ok"] = ok
                    rec["result"] = result
                    rec["error"] = error
                    rec["ended_at"] = now_iso()
            finally:
                if acquired_end:
                    self._lock.release()
            if self._publish:
                try:
                    self._publish({
                        "event": "job_done", "at": now_iso(),
                        "job_id": job_id, "kind": kind, "ok": ok,
                        "error": error,
                    })
                except Exception:
                    pass

        threading.Thread(target=worker, name=f"a2s-{kind}", daemon=True).start()
        if self._publish:
            try:
                self._publish({"event": "job_start", "at": now_iso(),
                               "job_id": job_id, "kind": kind})
            except Exception:
                pass
        return True, job_id

    def cancel_all(self, reason: str = "operator") -> int:
        acquired = self._lock.acquire(timeout=1.0)
        if not acquired:
            return 0
        try:
            tokens = [j["token"] for j in self._jobs.values() if j["alive"]]
        finally:
            self._lock.release()
        for token in tokens:
            token.set(reason)
        return len(tokens)

    def snapshot(self) -> list[dict[str, Any]]:
        acquired = self._lock.acquire(timeout=0.5)
        if not acquired:
            return []
        try:
            out = []
            for job in self._jobs.values():
                item = {k: v for k, v in job.items() if k != "token"}
                item["stopping"] = job["token"].is_set()
                out.append(item)
            return out
        finally:
            self._lock.release()


def acquire(lock: threading.Lock, timeout: float = 1.5) -> bool:
    """Adquiere un candado con tope: evita esperas infinitas."""
    return lock.acquire(timeout=max(0.05, timeout))


def sleep_cancellable(token: Optional[StopToken], seconds: float) -> bool:
    """Duerme a trozos. Devuelve True si se canceló."""
    if token is None:
        time.sleep(max(0.0, seconds))
        return False
    return token.wait(max(0.0, seconds))
