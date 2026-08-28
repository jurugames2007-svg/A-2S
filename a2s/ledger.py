"""Registro forense inmutable con cadena de custodia digital.

Implementa la directiva *"mantén registros inmutables de todas las actividades
para análisis post-mortem"* y *"preservación de cadena de custodia digital"*:

* ``ledger.jsonl`` — bitácora append-only donde cada entrada encadena el
  hash SHA-256 de la entrada anterior (hash chain).
* ``journal.sqlite`` — índice relacional para consultas forenses rápidas.

``verify()`` detecta dos tipos de manipulación:

1. **Modificación** de cualquier entrada (rompe la hash chain).
2. **Truncación** de la cola (el índice SQLite registra más entradas que el
   JSONL → recuento divergente).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading
from typing import Any, Iterator, Optional

from .models import now_iso


@contextlib.contextmanager
def _connect(path: str, timeout: float = 10.0) -> Iterator[sqlite3.Connection]:
    """Conexión SQLite que se CIERRA al salir (el context-manager nativo solo
    gestiona la transacción). Imprescindible en Windows: un manejador abierto
    bloquea el borrado del directorio temporal (WinError 32)."""
    con = sqlite3.connect(path, timeout=timeout)
    try:
        with con:  # commit/rollback de la transacción
            yield con
    finally:
        con.close()


class Ledger:
    """Bitácora forense append-only con hash chain y verificación de integridad."""

    def __init__(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        self.directory = directory
        self.path = os.path.join(directory, "ledger.jsonl")
        self.db_path = os.path.join(directory, "journal.sqlite")
        self._lock = threading.Lock()
        self._last_hash_cache: Optional[str] = None
        self._init_db()

    # -- persistencia ------------------------------------------------------
    def _init_db(self) -> None:
        with _connect(self.db_path, timeout=30) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(
                """CREATE TABLE IF NOT EXISTS journal (
                       seq INTEGER PRIMARY KEY AUTOINCREMENT,
                       ts TEXT NOT NULL,
                       event TEXT NOT NULL,
                       payload TEXT NOT NULL,
                       prev_hash TEXT,
                       hash TEXT UNIQUE)"""
            )

    def append(self, event: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Añade una entrada inmutable. Devuelve el registro completo."""
        payload = dict(payload or {})
        ts = now_iso()
        with self._lock:
            prev_hash = self._last_hash()
            record = {
                "ts": ts,
                "event": event,
                "payload": payload,
                "prev_hash": prev_hash,
            }
            record["hash"] = self._hash_of(record)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._last_hash_cache = record["hash"]
            try:  # el JSONL es la fuente de verdad; un fallo del índice no rompe el loop
                with _connect(self.db_path, timeout=30) as con:
                    con.execute(
                        "INSERT INTO journal (ts, event, payload, prev_hash, hash) VALUES (?,?,?,?,?)",
                        (ts, event, json.dumps(payload, ensure_ascii=False),
                         prev_hash, record["hash"]),
                    )
            except Exception:  # noqa: BLE001 — concurrencia o disco: tolerar
                pass
            return record

    # -- lectura y verificación ---------------------------------------------
    def entries(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _last_hash(self) -> Optional[str]:
        # Caché: sin esto cada append releería el archivo completo (O(n²)).
        if self._last_hash_cache is None:
            entries = self.entries()
            self._last_hash_cache = entries[-1]["hash"] if entries else None
        return self._last_hash_cache

    @staticmethod
    def _hash_of(record: dict[str, Any]) -> str:
        canon = json.dumps(
            {k: record[k] for k in ("ts", "event", "payload", "prev_hash")},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def _journal_count(self) -> Optional[int]:
        try:
            with _connect(self.db_path, timeout=10) as con:
                return con.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        except Exception:  # noqa: BLE001
            return None

    def verify(self) -> tuple[bool, str, int]:
        """Verifica la cadena de custodia. Devuelve (ok, mensaje, nº entradas)."""
        entries = self.entries()
        prev: Optional[str] = None
        for i, rec in enumerate(entries):
            if rec.get("prev_hash") != prev:
                return False, f"rotura de encadenamiento en la entrada {i}", len(entries)
            if rec.get("hash") != self._hash_of(rec):
                return False, f"hash no coincide en la entrada {i}", len(entries)
            prev = rec["hash"]
        count = self._journal_count()
        if count is not None and count != len(entries):
            return False, (f"posible truncación: el JSONL tiene {len(entries)} "
                           f"entradas pero el índice registra {count}"), len(entries)
        return True, "cadena de custodia íntegra", len(entries)

    def query(self, event: Optional[str] = None, limit: int = 100) -> Iterator[dict[str, Any]]:
        with _connect(self.db_path, timeout=10) as con:
            con.row_factory = sqlite3.Row
            if event:
                rows = con.execute(
                    "SELECT * FROM journal WHERE event=? ORDER BY seq DESC LIMIT ?",
                    (event, limit),
                )
            else:
                rows = con.execute("SELECT * FROM journal ORDER BY seq DESC LIMIT ?", (limit,))
            for row in rows:
                yield dict(row)
