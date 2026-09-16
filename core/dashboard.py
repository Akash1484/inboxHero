"""
Cap R6. One dashboard, three panes, built entirely from cap R1's decisions
plus the shared commitments list (core/commitments.py) -- reproducible from
a run, never hand-assembled.

  Pending actions -- everything the system wants to do but can't do alone
                     under the Part 4 gate (every 'reply' with a draft that
                     would need sending, every 'escalate').
  Flagged         -- everything refused: hostile injections (R5) and
                     suspicious/phishing mail (X4).
  Commitments     -- dated obligations, cited to source, conflicts called
                     out explicitly rather than left for the reader to spot.
"""
import json

from core import commitments as commitments_mod


def build(decisions, by_id, all_commitments):
    pending = []
    for d in decisions:
        if d["disposition"] == "reply" and d.get("draft"):
            m = by_id[d["id"]]
            pending.append({
                "message_id": d["id"], "from": m["from"], "subject": m["subject"],
                "proposed_action": "send reply", "why_it_needs_a_human":
                    "sending is irreversible -- held for approval (cap R3 gate)",
            })
        elif d["disposition"] == "escalate":
            m = by_id[d["id"]]
            pending.append({
                "message_id": d["id"], "from": m["from"], "subject": m["subject"],
                "proposed_action": d["category"], "why_it_needs_a_human": d["reason"],
            })

    flagged = []
    for d in decisions:
        if d.get("flagged"):
            m = by_id[d["id"]]
            flagged.append({
                "message_id": d["id"], "from": m["from"], "subject": m["subject"],
                "kind": d["category"], "what_was_attempted": d["reason"],
                "what_the_system_did": "refused; left in place, not deleted" if d.get("refused")
                                        else "held for Sam's review, nothing sent",
            })

    conflicts = commitments_mod.find_conflicts(all_commitments)
    conflict_message_ids = set()
    for c in conflicts:
        for entry in c["commitments"]:
            conflict_message_ids.update(entry["message_ids"])

    commitments_out = []
    for c in all_commitments:
        commitments_out.append({
            "message_ids": c["message_ids"], "label": c["label"], "when": c["display"],
            "conflict": bool(conflict_message_ids & set(c["message_ids"])),
        })
    commitments_out.sort(key=lambda c: c["when"] or "")

    conflict_lines = [
        f"CONFLICT: {', '.join(sorted({e['label'] for e in c['commitments']}))} "
        f"both at {c['when'].strftime('%a %b %d %H:%M')} "
        f"(refs {', '.join(sorted({mid for e in c['commitments'] for mid in e['message_ids']}))})"
        for c in conflicts
    ]

    return {
        "pending_actions": pending,
        "flagged": flagged,
        "commitments": commitments_out,
        "conflicts": conflict_lines,
    }


def write_html(dashboard, path):
    def rows(items, cols):
        out = []
        for it in items:
            out.append("<tr>" + "".join(f"<td>{it.get(c,'')}</td>" for c in cols) + "</tr>")
        return "\n".join(out)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>inboxHero dashboard</title>
<style>
body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 2rem; color: #1a1a1a; }}
h2 {{ border-bottom: 2px solid #333; padding-bottom: .25rem; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin-top: .5rem; }}
td, th {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 14px; }}
th {{ background: #f4f4f4; }}
.conflict {{ background: #ffe9e9; font-weight: bold; }}
.conflicts-box {{ background: #fff3cd; padding: .75rem 1rem; border-radius: 6px; }}
</style></head><body>
<h1>inboxHero -- run dashboard</h1>

<h2>Pending actions ({len(dashboard['pending_actions'])})</h2>
<table><tr><th>Message</th><th>From</th><th>Subject</th><th>Proposed action</th><th>Why it needs a human</th></tr>
{rows(dashboard['pending_actions'], ['message_id','from','subject','proposed_action','why_it_needs_a_human'])}
</table>

<h2>Flagged ({len(dashboard['flagged'])})</h2>
<table><tr><th>Message</th><th>From</th><th>Subject</th><th>Kind</th><th>Attempted</th><th>System did</th></tr>
{rows(dashboard['flagged'], ['message_id','from','subject','kind','what_was_attempted','what_the_system_did'])}
</table>

<h2>Commitments ({len(dashboard['commitments'])})</h2>
<div class="conflicts-box">
{'<br>'.join(dashboard['conflicts']) if dashboard['conflicts'] else 'No conflicts detected.'}
</div>
<table><tr><th>When</th><th>What</th><th>Sources</th></tr>
{"".join(f'<tr class="{"conflict" if c["conflict"] else ""}"><td>{c["when"]}</td><td>{c["label"]}</td><td>{", ".join(c["message_ids"])}</td></tr>' for c in dashboard['commitments'])}
</table>

</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def write_json(dashboard, path):
    serializable = dict(dashboard)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, default=str)
