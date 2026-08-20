"""Pruebas de la bitácora forense (hash chain + verificación)."""

import json
import os
import tempfile
import unittest

from a2s.ledger import Ledger


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.ledger = Ledger(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_verify(self):
        self.ledger.append("evento_a", {"x": 1})
        self.ledger.append("evento_b", {"y": 2})
        ok, msg, n = self.ledger.verify()
        self.assertTrue(ok, msg)
        self.assertEqual(n, 2)

    def test_tamper_detection(self):
        self.ledger.append("evento_a", {"x": 1})
        self.ledger.append("evento_b", {"y": 2})
        with open(self.ledger.path) as fh:
            lines = fh.readlines()
        rec = json.loads(lines[0])
        rec["payload"]["x"] = 999
        lines[0] = json.dumps(rec) + "\n"
        with open(self.ledger.path, "w") as fh:
            fh.writelines(lines)
        ok, msg, _ = self.ledger.verify()
        self.assertFalse(ok)
        self.assertIn("entrada 0", msg)

    def test_truncation_detection(self):
        """Borrar entradas de la cola debe detectarse (regresión v1.1.1)."""
        self.ledger.append("a", {"x": 1})
        self.ledger.append("b", {"x": 2})
        self.ledger.append("c", {"x": 3})
        with open(self.ledger.path) as fh:
            lines = fh.readlines()
        with open(self.ledger.path, "w") as fh:
            fh.writelines(lines[:2])  # elimina la última entrada
        ok, msg, _ = self.ledger.verify()
        self.assertFalse(ok)
        self.assertIn("truncación", msg)

    def test_append_cache(self):
        """El append no debe releer el archivo completo (regresión O(n²))."""
        for i in range(60):
            self.ledger.append("e", {"i": i})
        self.assertEqual(self.ledger._last_hash(), self.ledger.entries()[-1]["hash"])
        ok, msg, _ = self.ledger.verify()
        self.assertTrue(ok, msg)

    def test_query(self):
        self.ledger.append("paso", {"n": 1})
        self.ledger.append("paso", {"n": 2})
        rows = list(self.ledger.query(event="paso"))
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
