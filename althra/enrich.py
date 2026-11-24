"""Reads each opportunity's text and fills in prize, value, end date,
entry frequency, eligibility and score."""
from __future__ import annotations

import math
import re
from datetime import date, timedelta

from dateutil import parser as dateparser

from .models import Opportunity

PROVINCES = {
    "BC": ["british columbia", "b.c."],
    "AB": ["alberta"], "SK": ["saskatchewan"], "MB": ["manitoba"],
    "ON": ["ontario"], "QC": ["quebec", "québec"], "NB": ["new brunswick"],
    "NS": ["nova scotia"], "PE": ["prince edward island", "p.e.i."],
    "NL": ["newfoundland"], "YT": ["yukon"], "NT": ["northwest territories"],
    "NU": ["nunavut"],
}

US_ONLY = re.compile(
    r"\b(u\.?s\.?a?\.?|united states)\s+(residents\s+)?only\b"
    r"|open to (legal )?residents of the (50 |fifty )?(united states|u\.s\.)"
    r"|\b(48|50) (contiguous )?(united )?states\b"
    r"|\bus residents\b(?!.{0,40}canad)", re.I)
WORLDWIDE = re.compile(r"\b(worldwide|international|open to all countries|ww)\b", re.I)
CANADA = re.compile(r"\bcanad(a|ian|ians)\b|\bcdn\b|🇨🇦", re.I)
STUDENT_ONLY = re.compile(r"\b(students? only|must be (a |an )?(enrolled |current )?student)\b", re.I)
AGE_MIN = re.compile(r"\b(\d{2})\s*\+|\b(\d{2}) years of age or older|\bage (\d{2}) or older", re.I)

DAILY = re.compile(r"daily entr|enter daily|once (per|a) day|every day|1x ?/ ?day|daily contest|enter each day", re.I)
WEEKLY = re.compile(r"weekly entr|enter weekly|once (per|a) week|every week", re.I)

ENDS = re.compile(
    r"(?:ends?|closes?|deadline|expires?|until|end date|closing date)\s*(?:on|:|-)?\s*"
    r"((?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s*)?"
    r"([a-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
    r"|\d{1,2}\s+[a-z]{3,9}\.?(?:\s+\d{4})?"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?)", re.I)

MONEY = re.compile(r"\$\s?(\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.\d+)?\s*(k|K)?|(\d{1,3}(?:[,\s]\d{3})+|\d+)\s?\$")

# Rough CAD values when a contest doesn't state one.
GUESS_VALUES = [
    (r"\b(car|truck|suv|vehicle)\b", 35000), (r"\b(cruise|vacation|trip|getaway|flight)s?\b", 4000),
    (r"\bmacbook|laptop\b", 1600), (r"\biphone|pixel|galaxy s\d", 1300), (r"\bipad|tablet\b", 700),
    (r"\b(ps5|playstation|xbox|nintendo switch|steam deck)\b", 600), (r"\b(tv|television)\b", 900),
    (r"\b(airpods|headphones|earbuds)\b", 300), (r"\bbike|bicycle\b", 800),
    (r"\btickets?\b", 250), (r"\bgift ?card\b", 50), (r"\bgift basket|prize pack\b", 150),
]

SOCIAL = re.compile(r"\b(instagram|tiktok|tag (a|your) friend|follow @|repost)\b", re.I)


