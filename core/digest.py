"""
Cap X2. A one-screen morning digest built straight from cap R1's decisions
-- no separate classification pass, so the digest can never disagree with
the dashboard or the decisions file about what a message is.
"""


def build_digest(decisions, by_id):
    needs_you = [d for d in decisions if d["disposition"] == "escalate"]
    can_wait = [d for d in decisions if d["disposition"] in ("reply", "defer", "delegate")]
    auto_archived = [d for d in decisions if d["disposition"] == "archive"]

    def line(d):
        m = by_id[d["id"]]
        return f"{d['id']} ({m['from']}): {m['subject']} -- {d['reason']}"

    return {
        "needs_you": [line(d) for d in needs_you],
        "can_wait": [line(d) for d in can_wait],
        "auto_archived_count": len(auto_archived),
        "auto_archived_examples": [line(d) for d in auto_archived[:5]],
    }
