"""The notifier interface — how a confirmed appointment's invite reaches the caller.

Same discipline as the DMS adapter: the action layer depends only on this
abstract class, so the delivery channel (SMS, email, ...) is a swap-by-config
detail, not a rewrite. `MockNotifier` lets the whole invite flow run and be
tested with zero credentials; a real channel (e.g. Twilio SMS) is one more file.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from app.config import PUBLIC_BASE_URL
from app.models import Appointment


class Notifier(ABC):
    @abstractmethod
    def send_invite(self, appt: Appointment) -> dict:
        """Deliver a calendar-invite link for `appt` to the customer.
        Returns a delivery record: {channel, to, ics_url, status}."""
        ...

    @staticmethod
    def ics_url(appt: Appointment) -> str:
        """Public URL of the .ics for this appointment (what we text/email)."""
        return f"{PUBLIC_BASE_URL}/appointments/{appt.id}.ics"


class MockNotifier(Notifier):
    """Records would-be sends instead of hitting a provider. This is what runs
    until a real channel is configured — the booking, audit trail, and .ics
    endpoint all work; only the actual text/email is simulated."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.sent: list[dict] = []

    def send_invite(self, appt: Appointment) -> dict:
        record = {
            "channel": "mock",
            "to": appt.customer.phone,
            "ics_url": self.ics_url(appt),
            "status": "logged",
        }
        with self._lock:
            self.sent.append(record)
        return record
