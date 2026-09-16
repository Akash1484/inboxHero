"""
Configuration, loaded from environment variables (see .env.example).

inboxHero does not require any of these to run its demo. Drafting and
summarisation are done with deterministic templates (see core/llm.py) so the
system has no external dependency and nothing to rate-limit. The hooks below
exist so a real model can be dropped in later without touching the rest of
the codebase -- set MODEL_PROVIDER and the matching API key and core/llm.py
will route generation calls there instead of the template fallback.
"""
import os

# Load .env if python-dotenv is available; otherwise just read os.environ.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# "template" (default, no external calls) | "openai" | "anthropic" | "gemini"
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "template")
MODEL_NAME = os.environ.get("MODEL_NAME", "")
API_KEY = os.environ.get("MODEL_API_KEY", "")

# Paths
INBOX_PATH = os.environ.get("INBOX_PATH", "data/inbox.json")
PREFS_PATH = os.environ.get("PREFS_PATH", "prefs.json")
DECISIONS_PATH = os.environ.get("DECISIONS_PATH", "decisions.json")
TRACE_PATH = os.environ.get("TRACE_PATH", "trace.jsonl")
OUTBOX_DIR = os.environ.get("OUTBOX_DIR", "outbox")
DASHBOARD_HTML_PATH = os.environ.get("DASHBOARD_HTML_PATH", "dashboard.html")
DASHBOARD_JSON_PATH = os.environ.get("DASHBOARD_JSON_PATH", "dashboard.json")

# The mailbox owner. inbox.json is all addressed to/from this person.
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "sam@paperjet.io")

# Follow-up threshold used by X1 (days).
FOLLOWUP_DAYS = int(os.environ.get("FOLLOWUP_DAYS", "3"))

# "Now", for follow-up/digest freshness math. Fixed by default so the demo
# is reproducible; override to explore other points in the inbox's timeline.
DEMO_NOW = os.environ.get("DEMO_NOW", "2026-09-10T09:00:00")
