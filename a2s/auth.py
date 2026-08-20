"""Tokens de acceso estilo JWT (HS256) con expiración — stdlib puro.

Formato: ``base64url(header).base64url(payload).hex(hmac)``, firmados con el
secreto del workspace (mismo secreto que usa ``signing.Signer``, así un único
material de claves por workspace).

Límites honestos: sin TLS, el token viaja en claro por redes no confiables;
la expiración mitiga el robo pero no lo elimina.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

from .signing import Signer


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


class TokenManager:
    def __init__(self, signer: Signer):
        self.signer = signer

    def issue(self, scope: str = "dashboard", hours: float = 1.0,
              extra: Optional[dict[str, Any]] = None) -> str:
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"iat": now, "exp": now + int(hours * 3600), "scope": scope,
                   **(extra or {})}
        signing_input = f"{_b64e(json.dumps(header, separators=(',', ':')).encode())}" \
                        f".{_b64e(json.dumps(payload, separators=(',', ':')).encode())}"
        sig = hmac.new(self.signer.secret, signing_input.encode(),
                       hashlib.sha256).hexdigest()
        return f"{signing_input}.{sig}"

    def verify(self, token: Optional[str], scope: Optional[str] = None
               ) -> tuple[bool, Any]:
        """Devuelve (ok, payload|motivo). Comparación en tiempo constante."""
        if not token or token.count(".") != 2:
            return False, "token malformado"
        signing_input, sig = token.rsplit(".", 1)
        expected = hmac.new(self.signer.secret, signing_input.encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig or ""):
            return False, "firma inválida"
        try:
            _h, p = signing_input.split(".", 1)
            payload = json.loads(_b64d(p))
        except Exception:  # noqa: BLE001
            return False, "payload ilegible"
        if int(payload.get("exp", 0)) < int(time.time()):
            return False, "token expirado"
        if scope and payload.get("scope") != scope:
            return False, f"ámbito incorrecto (se esperaba '{scope}')"
        return True, payload


def workspace_token_manager(workspace: str) -> TokenManager:
    return TokenManager(Signer(workspace))
