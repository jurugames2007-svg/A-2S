import time
import unittest

from a2s.media_orchestration import MediaExtractor, Task, TaskOrchestrator


class TestMediaExtractor(unittest.TestCase):
    def test_download_requires_rights(self):
        with self.assertRaises(PermissionError):
            MediaExtractor("downloads").download("https://example.test/video")

    def test_status_is_explicit_when_optional_dependency_missing_or_present(self):
        status = MediaExtractor("downloads").status()
        self.assertIn("available", status)
        self.assertTrue(status["download_requires_rights"])


class TestTaskOrchestrator(unittest.TestCase):
    def test_runs_tasks_and_preserves_errors(self):
        result = TaskOrchestrator(max_workers=2).run([
            Task("ok", lambda: 42),
            Task("bad", lambda: 1 / 0),
        ])
        self.assertEqual(result["results"]["ok"], 42)
        self.assertIn("bad", result["errors"])
        self.assertEqual(result["total"], 2)

    def test_timeout_is_bounded(self):
        result = TaskOrchestrator().run(
            [Task("slow", lambda: time.sleep(0.2))], timeout=0.01)
        self.assertIn("slow", result["errors"])

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            TaskOrchestrator().run([Task("same", lambda: 1), Task("same", lambda: 2)])


if __name__ == "__main__":
    unittest.main()