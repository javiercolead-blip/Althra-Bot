from __future__ import annotations

import feedparser
from bs4 import BeautifulSoup

from ..models import Opportunity


def _text(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def scout_rss(src: dict, body: str) -> list[Opportunity]:
    feed = feedparser.parse(body)
    out = []
    for e in feed.entries:
        link = e.get("link", "")
        title = _text(e.get("title", ""))
        if not (link and title):
            continue
        summary = _text(e.get("summary", "") or e.get("description", ""))
        out.append(Opportunity(
            title=title, link=link, source=src["name"],
            kind=src.get("kind", "giveaway"), summary=summary[:1500],
        ))
    return out
