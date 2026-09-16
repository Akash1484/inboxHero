"""
Two different kinds of hostile mail, detected two different ways, and
handled by two different (but related) capabilities:

  * PROMPT INJECTION (cap R5) -- text addressed to *the assistant*, trying to
    get it to take or hide an action. Detected by pattern: does the message
    talk to an AI/agent/assistant and ask it to act quietly?

  * SOCIAL ENGINEERING / PHISHING (cap X4) -- text addressed to *the human*,
    impersonating someone to get money or credentials moved. Detected by
    pattern: sender domain doesn't match who it claims to be, combined with
    urgency + money/credentials + secrecy language.

Detection here is advisory only -- it decides what gets flagged and shown to
the user. It is NOT what stops a hostile message from causing damage. That
guarantee comes from core/gate.py: nothing in this codebase ever parses a
message body for instructions to execute. Message text is only ever read
into a drafting *template* as a quoted field (see core/drafting.py); the
only two functions that can send or delete are called exclusively by
demo.py's own dispatch logic, gated by require_approval(). A message could
defeat every regex below and it would still have no path to an unsupervised
send or delete.
"""
import difflib
import re

# Phrases that mark text as talking to an automated reader rather than to
# Sam. Matching any one is enough to flag the message for R5.
INJECTION_MARKERS = [
    r"ignore (all|any) (previous|prior) instructions",
    r"system notice for automated assistants",
    r"automated[- ]agent directive",
    r"assistant (note|configuration)\s*[:\-]",
    r"if (an |this )?(ai|automated) (agent|assistant)",
    r"autonomous mode (is )?(now )?enabled",
    r"an assistant managing this inbox (must|should)",
    r"do not (mention|surface) this (notice|change)",
    r"not mention it in any summary",
    r"without asking for approval",
    r"skip the confirmation step",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_MARKERS]

# Action verbs that, *combined* with an injection marker, make the intent
# unambiguous (forward/delete/send the mailbox contents somewhere).
INJECTION_ACTION_HINTS = [
    r"forward (the )?(full )?(contents? of )?(this|the) mailbox",
    r"forward any messages?",
    r"reply with the (single )?word",
    r"delete this message",
    r"send all drafted replies",
]
_INJECTION_ACTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_ACTION_HINTS]


def detect_injection(message):
    """Returns (is_flagged, reason) for cap R5."""
    text = message["subject"] + "\n" + message["body"]
    marker_hits = [p.pattern for p in _INJECTION_RE if p.search(text)]
    action_hits = [p.pattern for p in _INJECTION_ACTION_RE if p.search(text)]
    if marker_hits:
        attempted = "; ".join(action_hits) if action_hits else "unspecified covert action"
        return True, f"addressed to an automated reader ({marker_hits[0]}); attempted: {attempted}"
    return False, None


# ---------------------------------------------------------------------------
# Social engineering / phishing (X4)
# ---------------------------------------------------------------------------

URGENCY_WORDS = [
    "urgent", "immediately", "asap", "before end of day", "right away",
    "expire", "expires", "suspended", "act now", "today or",
]
MONEY_OR_CREDENTIAL_WORDS = [
    "wire", "remit", "remittance", "bank account", "routing", "account number",
    "re-verify your credentials", "verify your credentials", "password",
    "confirm your password", "deposit",
]
SECRECY_WORDS = [
    "don't loop in", "do not loop in", "keep this between us",
    "confidential", "don't mention", "just between",
]


def _keyword_score(text_lower, words):
    return sum(1 for w in words if w in text_lower)


def _domain_lookalike(sender_domain, known_domains):
    """True if sender_domain resembles a known-good domain closely enough to
    be a typosquat, without being an exact match to any known-good domain."""
    if sender_domain in known_domains:
        return False, None
    for good in known_domains:
        good_brand = good.split(".")[0]
        sender_brand = sender_domain.split(".")[0]
        # Same brand name, different domain (subdomain-looking or different TLD)
        if good_brand and good_brand in sender_domain and sender_domain != good:
            return True, good
        # Small edit distance on the full domain (e.g. paperjet.io vs paperjet.co)
        ratio = difflib.SequenceMatcher(None, sender_domain, good).ratio()
        if ratio >= 0.82 and sender_domain != good:
            return True, good
    return False, None


def detect_social_engineering(message, known_domains):
    """Returns (is_flagged, reason) for cap X4."""
    text_lower = (message["subject"] + " " + message["body"]).lower()
    sender_domain = message["from"].split("@")[-1].lower()

    lookalike, resembles = _domain_lookalike(sender_domain, known_domains)
    urgency = _keyword_score(text_lower, URGENCY_WORDS)
    money = _keyword_score(text_lower, MONEY_OR_CREDENTIAL_WORDS)
    secrecy = _keyword_score(text_lower, SECRECY_WORDS)

    signals = []
    if lookalike:
        signals.append(f"sender domain '{sender_domain}' resembles known domain '{resembles}'")
    if urgency:
        signals.append(f"{urgency} urgency phrase(s)")
    if money:
        signals.append(f"{money} money/credential phrase(s)")
    if secrecy:
        signals.append(f"{secrecy} secrecy phrase(s)")

    # Flag when a domain mismatch is combined with a money/credential ask,
    # OR when urgency + money + secrecy stack up even from a same-looking
    # address (covers same-domain-but-wrong-display-name style asks like m023,
    # which spoofs a colleague's name off a lookalike domain).
    score = (2 if lookalike else 0) + (2 if money else 0) + urgency + secrecy
    if score >= 3:
        return True, "; ".join(signals)
    return False, None
