import unittest

from tests.site import Site, html
from web_crawler import HostRateLimiter, RobotsCache


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class RateLimiterTests(unittest.TestCase):
    def test_spaces_requests_per_host(self):
        t = FakeTime()
        limiter = HostRateLimiter(clock=t.clock, sleep=t.sleep)
        self.assertEqual(limiter.wait("a", 1.0), 0)  # first request is immediate
        self.assertEqual(limiter.wait("a", 1.0), 1.0)
        self.assertEqual(limiter.wait("a", 1.0), 1.0)
        self.assertEqual(t.now, 2.0)

    def test_hosts_are_independent(self):
        t = FakeTime()
        limiter = HostRateLimiter(clock=t.clock, sleep=t.sleep)
        limiter.wait("a", 5)
        self.assertEqual(limiter.wait("b", 5), 0)

    def test_idle_time_counts(self):
        t = FakeTime()
        limiter = HostRateLimiter(clock=t.clock, sleep=t.sleep)
        limiter.wait("a", 2)
        t.now += 10
        self.assertEqual(limiter.wait("a", 2), 0)

    def test_zero_delay_never_sleeps(self):
        t = FakeTime()
        limiter = HostRateLimiter(clock=t.clock, sleep=t.sleep)
        for _ in range(5):
            limiter.wait("a", 0)
        self.assertEqual(t.sleeps, [])


class RobotsTests(unittest.TestCase):
    def cache(self, site):
        return RobotsCache("TestBot/1.0", timeout=5)

    def test_rules_and_crawl_delay_are_applied(self):
        robots = "User-agent: *\nDisallow: /private/\nCrawl-delay: 3\n"
        with Site({"/robots.txt": (200, "text/plain", robots)}) as site:
            cache = self.cache(site)
            self.assertTrue(cache.allowed(site.base + "/public"))
            self.assertFalse(cache.allowed(site.base + "/private/x"))
            self.assertEqual(cache.crawl_delay(site.base + "/"), 3.0)
            self.assertEqual(site.count("/robots.txt"), 1)  # cached

    def test_specific_agent_rules_win(self):
        robots = "User-agent: TestBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        with Site({"/robots.txt": (200, "text/plain", robots)}) as site:
            self.assertFalse(self.cache(site).allowed(site.base + "/anything"))

    def test_missing_robots_allows_everything(self):
        with Site({}) as site:
            self.assertTrue(self.cache(site).allowed(site.base + "/x"))

    def test_server_error_disallows_everything(self):
        with Site({"/robots.txt": (503, "text/plain", "down")}) as site:
            self.assertFalse(self.cache(site).allowed(site.base + "/x"))

    def test_unreachable_host_disallows_everything(self):
        with Site({}) as site:
            url = site.base + "/x"
        self.assertFalse(self.cache(None).allowed(url))  # server is shut down


if __name__ == "__main__":
    unittest.main()
