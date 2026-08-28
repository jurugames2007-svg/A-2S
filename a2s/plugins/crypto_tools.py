"""Plugin: herramientas criptográficas para evidencia (stdlib puro).

* ``sha256_file`` — hash SHA-256 de un archivo del workspace.
* ``sign_content`` — firma HMAC-SHA256 de contenido con el secreto del
  workspace (verificación criptográfica de resultados).
* ``verify_content`` — comprueba una firma HMAC (compare_digest).

Los resultados firmados por estas herramientas son verificables con
``a2s verify`` y quedan ligados a la cadena de custodia.
"""

import hashlib
import hmac
import os

PLUGIN = {
    "name": "crypto_tools",
    "version": "1.0.0",
    "description": "Hashes y firmas HMAC para evidencia digital",
    "tags": ["firma", "hash", "hmac", "criptografia", "integridad", "verificar",
            "evidencia", "forense"],
    "tools": [
        {"name": "sha256_file", "description": "Calcula el SHA-256 de un archivo del workspace.",
         "params": {"path": "str"}},
        {"name": "sign_content", "description": "Firma contenido con HMAC-SHA256 (secreto del workspace).",
         "params": {"content": "str"}},
        {"name": "verify_content", "description": "Verifica una firma HMAC-SHA256 de contenido.",
         "params": {"content": "str", "signature": "str hex"}},
    ],
}


def register(registry, ctx):
    from a2s.tools import Tool
    signer = ctx.get("signer")

    def f_sha256(path):
        full = registry._resolve(path)
        if not registry._inside_workspace(full) or not os.path.isfile(full):
            raise PermissionError("archivo fuera del workspace o inexistente")
        with open(full, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        return f"{digest}  {path}"

    def f_sign(content):
        if signer is None:
            raise PermissionError("firma no disponible sin secreto del workspace")
        return f"firma HMAC: {signer.sign(content)}"

    def f_verify(content, signature):
        if signer is None:
            raise PermissionError("verificación no disponible sin secreto del workspace")
        ok = signer.verify(content, signature)
        return f"firma {'VÁLIDA' if ok else 'INVÁLIDA'}"

    registry.register(Tool("sha256_file", PLUGIN["tools"][0]["description"],
                           PLUGIN["tools"][0]["params"], f_sha256))
    registry.register(Tool("sign_content", PLUGIN["tools"][1]["description"],
                           PLUGIN["tools"][1]["params"], f_sign))
    registry.register(Tool("verify_content", PLUGIN["tools"][2]["description"],
                           PLUGIN["tools"][2]["params"], f_verify))
