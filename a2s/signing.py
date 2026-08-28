"""Verificación criptográfica de resultados (HMAC-SHA256, solo stdlib).

Qué garantiza (y qué no, con honestidad):

* Cada workspace genera un secreto aleatorio (``.a2s/secret``, 0600) en su
  primer uso.
* Los resultados de ejecución y cada artefacto registrado se **firman** con
  HMAC-SHA256: ``firma = HMAC(secreto, payload canónico)``.
* ``a2s verify`` re-calcula y compara (``hmac.compare_digest``, sin timing
  leak). Una alteración posterior a la firma se detecta.

Qué NO garantiza:

* No demuestra que la tarea se hizo bien (eso es el verificador de misión).
* El secreto vive en el workspace: cualquiera con acceso de escritura al
  directorio puede re-firmar. Para no-repudio real, copia el secreto fuera
  del host o mueve la verificación a un servicio externo.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from typing import Any, Optional


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class Signer:
    """Firma y verifica payloads con el secreto del workspace."""

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)
        self._dir = os.path.join(self.workspace, ".a2s")
        os.makedirs(self._dir, exist_ok=True)
        self.secret_path = os.path.join(self._dir, "secret")
        self.secret = self._load_or_create_secret()

    def _load_or_create_secret(self) -> bytes:
        if os.path.exists(self.secret_path):
            with open(self.secret_path, "rb") as fh:
                return fh.read()
        secret = os.urandom(32)
        fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(secret)
        return secret

    def sign(self, payload: Any) -> str:
        """Firma un payload (dict/bytes/str) → hex."""
        data = payload if isinstance(payload, bytes) else _canonical(payload)
        return hmac.new(self.secret, data, hashlib.sha256).hexdigest()

    def sign_file(self, path: str) -> str:
        """HMAC del contenido binario de un archivo."""
        with open(path, "rb") as fh:
            return hmac.new(self.secret, fh.read(), hashlib.sha256).hexdigest()

    def verify(self, payload: Any, signature: str) -> bool:
        data = payload if isinstance(payload, bytes) else _canonical(payload)
        expected = hmac.new(self.secret, data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def verify_file(self, path: str, signature: str) -> bool:
        with open(path, "rb") as fh:
            data = fh.read()
        expected = hmac.new(self.secret, data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")


def report_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Payload canónico firmado de un informe (sin campos volátiles)."""
    return {
        "run_id": report.get("run_id"),
        "goal": report.get("goal"),
        "success": report.get("success"),
        "iterations": report.get("iterations"),
        "steps": report.get("steps"),
        "wall_seconds": report.get("wall_seconds"),
        "stagnation_events": report.get("stagnation_events"),
        "artifacts": sorted(report.get("artifacts") or []),
        "ended_at": report.get("ended_at"),
    }
