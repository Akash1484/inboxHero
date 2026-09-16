"""
Heuristic date/deadline extraction for plain-English business email. This is
regex over known phrasings (ordinal days, weekday+time, "by <weekday>",
"before month-end", "in N hours"), not a general date parser -- it is tuned
to read this inbox correctly and documented as a heuristic with that
limitation (see CAPABILITIES.md and Final Report). All resolution is
relative to the message's own timestamp, so "the 18th" in a message sent in
September resolves to September even if the run happens later.
"""
import calendar
import re
from datetime import datetime, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]

_ORDINAL_DAY_RE = re.compile(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", re.I)
_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(m[:3] for m in MONTHS) + r")[a-z]*\.?\s+(\d{1,2})\b", re.I
)
_WEEKDAY_RE = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b", re.I)
# When a sentence names two weekdays ("move it from Thursday to Wednesday
# at 2pm"), the one actually being committed to is the one sitting right
# next to the clock time -- prefer that over the first weekday mentioned.
_WEEKDAY_AT_TIME_RE = re.compile(
    r"\b(" + "|".join(WEEKDAYS) + r")\b\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)", re.I
)
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_BY_WEEKDAY_RE = re.compile(r"\bby (" + "|".join(WEEKDAYS) + r")\b", re.I)
_MONTH_END_RE = re.compile(r"\bbefore month-end\b|\bby month-end\b", re.I)
_RELATIVE_HOURS_RE = re.compile(r"\bin (\d+)\s*hours?\b", re.I)
_DAYS_BEFORE_RE = re.compile(r"\b(\d+|two|three|four|five)\s+days?\s+before\b", re.I)

_WORD_NUM = {"two": 2, "three": 3, "four": 4, "five": 5}


def _day_of_week(dt):
    return dt.weekday()  # Monday=0


def resolve_weekday_on_or_after(ref_dt, weekday_name, on_or_after=True):
    target = WEEKDAYS.index(weekday_name.lower())
    delta = (target - _day_of_week(ref_dt)) % 7
    if delta == 0 and not on_or_after:
        delta = 7
    return ref_dt + timedelta(days=delta)


def extract_time_of_day(text):
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "pm" and hour != 12:
        hour += 12
    if m.group(3).lower() == "am" and hour == 12:
        hour = 0
    return hour, minute


def _explicit_day(text, ref_dt):
    """Look anywhere in the text for an explicit day-of-month, either as
    "the Nth" or "<Month> N" (e.g. "September 15"). Returns (month, day) or
    None. Preferring an explicit day beats inferring one from a weekday
    name, since "Tuesday, September 15" and "Tuesday" alone need different
    handling -- the former names an exact date, the latter needs the next
    occurrence of that weekday computed."""
    md = _MONTH_DAY_RE.search(text)
    if md:
        month = [m[:3] for m in MONTHS].index(md.group(1).lower()) + 1
        return month, int(md.group(2))
    od = _ORDINAL_DAY_RE.search(text)
    if od:
        return ref_dt.month, int(od.group(1))
    return None


def extract_deadline(text, ref_dt):
    """Best-effort single deadline/commitment datetime (or a plain string
    for things that aren't a specific instant, e.g. "month-end"). Returns
    (datetime_or_None, display_string_or_None, has_explicit_time_bool).
    has_explicit_time distinguishes a real clock-time appointment (used for
    double-booking conflicts) from a date-only deadline (used for the
    commitments list but never treated as a same-time conflict)."""
    explicit = _explicit_day(text, ref_dt)
    wd = _WEEKDAY_AT_TIME_RE.search(text) or _WEEKDAY_RE.search(text)
    if explicit:
        month, day = explicit
        try:
            dt = ref_dt.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            return None, None, False
        tod = extract_time_of_day(text)
        if tod:
            dt = dt.replace(hour=tod[0], minute=tod[1])
        return dt, dt.strftime("%a %b %d" + (" %H:%M" if tod else "")), bool(tod)
    if wd:
        dt = resolve_weekday_on_or_after(ref_dt, wd.group(1))
        tod = extract_time_of_day(text)
        if tod:
            dt = dt.replace(hour=tod[0], minute=tod[1], second=0, microsecond=0)
        else:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt, dt.strftime("%a %b %d" + (" %H:%M" if tod else "")), bool(tod)

    if _MONTH_END_RE.search(text):
        last_day = calendar.monthrange(ref_dt.year, ref_dt.month)[1]
        dt = ref_dt.replace(day=last_day, hour=23, minute=59, second=0, microsecond=0)
        return dt, "month-end (" + dt.strftime("%b %d") + ")", False

    rel = _RELATIVE_HOURS_RE.search(text)
    if rel:
        dt = ref_dt + timedelta(hours=int(rel.group(1)))
        return dt, f"within {rel.group(1)}h of {ref_dt.strftime('%b %d %H:%M')}", True

    return None, None, False


def extract_days_before_reference(text):
    """For phrasing like 'two days before the board review' -- returns the
    integer offset and a short keyword to match against another message
    describing the anchor event, or None."""
    m = _DAYS_BEFORE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).lower()
    n = _WORD_NUM.get(raw, None)
    if n is None:
        n = int(raw)
    # crude anchor keyword: text right after "before"
    tail = text[m.end():].strip()
    anchor_keyword = re.split(r"[.,;?!]", tail)[0].strip()
    return n, anchor_keyword
