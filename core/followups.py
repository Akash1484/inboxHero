"""
Cap X1. Finds messages Sam sent that are still waiting on a reply 3+ days
later (see rules.is_sent_by_owner + rules.thread_already_answered, which
this reuses rather than re-implementing thread-walk logic) and drafts a
one-line chase for each.
"""
from datetime import datetime

import config
from core import rules
from core.llm import generate
from core.store import MessageStore


def find_followups(all_messages, store, owner_email, now=None, days=None):
    now = now or MessageStore.parse_ts(config.DEMO_NOW)
    days = days if days is not None else config.FOLLOWUP_DAYS
    results = []
    for m in all_messages:
        if not rules.is_sent_by_owner(m, owner_email):
            continue
        if rules.thread_continued_after(m, store):
            continue  # someone replied -- not a follow-up candidate
        sent_at = MessageStore.parse_ts(m["timestamp"])
        waiting_days = (now - sent_at).days
        if waiting_days < days:
            continue
        recipient_name = m["to"].split("@")[0].title()
        draft = generate(
            f"Hi {recipient_name} -- following up on this ({m['subject']}), "
            f"in case it slipped. Same ask as before, no rush but keen to close it out."
        )
        results.append({
            "message_id": m["id"], "days_waiting": waiting_days,
            "to": m["to"], "subject": m["subject"], "draft": draft,
        })
    return results
