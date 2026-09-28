"""
Cap R1 (and the backbone the rest of the demo hangs off of). Walks every
message once and assigns exactly one of:

  reply     -- Sam owes a response; a grounded draft is attached when one
               can be produced, otherwise the message is held with a
               stated reason instead of a guessed draft.
  archive   -- no further action needed (noise, an already-answered
               thread, an FYI, or a preference that's been recorded).
  defer     -- worth a look but not now, and not something the system
               should guess at (ambiguous, personal, or a low-urgency
               internal reminder).
  delegate  -- the ball is in someone else's court; Sam is the sender and
               is waiting on a reply (tracked by cap X1).
  escalate  -- needs Sam directly: a scheduling conflict, a decision only
               he can make, or a message flagged as hostile or suspicious.

Rule-based checks run first and are cheap: noise, internal notices,
thread-resolved, injections, phishing. Only messages that survive all of
that reach template-based drafting, and only a few of *those* need the
scheduler or cross-thread lookup. This is what cap R1's "rule_handled"
count measures.
"""
import re

from core import rules, security, drafting, scheduler
from core.tracing import log_event

CREDENTIAL_RESEND_RE = re.compile(r"resend.*\b(url|creds?|credentials?)\b|don.t want to rotate", re.I)


def _reason(text):
    return text


def classify_one(message, store, prefs, all_commitments, owner_email, owner_domain, known_domains):
    """Returns a decision dict for one message. Order matters: security
    checks run before anything else, so a message can't talk its way out
    of being flagged by also looking like noise or a preference."""

    is_injection, injection_reason = security.detect_injection(message)
    if is_injection:
        return {
            "id": message["id"], "disposition": "escalate",
            "category": "hostile-injection", "reason": injection_reason,
            "flagged": True, "refused": True, "draft": None,
        }

    is_social_eng, se_reason = security.detect_social_engineering(message, known_domains)
    if is_social_eng:
        return {
            "id": message["id"], "disposition": "escalate",
            "category": "suspicious", "reason": se_reason,
            "flagged": True, "refused": False, "draft": None,
        }

    if rules.is_self_note(message, owner_email):
        learned = prefs.get("_last_learned_from") == message["id"]
        reason = "standing preference recorded" if learned else "self-addressed note"
        return {
            "id": message["id"], "disposition": "archive", "category": "preference",
            "reason": reason, "flagged": False, "refused": False, "draft": None,
        }

    if rules.is_transactional_noise(message):
        return {
            "id": message["id"], "disposition": "archive", "category": "noise",
            "reason": "automated notification, no action needed",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.is_internal_system_notice(message, owner_domain):
        if rules.needs_real_world_action(message):
            return {
                "id": message["id"], "disposition": "defer", "category": "internal-fyi-actionable",
                "reason": "internal reminder with an action item, not urgent enough to draft",
                "flagged": False, "refused": False, "draft": None,
            }
        return {
            "id": message["id"], "disposition": "archive", "category": "internal-fyi",
            "reason": "internal notice, informational only",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.is_sent_by_owner(message, owner_email):
        newer = rules.thread_continued_after(message, store)
        if newer:
            return {
                "id": message["id"], "disposition": "archive", "category": "resolved",
                "reason": f"thread continued and resolved (see {newer})",
                "flagged": False, "refused": False, "draft": None,
            }
        return {
            "id": message["id"], "disposition": "delegate", "category": "awaiting-reply",
            "reason": "Sam is waiting on a reply to this", "flagged": False,
            "refused": False, "draft": None,
        }

    newer = rules.thread_already_answered(message, store, owner_email)
    if newer:
        return {
            "id": message["id"], "disposition": "archive", "category": "resolved",
            "reason": f"already answered in-thread (see {newer})",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.proposes_meeting(message):
        outcome = scheduler.evaluate(message, all_commitments, prefs)
        if outcome["outcome"] == "conflict":
            return {
                "id": message["id"], "disposition": "escalate", "category": "scheduling-conflict",
                "reason": outcome["reason"], "flagged": False, "refused": False, "draft": None,
            }
        if outcome["outcome"] in ("counter", "confirm"):
            return {
                "id": message["id"], "disposition": "reply", "category": "scheduling",
                "reason": outcome["reason"], "flagged": False, "refused": False,
                "draft": {"body": outcome["draft"], "cited_ids": outcome.get("cited_ids", [])},
            }
        # unparsed proposal -- fall through to generic handling below

    if rules.is_vague(message):
        return {
            "id": message["id"], "disposition": "defer", "category": "ambiguous",
            "reason": "no concrete, groundable ask -- needs Sam's input rather than a guess",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.is_personal(message, owner_domain, known_domains):
        return {
            "id": message["id"], "disposition": "defer", "category": "personal",
            "reason": "personal message, not business-critical",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.is_hiring_decision(message):
        return {
            "id": message["id"], "disposition": "escalate", "category": "needs-personal-judgment",
            "reason": "a hiring/compensation decision -- nothing in the mailbox to ground an answer",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.states_own_closure(message):
        return {
            "id": message["id"], "disposition": "archive", "category": "fyi-closed",
            "reason": "sender explicitly says there's nothing to do",
            "flagged": False, "refused": False, "draft": None,
        }

    if rules.is_group_thread(message, store) and "?" not in message["body"] and not rules.mentions_owner_by_name(
            message, owner_email.split("@")[0].split(".")[0].title()):
        return {
            "id": message["id"], "disposition": "archive", "category": "team-update",
            "reason": "status update in a shared thread, no direct ask of Sam",
            "flagged": False, "refused": False, "draft": None,
        }

    # Real business correspondence needing a reply. Pick a drafting path.
    body_low = message["body"].lower()
    domain = message["from"].split("@")[-1].lower()

    if CREDENTIAL_RESEND_RE.search(message["body"]):
        d = drafting.draft_credential_reply(message, store)
        category = "grounded-reply"
    elif domain == "techbrief.news":
        d = drafting.draft_press_reply(message, store)
        category = "grounded-reply-cross-thread"
    elif domain == "hartwellcho.com":
        d = drafting.draft_legal_ack(message, prefs)
        category = "legal-ack"
    else:
        d = drafting.draft_generic_ack(message)
        category = "ack"

    return {
        "id": message["id"], "disposition": "reply", "category": category,
        "reason": "awaiting a reply from Sam" if d.get("grounded", True) else
                  "awaiting a reply from Sam; not enough in the mailbox to draft confidently",
        "flagged": False, "refused": False, "draft": d,
    }


def classify_all(all_messages, store, prefs, all_commitments, owner_email, owner_domain, known_domains, cap="R1"):
    decisions = []
    for message in all_messages:
        d = classify_one(message, store, prefs, all_commitments, owner_email, owner_domain, known_domains)
        decisions.append(d)
        if cap:
            log_event(cap, "decision", message_id=d["id"], disposition=d["disposition"],
                  category=d["category"], reason=d["reason"])
    return decisions
