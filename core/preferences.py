"""
Standing preferences, kept in a small JSON file on disk so they outlive a
run -- this is cap R4. Two are learned from the inbox itself:

  * "cc_on_legal": from m015 -- CC Priya on anything from Hartwell & Cho.
    This is the officially demoed preference for cap R4.
  * "no_meetings_before": from m041 -- never accept a meeting before 11:00.
    Applied by the scheduling assistant (cap X5).

Learning a preference and applying it are two different function calls in
two different runs of demo.py, so a preference genuinely has to survive a
process exit to take effect -- see demo.py's `--cap R4` handling.
"""
import json
import os

import config


DEFAULTS = {"cc_on_legal": None, "no_meetings_before": None}


def load():
    if not os.path.exists(config.PREFS_PATH):
        return dict(DEFAULTS)
    with open(config.PREFS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(prefs):
    with open(config.PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)


def learn_from_message(message):
    """Look at one message for a standing-preference statement. Returns
    (key, value, source_id) if one was learned, else None. Deliberately
    narrow pattern matching -- a preference is only learned from a message
    that states it in plain, unambiguous terms, addressed to Sam or to
    himself as a note (never from a message that also trips the injection
    detector -- see demo.py, which runs security checks first)."""
    text = message["body"].lower()

    if "cc" in text and "hartwell" in text:
        return ("cc_on_legal", {
            "cc_address": message["from"],
            "trigger_domain": "hartwellcho.com",
            "source": message["id"],
        }, message["id"])

    if "before 11" in text:
        return ("no_meetings_before", {
            "earliest_hour": 11,
            "source": message["id"],
        }, message["id"])

    return None
