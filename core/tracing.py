"""
Append-only event log. Every capability writes its events here, tagged with
cap=<id>, so trace.jsonl is the evidence trail referenced by capabilities.json.
"""
import json
import os
import time

import config


def log_event(cap, event_type, **fields):
    """Append one event to trace.jsonl. Never raises -- logging must not be
    able to break the pipeline it's observing."""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cap": cap,
        "event": event_type,
    }
    record.update(fields)
    try:
        with open(config.TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return record


def reset_trace():
    """Used by --all so a full run starts from a clean trace file."""
    try:
        os.remove(config.TRACE_PATH)
    except FileNotFoundError:
        pass
