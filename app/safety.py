"""Safety, validation, and escalation.

The agent is authorizing real bookings on a dealer's calendar for callers who
can't see a screen, so guardrails are first-class, not an afterthought. Two
jobs: reject input that would create a bad booking, and decide when to hand off
to a human service advisor instead of pushing through.
"""

from __future__ import annotations

import re

from app.config import dealer
from app.models import ServiceType, Slot

_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


class ValidationError(Exception):
    pass


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[^0-9+]", "", raw or "")
    if not _PHONE_RE.match(digits):
        raise ValidationError(f"'{raw}' is not a usable phone number")
    return digits


def assert_within_hours(slot: Slot) -> None:
    local = slot.start.astimezone(dealer.timezone)
    if local.weekday() not in dealer.work_days:
        raise ValidationError("the service department is closed that day")
    if not (dealer.open_hour <= local.hour < dealer.close_hour):
        raise ValidationError("that time is outside service hours")


def escalation_reason(service_type: ServiceType, transcript_hint: str = "") -> str | None:
    """Return a human-readable reason to hand off to a live advisor, or None.

    Conservative on purpose: when in doubt, a human takes it. A wrong autonomous
    booking costs more trust than a transfer.
    """
    hint = (transcript_hint or "").lower()

    # Recalls and diagnostics often need VIN-level checks and parts confirmation
    # the agent can't safely complete alone in v1.
    if service_type in (ServiceType.RECALL, ServiceType.DIAGNOSTIC):
        return "this needs a service advisor to confirm parts and coverage"

    # Caller explicitly wants a person, or signals frustration/safety.
    if any(w in hint for w in ("human", "person", "manager", "speak to someone")):
        return "the caller asked for a person"
    if any(w in hint for w in ("smoke", "fire", "accident", "won't start", "stranded")):
        return "this sounds urgent and should reach a person right away"

    return None
