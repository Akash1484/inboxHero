"""
Cap R3. Reversible actions (draft, label, archive, defer) run without a
prompt -- see dispositions.py, which calls no function from this file for
any of them. Only two functions in the whole codebase can cause an
irreversible effect (send, delete), and both are defined here, and both
call require_approval() before doing anything. Nothing else in the system
holds a reference to outbox-writing or delete code, which is the actual
answer to "how do you know a hostile message can't reach a send" -- there
is no path from message content to these two functions except through
demo.py's own dispatch loop, which only calls them after a human-reviewed
disposition says to, gated here either way.

Deleting is treated as irreversible in this design even though the mock
store has no real trash: the point of the classification is "could Sam get
this back without help", and a deleted mock message is gone the moment
os.remove-equivalent runs, exactly like a real inbox with an emptied trash.
"""
import json
import os

import config
from core.tracing import log_event

_writes_this_run = 0


def require_approval(prompt, dry_run, auto_approve=None):
    """The gate itself. Returns True/False. In --dry-run mode nothing is
    ever approved -- the point is to show what *would* happen without
    doing it. Outside dry-run, asks interactively unless a test harness
    supplies auto_approve (used only by this project's own test script,
    never by the demo path a grader runs)."""
    if dry_run:
        print(f"[DRY-RUN] would ask: {prompt}")
        return False
    if auto_approve is not None:
        return auto_approve
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer == "y"


def send(message_id, to, cc, subject, body, cited_ids, dry_run=False, auto_approve=None, cap="R3"):
    prompt = f"Send reply to {to} (re: {subject!r})?"
    approved = require_approval(prompt, dry_run, auto_approve)
    log_event(cap, "gate", action="send", message_id=message_id, to=to, cc=cc,
              proposed=True, decision="approved" if approved else (
                  "dry_run" if dry_run else "denied"))
    if not approved:
        return False
    global _writes_this_run
    os.makedirs(config.OUTBOX_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTBOX_DIR, f"{message_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "in_reply_to": message_id, "to": to, "cc": cc, "subject": subject,
            "body": body, "cited_ids": cited_ids,
        }, f, indent=2)
    _writes_this_run += 1
    log_event(cap, "sent", message_id=message_id, path=out_path)
    return True


def delete(message_id, reason, dry_run=False, auto_approve=None, cap="R3"):
    prompt = f"Delete message {message_id} ({reason})?"
    approved = require_approval(prompt, dry_run, auto_approve)
    log_event(cap, "gate", action="delete", message_id=message_id, reason=reason,
              proposed=True, decision="approved" if approved else (
                  "dry_run" if dry_run else "denied"))
    if not approved:
        return False
    log_event(cap, "deleted", message_id=message_id)
    return True


def count_outbox_writes():
    """Files written by send() during THIS process (not files already
    sitting in outbox/ from an earlier run)."""
    return _writes_this_run
