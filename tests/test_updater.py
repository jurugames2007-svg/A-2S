"""Contratos de ``a2s update``: actualización EN EL SITIO (fetch +
fast-forward) sin re-descargar el repositorio. Apelativo admitido: ``tkm``.

Las pruebas construyen un origen y un clon reales en directorios temporales;
se saltan si no hay ``git`` en el host.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from a2s import __version__, updater

_GIT = shutil.which("git")

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test A2S",
    "GIT_AUTHOR_EMAIL": "test@a2s.local",
    "GIT_COMMITTER_NAME": "Test A2S",
    "GIT_COMMITTER_EMAIL": "test@a2s.local",
}


def _git(cwd: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", cwd, *args], env=_ENV,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} falló: {proc.stderr}")
    return proc.stdout.strip()


@unittest.skipIf(_GIT is None, "git no está instalado en este host")
class TestUpdateEnElSitio(unittest.TestCase):
    def setUp(self):
        self.origin = tempfile.mkdtemp(prefix="a2s-origin-")
        self.checkout = tempfile.mkdtemp(prefix="a2s-checkout-")
        self.addCleanup(shutil.rmtree, self.origin, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.checkout, ignore_errors=True)

        _git(self.origin, "init", "-q")
        self._commit_origin("v1")
        subprocess.run(["git", "clone", "-q", self.origin, self.checkout],
                       env=_ENV, capture_output=True, timeout=120, check=True)
        self.branch = _git(self.origin, "rev-parse", "--abbrev-ref", "HEAD")

    def _commit_origin(self, contenido: str) -> None:
        with open(os.path.join(self.origin, "file.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(contenido)
        _git(self.origin, "add", "file.txt")
        _git(self.origin, "commit", "-q", "-m", f"origen {contenido}")

    def _contenido_checkout(self) -> str:
        with open(os.path.join(self.checkout, "file.txt"),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_detect_repo(self):
        info = updater.detect_repo(self.checkout)
        self.assertIsNotNone(info)
        self.assertEqual(info["branch"], self.branch)
        self.assertTrue(info["remote"])
        self.assertEqual(info["root"], os.path.abspath(self.checkout))

    def test_detect_no_repo(self):
        vacio = tempfile.mkdtemp(prefix="a2s-vacio-")
        self.addCleanup(shutil.rmtree, vacio, ignore_errors=True)
        self.assertIsNone(updater.detect_repo(vacio))

    def test_check_only_no_muta(self):
        self._commit_origin("v2")
        mensajes: list[str] = []
        rc = updater.update(root=self.checkout, check_only=True,
                            out=mensajes.append)
        self.assertEqual(rc, 0)
        self.assertEqual(self._contenido_checkout(), "v1")  # intacto
        self.assertIn("1 commit(s) nuevo(s)", "\n".join(mensajes))

    def test_update_fast_forward_y_alias_tkm(self):
        self._commit_origin("v2")
        mensajes: list[str] = []
        rc = updater.update(root=self.checkout, alias="tkm",
                            out=mensajes.append)
        texto = "\n".join(mensajes)
        self.assertEqual(rc, 0, texto)
        self.assertIn("tkm", texto)
        self.assertIn("actualizado en el sitio", texto)
        self.assertEqual(self._contenido_checkout(), "v2")

    def test_ya_actualizado_es_noop(self):
        mensajes: list[str] = []
        rc = updater.update(root=self.checkout, out=mensajes.append)
        self.assertEqual(rc, 0)
        self.assertIn("última versión", "\n".join(mensajes))

    def test_dirty_sin_force_no_toca(self):
        self._commit_origin("v2")
        ruta = os.path.join(self.checkout, "file.txt")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("cambio local")
        mensajes: list[str] = []
        rc = updater.update(root=self.checkout, out=mensajes.append)
        self.assertEqual(rc, 4)
        self.assertEqual(self._contenido_checkout(), "cambio local")
        self.assertIn("cambios locales", "\n".join(mensajes))

    def test_force_sincroniza_descartando_lo_local(self):
        self._commit_origin("v2")
        with open(os.path.join(self.checkout, "file.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("cambio local")
        mensajes: list[str] = []
        rc = updater.update(root=self.checkout, force=True,
                            out=mensajes.append)
        self.assertEqual(rc, 0, "\n".join(mensajes))
        self.assertEqual(self._contenido_checkout(), "v2")

    def test_directorio_sin_checkout(self):
        vacio = tempfile.mkdtemp(prefix="a2s-vacio-")
        self.addCleanup(shutil.rmtree, vacio, ignore_errors=True)
        mensajes: list[str] = []
        rc = updater.update(root=vacio, out=mensajes.append)
        self.assertEqual(rc, 3)
        self.assertIn("no es un checkout git", "\n".join(mensajes))

    def test_read_version_del_paquete_real(self):
        self.assertEqual(updater.read_version(updater.package_root()),
                         __version__)


if __name__ == "__main__":
    unittest.main()