def _parse_date(text: str, today: date) -> date | None:
    try:
        d = dateparser.parse(text, default=dateparser.parse(f"{today.year}-01-01"), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None
    if not re.search(r"\d{4}", text) and d < today - timedelta(days=60):
        d = d.replace(year=d.year + 1)  # "Jan 5" seen in December -> next year
    if not (today - timedelta(days=400) <= d <= today + timedelta(days=730)):
        return None
    return d


def find_end_date(text: str, today: date) -> date | None:
    for m in ENDS.finditer(text):
        d = _parse_date(m.group(2), today)
        if d:
            return d
    return None


def estimate_value(text: str) -> float:
    amounts = []
    for m in MONEY.finditer(text):
        raw = m.group(1) or m.group(3)
        v = float(re.sub(r"[,\s]", "", raw))
        if m.group(2):
            v *= 1000
        if 5 <= v <= 1_000_000:
            amounts.append(v)
    if amounts:
        return max(amounts)
    low = text.lower()
    for pat, v in GUESS_VALUES:
        if re.search(pat, low):
            return float(v)
    return 0.0


# Structured fields used by Contest Canada and similar listing sites.
OPEN_TO = re.compile(r"(?<![Nn]ot )\b[Oo]pen to:\s*((?:PEI|[A-Z]{2})(?:\s*,\s*(?:PEI|[A-Z]{2}))*)")
NOT_OPEN_TO = re.compile(r"\b[Nn]ot open to:\s*((?:PEI|[A-Z]{2})(?:\s*,\s*(?:PEI|[A-Z]{2}))*)")
FREQ_FIELD = re.compile(r"Entry Frequency:\s*(\w+)", re.I)

# Extra effort / cost flags: (pattern, label, score penalty)
FLAGS = [
    (re.compile(r"\bwith (a |any )?purchase|\bpurchase (a|an|any)\b|\breceipt\b|\bPIN required|\border from\b|\bbuy (a|an|any)\b", re.I), "💸 purchase", -15),
    (re.compile(r"Trivia/Product question|\bkeywords?\b|\blisten to\b|lucky song|boarding call", re.I), "🔑 keyword/trivia", -5),
    (re.compile(r"Membership required|create an account|sign up for", re.I), "👤 account", -3),
    (SOCIAL, "📱 social", 0),
]


def _codes(raw: str) -> list[str]:
    return ["PE" if c.strip() == "PEI" else c.strip() for c in raw.split(",")]


def check_eligibility(text: str, profile: dict, region: str = "") -> tuple[bool, str]:
    low = text.lower()
    my_code = profile.get("province_code", "BC")
    my_names = PROVINCES.get(my_code, [])

    # ---- hard "no"s ---------------------------------------------------
    for word in profile.get("blocklist", []):
        if word.lower() in low:
            return False, f"Blocked word: {word}"

    m = NOT_OPEN_TO.search(text)
    if m and my_code in _codes(m.group(1)):
        return False, f"Excludes {my_code}"
    if re.search(rf"exclud\w*[^.]{{0,60}}({'|'.join(map(re.escape, my_names + [my_code.lower()]))})\b", low):
        return False, f"Excludes {my_code}"

    open_to = OPEN_TO.search(text)
    if open_to and my_code not in _codes(open_to.group(1)):
        return False, f"{', '.join(_codes(open_to.group(1)))} only"

    # "<Province> residents only" / "open to residents of <Province>" for a province that isn't ours
    for code, names in PROVINCES.items():
        if code == my_code:
            continue
        for n in names:
            if re.search(rf"\b{re.escape(n)}\s+residents\s+only|open (only )?to (legal )?residents of {re.escape(n)}\b(?![^.]{{0,80}}{my_names[0] if my_names else '@@'})", low):
                return False, f"{code} residents only"

    is_canada = bool(CANADA.search(text)) or region == "canada"
    if US_ONLY.search(text) and not is_canada:
        return False, "US only"

    for m in AGE_MIN.finditer(text):
        age = int(next(g for g in m.groups() if g))
        if 13 <= age <= 99 and age > profile.get("age", 99):
            return False, f"Must be {age}+"

    if STUDENT_ONLY.search(text) and not profile.get("student"):
        return False, "Students only"

    # ---- eligible: how small is the pool? ------------------------------
    if open_to:  # restricted to a list of provinces that includes ours
        codes = _codes(open_to.group(1))
        return True, f"📍 {my_code} only" if codes == [my_code] else f"📍 {', '.join(codes)}"
    places = my_names + [profile.get("city", "")] + profile.get("local_places", [])
    if any(p and re.search(rf"\b{re.escape(p.lower())}\b", low) for p in places) or \
            re.search(rf"\b{my_code.lower()}\s+residents\b", low):
        return True, f"📍 {my_code} / local"
    if is_canada:
        return True, "🇨🇦 Canada"
    if WORLDWIDE.search(text):
        return True, "🌍 Worldwide"
    return True, "❓ Check rules"


def score(o: Opportunity, profile: dict, today: date) -> float:
    if not o.eligible:
        return 0.0
    s = 10 * math.log10(o.value + 1)              # $10 ≈ 10, $1k ≈ 30, $10k ≈ 40
    # Smaller entry pool = better odds: local beats Canada-wide beats worldwide.
    s += next((v for k, v in (("📍", 20), ("🇨🇦", 12), ("🌍", -5)) if o.eligibility.startswith(k)), 0)
    s += {"daily": 8, "weekly": 4}.get(o.frequency, 0)
    text = f"{o.title} {o.summary}".lower()
    s += min(10, 5 * sum(1 for i in profile.get("interests", []) if i.lower() in text))
    if o.ends and 0 <= (o.ends - today).days <= 7:
        s += 5                                    # closing soon: fewer people enter late
    if o.value == 0:
        s += 5                                    # unknown value shouldn't sink it entirely
    s += sum(pen for pat, label, pen in FLAGS if label in o.eligibility)
    return round(max(s, 1.0), 1)


def enrich(o: Opportunity, profile: dict, today: date | None = None, region: str = "") -> Opportunity:
    today = today or date.today()
    text = f"{o.title}. {o.summary}"
    o.prize = re.sub(r"^\s*(\[[^\]]*\]\s*)*(contest:|giveaway:|win\b:?(\s+an?\b)?)?\s*", "", o.title, flags=re.I)[:120]
    # The title usually states the actual prize; summaries can include unrelated
    # totals ("$187,624 in prizes today"), so only fall back to them.
    o.value = estimate_value(o.title) or estimate_value(o.summary)
    m = re.search(r"\b1 of (\d+)\b.*total value", o.title, re.I)
    if m:
        o.value = round(o.value / int(m.group(1)))
    o.ends = o.ends or find_end_date(text, today)
    f = FREQ_FIELD.search(text)
    f = f.group(1).lower() if f else ""
    if f in ("daily", "unlimited") or (not f and DAILY.search(text)):
        o.frequency = "daily"
    elif f == "weekly" or (not f and WEEKLY.search(text)):
        o.frequency = "weekly"
    else:
        o.frequency = "once"
    o.eligible, o.eligibility = check_eligibility(text, profile, region)
    if o.eligible:
        o.eligibility += "".join(f" · {label}" for pat, label, _ in FLAGS if pat.search(text))
    o.score = score(o, profile, today)
    return o
