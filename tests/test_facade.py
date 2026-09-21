import unittest
from urllib.parse import urlsplit

from ldoce5viewer.facade import SearchResult, ViewerFacade


class SearchResultTests(unittest.TestCase):
    def test_plain_label_strips_ldoce_markup(self):
        result = SearchResult(
            "<h>abandon</h>",
            "/fs/example",
            "abandon",
            1,
        )
        self.assertEqual(result.plain_label, "abandon")

    def test_dict_uri_is_canonical(self):
        self.assertEqual(
            SearchResult("word", "fs/example", "word", 1).uri,
            "dict:///fs/example",
        )
        self.assertEqual(
            SearchResult("word", "/fs/example", "word", 1).uri,
            "dict:///fs/example",
        )


class FacadeUriTests(unittest.TestCase):
    def test_uri_path_accepts_three_slash_form(self):
        parsed = urlsplit("dict:///fs/example")
        self.assertEqual(ViewerFacade._uri_path(parsed), "/fs/example")

    def test_uri_path_recovers_two_slash_form(self):
        parsed = urlsplit("dict://fs/example")
        self.assertEqual(ViewerFacade._uri_path(parsed), "/fs/example")

    def test_lookup_query_decodes_query(self):
        self.assertEqual(
            ViewerFacade.lookup_query("lookup:///?q=ice+cream"),
            "ice cream",
        )

    def test_non_lookup_uri_has_no_lookup_query(self):
        self.assertIsNone(ViewerFacade.lookup_query("dict:///fs/example"))


if __name__ == "__main__":
    unittest.main()
