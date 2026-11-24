"""The tracker's memory: merges fresh scout results with what's already known
and with whatever you changed in the spreadsheet, then decides statuses."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import (ENTER_AGAIN, ENTERED, EXPIRED, INELIGIBLE, NEW, SKIP,
                     STATUSES, TO_ENTER, USER_FINAL, WON, Opportunity, make_id)

# Order rows appear in the sheet: things needing action first.
STATUS_ORDER = {s: i for i, s in enumerate(
    [ENTER_AGAIN, TO_ENTER, NEW, ENTERED, WON, EXPIRED, SKIP, INELIGIBLE])}


UNDATED_DAYS = 30


class Tracker:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, Opportunity] = {}
        if path.exists():
            for d in json.loads(path.read_text(encoding="utf-8")):
                o = Opportunity.from_dict(d)
                self.items[o.id] = o

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [o.to_dict() for o in self.sorted()]
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    def sorted(self) -> list[Opportunity]:
        return sorted(self.items.values(), key=lambda o: (STATUS_ORDER.get(o.status, 99), -o.score))

    # ------------------------------------------------------------------ #
    def apply_sheet_edits(self, rows: list[dict], today: date) -> int:
        """rows: dicts keyed by sheet header. Pulls in your status/notes edits
        and any links you pasted in yourself. Returns number of changes."""
        changes = 0
        for r in rows:
            link = (r.get("Link") or "").strip()
            oid = (r.get("ID") or "").strip() or (make_id(link, r.get("Prize", "")) if link else "")
            if not oid:
                continue
            status = (r.get("Status") or "").strip()
            o = self.items.get(oid)
            if o is None:  # a row you added by hand
                o = Opportunity(title=r.get("Prize") or link, link=link, source="Manual",
                                prize=r.get("Prize") or link, eligibility="✍️ Added by you",
                                score=50.0, id=oid, found=today)
                o.status = status if status in STATUSES else TO_ENTER
                self.items[oid] = o
                changes += 1
            if status in STATUSES and status != o.status:
                if status == ENTERED:
                    o.times_entered += 1
                    o.last_entered = today
                o.status = status
                changes += 1
            notes = r.get("Notes", "")
            if notes != o.notes:
                o.notes = notes
                changes += 1
        return changes

    def add_found(self, found: list[Opportunity]) -> list[Opportunity]:
        new = []
        for o in found:
            if o.id in self.items:
                old = self.items[o.id]
                # refresh details the scout may now know better, keep your progress
                old.summary = o.summary or old.summary
                old.ends = o.ends or old.ends
                if old.status in (NEW, TO_ENTER, INELIGIBLE):   # not acted on yet: re-judge
                    for f in ("prize", "value", "frequency", "eligible", "eligibility", "score"):
                        setattr(old, f, getattr(o, f))
                    if old.status == INELIGIBLE and old.eligible:
                        old.status = NEW
                continue
            self.items[o.id] = o
            new.append(o)
        return new

    def update_statuses(self, today: date, queue_size: int) -> None:
        for o in self.items.values():
            if o.status in USER_FINAL:
                continue
            if not o.eligible and o.status in (NEW, TO_ENTER):
                o.status = INELIGIBLE
                continue
            if o.ends is not None:
                ended = o.ends < today
            else:  # no end date known: assume most contests run about a month
                ended = (today - (o.found or today)).days > UNDATED_DAYS
            if ended and o.status in (NEW, TO_ENTER, ENTER_AGAIN):
                o.status = EXPIRED
                continue
            if o.status == ENTERED and not ended and o.last_entered:
                gap = {"daily": 1, "weekly": 7}.get(o.frequency)
                if gap and (today - o.last_entered).days >= gap:
                    o.status = ENTER_AGAIN

        # Today's queue: promote the best new finds to "To Enter".
        waiting = sum(1 for o in self.items.values() if o.status == TO_ENTER)
        for o in sorted((o for o in self.items.values() if o.status == NEW), key=lambda o: -o.score):
            if waiting >= queue_size:
                break
            o.status = TO_ENTER
            waiting += 1

    def prune(self, today: date) -> int:
        """Drop dead rows so the sheet stays readable. Wins are kept forever."""
        def dead(o: Opportunity) -> bool:
            age = (today - (o.found or today)).days
            if o.status in (EXPIRED, SKIP, INELIGIBLE):
                return age > 14
            if o.status == ENTERED and o.ends:
                return o.ends < today - timedelta(days=90)   # long past any draw
            if o.status == NEW:
                return age > 45
            return False
        gone = [k for k, o in self.items.items() if dead(o)]
        for k in gone:
            del self.items[k]
        return len(gone)

    def stats(self) -> dict[str, int]:
        out = {s: 0 for s in STATUSES}
        for o in self.items.values():
            out[o.status] = out.get(o.status, 0) + 1
        return out
