"""Compatibilidad entre plataformas: UTF-8 forzado en consolas cp1252 (Windows)
y localización de un shell POSIX (Git-Bash/MSYS2/WSL) para la mini-shell."""

import io
import os
import sys
import unittest
from unittest import mock

from a2s import _platform
from a2s._platform import find_posix_shell, force_utf8
from a2s.models import ToolCall
from a2s.tools import ToolRegistry


class TestForceUtf8(unittest.TestCase):
    def test_reconfigura_stdout_stderr_a_utf8(self):
        fake_out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        fake_err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with mock.patch.object(sys, "stdout", fake_out), \
             mock.patch.object(sys, "stderr", fake_err):
            # Reseteamos el guard de idempotencia para ejercer la ruta.
            with mock.patch.object(_platform, "_UTF8_DONE", False):
                force_utf8()
            self.assertEqual(fake_out.encoding.lower(), "utf-8")
            self.assertEqual(fake_err.encoding.lower(), "utf-8")
            # No debe lanzar aunque el símbolo no exista en cp1252.
            fake_out.write("✔ → · A²S")

    def test_es_idempotente(self):
        with mock.patch.object(_platform, "_UTF8_DONE", False):
            force_utf8()
            self.assertTrue(_platform._UTF8_DONE)
            force_utf8()  # no debe reconfigurar de nuevo ni fallar


class TestPosixShellDiscovery(unittest.TestCase):
    def setUp(self):
        # La caché del shell verificado es global por proceso.
        _platform._clear_shell_cache()
        self.addCleanup(_platform._clear_shell_cache)

    def test_no_windows_devuelve_none(self):
        with mock.patch.object(os, "name", "posix"):
            self.assertIsNone(find_posix_shell())

    def test_windows_sin_bash_devuelve_none(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(_platform.shutil, "which", return_value=None), \
             mock.patch.object(_platform.os.path, "isfile", return_value=False):
            self.assertIsNone(find_posix_shell())

    def test_windows_con_bash_en_path(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(_platform.shutil, "which",
                               return_value=r"C:\Git\bin\bash.exe"), \
             mock.patch.object(_platform, "_probe_shell", return_value=True):
            self.assertEqual(find_posix_shell(), r"C:\Git\bin\bash.exe")

    def test_bash_roto_se_descarta_y_pasa_al_siguiente(self):
        """Regresión v1.12: el lanzador de WSL sin distribución responde con
        exit != 0 a TODO comando; la sonda debe descartarlo y elegir un
        candidato funcional (p. ej. Git-Bash) en vez del primero que exista."""
        candidatos = [r"C:\Windows\System32\bash.exe",
                      r"C:\Git\bin\bash.exe"]
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(_platform, "_candidate_shells",
                               return_value=candidatos), \
             mock.patch.object(_platform, "_probe_shell",
                               side_effect=lambda p: p.endswith("Git\\bin\\bash.exe")):
            self.assertEqual(find_posix_shell(), r"C:\Git\bin\bash.exe")

    def test_todos_rotos_devuelve_none(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(_platform, "_candidate_shells",
                               return_value=[r"C:\roto\bash.exe"]), \
             mock.patch.object(_platform, "_probe_shell", return_value=False):
            self.assertIsNone(find_posix_shell())
            self.assertFalse(_platform.windows_has_posix_tools())

    def test_el_resultado_verificado_se_cachea(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(_platform, "_candidate_shells",
                               return_value=[r"C:\Git\bin\bash.exe"]), \
             mock.patch.object(_platform, "_probe_shell",
                               return_value=True) as probe:
            self.assertEqual(find_posix_shell(), r"C:\Git\bin\bash.exe")
            self.assertEqual(find_posix_shell(), r"C:\Git\bin\bash.exe")
            self.assertEqual(probe.call_count, 1)  # una sola sonda real

    def test_wsl_va_al_final_de_los_candidatos(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(_platform.shutil, "which", return_value=None):
            candidatos = _platform._candidate_shells()
        self.assertTrue(candidatos[-1].lower().endswith(
            os.path.join("system32", "bash.exe").lower()))


class TestShellOnWindows(unittest.TestCase):
    """En Windows la mini-shell delega en bash; si no hay bash, da un error
    de permiso claro en vez de FileNotFoundError (WinError 2)."""

    def test_sin_bash_da_error_limpio(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch("a2s.tools.find_posix_shell", return_value=None):
            reg = ToolRegistry(workspace=".", allow_network=False)
            obs = reg.invoke(ToolCall("shell", {"command": "echo hola"}))
            self.assertFalse(obs.ok)
            self.assertIn("POSIX", obs.error)

    def test_salida_no_utf8_no_pierde_el_resultado(self):
        """Regresión v1.12 (Windows): un hijo que emite bytes cp1252/cp850
        (mensajes localizados) no debe tumbar los hilos lectores ni dejar la
        salida vacía — la decodificación es UTF-8 con reemplazo."""
        code = ("import sys; sys.stdout.buffer.write(b'caf\\xf3 ok\\n'); "
                "sys.stdout.buffer.flush()")
        reg = ToolRegistry(workspace=".", allow_network=False, shell_unsafe=True)
        obs = reg.invoke(ToolCall("shell", {"command": f"{sys.executable} -c {code!r}"}))
        self.assertTrue(obs.ok, obs.error)
        self.assertIn("caf", obs.output)
        self.assertIn("ok", obs.output)

    def test_con_bash_ejecuta_el_segmento(self):
        fake_proc = mock.Mock()
        fake_proc.communicate.return_value = ("hola\r\n", "")
        fake_proc.returncode = 0
        with mock.patch.object(os, "name", "nt"), \
             mock.patch("a2s.tools.find_posix_shell",
                        return_value=r"C:\Git\bin\bash.exe"), \
             mock.patch("a2s.tools.subprocess.Popen",
                        return_value=fake_proc) as popen:
            reg = ToolRegistry(workspace=".", allow_network=False)
            obs = reg.invoke(ToolCall("shell", {"command": "echo hola"}))
            self.assertTrue(obs.ok, obs.error)
            args, kwargs = popen.call_args
            self.assertEqual(args[0][0], r"C:\Git\bin\bash.exe")
            self.assertEqual(args[0][1], "-c")
            self.assertIn("echo hola", args[0][2])
            self.assertEqual(kwargs.get("cwd"), reg.workspace)
            # Se cerraron los pipes al terminar.
            fake_proc.communicate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
