"""
Single source of truth for "what dated obligations are in this mailbox".
Used by cap R6 (dashboard commitments pane) and cap X5 (the scheduler checks
new proposals against these before confirming). Keeping it in one place
means a date only ever gets parsed one way, and a conflict found by the
dashboard is the same conflict the scheduler would refuse to double-book.
"""
from core import dates, store as store_mod


def extract_all(all_messages, skip_ids=frozenset()):
    """Returns a list of commitment dicts:
        {message_ids, when (datetime), display, label, has_time}
    `label` is a short human description of the event, taken from the
    subject line (cleaned of "Re:"/leading noise). `skip_ids` should carry
    every message this run already classified as noise, an internal
    system notice, or a hostile/suspicious message (see demo.py) --
    commitments are only worth extracting from substantive mail; a
    marketing receipt's "renews in 7 days" isn't an obligation of Sam's,
    and a phishing message's fake 2-hour deadline definitely isn't one."""
    commitments = []
    by_id = {m["id"]: m for m in all_messages}

    # Pass 1: direct commitments (a message names its own date/deadline).
    direct = {}
    for m in all_messages:
        if m["id"] in skip_ids:
            continue
        ref = store_mod.MessageStore.parse_ts(m["timestamp"])
        dt, disp, has_time = dates.extract_deadline(m["body"], ref)
        if dt:
            label = _clean_subject(m["subject"])
            entry = {"message_ids": [m["id"]], "when": dt, "display": disp,
                      "label": label, "has_time": has_time}
            commitments.append(entry)
            direct[m["id"]] = entry

    # Pass 2: relative commitments ("N days before <anchor>"), resolved
    # against another message's direct commitment -- this is the
    # multi-message case (see cap R6's manifest note).
    for m in all_messages:
        if m["id"] in skip_ids or m["id"] in direct:
            continue
        offset = dates.extract_days_before_reference(m["body"])
        if not offset:
            continue
        n_days, anchor_keyword = offset
        anchor = _find_anchor(anchor_keyword, direct, by_id, exclude_id=m["id"])
        if not anchor:
            continue
        anchor_entry = anchor
        when = anchor_entry["when"] - __import__("datetime").timedelta(days=n_days)
        label = _clean_subject(m["subject"])
        commitments.append({
            "message_ids": [m["id"]] + anchor_entry["message_ids"],
            "when": when,
            "display": when.strftime("%a %b %d"),
            "label": label,
            "has_time": anchor_entry["has_time"],
        })

    return commitments


def _clean_subject(subject):
    return subject.replace("Re: ", "").strip()


def _find_anchor(keyword, direct, by_id, exclude_id):
    keyword_words = [w for w in keyword.lower().split() if len(w) > 3]
    best = None
    for mid, entry in direct.items():
        if mid == exclude_id:
            continue
        hay = by_id[mid]["subject"].lower() + " " + by_id[mid]["body"].lower()
        if all(w in hay for w in keyword_words):
            best = entry
            break
    return best


def find_conflicts(commitments):
    """Groups *timed* commitments (has_time=True -- an actual clock-time
    appointment, not just a same-day deadline) by exact datetime; 2+ of them
    at the same instant is a double-booking, surfaced rather than silently
    listed (Part 7 requirement)."""
    timed = [c for c in commitments if c.get("has_time")]
    by_time = {}
    for c in timed:
        by_time.setdefault(c["when"], []).append(c)
    conflicts = []
    for when, group in by_time.items():
        all_ids = set()
        for c in group:
            all_ids.update(c["message_ids"])
        if len(group) > 1 and len(all_ids) > 1:
            conflicts.append({"when": when, "commitments": group})
    return conflicts
