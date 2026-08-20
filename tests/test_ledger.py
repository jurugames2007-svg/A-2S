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

    def test_query(self):
        self.ledger.append("paso", {"n": 1})
        self.ledger.append("paso", {"n": 2})
        rows = list(self.ledger.query(event="paso"))
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
