"""Spreadsheet layout shared by the Excel and Google Sheets writers."""
from __future__ import annotations

from ..models import (ENTER_AGAIN, ENTERED, EXPIRED, INELIGIBLE, NEW, SKIP,
                      TO_ENTER, WON, Opportunity)

COLUMNS = [  # (header, width)
    ("Status", 16), ("Score", 7), ("Prize", 48), ("Est. Value", 11), ("Ends", 11),
    ("Frequency", 10), ("Eligibility", 20), ("Link", 40), ("Source", 18),
    ("Found", 11), ("Last Entered", 12), ("Times Entered", 8), ("Notes", 30), ("ID", 11),
]
HEADERS = [c[0] for c in COLUMNS]

# status -> (background, text colour, bold)
COLOURS = {
    NEW:         ("#FFFFFF", "#000000", False),
    TO_ENTER:    ("#FFF2CC", "#7F6000", True),    # yellow  – do these today
    ENTER_AGAIN: ("#CFE2F3", "#073763", True),    # blue    – daily/weekly entry due
    ENTERED:     ("#D9EAD3", "#274E13", False),   # light green – done
    WON:         ("#00B050", "#FFFFFF", True),    # bright green – you won!
    EXPIRED:     ("#EFEFEF", "#999999", False),   # grey
    SKIP:        ("#F4CCCC", "#990000", False),   # light red
    INELIGIBLE:  ("#F4CCCC", "#999999", False),
}

LEGEND = [
    (TO_ENTER, "Today's queue — best new finds. Enter, then set to ✅ Entered."),
    (ENTER_AGAIN, "Daily/weekly contest you've entered before — it's open for another entry."),
    (NEW, "Found, but not in today's top picks. Promote to ⭐ if it looks good."),
    (ENTERED, "Done. Daily/weekly ones flip back to 🔁 automatically."),
    (WON, "You won! Set this yourself — it's kept forever."),
    (EXPIRED, "Closed before you entered. Cleared after 2 weeks."),
    (SKIP, "Not interested. Bot won't touch it again."),
    (INELIGIBLE, "Rules exclude you (US-only, other province, etc.)."),
]


def to_row(o: Opportunity) -> list:
    return [
        o.status, o.score, o.prize or o.title, round(o.value) if o.value else "",
        o.ends.isoformat() if o.ends else "", o.frequency, o.eligibility, o.link,
        o.source, o.found.isoformat() if o.found else "",
        o.last_entered.isoformat() if o.last_entered else "", o.times_entered or "",
        o.notes, o.id,
    ]


def rows_to_dicts(values: list[list]) -> list[dict]:
    """Turn raw sheet values (header row first) into dicts keyed by header."""
    if not values:
        return []
    header = [str(h).strip() for h in values[0]]
    return [{h: ("" if v is None else str(v)) for h, v in zip(header, row)} for row in values[1:] if any(row)]
