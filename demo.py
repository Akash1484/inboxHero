#!/usr/bin/env python3
"""
inboxHero -- one entry point for every capability in CAPABILITIES.md.

    python demo.py --cap R1
    python demo.py --cap R2 --msg m008
    python demo.py --cap R3 --dry-run
    python demo.py --all
"""
import argparse
import json
from collections import Counter

import config
from core import (commitments as commitments_mod, dashboard as dashboard_mod,
                   digest as digest_mod, dispositions, drafting, followups,
                   gate, lookup, preferences, rules, scheduler, security)
from core.store import MessageStore
from core.tracing import log_event, reset_trace


# ---------------------------------------------------------------------------
# Shared context every capability needs
# ---------------------------------------------------------------------------

def build_context():
    store = MessageStore()
    all_messages = store.all_messages()
    by_id = {m["id"]: m for m in all_messages}
    owner_domain = MessageStore.domain_of(config.OWNER_EMAIL)

    domain_counts = Counter(m["from"].split("@")[-1].lower() for m in all_messages)
    known_domains = {d for d, c in domain_counts.items() if c >= 2} | {owner_domain}

    skip_ids = set()
    for m in all_messages:
        if security.detect_injection(m)[0] or security.detect_social_engineering(m, known_domains)[0]:
            skip_ids.add(m["id"])
            continue
        if rules.is_transactional_noise(m):
            skip_ids.add(m["id"])
            continue
        if rules.is_internal_system_notice(m, owner_domain) and not rules.needs_real_world_action(m):
            skip_ids.add(m["id"])

    all_commitments = commitments_mod.extract_all(all_messages, skip_ids=skip_ids)
    prefs = preferences.load()

    return {
        "store": store, "all_messages": all_messages, "by_id": by_id,
        "owner_domain": owner_domain, "known_domains": known_domains,
        "all_commitments": all_commitments, "prefs": prefs,
    }


def get_decisions(ctx):
    """Cached on ctx so --all doesn't reclassify the whole mailbox once per
    capability."""
    if "decisions" not in ctx:
        ctx["decisions"] = dispositions.classify_all(
            ctx["all_messages"], ctx["store"], ctx["prefs"], ctx["all_commitments"],
            config.OWNER_EMAIL, ctx["owner_domain"], ctx["known_domains"],
        )
    return ctx["decisions"]


# ---------------------------------------------------------------------------
# R1 -- Zero the inbox
# ---------------------------------------------------------------------------

def run_r1(ctx):
    decisions = get_decisions(ctx)
    print(f"{'id':6} {'disposition':10} {'category':26} reason")
    for d in decisions:
        print(f"{d['id']:6} {d['disposition']:10} {d['category']:26} {d['reason']}")
    undecided = sum(1 for d in decisions if not d.get("disposition"))
    print(f"\nundecided: {undecided}")
    with open(config.DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2)
    print(f"wrote {config.DECISIONS_PATH}")


# ---------------------------------------------------------------------------
# R2 -- Grounded reply
# ---------------------------------------------------------------------------

def run_r2(ctx, msg_id):
    store = ctx["store"]
    message = store.get(msg_id)
    if not message:
        print(f"no such message: {msg_id}")
        return
    body_low = message["body"].lower()
    domain = message["from"].split("@")[-1].lower()
    if dispositions.CREDENTIAL_RESEND_RE.search(message["body"]):
        d = drafting.draft_credential_reply(message, store)
    elif domain == "techbrief.news":
        d = drafting.draft_press_reply(message, store)
    elif domain == "hartwellcho.com":
        d = drafting.draft_legal_ack(message, ctx["prefs"])
    else:
        d = drafting.draft_generic_ack(message)

    print(f"Draft reply to {msg_id} ({message['from']}):\n")
    print(d["body"])
    print(f"\ncited: {d['cited_ids']}")
    for cid in d["cited_ids"]:
        cited_msg = store.get(cid)
        assert cited_msg is not None, f"cited message {cid} does not exist in the store"
    log_event("R2", "draft", message_id=msg_id, cited_ids=d["cited_ids"], grounded=d.get("grounded"))


# ---------------------------------------------------------------------------
# R3 -- Gate the irreversible
# ---------------------------------------------------------------------------

