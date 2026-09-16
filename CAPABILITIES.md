# CAPABILITIES.md

**Student:** Akash Chaudhari, cert-aai-2026-06-0052
**Repository:** https://github.com/akashchaudhari/inboxHero

Run everything through one entry point:

```
python demo.py --cap R1        # one capability
python demo.py --all           # all of them, in order
```

---

## The system, in one paragraph

A single Python pipeline, no framework. Messages are loaded once; every
message is run through a chain of cheap, deterministic checks (is it
automated noise, is it an internal FYI, has Sam already replied in this
thread, does it carry an instruction addressed to an assistant, does it
look like phishing) before anything resembling "drafting" happens. Only the
messages that survive all of that -- about a sixth of the inbox -- reach a
template-based drafter, a preference-aware scheduler, or a cross-thread
lookup. A final pass over the same decisions builds the dashboard, the
digest, and the follow-up list, so none of those three can disagree with
each other about what a message is. State that must outlive a run
(preferences, the trace log) lives in small files on disk: `prefs.json`,
`trace.jsonl`, `decisions.json`.

## Data assumptions

100 messages processed (`system.messages_processed` in capabilities.json).
Assumptions made about `inbox.json`'s format: `timestamp` is naive local
time with no timezone offset, and every timestamp in the file falls within
a single month (September 2026) -- `core/dates.py`'s date resolution
leans on that to turn "the 18th" or "Tuesday" into a full date without
needing a timezone or a year-rollover case. `to` is always the mailbox
owner (`sam@paperjet.io`) even on messages that read like a multi-person
broadcast (the launch-week thread, the legal correspondence) -- there's no
CC list in the schema, so a message's "audience" is inferred from its
thread's participant count instead (`core/rules.py:is_group_thread`), not
from headers. `thread_id` is treated as ground truth for conversation
structure (the basis for thread-walk retrieval) and is never
re-derived from subject lines.

## Design choices you were asked to state

- **Framework: none.** The work is a linear pipeline with one real branch
  (does this message reach drafting or not), so a crew/graph framework
  would have added indirection without buying anything. See Final Report
  Q4 for what a framework would and wouldn't have saved me.
- **Model: template-based by default, not "no model where it matters."**
  `core/llm.py` is the single seam every draft passes through, and by
  default it does not call out anywhere -- it fills a plain-language
  template with facts the rest of the pipeline already grounded and
  verified. I made this call deliberately, not because a model call is
  hard to wire up: this inbox's replies are short, factual acknowledgments
  where the correct wording is mechanical once the grounding is right, so
  a template is more auditable (every word traces to a field on a message
  object) and immune to rate limits and hallucinated phrasing. The hook is
  real, though -- set `MODEL_PROVIDER` and `MODEL_API_KEY` in `.env` and
  extend the one branch in `core/llm.py`; nothing else in the codebase
  would need to change.
- **Retrieval: thread-walk.** `thread_id` already gives the inbox its
  structure, so walking a thread backward from a message is both cheaper
  and more precise than embeddings for grounding a reply in *this*
  conversation. Keyword search (`core/store.py:keyword_search`) is the
  documented fallback for a cross-thread fact -- used exactly once, in the
  press-question draft for m046, which needs the launch date from a
  different thread entirely.
- **Reversible vs irreversible.** `send` and `delete` are irreversible;
  `draft`, `label`, `archive`, and `defer` are reversible and run without
  a prompt. Deleting is irreversible in this design even though the mock
  store has no trash: the test I used is "could Sam get this back without
  outside help", and a message removed from a JSON-backed store fails that
  test exactly as hard as one removed from a real mailbox with an emptied
  trash.
- **Where the gate sits.** Exactly two functions in the whole codebase can
  cause an irreversible effect -- `core/gate.py:send` and
  `core/gate.py:delete` -- and both call `require_approval()` as their
  first line. No other module imports outbox-writing or delete code, and
  nothing parses a message body looking for a command to run (see Final
  Report Q2). That's the actual defence behind cap R5: a hostile message
  can shape what a *draft* says, but there is no code path from message
  content to a send or delete that skips the gate.
- **Escalation line.** The system escalates (holds for Sam, drafts
  nothing) only for: a scheduling conflict between two timed commitments,
  a decision with no basis anywhere in the mailbox (the hiring follow-up,
  m042), and anything flagged as hostile or suspicious. Everything else
  that needs a reply gets a draft Sam can approve or edit in one glance.
  The trade-off: an internal status update that happens to contain a
  buried, unstated ask could slip through as "no direct ask of Sam" -- in
  exchange for not asking Sam to personally triage 100 messages one at a
  time. See the `team-update` category (9 messages in a 5-person launch
  thread) for where this line was actually drawn.

## Disposition vocabulary

| disposition | meaning |
|---|---|
| `reply` | Sam owes a response; a grounded draft is attached, or the draft says plainly it couldn't ground the ask rather than guessing. |
| `archive` | Nothing further needed -- noise, an internal FYI, a thread Sam already answered, a status update not addressed to him, a preference that's now on file. |
| `defer` | Worth a look, not urgent, and not something to guess at (ambiguous, personal, or a low-priority internal reminder). |
| `delegate` | Sam is the sender and is waiting on someone else's reply -- tracked by cap X1. |
| `escalate` | Needs Sam directly: a conflict, a decision nothing in the mailbox can ground, or a flagged message. |

## Capabilities

