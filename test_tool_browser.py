import unittest
from unittest.mock import patch

from tools.tool_browser import run_browser_command


class TestBrowserCommand(unittest.TestCase):
    @patch("tools.tool_browser.archive_web_page_to_vault")
    @patch("tools.tool_browser.web_search_structured")
    def test_keyword_search_archives_first_result_url(self, mock_search, mock_archive):
        mock_search.return_value = (
            "formatted search context",
            [{"title": "Example result", "url": "https://example.com/article"}],
        )
        mock_archive.return_value = {
            "success": True,
            "title": "Example article",
            "url": "https://example.com/article",
            "filename": "Web - Example article.md",
            "preview": "Article preview",
        }

        result = run_browser_command("latest AI research")

        mock_search.assert_called_once_with("latest AI research", deep_read=False)
        mock_archive.assert_called_once_with("https://example.com/article")
        self.assertIn("Example article", result)

    @patch("tools.tool_browser.archive_web_page_to_vault")
    @patch("tools.tool_browser.web_search_structured")
    def test_keyword_search_with_no_results_does_not_archive(self, mock_search, mock_archive):
        mock_search.return_value = ("No results", [])

        result = run_browser_command("latest AI research")

        self.assertIn("Tidak dapat menemukan halaman web", result)
        mock_archive.assert_not_called()

    @patch("tools.tool_browser.archive_web_page_to_vault")
    @patch("tools.tool_browser.web_search_structured")
    def test_direct_url_skips_search(self, mock_search, mock_archive):
        mock_archive.return_value = {
            "success": True,
            "title": "Example",
            "url": "https://example.com",
            "filename": "Web - Example.md",
            "preview": "Preview",
        }

        result = run_browser_command("https://example.com")

        mock_search.assert_not_called()
        mock_archive.assert_called_once_with("https://example.com")
        self.assertIn("Halaman web berhasil", result)

    @patch("tools.tool_browser.archive_web_page_to_vault")
    @patch("tools.tool_browser.web_search_structured")
    def test_keyword_search_rejects_result_without_url(self, mock_search, mock_archive):
        mock_search.return_value = ("formatted search context", [{"title": "No URL"}])

        result = run_browser_command("latest AI research")

        self.assertIn("tidak memiliki URL yang valid", result)
        mock_archive.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