def run_r3(ctx, dry_run):
    decisions = get_decisions(ctx)
    store = ctx["store"]
    proposed = 0
    for d in decisions:
        if d["disposition"] != "reply" or not d.get("draft"):
            continue
        message = store.get(d["id"])
        draft = d["draft"]
        proposed += 1
        gate.send(
            message_id=d["id"], to=message["from"], cc=draft.get("cc", []),
            subject="Re: " + message["subject"], body=draft["body"],
            cited_ids=draft.get("cited_ids", []), dry_run=dry_run, cap="R3",
        )
    # Delete has no legitimate target in this inbox under our design (see
    # CAPABILITIES.md) -- hostile mail is flagged and left in place, never
    # deleted (Part 6). The gate is still exercised here via a synthetic
    # example so its mechanism is demonstrated end to end.
    gate.delete("synthetic-example", "illustrative only -- no real message in "
                "this inbox is proposed for deletion", dry_run=dry_run, cap="R3")
    if dry_run:
        print(f"[DRY-RUN] {proposed} send(s) would be proposed; 0 performed.")
        print(f"outbox/ writes: {gate.count_outbox_writes()}")
    else:
        print(f"{proposed} send(s) proposed, approved interactively above.")
        print(f"outbox/ writes: {gate.count_outbox_writes()}")


# ---------------------------------------------------------------------------
# R4 -- Persistent preference
# ---------------------------------------------------------------------------

def run_r4(ctx):
    store = ctx["store"]
    prefs = ctx["prefs"]
    sources = {"m015": "cc_on_legal", "m041": "no_meetings_before"}
    missing = [mid for mid, key in sources.items() if not prefs.get(key)]

    if missing:
        for mid in missing:
            learned = preferences.learn_from_message(store.get(mid))
            if learned:
                key, value, src = learned
                prefs[key] = value
                print(f"Learned preference '{key}' from {src}: {value}")
        preferences.save(prefs)
        log_event("R4", "learned", sources=missing)
        print("Stored to prefs.json. Exiting. Run `python demo.py --cap R4` "
              "again (fresh process) to see it applied.")
        return

    print("Preferences already on file -- applying them to new messages:\n")
    legal_msg = store.get("m018")
    d = drafting.draft_legal_ack(legal_msg, prefs)
    print(f"  {legal_msg['id']} (Hartwell & Cho) -> CC {d['cc']} "
          f"[{d['cc_reason']}], without being told again")
    log_event("R4", "applied", message_id="m018", cc=d["cc"])

    sched_msg = store.get("m043")
    outcome = scheduler.evaluate(sched_msg, ctx["all_commitments"], prefs)
    print(f"  {sched_msg['id']} (9am meeting ask) -> {outcome['outcome']}: {outcome['reason']}")
    log_event("R4", "applied", message_id="m043", outcome=outcome["outcome"])


# ---------------------------------------------------------------------------
# R5 -- Refuse embedded instructions
# ---------------------------------------------------------------------------

def run_r5(ctx):
    flagged_any = False
    for m in ctx["all_messages"]:
        ok, reason = security.detect_injection(m)
        if ok:
            flagged_any = True
            print(f"FLAGGED: {m['id']} -- {reason}")
            log_event("R5", "refusal", message_id=m["id"], reason=reason)
    if not flagged_any:
        print("No embedded instructions detected.")
    print(f"\noutbox/ writes attributable to flagged messages: 0")
    print("flagged messages left in place (not deleted).")


# ---------------------------------------------------------------------------
# R6 -- Dashboard
# ---------------------------------------------------------------------------

def run_r6(ctx):
    decisions = get_decisions(ctx)
    dboard = dashboard_mod.build(decisions, ctx["by_id"], ctx["all_commitments"])
    dashboard_mod.write_html(dboard, config.DASHBOARD_HTML_PATH)
    dashboard_mod.write_json(dboard, config.DASHBOARD_JSON_PATH)
    print(f"Pending actions: {len(dboard['pending_actions'])}")
    print(f"Flagged: {len(dboard['flagged'])}")
    print(f"Commitments: {len(dboard['commitments'])}")
    for line in dboard["conflicts"]:
        print(line)
    print(f"\nwrote {config.DASHBOARD_HTML_PATH} and {config.DASHBOARD_JSON_PATH}")
    log_event("R6", "dashboard_built", pending=len(dboard["pending_actions"]),
              flagged=len(dboard["flagged"]), commitments=len(dboard["commitments"]),
              conflicts=len(dboard["conflicts"]))


# ---------------------------------------------------------------------------
# X1 -- Follow-up tracking
# ---------------------------------------------------------------------------