| id | name | tier | one-line claim |
|----|------|------|----------------|
| R1 | Zero the inbox | B | every message gets one disposition + reason, none left |
| R2 | Grounded reply | B | drafts cite the earlier message they used |
| R3 | Gate the irreversible | C | no send/delete without approval or --dry-run |
| R4 | Persistent preference | C | a stated preference survives a restart |
| R5 | Refuse embedded instructions | C | detects, refuses, flags, reports injections |
| R6 | Dashboard | C | three panes, commitments cited, conflicts surfaced |
| X1 | Follow-up tracking | B | unanswered sent mail, with a drafted chase |
| X2 | Morning digest | B | what needs me / what can wait / what was archived |
| X3 | Correspondent lookup | A | one lookup, one output: all mail from a sender/domain |
| X4 | Phishing / social-engineering detector | C | domain-lookalike + urgency/money/secrecy scoring, held for review |
| X5 | Preference-aware scheduling assistant | C | confirms, counter-offers, or holds -- never guesses which meeting wins |

The exact command, observable outcome and evidence for each is in
`capabilities.json`.

---

## Final Report

### 1. What did you refuse to automate?

The clearest case is m008: Devika, a real colleague in a real thread, asks
the system to resend a secret (the rotated staging broker credential) over
email. The system *drafts* that reply -- grounding is exactly what cap R2
is supposed to prove, and refusing to draft it would hide a legitimate
capability -- but it will never send it unsupervised, because sending is
irreversible and gated behind `require_approval()` regardless of who's
asking or how routine the request looks. That's the actual line I drew:
the system will compose an answer to almost anything, but restating a
secret over email only leaves the building after a human looked at it.
Similarly, when two commitments collide (m010's investor call and m061's
dentist appointment, both Tuesday 3pm; m013's moved 1:1 and m016's Acme
demo, both Wednesday 2pm), the system refuses to pick a winner -- it holds
both for Sam rather than silently keeping one and dropping the other.

### 2. Where does untrusted text enter your system?

Every message body is untrusted the moment it's read, and it stays that
way structurally, not by prompt-level convention. Concretely: message text
only ever flows into two kinds of code. First, pattern-matching functions
in `core/security.py` and `core/rules.py` that check *whether* the text
looks like an instruction or a threat -- these functions return booleans
and strings, they don't execute anything they find. Second, string
interpolation inside a drafting template (`core/drafting.py`), where a
fact pulled from an earlier message becomes one field in a fixed sentence
shape -- it is never treated as code, a command, or a new instruction to
follow. No function in this codebase parses a message body looking for
"what should I do", and the only two functions that can send or delete
(`core/gate.py`) are called exclusively from `demo.py`'s own dispatch
logic, driven by a disposition the pipeline computed, never by text found
inside a message. To make my system act on an attacker's behalf, they
would have to get code into `demo.py`'s dispatch loop itself, not just
clever wording into an email -- which is why m017, m024, m039, and m047
(one of which pretends to be a self-addressed note updating "assistant
settings" to disable approval and autonomy) all fail identically: not
because a regex happened to catch their exact wording, but because there
was never a path from message content to `gate.send`/`gate.delete` in the
first place.

### 3. Who is accountable when it sends the wrong thing?

Sam is -- the system drafts, Sam approves, and `core/gate.py` only ever
writes to `outbox/` after that approval (interactive `y`, or a
non-dry-run invocation), which is logged. If something sent in Sam's name
turns out wrong, `trace.jsonl` is the trace back: every send is logged
with the message it was replying to, the recipients, and the exact
cited message ids the draft was grounded in (`core/gate.py:send`, the
`"sent"` event). If the draft cited a fact, that citation is checked
against the store before it's ever shown (see the `assert` in
`demo.py:run_r2`), so a wrong send is traceable to either a bad citation
(a grounding bug, my fault to fix) or a human approving something they
shouldn't have (Sam's call to make, and mine to make easier -- e.g. by
showing the cited source inline before he approves, which the R3 output
currently doesn't do and is the clearest next improvement).

### 4. Name your own machinery.

There's no Agent/Task/Crew abstraction here, so the honest mapping is to
what those roles *do*, not what they're called. `demo.py`'s `CAPS` dict
plus its dispatch in `main()` is the Router/Crew: it's the only place that
decides which code runs for a given command, and the only place allowed
to call into `core/gate.py`. Each `core/*.py` module is closer to a
single-purpose Task than an Agent -- `core/dispositions.py` doesn't call
`core/drafting.py` on its own initiative, it's handed a message and
returns a decision; nothing in this codebase has open-ended autonomy to
decide what to do next. The one thing a framework would have handed me for
free is retries/backoff and structured tool-calling around a *real* model
provider -- `core/llm.py`'s `RateLimitBackoff` is my hand-rolled, much
smaller version of that, and it's currently unexercised because the
default path never calls a model at all. Whether a framework would have
helped here: for this system, no -- the entire "agentic" surface area is
one decision per message with no back-and-forth, no tool loop, and no
need for an LLM to decide what to do next, so CrewAI/ADK's machinery
(agent handoffs, shared scratchpads, tool-call loops) would have been
overhead for a problem that's a router with a gate on the dangerous exits.
I'd reach for a framework the moment a capability needed genuine
back-and-forth reasoning -- e.g. an LLM negotiating a meeting time across
several email round-trips -- because that's where retry/state-tracking
machinery actually starts paying for itself.
