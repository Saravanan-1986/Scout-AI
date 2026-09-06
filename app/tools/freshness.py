"""Freshness checks — ScoutAI only presents opportunities that are still open.

Rules (spec-aligned: never show stale/out-dated listings):
    1. URLs pointing to past editions (e.g. ".../hackathon-2025/...") are
       skipped BEFORE scraping.
    2. Pages that announce winners/results/conclusion are skipped.
    3. Deadlines anchored to deadline words ("Apply by", "Deadline:",
       "Registration closes", ...) that are already in the past are skipped.

Opportunities with NO date information are kept — ScoutAI never assumes
something is expired without evidence.
"""

import calendar
import re
from datetime import date, datetime
from typing import List, Optional, Tuple

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_NAME = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"

# "March 15, 2026" / "Mar 15 2026" / "15 March 2026" / "15th Mar, 2026"
_MONTH_DAY_YEAR = re.compile(
    r"\b" + _MONTH_NAME + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH_NAME + r"\.?\s*,?\s*(\d{4})\b",
    re.IGNORECASE,
)
# "March 2026" — treated as end-of-month
_MONTH_YEAR = re.compile(r"\b" + _MONTH_NAME + r"\.?\s+(\d{4})\b", re.IGNORECASE)
# ISO + numeric: 2026-03-15 / 15/03/2026 / 15-03-26 (day-first, Indian format)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
_YEAR = re.compile(r"\b(20\d{2})\b")

_DEADLINE_CONTEXT = (
    "deadline", "apply by", "apply before", "ends on", "ends", "closes on",
    "closes", "close by", "closing", "last date", "register by",
    "registration ends", "submit by",
)

_CONCLUDED_MARKERS = (
    "congratulations",
    "winners announced",
    "winner announced",
    "results announced",
    "results declared",
    "result declared",
    "has concluded",
    "have concluded",
    "is now over",
    "are now over",
    "event over",
    "submissions closed",
    "submissions are closed",
    "applications closed",
    "applications are closed",
    "registration closed",
    "registrations closed",
    "no longer accepting",
    "thank you for participating",
)


def years_in_url(url: str) -> List[int]:
    """All 4-digit 20xx years appearing in the URL."""
    return [int(y) for y in _YEAR.findall(url or "")]


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _month(month_token: str) -> int:
    return _MONTHS[month_token.lower()[:3]]


def _end_of_month(year: int, month: int) -> Optional[date]:
    try:
        return date(year, month, calendar.monthrange(year, month)[1])
    except (ValueError, TypeError):
        return None


def _find_dates(text: str) -> List[Tuple[date, int, int]]:
    """All dates found in text as (date, start_pos, end_pos)."""
    found: List[Tuple[date, int, int]] = []
    for m in _MONTH_DAY_YEAR.finditer(text):
        d = _safe_date(int(m.group(3)), _month(m.group(1)), int(m.group(2)))
        if d:
            found.append((d, m.start(), m.end()))
    for m in _DAY_MONTH_YEAR.finditer(text):
        d = _safe_date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
        if d:
            found.append((d, m.start(), m.end()))
    for m in _ISO.finditer(text):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.append((d, m.start(), m.end()))
    for m in _NUMERIC.finditer(text):
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yy < 100:
            yy += 2000
        if mm > 12 and dd <= 12:  # tolerate mm/dd ordering
            dd, mm = mm, dd
        d = _safe_date(yy, mm, dd)
        if d:
            found.append((d, m.start(), m.end()))
    for m in _MONTH_YEAR.finditer(text):
        d = _end_of_month(int(m.group(2)), _month(m.group(1)))
        if d:
            found.append((d, m.start(), m.end()))
    return found


def latest_deadline_date(text: str) -> Optional[date]:
    """Latest date whose surrounding context mentions a deadline word."""
    best: Optional[date] = None
    for d, start, end in _find_dates(text or ""):
        context = text[max(0, start - 70) : end + 30].lower()
        if any(keyword in context for keyword in _DEADLINE_CONTEXT):
            if best is None or d > best:
                best = d
    return best


def is_concluded_text(text: str) -> bool:
    """Detect pages announcing results/winners/closure of a past event."""
    lowered = (text or "").lower()[:8000]
    return any(marker in lowered for marker in _CONCLUDED_MARKERS)


def check_freshness(url: str, text: str, today: Optional[date] = None) -> Tuple[bool, str]:
    """Return (is_fresh, reason). Only evidence of being past marks staleness."""
    today = today or date.today()

    years = years_in_url(url or "")
    if years:
        latest = max(years)
        if latest < today.year:
            return False, f"page belongs to {latest} (past edition)"

    if is_concluded_text(text):
        return False, "page announces winners/results (event already concluded)"

    deadline = latest_deadline_date(text or "")
    if deadline and deadline < today:
        return False, f"deadline {deadline.strftime('%d %b %Y')} has already passed"

    return True, ""


def deadline_is_past(deadline_text: str, today: Optional[date] = None) -> Optional[bool]:
    """Parse the extracted deadline string. True/False when parseable, None if unknown."""
    if not deadline_text or deadline_text == "Not specified":
        return None
    today = today or date.today()
    dates = _find_dates(deadline_text)
    if not dates:
        return None
    return min(d for d, _, _ in dates) < today


def current_year() -> int:
    return datetime.now().year
