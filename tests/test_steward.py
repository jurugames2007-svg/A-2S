"""Mayordomo, bóveda, hardware, consejo, horizonte y programas locales."""

import os
import unittest

from a2s.codegen import generate_program
from a2s.counsel import advise, DISCLAIMER
from a2s.hardware import diagnose
from a2s.horizon import brief
from a2s.intent import classify_intent
from a2s.macros import run_macro
from a2s.steward import (apply_moves, cleanup, is_protected, plan_organize,
                         rename_file, run_steward, undo_last)
from a2s.studio import classify_job, produce
from a2s.vault import handle
from tests._winutil import temp_dir


class TestIntentSteward(unittest.TestCase):
    def test_rutas_especiales(self):
        self.assertEqual(classify_intent("ordena el escritorio").kind, "steward")
        self.assertEqual(classify_intent("genera un programa de listas").kind, "codegen")
        self.assertEqual(classify_intent("necesito un abogado para un contrato").kind, "counsel")
        self.assertEqual(classify_intent("me duele el pecho y tengo fiebre").kind, "counsel")
        self.assertEqual(classify_intent("busca empleo en Ñuble").kind, "horizon")
        self.assertEqual(classify_intent("ayúdame con la BIOS").kind, "hardware")
        self.assertEqual(classify_intent("genera una wallet").kind, "vault")
        self.assertEqual(classify_intent("Crea un libro sobre El Principito").kind, "create")


class TestStewardFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)
        self.ws = self.tmp.name
        with open(os.path.join(self.ws, "foto.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
        os.makedirs(os.path.join(self.ws, ".a2s"))
        with open(os.path.join(self.ws, ".a2s", "secret.txt"), "w") as fh:
            fh.write("no tocar")
        with open(os.path.join(self.ws, "contrato-alquiler.txt"), "w") as fh:
            fh.write("importante")
        with open(os.path.join(self.ws, "basura.tmp"), "w") as fh:
            fh.write("x")

    def test_protege_y_ordena(self):
        self.assertTrue(is_protected(".a2s/secret.txt"))
        self.assertTrue(is_protected("contrato-alquiler.txt"))
        moves = plan_organize(self.ws)
        srcs = [m["from"] for m in moves]
        self.assertIn("foto.png", srcs)
        self.assertNotIn("contrato-alquiler.txt", srcs)
        result = apply_moves(self.ws, moves)
        self.assertGreaterEqual(result["moved"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "media", "images", "foto.png")))
        undo = undo_last(self.ws)
        self.assertGreaterEqual(undo["restored"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "foto.png")))

    def test_cleanup_no_borra_importante(self):
        preview = cleanup(self.ws, apply=False)
        self.assertIn("basura.tmp", preview["candidates"])
        done = cleanup(self.ws, apply=True)
        self.assertFalse(os.path.isfile(os.path.join(self.ws, "basura.tmp")))
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "contrato-alquiler.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.ws, ".a2s", "secret.txt")))
        self.assertGreaterEqual(len(done["deleted"]), 1)

    def test_rename_y_desktop(self):
        with open(os.path.join(self.ws, "nota.txt"), "w") as fh:
            fh.write("hola")
        renamed = rename_file(self.ws, "nota.txt", "nota limpia.txt")
        self.assertTrue(os.path.isfile(os.path.join(self.ws, renamed["to"])))
        desk = run_steward(self.ws, "personaliza y anima iconos")
        self.assertEqual(desk["status"], "desktop_virtual")
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "desktop", "desktop.html")))


class TestVaultHardwareCounsel(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)

    def test_wallet_rechazada(self):
        got = handle(self.tmp.name, "genera una wallet")
        self.assertEqual(got["status"], "wallet_refused")
        self.assertFalse(got["generated_keys"])
        with open(os.path.join(self.tmp.name, "vault", "policy.md"), encoding="utf-8") as fh:
            self.assertIn("No genero wallets", fh.read())

    def test_bios_flash_rechazado(self):
        got = diagnose(self.tmp.name, "flashear la BIOS")
        self.assertEqual(got["status"], "refused_hardware_write")
        self.assertFalse(got["writes_firmware"])

    def test_counsel_disclaimer(self):
        got = advise(self.tmp.name, "necesito un abogado para un contrato")
        self.assertEqual(got["domain"], "legal")
        self.assertTrue(got["disclaimer"])
        with open(os.path.join(self.tmp.name, "counsel", "legal.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(DISCLAIMER[:20], text)

    def test_horizon_no_suplanta(self):
        got = brief(self.tmp.name, "busca empleo")
        self.assertFalse(got["impersonates"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "opportunities", "brief.md")))

    def test_programa_local(self):
        got = generate_program(self.tmp.name, "numerar lineas")
        main = os.path.join(self.tmp.name, got["artifacts"][0])
        self.assertTrue(os.path.isfile(main))
        with open(main, encoding="utf-8") as fh:
            self.assertIn("stdlib", fh.read().lower())

    def test_produce_enruta(self):
        self.assertEqual(classify_job("ordena archivos", {"kind": "steward"}), "steward")
        result = produce(self.tmp.name, "política de wallets", {"kind": "vault"})
        self.assertEqual(result["status"], "wallet_refused")

    def test_macro_ordenar(self):
        with open(os.path.join(self.tmp.name, "x.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n00")
        result = run_macro(self.tmp.name, "ordenar_workspace")
        self.assertEqual(result["status"], "macro_done")


if __name__ == "__main__":
    unittest.main()
