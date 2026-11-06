"""Command line interface."""

import argparse
import json
import sys
from typing import List, Optional

from .crawler import DEFAULT_USER_AGENT, Crawler


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="web_crawler", description="Polite concurrent web crawler")
    p.add_argument("url")
    p.add_argument("--depth", type=int, default=2, help="link depth limit (default 2)")
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    p.add_argument("--allow-host", action="append", default=[], metavar="HOST[:PORT]",
                   help="also crawl this host (repeatable)")
    p.add_argument("--ignore-robots", action="store_true", help="do not read robots.txt (use only on your own sites)")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        crawler = Crawler(
            args.url,
            max_depth=args.depth,
            max_pages=args.max_pages,
            workers=args.workers,
            delay=args.delay,
            user_agent=args.user_agent,
            allowed_hosts=set(args.allow_host),
            respect_robots=not args.ignore_robots,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    results = crawler.crawl()
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        for r in results:
            status = {0: "ERR", -1: "ROB"}.get(r.status, str(r.status))
            detail = r.title or r.error or ""
            print(f"{'  ' * r.depth}[{status}] {r.url}  {detail}".rstrip())
        ok = sum(1 for r in results if r.ok)
        print(f"\n{len(results)} pages, {ok} ok, {sum(1 for r in results if r.status == -1)} blocked by robots.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
