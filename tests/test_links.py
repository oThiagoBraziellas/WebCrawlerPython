import unittest

from web_crawler import extract_links, normalize_url
from web_crawler.links import parse_page


class NormalizeTests(unittest.TestCase):
    def test_equivalent_urls_collapse(self):
        base = normalize_url("http://example.com/a")
        for variant in ["HTTP://EXAMPLE.com/a", "http://example.com:80/a", "http://example.com/a#section"]:
            self.assertEqual(normalize_url(variant), base)

    def test_empty_path_becomes_slash(self):
        self.assertEqual(normalize_url("https://example.com"), "https://example.com/")

    def test_non_default_port_and_query_kept(self):
        self.assertEqual(normalize_url("http://example.com:8080/a?x=1&y=2"), "http://example.com:8080/a?x=1&y=2")
        self.assertEqual(normalize_url("https://example.com:443/"), "https://example.com/")

    def test_rejects_other_schemes_and_junk(self):
        for bad in ["mailto:a@b.c", "javascript:void(0)", "ftp://example.com/", "", "/relative", "http://", "http://u:p@h/"]:
            self.assertIsNone(normalize_url(bad), bad)


class ExtractTests(unittest.TestCase):
    PAGE = "http://example.com/dir/page.html"

    def test_relative_resolution(self):
        html = '<a href="other.html">1</a><a href="/root">2</a><a href="../up">3</a><a href="//cdn.example.com/x">4</a>'
        self.assertEqual(
            extract_links(html, self.PAGE),
            [
                "http://example.com/dir/other.html",
                "http://example.com/root",
                "http://example.com/up",
                "http://cdn.example.com/x",
            ],
        )

    def test_dedup_and_fragment_and_non_http(self):
        html = '<a href="/a">1</a><a href="/a#x">2</a><a href="mailto:x@y.z">3</a><a href="javascript:f()">4</a><a>5</a>'
        self.assertEqual(extract_links(html, self.PAGE), ["http://example.com/a"])

    def test_base_href(self):
        html = '<base href="http://other.example/base/"><a href="x">1</a>'
        self.assertEqual(extract_links(html, self.PAGE), ["http://other.example/base/x"])

    def test_nofollow_link_and_meta(self):
        self.assertEqual(extract_links('<a rel="nofollow" href="/a">1</a><a href="/b">2</a>', self.PAGE),
                         ["http://example.com/b"])
        self.assertEqual(extract_links('<meta name="robots" content="noindex, nofollow"><a href="/b">2</a>', self.PAGE), [])

    def test_title_and_broken_html(self):
        title, links = parse_page("<title>  Hello \n World </title><a href='/x'>unclosed <b>", self.PAGE)
        self.assertEqual(title, "Hello World")
        self.assertEqual(links, ["http://example.com/x"])


if __name__ == "__main__":
    unittest.main()
