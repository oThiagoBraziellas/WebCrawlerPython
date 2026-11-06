"""Polite, concurrent, robots.txt-aware web crawler."""

from .crawler import Crawler, PageResult
from .fetcher import FetchResult, fetch
from .links import extract_links, normalize_url
from .politeness import HostRateLimiter, RobotsCache

__all__ = [
    "Crawler",
    "PageResult",
    "FetchResult",
    "fetch",
    "extract_links",
    "normalize_url",
    "HostRateLimiter",
    "RobotsCache",
]
