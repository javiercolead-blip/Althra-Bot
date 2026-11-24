"""Scouts fetch raw opportunities from each configured source."""
from __future__ import annotations

import logging

import requests

from ..models import Opportunity
from .html import scout_html
from .rss import scout_rss

log = logging.getLogger("althra")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 althra-scout/0.1"
}

SCOUTS = {"rss": scout_rss, "html": scout_html}


def fetch(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def run_scouts(sources: list[dict], fetcher=fetch) -> list[Opportunity]:
    """Run every source; a broken source is logged and skipped, never fatal."""
    found: list[Opportunity] = []
    for src in sources:
        scout = SCOUTS.get(src.get("type", "rss"))
        if not scout:
            log.warning("[scout] %s: unknown type %r", src.get("name"), src.get("type"))
            continue
        try:
            items = scout(src, fetcher(src["url"]))
            log.info("[scout] %s: %d items", src["name"], len(items))
            found.extend(items)
        except Exception as e:  # noqa: BLE001 - one bad site must not stop the run
            log.warning("[scout] %s: FAILED (%s)", src.get("name"), e)
    return found
