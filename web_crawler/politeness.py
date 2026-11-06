"""robots.txt handling and per-host rate limiting."""

import threading
import time
import urllib.robotparser
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit

from .fetcher import fetch


class HostRateLimiter:
    """Guarantees a minimum interval between requests to the same host.

    Threads reserve consecutive time slots under a lock and then sleep
    outside of it, so a slow host never blocks work on other hosts and
    concurrent workers are serialised to one request per ``delay`` seconds.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._clock = clock
        self._sleep = sleep
        self._next_slot: Dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str, delay: float) -> float:
        """Block until a request to ``host`` is allowed; returns the time slept."""
        if delay <= 0:
            return 0.0
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot.get(host, now))
            self._next_slot[host] = slot + delay
        pause = slot - now
        if pause > 0:
            self._sleep(pause)
        return max(pause, 0.0)


class _HostRules:
    def __init__(self, parser: Optional[urllib.robotparser.RobotFileParser], allow_all: bool = False,
                 disallow_all: bool = False):
        self.parser = parser
        self.allow_all = allow_all
        self.disallow_all = disallow_all


class RobotsCache:
    """Fetches and caches robots.txt once per host (RFC 9309 semantics).

    * 2xx: rules are parsed and applied.
    * 4xx (file missing): everything is allowed.
    * 5xx or network failure: the host is treated as fully disallowed.
    """

    def __init__(self, user_agent: str, timeout: float = 10.0,
                 before_fetch: Optional[Callable[[str], None]] = None):
        self.user_agent = user_agent
        self._timeout = timeout
        self._before_fetch = before_fetch
        self._rules: Dict[str, _HostRules] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _load(self, origin: str, host: str) -> _HostRules:
        with self._guard:
            lock = self._locks.setdefault(origin, threading.Lock())
        with lock:  # only one thread fetches robots.txt for a given origin
            rules = self._rules.get(origin)
            if rules is not None:
                return rules
            if self._before_fetch:
                self._before_fetch(host)
            result = fetch(origin + "/robots.txt", self.user_agent, self._timeout)
            if result.status == 0 or result.status >= 500:
                rules = _HostRules(None, disallow_all=True)
            elif 400 <= result.status < 500 or not (200 <= result.status < 300):
                rules = _HostRules(None, allow_all=True)
            else:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(result.body.splitlines())
                rules = _HostRules(parser)
            self._rules[origin] = rules
            return rules

    def _for(self, url: str) -> _HostRules:
        parts = urlsplit(url)
        return self._load(f"{parts.scheme}://{parts.netloc}", parts.netloc)

    def allowed(self, url: str) -> bool:
        rules = self._for(url)
        if rules.disallow_all:
            return False
        if rules.allow_all or rules.parser is None:
            return True
        return rules.parser.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float:
        rules = self._for(url)
        if rules.parser is None:
            return 0.0
        value = rules.parser.crawl_delay(self.user_agent)
        return float(value) if value is not None else 0.0
