"""
Cap X5. A meeting proposal gets one of three outcomes:

  * CONFLICT -- it lands on the same clock-time as something already
    confirmed elsewhere in the mailbox. Held for Sam; nothing is drafted,
    because picking which one wins isn't the system's call.
  * COUNTER -- it violates the standing "no meetings before 11:00"
    preference (cap R4's second demoed preference). The system already
    knows the rule and the correct response, so it drafts a counter-offer
    without asking Sam to repeat himself.
  * CONFIRM -- neither problem applies; draft a plain confirmation.

This is the tier-C capability that ties memory (a persisted preference),
multi-message reasoning (the shared commitments list) and a held-for-human
outcome together in one place.
"""
from core import dates, store as store_mod
from core.llm import generate


def evaluate(message, all_commitments, prefs):
    ref = store_mod.MessageStore.parse_ts(message["timestamp"])
    dt, display, has_time = dates.extract_deadline(message["body"], ref)
    if not dt or not has_time:
        return {"outcome": "unparsed", "reason": "could not find a specific proposed time"}

    # Conflict check: same clock-time as an existing timed commitment from
    # a different message.
    for c in all_commitments:
        if not c.get("has_time"):
            continue
        if c["when"] == dt and message["id"] not in c["message_ids"]:
            other_id = c["message_ids"][0]
            return {
                "outcome": "conflict",
                "reason": f"proposed {display} conflicts with an existing commitment ({c['label']}, ref {other_id})",
                "conflicts_with": other_id,
                "proposed": dt,
            }

    # Preference check: no meetings before the stated hour.
    pref = prefs.get("no_meetings_before")
    if pref and dt.hour < pref["earliest_hour"]:
        counter_hour = pref["earliest_hour"]
        body = generate(
            f"Thanks for the offer -- {display} is a bit early for Sam's calendar "
            f"(standing rule: nothing before {counter_hour}:00). Could we do "
            f"{counter_hour}:00 or later that day instead?"
        )
        return {
            "outcome": "counter",
            "reason": f"proposed {display} is before Sam's {counter_hour}:00 floor (pref from {pref['source']})",
            "draft": body,
            "cited_ids": [pref["source"]],
            "proposed": dt,
        }

    body = generate(f"That works -- confirming {display}.")
    return {"outcome": "confirm", "reason": f"{display} is clear and within Sam's preferences",
            "draft": body, "cited_ids": [], "proposed": dt}