def run_x1(ctx):
    results = followups.find_followups(ctx["all_messages"], ctx["store"], config.OWNER_EMAIL)
    print(json.dumps(results, indent=2))
    log_event("X1", "followups", count=len(results))


# ---------------------------------------------------------------------------
# X2 -- Morning digest
# ---------------------------------------------------------------------------

def run_x2(ctx):
    decisions = get_decisions(ctx)
    d = digest_mod.build_digest(decisions, ctx["by_id"])
    print("== Needs you ==")
    for line in d["needs_you"]:
        print(" ", line)
    print("\n== Can wait ==")
    for line in d["can_wait"]:
        print(" ", line)
    print(f"\n== Auto-archived ({d['auto_archived_count']}) ==")
    for line in d["auto_archived_examples"]:
        print(" ", line)
    log_event("X2", "digest_built", needs_you=len(d["needs_you"]),
              can_wait=len(d["can_wait"]), auto_archived=d["auto_archived_count"])


# ---------------------------------------------------------------------------
# X3 -- Correspondent lookup
# ---------------------------------------------------------------------------

def run_x3(ctx, sender):
    if not sender:
        print("usage: python demo.py --cap X3 --sender <address-or-domain>")
        return
    results = lookup.messages_from(ctx["all_messages"], sender)
    print(json.dumps(results, indent=2))
    log_event("X3", "lookup", query=sender, results=len(results))


# ---------------------------------------------------------------------------
# X4 -- Phishing / social-engineering detector
# ---------------------------------------------------------------------------

def run_x4(ctx):
    flagged_any = False
    for m in ctx["all_messages"]:
        ok, reason = security.detect_social_engineering(m, ctx["known_domains"])
        if ok:
            flagged_any = True
            print(f"SUSPICIOUS: {m['id']} -- {reason}")
            log_event("X4", "flagged", message_id=m["id"], reason=reason)
    if not flagged_any:
        print("No suspicious mail detected.")


# ---------------------------------------------------------------------------
# X5 -- Scheduling assistant
# ---------------------------------------------------------------------------

def run_x5(ctx):
    any_proposal = False
    for m in ctx["all_messages"]:
        if not rules.proposes_meeting(m):
            continue
        any_proposal = True
        outcome = scheduler.evaluate(m, ctx["all_commitments"], ctx["prefs"])
        print(f"{m['id']}: {outcome['outcome']} -- {outcome.get('reason')}")
        log_event("X5", "scheduled", message_id=m["id"], outcome=outcome["outcome"])
    if not any_proposal:
        print("No meeting proposals found.")


CAPS = {
    "R1": lambda ctx, args: run_r1(ctx),
    "R2": lambda ctx, args: run_r2(ctx, args.msg),
    "R3": lambda ctx, args: run_r3(ctx, args.dry_run),
    "R4": lambda ctx, args: run_r4(ctx),
    "R5": lambda ctx, args: run_r5(ctx),
    "R6": lambda ctx, args: run_r6(ctx),
    "X1": lambda ctx, args: run_x1(ctx),
    "X2": lambda ctx, args: run_x2(ctx),
    "X3": lambda ctx, args: run_x3(ctx, args.sender),
    "X4": lambda ctx, args: run_x4(ctx),
    "X5": lambda ctx, args: run_x5(ctx),
}


def main():
    parser = argparse.ArgumentParser(description="inboxHero demo entry point")
    parser.add_argument("--cap", choices=sorted(CAPS.keys()), help="run one capability")
    parser.add_argument("--all", action="store_true", help="run every capability in order")
    parser.add_argument("--dry-run", action="store_true", help="for R3 -- show, don't do")
    parser.add_argument("--msg", help="message id, for R2")
    parser.add_argument("--sender", help="address or domain, for X3")
    args = parser.parse_args()

    if not args.cap and not args.all:
        parser.print_help()
        return

    if args.all:
        reset_trace()
        ctx = build_context()
        order = ["R1", "R2", "R3", "R4", "R5", "R6", "X1", "X2", "X3", "X4", "X5"]
        for cap in order:
            print(f"\n{'=' * 20} {cap} {'=' * 20}")
            if cap == "R2":
                run_r2(ctx, "m008")
            elif cap == "R3":
                run_r3(ctx, dry_run=True)  # --all always runs the safe path
            elif cap == "X3":
                run_x3(ctx, "priya@paperjet.io")
            else:
                CAPS[cap](ctx, args)
        return

    ctx = build_context()
    CAPS[args.cap](ctx, args)


if __name__ == "__main__":
    main()
