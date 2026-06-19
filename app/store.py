"""Idempotency + audit log.

Both are in-memory for v1 (single process). The interfaces are what matter:
swap the dicts for Redis / Postgres without touching the action layer.

Why these exist in v1 and aren't "later" work:
- Idempotency: an LLM may call `book` twice for one intent (retry, double
  confirm). Without a key, that double-books a bay. This is the kind of failure
  that loses a dealer on day one, so it ships in v1.
- Audit log: every booking the agent makes is a transaction on the dealer's
  behalf. We keep an immutable trail for dispute resolution and QA.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


class IdempotencyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: dict[str, str] = {}  # key -> appointment_id

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._seen.get(key)

    def put(self, key: str, appointment_id: str) -> None:
        with self._lock:
            self._seen[key] = appointment_id


class AuditLog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []

    def record(self, action: str, **payload: Any) -> None:
        with self._lock:
            self._events.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "action": action,
                    **payload,
                }
            )

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)
