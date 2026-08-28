import json
import unittest
from unittest import mock

from a2s.web_integrations import BookToSkill, SEOAuditor, WebCrawler


class TestWebIntegrations(unittest.TestCase):
    def test_fetch_extracts_text_links_and_headers(self):
        response = mock.MagicMock()
        response.status = 200
        response.geturl.return_value = "https://example.test/"
        response.headers.items.return_value = [("Content-Security-Policy", "self")]
        response.read.return_value = (
            b"<html><title>Demo</title><script>secret</script>"
            b"<body>Texto <a href='/next'>siguiente</a></body></html>")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch("a2s.web_integrations.urllib.request.urlopen", return_value=response):
            page = WebCrawler(allow_hosts=["example.test"]).fetch("https://example.test/")
        self.assertEqual(page.title, "Demo")
        self.assertIn("Texto", page.text)
        self.assertNotIn("secret", page.text)
        self.assertEqual(page.links, ["https://example.test/next"])
        self.assertTrue(SEOAuditor().audit(page)["security_headers"]["content_security_policy"])

    def test_crawler_rejects_non_https_and_unknown_host(self):
        crawler = WebCrawler(allow_hosts=["example.test"])
        with self.assertRaises(PermissionError):
            crawler.fetch("http://example.test/")
        with self.assertRaises(PermissionError):
            crawler.fetch("https://other.test/")

    def test_book_to_skill_converts_and_queries_operator_text(self):
        skill = BookToSkill().convert("Python procesa datos y Python automatiza tareas", "python")
        self.assertEqual(skill["source"], "operator-provided")
        self.assertIn("Python", BookToSkill().query(skill, "Python")[0])
        json.dumps(skill)


if __name__ == "__main__":
    unittest.main()