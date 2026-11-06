"""The crawler: breadth-first, concurrent, polite."""

import queue
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, Set
from urllib.parse import urlsplit

from .fetcher import FetchResult, fetch
from .links import normalize_url, parse_page
from .politeness import HostRateLimiter, RobotsCache

DEFAULT_USER_AGENT = "PortfolioCrawler/1.0"


@dataclass
class PageResult:
    url: str
    depth: int
    status: int  # HTTP status; 0 = network error, -1 = blocked by robots.txt
    title: str = ""
    links_found: int = 0
    content_type: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Crawler:
    """Crawl from ``start_url`` up to ``max_depth`` links away.

    * **Dedup:** URLs are normalised (case, default port, fragment) and each is
      scheduled at most once; redirect targets are deduplicated as well.
    * **Depth limit:** the start page has depth 0; pages at ``max_depth`` are
      fetched but their links are not followed.
    * **Page limit:** ``max_pages`` caps the number of URLs scheduled.
    * **Politeness:** robots.txt is honored (including Crawl-delay) and at
      least ``delay`` seconds separate two requests to the same host, no
      matter how many workers run.
    * **Scope:** by default only the start page's host (host and port) is
      crawled; pass ``allowed_hosts`` to widen it.
    """

    def __init__(
        self,
        start_url: str,
        max_depth: int = 2,
        max_pages: int = 100,
        workers: int = 4,
        delay: float = 0.0,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 10.0,
        allowed_hosts: Optional[Set[str]] = None,
        respect_robots: bool = True,
        on_page: Optional[Callable[[PageResult], None]] = None,
        limiter: Optional[HostRateLimiter] = None,
    ):
        start = normalize_url(start_url)
        if start is None:
            raise ValueError(f"not an http(s) URL: {start_url!r}")
        if max_depth < 0 or max_pages < 1 or workers < 1 or delay < 0:
            raise ValueError("invalid crawler limits")
        self.start_url = start
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.workers = workers
        self.delay = delay
        self.user_agent = user_agent
        self.timeout = timeout
        self.allowed_hosts = {urlsplit(start).netloc} | set(allowed_hosts or ())
        self.respect_robots = respect_robots
        self._on_page = on_page
        self._limiter = limiter or HostRateLimiter()
        self._robots = RobotsCache(user_agent, timeout, before_fetch=lambda host: self._limiter.wait(host, delay))
        self._queue: "queue.Queue" = queue.Queue()
        self._seen: Set[str] = set()
        self._lock = threading.Lock()
        self.results: List[PageResult] = []

    # -- scheduling ------------------------------------------------------------

    def _schedule(self, url: str, depth: int) -> bool:
        with self._lock:
            if url in self._seen or len(self._seen) >= self.max_pages:
                return False
            self._seen.add(url)
        self._queue.put((url, depth))
        return True

    def _in_scope(self, url: str) -> bool:
        return urlsplit(url).netloc in self.allowed_hosts

    def _record(self, result: PageResult) -> None:
        with self._lock:
            self.results.append(result)
        if self._on_page:
            self._on_page(result)

    # -- work --------------------------------------------------------------------

    def _process(self, url: str, depth: int) -> None:
        host = urlsplit(url).netloc
        wait = self.delay
        if self.respect_robots:
            if not self._robots.allowed(url):
                self._record(PageResult(url, depth, -1, error="blocked by robots.txt"))
                return
            wait = max(wait, self._robots.crawl_delay(url))
        self._limiter.wait(host, wait)
        page = fetch(url, self.user_agent, self.timeout)
        if page.status == 0:
            self._record(PageResult(url, depth, 0, error=page.error))
            return
        final = normalize_url(page.final_url) or url
        if final != url:
            with self._lock:
                duplicate = final in self._seen
                self._seen.add(final)
            if duplicate:
                self._record(PageResult(url, depth, page.status, error=f"redirects to already seen {final}"))
                return
        title, links = "", []
        if page.is_html and page.body:
            title, links = parse_page(page.body, final)
        result = PageResult(final, depth, page.status, title, len(links), page.content_type)
        self._record(result)
        if page.is_html and 200 <= page.status < 300 and depth < self.max_depth:
            for link in links:
                if self._in_scope(link):
                    self._schedule(link, depth + 1)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self._process(*item)
            except Exception as exc:  # a bug in one page must not stall the crawl
                self._record(PageResult(item[0], item[1], 0, error=f"internal error: {exc!r}"))
            finally:
                self._queue.task_done()

    def crawl(self) -> List[PageResult]:
        self._schedule(self.start_url, 0)
        threads = [threading.Thread(target=self._worker, daemon=True) for _ in range(self.workers)]
        for t in threads:
            t.start()
        self._queue.join()  # empty queue and every task finished: nothing can add more work
        for _ in threads:
            self._queue.put(None)
        for t in threads:
            t.join()
        return sorted(self.results, key=lambda r: (r.depth, r.url))
