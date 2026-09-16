"""
Loads the mock inbox and gives the rest of the system one place to read
messages from. Retrieval is thread-walk: paperjet's inbox already carries
its own structure in thread_id, so walking a thread is cheaper and more
precise than embedding search for this task. Keyword search is the fallback
for the rare cross-thread lookup (see cap R2's manifest note).
"""
import json
from datetime import datetime

import config


class MessageStore:
    def __init__(self, path=None):
        self.path = path or config.INBOX_PATH
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._by_id = {m["id"]: m for m in raw}
        self._order = [m["id"] for m in raw]  # file order, preserved
        self._threads = {}
        for m in raw:
            self._threads.setdefault(m["thread_id"], []).append(m["id"])
        for tid in self._threads:
            self._threads[tid].sort(key=lambda mid: self._by_id[mid]["timestamp"])

    # -- basic access -----------------------------------------------------
    def all_messages(self):
        return [self._by_id[mid] for mid in self._order]

    def get(self, message_id):
        return self._by_id.get(message_id)

    def __len__(self):
        return len(self._order)

    # -- thread-walk retrieval ---------------------------------------------
    def thread_messages(self, thread_id, before_id=None):
        """All messages in a thread, oldest first. If before_id is given,
        only messages strictly earlier (by timestamp) than that message."""
        ids = self._threads.get(thread_id, [])
        if before_id is None:
            return [self._by_id[mid] for mid in ids]
        cutoff = self._by_id[before_id]["timestamp"]
        return [
            self._by_id[mid] for mid in ids
            if self._by_id[mid]["timestamp"] < cutoff
        ]

    def thread_history_for(self, message_id):
        """Everything in the same thread that came before this message --
        the natural grounding set for drafting a reply to it."""
        msg = self._by_id[message_id]
        return self.thread_messages(msg["thread_id"], before_id=message_id)

    # -- keyword fallback ----------------------------------------------------
    def keyword_search(self, terms, exclude_thread=None, limit=5):
        """Very small keyword search across subject+body, used only when a
        needed fact isn't in the same thread (cross-thread lookup)."""
        terms = [t.lower() for t in terms if t.strip()]
        hits = []
        for mid in self._order:
            m = self._by_id[mid]
            if exclude_thread and m["thread_id"] == exclude_thread:
                continue
            hay = (m["subject"] + " " + m["body"]).lower()
            score = sum(hay.count(t) for t in terms)
            if score > 0:
                hits.append((score, m))
        hits.sort(key=lambda pair: (-pair[0], pair[1]["timestamp"]))
        return [m for _, m in hits[:limit]]

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def domain_of(address):
        return address.split("@")[-1].lower().strip() if "@" in address else ""

    @staticmethod
    def parse_ts(ts_str):
        return datetime.fromisoformat(ts_str)
