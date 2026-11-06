import unittest

from tests.site import Site, html
from web_crawler import Crawler


def paths(results):
    return sorted(urlpath(r.url) for r in results)


def urlpath(url):
    return "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"


def crawl(site, **kw):
    kw.setdefault("delay", 0)
    kw.setdefault("workers", 4)
    kw.setdefault("timeout", 5)
    return Crawler(site.base + "/", **kw).crawl()


class CrawlTests(unittest.TestCase):
    def test_follows_links_and_visits_each_page_once(self):
        routes = {
            "/": html("/a", "/b", "/a", "/a#frag", title="Home"),
            "/a": html("/", "/c", title="A"),   # links back: a cycle
            "/b": html("/c", "/b", title="B"),  # links to itself
            "/c": html(title="C"),
        }
        with Site(routes) as site:
            results = crawl(site, max_depth=5)
            self.assertEqual(paths(results), ["/", "/a", "/b", "/c"])
            for p in routes:
                self.assertEqual(site.count(p), 1, p)
        self.assertEqual({r.title for r in results}, {"Home", "A", "B", "C"})
        self.assertTrue(all(r.ok for r in results))

    def test_depth_limit(self):
        routes = {"/": html("/1"), "/1": html("/2"), "/2": html("/3"), "/3": html()}
        with Site(routes) as site:
            self.assertEqual(paths(crawl(site, max_depth=0)), ["/"])
            self.assertEqual(paths(crawl(site, max_depth=2)), ["/", "/1", "/2"])
            self.assertEqual(site.count("/3"), 0)

    def test_depth_is_reported(self):
        routes = {"/": html("/1"), "/1": html("/2"), "/2": html()}
        with Site(routes) as site:
            results = crawl(site, max_depth=5)
        self.assertEqual({urlpath(r.url): r.depth for r in results}, {"/": 0, "/1": 1, "/2": 2})

    def test_page_limit(self):
        routes = {"/": html(*[f"/p{i}" for i in range(20)])}
        routes.update({f"/p{i}": html() for i in range(20)})
        with Site(routes) as site:
            results = crawl(site, max_pages=5)
            self.assertEqual(len(results), 5)
            self.assertEqual(len(site.paths()) - site.count("/robots.txt"), 5)

    def test_robots_disallow_is_respected(self):
        routes = {
            "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private\n"),
            "/": html("/public", "/private/secret", "/private"),
            "/public": html(),
            "/private/secret": html(),
            "/private": html(),
        }
        with Site(routes) as site:
            results = crawl(site)
            self.assertNotIn("/private/secret", site.paths())
            self.assertNotIn("/private", site.paths())
            self.assertEqual(site.count("/robots.txt"), 1)
        blocked = sorted(urlpath(r.url) for r in results if r.status == -1)
        self.assertEqual(blocked, ["/private", "/private/secret"])
        self.assertEqual(paths([r for r in results if r.ok]), ["/", "/public"])

    def test_robots_can_be_ignored_for_own_sites(self):
        routes = {
            "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /\n"),
            "/": html("/a"),
            "/a": html(),
        }
        with Site(routes) as site:
            results = crawl(site, respect_robots=False)
            self.assertEqual(site.count("/robots.txt"), 0)
        self.assertEqual(paths(results), ["/", "/a"])

    def test_polite_delay_between_requests(self):
        routes = {"/": html("/a", "/b", "/c"), "/a": html(), "/b": html(), "/c": html()}
        with Site(routes) as site:
            crawl(site, delay=0.15, workers=4)
            times = sorted(t for _, t, _ in site.requests)
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertEqual(len(times), 5)  # robots.txt + 4 pages
        self.assertTrue(all(g >= 0.13 for g in gaps), gaps)

    def test_crawl_delay_from_robots_overrides_smaller_default(self):
        routes = {
            "/robots.txt": (200, "text/plain", "User-agent: *\nCrawl-delay: 1\n"),
            "/": html("/a"),
            "/a": html(),
        }
        with Site(routes) as site:
            crawl(site, delay=0)
            page_times = [t for p, t, _ in site.requests if p != "/robots.txt"]
        self.assertGreaterEqual(page_times[1] - page_times[0], 0.95)

    def test_workers_fetch_concurrently(self):
        routes = {"/": html(*[f"/p{i}" for i in range(8)])}
        routes.update({f"/p{i}": html() for i in range(8)})
        with Site(routes, latency=0.1) as site:
            crawl(site, workers=8)
            self.assertGreater(site.max_in_flight, 1)

    def test_single_worker_is_sequential(self):
        routes = {"/": html("/a", "/b"), "/a": html(), "/b": html()}
        with Site(routes, latency=0.02) as site:
            crawl(site, workers=1)
            self.assertEqual(site.max_in_flight, 1)

    def test_other_hosts_are_ignored_unless_allowed(self):
        with Site({"/ext": html(title="external")}) as external:
            routes = {"/": html(external.base + "/ext", "/internal"), "/internal": html()}
            with Site(routes) as site:
                results = crawl(site)
                self.assertEqual(paths(results), ["/", "/internal"])
                self.assertEqual(external.count("/ext"), 0)
                results = crawl(site, allowed_hosts={external.netloc})
                self.assertEqual(external.count("/ext"), 1)
                self.assertEqual(len(results), 3)

    def test_errors_do_not_stop_the_crawl(self):
        routes = {
            "/": html("/missing", "/boom", "/ok"),
            "/boom": (500, "text/html", "oops"),
            "/ok": html(),
        }
        with Site(routes) as site:
            results = crawl(site)
        by_path = {urlpath(r.url): r.status for r in results}
        self.assertEqual(by_path, {"/": 200, "/missing": 404, "/boom": 500, "/ok": 200})

    def test_non_html_is_recorded_but_not_parsed(self):
        routes = {
            "/": html("/data.json", "/doc.pdf"),
            "/data.json": (200, "application/json", '{"link": "<a href=\\"/hidden\\">"}'),
            "/doc.pdf": (200, "application/pdf", b"%PDF-1.4 <a href='/hidden'>"),
            "/hidden": html(),
        }
        with Site(routes) as site:
            results = crawl(site)
            self.assertNotIn("/hidden", site.paths())
        self.assertEqual(paths(results), ["/", "/data.json", "/doc.pdf"])

    def test_redirects_are_followed_and_deduplicated(self):
        routes = {
            "/": html("/old", "/new"),
            "/old": (301, "text/html", "", {"Location": "/new"}),
            "/new": html(title="New"),
        }
        with Site(routes) as site:
            results = crawl(site, workers=1)
            self.assertEqual(site.count("/new"), 2)  # once via the redirect, once directly; only one result is kept
        pages = [r for r in results if r.title == "New"]
        self.assertEqual(len(pages), 1)
        self.assertTrue(any(r.error and "already seen" in r.error for r in results))

    def test_user_agent_is_sent(self):
        with Site({"/": html()}) as site:
            crawl(site, user_agent="MyBot/9.9")
            self.assertTrue(all(ua == "MyBot/9.9" for _, _, ua in site.requests))

    def test_unreachable_start_url(self):
        with Site({}) as site:
            url = site.base + "/"
        results = Crawler(url, respect_robots=False, timeout=2).crawl()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 0)
        self.assertIsNotNone(results[0].error)

    def test_invalid_arguments(self):
        for kwargs in ({"start_url": "ftp://x"}, {"start_url": "http://x", "workers": 0},
                       {"start_url": "http://x", "max_pages": 0}):
            with self.assertRaises(ValueError):
                Crawler(**kwargs)

    def test_larger_site_terminates_with_many_workers(self):
        n = 60
        routes = {"/": html(*[f"/p{i}" for i in range(n)])}
        for i in range(n):
            routes[f"/p{i}"] = html(f"/p{(i + 1) % n}", f"/p{(i * 7) % n}", "/")
        with Site(routes) as site:
            results = crawl(site, workers=8, max_depth=10, max_pages=1000)
            for i in range(n):
                self.assertEqual(site.count(f"/p{i}"), 1)
        self.assertEqual(len(results), n + 1)


if __name__ == "__main__":
    unittest.main()
