"""Althra scout.

  python -m althra run                  scout, merge, update spreadsheet(s)
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import DATA_DIR, load_profile, load_sources
from .enrich import enrich
from .scouts import fetch, run_scouts
from .sheets import excel, google
from .tracker import Tracker

log = logging.getLogger("althra")


def run(queue_size: int, fetcher=fetch) -> None:
    profile = load_profile()
    today = datetime.now(ZoneInfo(profile.get("timezone", "America/Vancouver"))).date()
    tracker = Tracker(DATA_DIR / "opportunities.json")
    xlsx = DATA_DIR / "tracker.xlsx"

    # 1. Pull in your edits (Google Sheet wins if configured, else the Excel file).
    sheet = google.GoogleSheet() if google.configured() else None
    edits = sheet.read() if sheet else excel.read_excel(xlsx)
    changed = tracker.apply_sheet_edits(edits, today)
    log.info("[sheet] picked up %d edits from %s", changed, "Google Sheets" if sheet else "Excel")

    # 2. Scout.
    found = [enrich(o, profile, today) for o in run_scouts(load_sources(), fetcher)]
    new = tracker.add_found(found)
    log.info("[scout] %d found, %d new", len(found), len(new))

    # 3. Decide statuses, clean up, save.
    tracker.update_statuses(today, queue_size)
    pruned = tracker.prune(today)
    tracker.save()
    items = tracker.sorted()
    excel.write_excel(xlsx, items)
    if sheet:
        sheet.write(items)
    stats = {k: v for k, v in tracker.stats().items() if v}
    log.info("[done] %d rows (%d pruned) · %s", len(items), pruned, " · ".join(f"{k}: {v}" for k, v in stats.items()))


def main() -> None:
    ap = argparse.ArgumentParser(prog="althra")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--queue", type=int, default=int(os.environ.get("ALTHRA_QUEUE_SIZE", 25)),
                   help="max rows marked ⭐ To Enter at once")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.queue)


if __name__ == "__main__":
    main()
