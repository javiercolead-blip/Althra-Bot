"""Core data model: one Opportunity = one row in the tracker."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date


# Status values shown in the spreadsheet dropdown. The emoji makes them
# readable at a glance on a phone; the colour rules key off these exact strings.
NEW = "🆕 New"
TO_ENTER = "⭐ To Enter"
ENTERED = "✅ Entered"
ENTER_AGAIN = "🔁 Enter Again"
WON = "🏆 Won"
EXPIRED = "⌛ Expired"
SKIP = "🚫 Skip"
INELIGIBLE = "⛔ Not Eligible"

STATUSES = [NEW, TO_ENTER, ENTER_AGAIN, ENTERED, WON, EXPIRED, SKIP, INELIGIBLE]

# Statuses the user sets by hand that the bot must never overwrite.
USER_FINAL = {WON, SKIP}


def make_id(link: str, title: str = "") -> str:
    key = (link or title).strip().lower().rstrip("/")
    return hashlib.sha1(key.encode()).hexdigest()[:10]


@dataclass
class Opportunity:
    title: str
    link: str
    source: str
    kind: str = "giveaway"            # giveaway | job | event
    summary: str = ""
    prize: str = ""
    value: float = 0.0                # estimated CAD value
    ends: date | None = None
    frequency: str = "once"           # once | daily | weekly
    eligibility: str = ""             # human-readable note
    eligible: bool = True
    score: float = 0.0
    status: str = NEW
    found: date = field(default_factory=date.today)
    last_entered: date | None = None
    times_entered: int = 0
    notes: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = make_id(self.link, self.title)

    # --- (de)serialisation for data/opportunities.json -------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("ends", "found", "last_entered"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Opportunity":
        d = dict(d)
        for k in ("ends", "found", "last_entered"):
            d[k] = date.fromisoformat(d[k]) if d.get(k) else None
        if d.get("found") is None:
            d["found"] = date.today()
        known = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in known})
