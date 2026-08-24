"""PCB, colas de planificación y catálogo de 1000 mejoras aplicadas."""

import json
import os
import unittest

from a2s.catalog import CATALOG_SIZE, apply_all, build_catalog
from a2s.intent import classify_intent
from a2s.kernel import Kernel
from a2s.pcb import ProcessTable
from tests._winutil import temp_dir


class TestCatalog(unittest.TestCase):
    def test_son_1000_unicas(self):
        items = build_catalog()
        self.assertEqual(len(items), CATALOG_SIZE)
        self.assertEqual(len({i["id"] for i in items}), CATALOG_SIZE)
        self.assertEqual(len({i["policy"] for i in items}), CATALOG_SIZE)
        self.assertEqual(items[0]["id"], "IMP-0001")
        self.assertEqual(items[-1]["id"], "IMP-1000")

    def test_apply_all_idempotente(self):
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        first = apply_all(tmp.name)
        second = apply_all(tmp.name)
        self.assertEqual(first["applied"], 1000)
        self.assertTrue(all(i["applied"] for i in first["items"]))
        self.assertEqual(second["applied"], 1000)
        marker = os.path.join(tmp.name, ".a2s", "pcb", "APPLIED")
        self.assertTrue(os.path.isfile(marker))
        with open(os.path.join(tmp.name, ".a2s", "pcb", "CATALOG.md"),
                  encoding="utf-8") as fh:
            self.assertIn("IMP-1000", fh.read())


class TestPCBQueues(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir()
        self.addCleanup(self.tmp.cleanup)
        self.k = Kernel.open(self.tmp.name)

    def test_admit_checkpoint_park_resume(self):
        pcb = self.k.admit("escribir informe", kind="mission")
        self.assertEqual(pcb.state, "ready")
        self.assertEqual(self.k.applied, 1000)
        self.k.dispatch(pcb.pid)
        self.k.checkpoint(pcb.pid, pc=7, registers={"step": "s2"})
        self.k.park(pcb.pid, "interrupt")
        again = Kernel.open(self.tmp.name)
        loaded = again.table.get(pcb.pid)
        self.assertEqual(loaded.state, "parked")
        self.assertEqual(loaded.pc, 7)
        self.assertEqual(loaded.registers.get("step"), "s2")
        restored = again.resume(pcb.pid)
        self.assertEqual(restored.state, "ready")

    def test_dedup_y_backpressure(self):
        a = self.k.admit("mismo objetivo", kind="mission")
        b = self.k.admit("mismo objetivo", kind="mission")
        self.assertEqual(a.pid, b.pid)
        table = ProcessTable(self.tmp.name)
        for i in range(8):
            table.admit(f"extra-{i}", kind="chat")
        snap = self.k.snapshot()
        self.assertGreaterEqual(snap["total"], 1)

    def test_deadlock_roto(self):
        a = self.k.admit("A", kind="mission")
        b = self.k.admit("B", kind="mission")
        self.k.block(a.pid, f"pcb:{b.pid}")
        self.k.block(b.pid, f"pcb:{a.pid}")
        cycles = self.k.detect_deadlock()
        self.assertTrue(cycles)
        n = self.k.break_deadlock()
        self.assertGreaterEqual(n, 1)
        states = {self.k.table.get(a.pid).state, self.k.table.get(b.pid).state}
        self.assertIn("ready", states)

    def test_mlfq_chat_antes_que_batch(self):
        batch = self.k.admit("estudio largo", kind="growth")
        chat = self.k.admit("hola estado", kind="chat")
        picked = self.k.pick()
        self.assertEqual(picked.pid, chat.pid)
        self.assertEqual(batch.queue, "Q3")
        self.assertEqual(chat.queue, "Q0")

    def test_drain_handler(self):
        seen = []

        def handler(pcb):
            seen.append(pcb.goal)
            return {"status": "ok", "echo": pcb.goal}

        self.k.register("codegen", handler)
        self.k.admit("numerar", kind="codegen")
        out = self.k.drain(max_jobs=3)
        self.assertEqual(len(seen), 1)
        self.assertEqual(out[0]["status"], "ok")
        self.assertEqual(self.k.table.by_state("completed")[0].goal, "numerar")

    def test_cli_y_intent(self):
        self.assertEqual(classify_intent("reanuda las colas").kind, "resume")
        self.assertEqual(classify_intent("pcb").kind, "resume")
        from a2s.cli import main
        rc = main(["pcb", "status", "--workspace", self.tmp.name])
        self.assertEqual(rc, 0)
        rc = main(["pcb", "catalog", "--workspace", self.tmp.name])
        self.assertEqual(rc, 0)

    def test_journal_sobrevive(self):
        pcb = self.k.admit("persistir", kind="mission")
        self.k.park(pcb.pid, "cut")
        path = os.path.join(self.tmp.name, ".a2s", "pcb", "journal.jsonl")
        with open(path, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        events = {row["event"] for row in lines}
        self.assertIn("admit", events)
        self.assertIn("state:parked", events)


if __name__ == "__main__":
    unittest.main()
