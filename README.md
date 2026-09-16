# inboxHero

*Build It, Then Prove It -- Assignment 06, Agentic AI: From Concepts to Practice*

**Repository:** https://github.com/akashchaudhari/inboxHero
**Student:** Akash Chaudhari, cert-aai-2026-06-0052

An agentic triage system for a mock 100-message inbox: it assigns every
message a disposition, drafts grounded replies, gates every irreversible
action behind approval, remembers stated preferences across restarts,
refuses hostile instructions embedded in mail, and builds a three-pane
dashboard -- plus five more capabilities of its own (follow-up tracking,
a morning digest, a correspondent lookup, a phishing/social-engineering
detector, and a preference-aware scheduling assistant).

## Quickstart

```bash
git clone https://github.com/akashchaudhari/inboxHero.git
cd inboxHero
python demo.py --cap R1        # any single capability
python demo.py --all           # everything, in order (R3 runs --dry-run)
```

No dependencies to install and no API key needed -- see "Model" below.

## Project layout

```
demo.py              single --cap entry point
config.py             env-var configuration
core/
  store.py             load inbox.json, thread-walk retrieval, keyword search
  rules.py              cheap, model-free classification rules
  security.py            prompt-injection (R5) and phishing (X4) detection
  dates.py                 deadline/date parsing
  commitments.py            shared commitment extraction + conflict detection
  preferences.py             persisted standing preferences (R4)
  scheduler.py                 preference-aware meeting evaluation (X5)
  drafting.py                   grounded reply templates (R2)
  llm.py                         pluggable generation, template by default
  gate.py                         send/delete, both behind approval (R3)
  dispositions.py                 R1 -- assigns every message one disposition
  dashboard.py                     R6 -- three-pane dashboard
  followups.py, digest.py, lookup.py    X1, X2, X3
  tracing.py                        trace.jsonl event log
data/inbox.json        the 100-message mock inbox
outbox/, trace.jsonl, decisions.json, prefs.json, dashboard.html/json  -- run outputs
```

## Architecture, in short

No framework (see CAPABILITIES.md for why). Every message runs through a
chain of cheap, deterministic checks before anything resembling drafting
happens: is it automated noise, an internal FYI, a thread Sam already
replied in, an instruction addressed to an assistant, or phishing. Only
the messages that survive all of that reach a template-based drafter, the
scheduler, or a cross-thread keyword lookup. Full design rationale --
framework choice, retrieval approach, the reversible/irreversible split,
where the escalation line sits, and all capability evidence -- is in
**CAPABILITIES.md**, the primary graded document; **capabilities.json** is
its machine-readable twin, read by whatever marking script parses this
submission.

## Model

Drafting (`core/llm.py`) is template-based by default -- no external model
call happens anywhere in a default run. This was a deliberate choice, not
a missing integration: see CAPABILITIES.md's "Design choices" section for
the reasoning, and `.env.example` / `config.py` for the hook that would
route generation through a real provider if one were wired in.

## Disposition vocabulary

`reply`, `archive`, `defer`, `delegate`, `escalate` -- defined in
CAPABILITIES.md, applied consistently by `core/dispositions.py`.

## Reversible vs. irreversible, and the gate

`draft`, `label`, `archive`, `defer` are reversible and run without a
prompt. `send` and `delete` are irreversible and both live behind
`core/gate.py:require_approval()` -- either per-action `y/N` approval, or
`--dry-run`, which shows every proposed send/delete and performs none of
them. Full reasoning in CAPABILITIES.md.

## Retrieval

Thread-walk (`core/store.py:thread_history_for`), with keyword search as
the documented fallback for the one cross-thread fact this inbox needs
(the launch date, grounding the press-question reply to m046).

## Retrieval and outputs of a full run

`python demo.py --all` produces (all included in this submission):
- `decisions.json` -- one disposition + reason per message (R1)
- `outbox/` -- sent replies (empty after `--all`, since R3 there always
  runs `--dry-run`; run `python demo.py --cap R3` without the flag to see
  real, approved sends land here)
- `trace.jsonl` -- the full event log, tagged `cap=<id>` per capability
- `dashboard.html` / `dashboard.json` -- the three-pane dashboard (R6)
- `prefs.json` -- standing preferences, persisted across process restarts (R4)

## Final Report

### 1. What did you refuse to automate?

The clearest case is m008: Devika, a real colleague in a real thread,
asks the system to resend a secret (the rotated staging broker
credential) over email. The system *drafts* that reply -- grounding is
exactly what cap R2 is supposed to prove -- but it will never send it
unsupervised, because sending is irreversible and gated behind
`require_approval()` regardless of who's asking or how routine the
request looks. Similarly, when two commitments collide (m010's investor
call and m061's dentist appointment, both Tuesday 3pm; m013's moved 1:1
and m016's Acme demo, both Wednesday 2pm), the system refuses to pick a
winner -- it holds both for Sam rather than silently keeping one and
dropping the other.

### 2. Where does untrusted text enter your system?

Every message body is untrusted the moment it's read, and stays that way
structurally, not by prompt convention. Message text only ever flows into
two kinds of code: pattern-matching functions (`core/security.py`,
`core/rules.py`) that check *whether* text looks hostile and return a
boolean, never executing anything they find; and string interpolation
inside a fixed drafting template (`core/drafting.py`), where a fact
becomes one field in a sentence, never a new instruction to follow. The
only two functions that can send or delete (`core/gate.py`) are called
exclusively from `demo.py`'s own dispatch logic, driven by a disposition
the pipeline computed -- never by text found inside a message. That's why
m017, m024, m039 (a self-addressed note posing as an "assistant settings"
change to disable approval and autonomy), and m047 all fail identically:
there was never a path from message content to `gate.send`/`gate.delete`
in the first place.

### 3. Who is accountable when it sends the wrong thing?

Sam is -- the system drafts, Sam approves, and `core/gate.py` only writes
to `outbox/` after that approval, logged in `trace.jsonl` alongside the
recipients and the exact cited message ids the draft was grounded in. A
wrong send traces back to either a bad citation (a grounding bug, mine to
fix -- and citations are asserted against the store before being shown,
see `demo.py:run_r2`) or a human approving something he shouldn't have
(Sam's call, and mine to make easier, e.g. by surfacing the cited source
inline before approval -- the clearest next improvement).

### 4. Name your own machinery.

No Agent/Task/Crew abstraction, so the honest mapping is to what those
roles *do*. `demo.py`'s `CAPS` dispatch is the Router/Crew: the only place
that decides which code runs, and the only place allowed to call
`core/gate.py`. Each `core/*.py` module is closer to a single-purpose Task
than an autonomous Agent -- it's handed a message and returns a decision;
nothing here decides what to do next on its own. The one thing a
framework would have given me for free is retries/backoff around a real
model call -- `core/llm.py`'s `RateLimitBackoff` is my small hand-rolled
version, currently unexercised since the default path never calls a model
at all. For this system a framework would have been overhead: the entire
"agentic" surface is one decision per message, no tool loop, no
multi-turn negotiation. I'd reach for one the moment a capability needed
genuine back-and-forth -- e.g. an LLM negotiating a meeting time across
several round-trips -- because that's where the machinery starts paying
for itself.
