# inboxHero

*Build It, Then Prove It -- Assignment 06, Agentic AI: From Concepts to Practice*

**Repository:** https://github.com/Akash1484/inboxHero
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
git clone https://github.com/Akash1484/inboxHero.git
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

The clearest case is m008: Devika asks the system to resend a rotated staging broker credential over email. The system can draft that response because grounded drafting is part of R2, but it will never send it without human approval because sending is irreversible. Similarly, when two commitments collide, such as m010 with m061 or m013 with m016, the system refuses to decide which meeting should win and instead holds the conflict for Sam. This boundary keeps the system useful for preparation while leaving consequential decisions and secret-bearing sends under human control.

### 2. Where does untrusted text enter your system?

Every message body is treated as untrusted data as soon as it enters the system, rather than as an instruction to the program. Message text flows into pattern-matching functions in `core/security.py` and `core/rules.py`, or into fixed drafting templates where message facts become fields rather than executable instructions. The only two functions capable of sending or deleting are `core/gate.py:send` and `core/gate.py:delete`, and both require the gate before performing an irreversible action. An attacker would therefore have to compromise the program's own dispatch or gate code rather than merely persuading the inbox reader with carefully written email text.

### 3. Who is accountable when it sends the wrong thing?

Sam remains accountable because the system only writes a message to `outbox/` after the human approves the irreversible send. The system helps trace the failure through `trace.jsonl`, which records the message being answered, recipients, and cited source message ids for the draft. Grounding citations are also checked against the message store before the draft is shown, so a bad factual grounding can be traced back to the system's retrieval or drafting logic. If the draft was correctly grounded but Sam approved an inappropriate message, the approval decision remains the human's responsibility.

### 4. Name your own machinery.

There is no Agent/Task/Crew abstraction here, so the honest mapping is to what those roles do rather than what they are called. `demo.py`'s `CAPS` dispatch and `main()` act as the Router/Crew because they decide which capability runs, while each `core/*.py` module is closer to a single-purpose Task that receives data and returns a result. The only functions capable of sending or deleting are in `core/gate.py`, which keeps the irreversible boundary centralized. A framework would have given me more built-in machinery for model retries, tool calling, and multi-agent orchestration; I implemented only the small retry/backoff seam in `core/llm.py` because the default system deliberately does not call an external model. For this inbox, using CrewAI or ADK would have added abstraction without solving a real problem, but a framework would become more useful if the system later needed genuine multi-step LLM reasoning or multi-turn tool use.
