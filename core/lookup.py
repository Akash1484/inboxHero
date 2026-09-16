"""
Cap X3. Tier A: one lookup, one output. Lists every message from a given
sender or domain, most recent first. No classification, no drafting --
just a direct read of the store.
"""


def messages_from(all_messages, sender_or_domain):
    needle = sender_or_domain.lower()
    hits = [
        m for m in all_messages
        if needle in m["from"].lower()
    ]
    hits.sort(key=lambda m: m["timestamp"], reverse=True)
    return [
        {"id": m["id"], "from": m["from"], "subject": m["subject"],
         "timestamp": m["timestamp"], "unread": m["unread"]}
        for m in hits
    ]
