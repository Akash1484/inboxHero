"""
Everything here is a plain rule: no model call, no randomness. These are
the checks that let cap R1 report how many of the ~100 messages never
touched a model at all (see the "rule_handled" figure in capabilities.json).
"""
import re

import config

NOISE_LOCAL_PART_RE = re.compile(
    r"^(no[-_]?reply(-\w+)?|noreply|notifications?|notify|notification|alerts?|"
    r"billing|receipts?|info|updates?|digest|orders?|checkin|ship-confirm|"
    r"invoice(\+.*)?|feedback|newsletter|insights?|calendar-notification|"
    r"security|hello|support)$",
    re.I,
)
NOISE_PHRASES = [
    "no action needed", "no further action needed", "for your records",
    "no issues found", "this is an automated receipt",
]

INTERNAL_SYSTEM_LOCAL_PARTS = {"hr", "facilities", "notes"}

VAGUE_PHRASES = [r"\bthe thing\b", r"\bthat thing we talked about\b"]

PERSONAL_PHRASES = [
    "catch up", "no agenda", "coffee when", "just curious what you're building",
]

MEETING_PROPOSAL_RE = re.compile(
    r"\b(does (that|this) (slot |time )?work|"
    r"could (you|we) do|can we (move|do)|one more slot|"
    r"work on your side)\b",
    re.I,
)


FYI_CLOSURE_PHRASES = [
    "nothing pending on my side", "no need to reply", "just a heads up",
    "nothing for you to do", "no action needed on your end",
]


def states_own_closure(message):
    """A real (non-automated) message that explicitly says there's nothing
    to do -- still worth archiving rather than drafting a pointless ack."""
    body_low = message["body"].lower()
    return any(p in body_low for p in FYI_CLOSURE_PHRASES)


def local_part(address):
    return address.split("@")[0].lower()


def is_transactional_noise(message):
    """Automated vendor mail -- receipts, notifications, digests. Archived
    without a model call."""
    if NOISE_LOCAL_PART_RE.match(local_part(message["from"])):
        return True
    body_low = message["body"].lower()
    return any(p in body_low for p in NOISE_PHRASES)


def is_internal_system_notice(message, owner_domain):
    """Automated internal mail (HR/facilities/notes bots), distinct from
    vendor noise because it's from the owner's own org."""
    domain = message["from"].split("@")[-1].lower()
    return domain == owner_domain and local_part(message["from"]) in INTERNAL_SYSTEM_LOCAL_PARTS


def needs_real_world_action(message):
    """An internal notice that still asks Sam to *do* something (submit a
    timesheet) rather than just informing him (office is closed)."""
    body_low = message["body"].lower()
    return "reminder" in body_low and any(
        w in body_low for w in ("submit", "complete", "fill out")
    )


def is_self_note(message, owner_email):
    return message["from"] == owner_email and message["to"] == owner_email


def is_sent_by_owner(message, owner_email):
    return message["from"] == owner_email and message["to"] != owner_email


def thread_already_answered(message, store, owner_email):
    """True if the owner has already sent a later message in this same
    thread -- i.e. Sam himself already replied, which is what "already
    answered" should mean. (Checking for *any* later message from anyone
    else is too loose: in a multi-person thread, someone else posting next
    doesn't mean Sam's specific question got answered -- see is_group_thread
    for how those are handled instead.)"""
    thread = store.thread_messages(message["thread_id"])
    idx = next(i for i, m in enumerate(thread) if m["id"] == message["id"])
    for later in thread[idx + 1:]:
        if later["from"] == owner_email:
            return later["id"]
    return None


def thread_continued_after(message, store):
    """For the owner's own sent messages: did anyone reply after it? Used
    to tell an answered send (thread moved on) from one still awaiting
    a reply (cap X1 territory)."""
    thread = store.thread_messages(message["thread_id"])
    idx = next(i for i, m in enumerate(thread) if m["id"] == message["id"])
    for later in thread[idx + 1:]:
        if later["from"] != message["from"]:
            return later["id"]
    return None


def is_group_thread(message, store):
    thread = store.thread_messages(message["thread_id"])
    participants = {m["from"] for m in thread}
    return len(participants) > 2


def mentions_owner_by_name(message, owner_first_name):
    return bool(re.search(r"\b" + re.escape(owner_first_name) + r"\b", message["body"]))

def is_vague(message):
    body_low = message["body"].lower()
    return any(re.search(p, body_low) for p in VAGUE_PHRASES)


def is_personal(message, owner_domain, business_domains):
    domain = message["from"].split("@")[-1].lower()
    if domain == owner_domain or domain in business_domains:
        return False
    body_low = message["body"].lower()
    return any(p in body_low for p in PERSONAL_PHRASES)


def proposes_meeting(message):
    return bool(MEETING_PROPOSAL_RE.search(message["body"]))


def is_hiring_decision(message):
    domain = message["from"].split("@")[-1].lower()
    generic_personal_domains = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}
    body_low = message["body"].lower()
    return domain in generic_personal_domains and (
        "role" in body_low or "offer" in body_low or "position" in body_low
    )
