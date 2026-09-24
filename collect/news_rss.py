"""News fetcher — RSS feeds + light web crawl of allowlisted free pages.

Stores headlines + snippets (ts, title, link, snippet, source) into
warehouse/raw. RSS via feedparser; the crawl is deliberately light: fetch
the page, pull headline links out of <h2>/<h3> elements.
"""
from __future__ import annotations

import html
import logging
import re
import time
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlparse

import feedparser
import requests

from common import config

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT_S = 30


def slugify(url: str) -> str:
    p = urlparse(url)
    base = p.netloc.replace("www.", "") + (p.path or "")
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")
    return base[:60] or "feed"


def with_retries(fn: Callable, attempts: int = 3, backoff: float = 2.0):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
    assert last is not None
    raise last


# -------------------------------------------------------------------- rss ---

def fetch_rss(url: str) -> list[dict]:
    def _do() -> list[dict]:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT_S)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f"RSS parse error: {feed.bozo_exception}")
        items = []
        for e in feed.entries[:100]:
            ts = 0.0
            if e.get("published_parsed"):
                ts = time.mktime(e["published_parsed"])
            elif e.get("updated_parsed"):
                ts = time.mktime(e["updated_parsed"])
            items.append(
                {
                    "ts": ts,
                    "title": html.unescape(e.get("title", "")).strip(),
                    "link": e.get("link", ""),
                    "snippet": re.sub(r"<[^>]+>", "", html.unescape(e.get("summary", "")))[:500],
                    "source": url,
                }
            )
        return items

    return with_retries(_do)


# ----------------------------------------------------------------- crawl ---

class _HeadlineParser(HTMLParser):
    """Pull (href, text) pairs out of <h2>/<h3> elements."""

    def __init__(self) -> None:
        super().__init__()
        self.headings: list[tuple[str, str]] = []
        self._in_heading = 0
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3"):
            self._in_heading += 1
            self._buf = []
        elif tag == "a" and self._in_heading:
            for k, v in attrs:
                if k == "href" and v and not v.startswith(("javascript:", "#")):
                    self._href = v
                    break

    def handle_endtag(self, tag):
        if tag in ("h2", "h3") and self._in_heading:
            self._in_heading -= 1
            text = " ".join("".join(self._buf).split())
            if text and self._href:
                self.headings.append((self._href, text))
            self._href = None
            self._buf = []

    def handle_data(self, data):
        if self._in_heading:
            self._buf.append(data)


def fetch_crawl(url: str) -> list[dict]:
    """Light crawl: headline links from <h2>/<h3> of one allowlisted page."""

    def _do() -> list[dict]:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT_S)
        r.raise_for_status()
        parser = _HeadlineParser()
        parser.feed(r.text)
        items = []
        for href, text in parser.headings[:100]:
            items.append(
                {
                    "ts": time.time(),
                    "title": html.unescape(text).strip(),
                    "link": urljoin(url, href),
                    "snippet": "",
                    "source": url,
                }
            )
        return items

    return with_retries(_do)


# -------------------------------------------------------------------- run ---

def run() -> int:
    """CLI entry: fetch all configured RSS feeds + crawl pages into raw."""
    config.load_env()
    feeds = config.get_list("NEWS_FEEDS")
    crawl_pages = config.get_list("NEWS_CRAWL_PAGES")
    if not feeds and not crawl_pages:
        log.error("NEWS_FEEDS and NEWS_CRAWL_PAGES are empty — nothing to fetch")
        return 1

    from collect import raw_store

    failed = 0
    total = 0
    for url in feeds:
        slug = slugify(url)
        try:
            items = fetch_rss(url)
            n = raw_store.append_news(slug, items)
            raw_store.record_fetch(f"news:rss:{slug}", "news", n, "ok")
            log.info("news rss ok: %s (+ %d new)", slug, n)
            total += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            raw_store.record_fetch(f"news:rss:{slug}", "news", 0, "failed", str(e))
            log.warning("news rss FAILED: %s: %s", slug, e)
    for url in crawl_pages:
        slug = slugify(url)
        try:
            items = fetch_crawl(url)
            n = raw_store.append_news(slug, items)
            raw_store.record_fetch(f"news:crawl:{slug}", "news", n, "ok")
            log.info("news crawl ok: %s (+ %d new)", slug, n)
            total += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            raw_store.record_fetch(f"news:crawl:{slug}", "news", 0, "failed", str(e))
            log.warning("news crawl FAILED: %s: %s", slug, e)
    return 1 if (feeds or crawl_pages) and failed == total else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(run())
