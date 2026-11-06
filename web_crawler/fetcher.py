"""HTTP fetching with the standard library."""

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

MAX_BODY_BYTES = 2 * 1024 * 1024


@dataclass
class FetchResult:
    url: str  # URL requested
    final_url: str  # after redirects
    status: int  # 0 when the request failed before any response
    content_type: str
    body: str  # decoded text, only for HTML/text responses
    error: Optional[str] = None

    @property
    def is_html(self) -> bool:
        return self.content_type.split(";")[0].strip().lower() in ("text/html", "application/xhtml+xml")


def fetch(url: str, user_agent: str, timeout: float = 10.0) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _from_response(url, response, response.status)
    except urllib.error.HTTPError as exc:
        try:
            return _from_response(url, exc, exc.code)
        finally:
            exc.close()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return FetchResult(url, url, 0, "", "", error=str(reason))


def _from_response(url: str, response, status: int) -> FetchResult:
    content_type = response.headers.get("Content-Type", "")
    final_url = response.geturl() if hasattr(response, "geturl") else url
    body = ""
    if content_type.split(";")[0].strip().lower() in ("text/html", "application/xhtml+xml", "text/plain"):
        raw = response.read(MAX_BODY_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"
        body = raw.decode(charset, errors="replace")
    return FetchResult(url, final_url, status, content_type, body)
