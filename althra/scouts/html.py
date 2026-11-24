from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Opportunity


def scout_html(src: dict, body: str) -> list[Opportunity]:
    """Generic listing-page scraper driven by CSS selectors in sources.yaml."""
    soup = BeautifulSoup(body, "html.parser")
    out = []
    for block in soup.select(src["item"]):
        t = block.select_one(src.get("title", "a"))
        a = block.select_one(src.get("link", "a"))
        if not t or not a or not a.get("href"):
            continue
        s = block.select_one(src["summary"]) if src.get("summary") else block
        out.append(Opportunity(
            title=t.get_text(" ", strip=True),
            link=urljoin(src["url"], a["href"]),
            source=src["name"],
            kind=src.get("kind", "giveaway"),
            summary=(s.get_text(" ", strip=True) if s else "")[:1500],
        ))
    return out
