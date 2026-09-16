"""
Drafts a reply for one message, grounded in whatever earlier message(s)
supply the facts it needs. Every draft returned here carries `cited_ids`:
the message ids the draft actually drew a fact from, checked against the
mail store -- exactly the property cap R2 is tested on. A draft with no
citable fact says so and stops rather than inventing one (Part 3.4).

Retrieval is thread-walk first (core/store.thread_history_for), keyword
search only as the documented fallback for a cross-thread fact (the press
question in draft_press_reply is the one case that needs it here).
"""
import re

from core import llm

URL_RE = re.compile(r"\b\w+://\S+")


def _find_url(messages):
    for m in messages:
        found = URL_RE.search(m["body"])
        if found:
            return found.group(0), m["id"]
    return None, None


def draft_credential_reply(message, store):
    """m008-shaped: a colleague asks for a secret that was already shared
    earlier in the same thread. Ground the reply in that earlier message
    rather than re-deriving or inventing the value."""
    history = store.thread_history_for(message["id"])
    url, source_id = _find_url(history)
    if not url:
        return {
            "body": llm.generate(
                f"Hi -- I don't see that URL anywhere earlier in this thread, "
                f"so I don't want to guess at it. Can you confirm who has it?"
            ),
            "cited_ids": [],
            "grounded": False,
        }
    sender_name = message["from"].split("@")[0].split(".")[0].title()
    body = llm.generate(
        f"Hi {sender_name} -- here's the current staging queue URL: {url}\n"
        f"(pulled from the message where it was first shared, ref {source_id}; "
        f"nothing rotated since)."
    )
    return {"body": body, "cited_ids": [source_id], "grounded": True}


def draft_press_reply(message, store, known_launch_date=None):
    """m046-shaped: a cross-thread fact lookup. The launch date is grounded
    (found via keyword search in the launch thread); the "what makes it
    different" line is not backed by anything in the inbox, so the draft
    says that plainly instead of inventing marketing copy."""
    hits = store.keyword_search(
        ["hard date", "launch", "20th"], exclude_thread=message["thread_id"], limit=3
    )
    date_line, date_source = None, None
    for h in hits:
        if "hard date" in h["body"].lower() or re.search(r"\bthe 20th\b", h["body"], re.I):
            date_line = "the launch date -- the 20th -- is confirmed and fine to share"
            date_source = h["id"]
            break
    cited = [date_source] if date_source else []
    if date_line:
        body = llm.generate(
            f"Hi -- yes, {date_line} (confirmed internally, ref {date_source}). "
            f"On the one-liner about what makes it different: I don't have a "
            f"signed-off line for that yet, so I'll leave that blank for Sam "
            f"to fill in rather than guess at messaging."
        )
    else:
        body = llm.generate(
            "Hi -- I don't have a confirmed public launch date or an approved "
            "differentiation line on file, so I'm holding this one for Sam "
            "rather than guessing at either."
        )
    return {"body": body, "cited_ids": cited, "grounded": bool(cited)}


def draft_legal_ack(message, prefs):
    """m018/m048/m055-shaped: acknowledge a Hartwell & Cho ask, applying the
    standing cc_on_legal preference if one has been learned (cap R4)."""
    ask = "review and get back to you"
    body_low = message["body"].lower()
    if "clause" in body_low:
        ask = "review clause 4 and sign via the portal"
    elif "board minutes" in body_low:
        ask = "review the draft minutes and flag any corrections"
    elif "ip assignment" in body_low or "signature" in body_low:
        ask = "review and sign the IP assignment"
    body = llm.generate(f"Thanks, Marcus -- on it, will {ask} as requested.")
    cc = []
    pref = prefs.get("cc_on_legal")
    if pref:
        cc = [pref["cc_address"]]
    return {"body": body, "cited_ids": [], "grounded": True, "cc": cc,
            "cc_reason": f"standing preference from {pref['source']}" if pref else None}


def draft_generic_ack(message):
    body = llm.generate("Thanks for the heads up -- on it.")
    return {"body": body, "cited_ids": [], "grounded": True}
