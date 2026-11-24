from datetime import date, timedelta
from pathlib import Path

import pytest

from althra.config import load_profile
from althra.enrich import enrich, estimate_value, find_end_date
from althra.models import (ENTER_AGAIN, ENTERED, EXPIRED, INELIGIBLE, NEW, SKIP,
                           TO_ENTER, WON, Opportunity)
from althra.scouts import run_scouts
from althra.scouts.html import scout_html
from althra.scouts.rss import scout_rss
from althra.sheets import excel, to_row, HEADERS
from althra.tracker import Tracker

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 24)


@pytest.fixture
def profile():
    return load_profile()


@pytest.fixture
def found(profile):
    items = scout_rss({"name": "Sample"}, (FIX / "sample_feed.xml").read_text())
    return {o.link.rsplit("/", 1)[1]: enrich(o, profile, TODAY) for o in items}


def test_eligibility(found):
    assert found["vacation"].eligible and found["vacation"].eligibility.startswith("🇨🇦")
    assert found["macbook"].eligible and found["macbook"].eligibility.startswith("📍")
    assert (found["giftcard"].eligible, found["giftcard"].eligibility) == (False, "US only")
    assert (found["hockey"].eligible, found["hockey"].eligibility) == (False, "ON residents only")
    assert (found["ps5"].eligible, found["ps5"].eligibility) == (False, "Must be 25+")
    assert (found["headphones"].eligible, found["headphones"].eligibility) == (False, "Excludes BC")
    assert found["cash"].eligible  # "excluding Quebec" is fine for BC
    assert "social" in found["cash"].eligibility


def test_details(found):
    assert found["vacation"].prize == "$5,000 Vacation Getaway"
    assert found["vacation"].value == 5000
    assert found["vacation"].ends == date(2026, 12, 31)
    assert found["macbook"].frequency == "daily"
    assert found["cash"].ends == date(2027, 1, 5)  # "Jan 5" with no year -> next one
    assert found["macbook"].score > found["vacation"].score  # BC-only + daily beats bigger national prize


def test_value_and_dates():
    assert estimate_value("Win $2.5k in prizes or $10,000 grand prize") == 10000
    assert estimate_value("Prix de 1 500 $") == 1500
    assert estimate_value("Win a trip to Mexico") == 4000
    assert find_end_date("Contest closes: 2026-12-01 at noon", TODAY) == date(2026, 12, 1)
    assert find_end_date("No dates here", TODAY) is None


def test_lifecycle(tmp_path, found):
    t = Tracker(tmp_path / "o.json")
    t.add_found(list(found.values()))
    t.update_statuses(TODAY, queue_size=2)
    st = {k: t.items[o.id].status for k, o in found.items()}
    assert st["macbook"] == TO_ENTER and st["vacation"] == TO_ENTER   # top 2
    assert st["cash"] == NEW                                          # queue full
    assert st["giftcard"] == INELIGIBLE

    # You enter the MacBook (daily) and vacation (once), and skip cash, in the sheet.
    mac, vac, cash = (found[k].id for k in ("macbook", "vacation", "cash"))
    rows = [dict(zip(HEADERS, map(str, to_row(o)))) for o in t.sorted()]
    for r in rows:
        r["Status"] = {mac: ENTERED, vac: ENTERED, cash: SKIP}.get(r["ID"], r["Status"])
    rows.append({"Status": "", "Prize": "Local radio contest", "Link": "https://radio.example/win"})
    assert t.apply_sheet_edits(rows, TODAY) == 4
    assert t.items[mac].times_entered == 1
    manual = [o for o in t.items.values() if o.source == "Manual"][0]
    assert manual.status == TO_ENTER

    t.save()
    t = Tracker(tmp_path / "o.json")  # survives a reload
    tomorrow = TODAY + timedelta(days=1)
    t.update_statuses(tomorrow, queue_size=2)
    assert t.items[mac].status == ENTER_AGAIN   # daily -> due again
    assert t.items[vac].status == ENTERED       # one-time stays done
    assert t.items[cash].status == SKIP

    # Past the MacBook's end date, a pending re-entry expires.
    t.update_statuses(date(2026, 12, 16), queue_size=2)
    assert t.items[mac].status == EXPIRED

    # A win is never touched again, even long after it ends.
    t.items[vac].status = WON
    t.update_statuses(date(2027, 6, 1), queue_size=2)
    t.prune(date(2027, 6, 1))
    assert t.items[vac].status == WON


def test_excel_roundtrip(tmp_path, found):
    path = tmp_path / "t.xlsx"
    items = list(found.values())
    excel.write_excel(path, items)
    rows = excel.read_excel(path)
    assert len(rows) == len(items)
    assert {r["ID"] for r in rows} == {o.id for o in items}


def test_broken_source_does_not_stop_run():
    def fetcher(url):
        if "bad" in url:
            raise ConnectionError("nope")
        return (FIX / "sample_feed.xml").read_text()
    out = run_scouts([{"name": "bad", "url": "https://bad"}, {"name": "ok", "url": "https://ok"}], fetcher)
    assert len(out) == 7


def test_html_scout():
    html = '<div class="c"><h3><a href="/win/1">Win a Bike</a></h3><p>Canada only</p></div>'
    out = scout_html({"name": "h", "url": "https://x.ca/list", "item": "div.c", "title": "h3", "link": "a"}, html)
    assert out[0].link == "https://x.ca/win/1" and out[0].title == "Win a Bike"


def test_structured_fields(profile):
    """Formats seen on real Contest Canada posts (first live run, Nov 2026)."""
    def e(title, summary):
        return enrich(Opportunity(title=title, link=title, source="Contest Canada", summary=summary),
                      profile, TODAY, "canada")
    qc = e("Win a Canadian Tire gift card valued at $1,000", "Entry Frequency: daily Open to: QC")
    assert (qc.eligible, qc.eligibility) == (False, "QC only")
    multi = e("Win $20,000 or 1 of 19 prizes of $500",
              "Entry Frequency: daily Open to: BC, ON, NB, NS Trivia/Product question response required")
    assert multi.eligible and multi.eligibility.startswith("📍 BC, ON, NB, NS") and "keyword" in multi.eligibility
    assert multi.frequency == "daily" and multi.value == 20000
    notqc = e("Win a travel voucher valued at $4,325",
              "Purchase a beverage at Swiss Chalet. Entry Frequency: unlimited Not open to: QC PIN required")
    assert notqc.eligibility.startswith("🇨🇦 Canada") and "💸 purchase" in notqc.eligibility
    assert notqc.score < e("Win a travel voucher valued at $4,325", "Entry Frequency: unlimited").score
    pei = e("Win a Lawtons gift card valued at $500", "Entry Frequency: single Open to: NB, NS, PEI, NL")
    assert (pei.eligible, pei.frequency) == (False, "once")
    big = e("Win 1 of 10 McDonalds meals valued at $11,000",
            "Good Canadian, we have $187,624 in new contest prize values today!")
    assert big.value == 11000
    local = e("Victoria – $100 gift FARO Handcrafted Pizza", "")
    assert local.eligibility.startswith("📍")
