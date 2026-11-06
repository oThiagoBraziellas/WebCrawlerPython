"""Link extraction and URL normalisation."""

from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> Optional[str]:
    """Canonical form used for de-duplication, or None for non-http(s) URLs.

    Lowercases scheme and host, removes the default port and the fragment,
    and turns an empty path into ``/``. The query string is kept as is.
    """
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    netloc = host.lower()
    if ":" in netloc:  # IPv6 literal
        netloc = f"[{netloc}]"
    if port and port != _DEFAULT_PORTS[scheme]:
        netloc += f":{port}"
    if parts.username:
        return None  # credentials in URLs are never followed
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base: Optional[str] = None
        self.hrefs: List[Tuple[str, bool]] = []  # (href, nofollow)
        self.title = ""
        self._in_title = False
        self.robots_nofollow = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        elif tag == "a" and a.get("href"):
            nofollow = "nofollow" in (a.get("rel") or "").lower().split()
            self.hrefs.append((a["href"], nofollow))
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or "").lower() == "robots":
            if "nofollow" in (a.get("content") or "").lower():
                self.robots_nofollow = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse_page(html: str, page_url: str) -> Tuple[str, List[str]]:
    """Return ``(title, normalised absolute links)``.

    Honors ``<base href>``, ``rel="nofollow"`` and ``<meta name="robots"
    content="nofollow">``. Duplicates are removed, order is preserved.
    """
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    title = " ".join(parser.title.split())
    if parser.robots_nofollow:
        return title, []
    base = urljoin(page_url, parser.base) if parser.base else page_url
    seen, out = set(), []
    for href, nofollow in parser.hrefs:
        if nofollow:
            continue
        absolute = normalize_url(urljoin(base, href.strip()))
        if absolute and absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return title, out


def extract_links(html: str, page_url: str) -> List[str]:
    return parse_page(html, page_url)[1]
