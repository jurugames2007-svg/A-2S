"""Registro forense inmutable con cadena de custodia digital.

Implementa la directiva *"mantén registros inmutables de todas las actividades
para análisis post-mortem"* y *"preservación de cadena de custodia digital"*:

* ``ledger.jsonl`` — bitácora append-only donde cada entrada encadena el
  hash SHA-256 de la entrada anterior (hash chain). Cualquier alteración de
  una entrada rompe toda la cadena posterior y es detectable con
  ``verify()``.
* ``journal.sqlite`` — índice relacional para consultas forenses rápidas.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from typing import Any, Iterator, Optional

from .models import now_iso


class Ledger:
    """Bitácora forense append-only con hash chain y verificación de integridad."""

    def __init__(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        self.directory = directory
        self.path = os.path.join(directory, "ledger.jsonl")
        self.db_path = os.path.join(directory, "journal.sqlite")
        self._lock = threading.Lock()
        self._init_db()

    # -- persistencia ------------------------------------------------------
    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as con:
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
            with sqlite3.connect(self.db_path) as con:
                con.execute(
                    "INSERT INTO journal (ts, event, payload, prev_hash, hash) VALUES (?,?,?,?,?)",
                    (ts, event, json.dumps(payload, ensure_ascii=False), prev_hash, record["hash"]),
                )
            return record

    # -- lectura y verificación ---------------------------------------------
    def entries(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _last_hash(self) -> Optional[str]:
        entries = self.entries()
        return entries[-1]["hash"] if entries else None

    @staticmethod
    def _hash_of(record: dict[str, Any]) -> str:
        canon = json.dumps(
            {k: record[k] for k in ("ts", "event", "payload", "prev_hash")},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

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
        return True, "cadena de custodia íntegra", len(entries)

    def query(self, event: Optional[str] = None, limit: int = 100) -> Iterator[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as con:
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
