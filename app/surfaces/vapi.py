"""VAPI (phone) surface adapter.

This is the only file that knows VAPI exists. It parses VAPI's tool-call payload,
calls the surface-agnostic action layer, and formats concise, single-line,
voice-friendly strings (VAPI requires single-line string results). When we add
the in-cabin or telematics surfaces, we add sibling files here; the action layer
underneath is untouched.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.actions.scheduling import SchedulingService
from app.config import dealer
from app.models import (
    SERVICE_LABEL,
    Customer,
    ServiceType,
    Slot,
    Source,
    Vehicle,
)
from app.safety import ValidationError, escalation_reason, normalize_phone


# ---- formatting helpers ---------------------------------------------------

def _fmt_time(dt: datetime) -> str:
    local = dt.astimezone(dealer.timezone)
    minute = "" if local.minute == 0 else f":{local.minute:02d}"
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{hour}{minute} {ampm}"


def _fmt_slot(slot: Slot) -> str:
    local = slot.start.astimezone(dealer.timezone)
    return f"{local.strftime('%A, %B %-d')} at {_fmt_time(slot.start)}"


def _parse_dt(date_str: str | None, time_str: str | None) -> datetime:
    """Build a dealer-local datetime from 'YYYY-MM-DD' + 'HH:MM'."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    t = datetime.strptime(time_str, "%H:%M").time() if time_str else datetime.min.time()
    return datetime.combine(d, t, tzinfo=dealer.timezone)


def _service(args: dict) -> ServiceType:
    raw = (args.get("service_type") or "other").strip().lower().replace(" ", "_")
    try:
        return ServiceType(raw)
    except ValueError:
        return ServiceType.OTHER


# ---- the surface ----------------------------------------------------------

class VapiSurface:
    SOURCE = Source.PHONE

    def __init__(self, service: SchedulingService) -> None:
        self.service = service

    def handle(
        self, tool_name: str, args: dict, caller_number: str | None = None
    ) -> str:
        try:
            if tool_name == "find_service_slots":
                return self._find_slots(args)
            if tool_name == "check_service_availability":
                return self._check(args)
            if tool_name == "book_service_appointment":
                return self._book(args, caller_number)
            if tool_name == "request_human_advisor":
                return "Transferring you to a service advisor now."
            return f"I don't have a way to handle '{tool_name}' yet."
        except ValidationError as e:
            return f"I can't do that: {e}. Could we try again?"
        except Exception:
            # Never leak a stack trace into a phone call.
            return (
                "I hit a snag on my end. Let me get a service advisor to help you."
            )

    # ---- tool handlers ----

    def _find_slots(self, args: dict) -> str:
        service = _service(args)
        if args.get("date"):
            start = _parse_dt(args["date"], "00:00")
            end = start + timedelta(days=1)
        else:
            start = datetime.now(dealer.timezone)
            end = start + timedelta(days=7)

        slots = self.service.find_slots(service, start, end, limit=3)
        if not slots:
            return "I don't see any openings in that window. Want me to look further out?"
        label = SERVICE_LABEL[service]
        offered = "; ".join(_fmt_slot(s) for s in slots)
        return f"For your {label}, I have: {offered}. Which works best?"

    def _check(self, args: dict) -> str:
        service = _service(args)
        desired = _parse_dt(args.get("date"), args.get("time"))
        exact, alts = self.service.check_availability(service, desired)
        label = SERVICE_LABEL[service]
        if exact:
            return f"Yes, {_fmt_slot(exact)} is open for your {label}. Want me to book it?"
        if alts:
            options = " or ".join(_fmt_time(s.start) for s in alts)
            return (
                f"That time's taken, but the same day I have {options}. "
                "Would either work?"
            )
        return "That time isn't available and I don't see nearby openings that day."

    def _book(self, args: dict, caller_number: str | None = None) -> str:
        service = _service(args)

        reason = escalation_reason(service, args.get("notes", ""))
        if reason:
            return f"For this I'll connect you to a service advisor — {reason}."

        # Prefer the actual caller ID; fall back to a number the caller dictated.
        phone = normalize_phone(caller_number or args.get("phone", ""))
        customer = Customer(name=args.get("customer_name", "Caller"), phone=phone)
        vehicle = Vehicle(
            year=args.get("vehicle_year"),
            make=args.get("vehicle_make"),
            model=args.get("vehicle_model"),
        )
        desired = _parse_dt(args.get("date"), args.get("time"))

        # Re-resolve the concrete open slot (with advisor) at that start.
        exact, alts = self.service.check_availability(service, desired)
        if not exact:
            if alts:
                options = " or ".join(_fmt_time(s.start) for s in alts)
                return (
                    f"That slot was just taken. I can do {options} the same day — "
                    "want one of those?"
                )
            return "That slot is no longer open. Want me to find the next available time?"

        appt = self.service.book(customer, vehicle, service, exact, self.SOURCE)
        label = SERVICE_LABEL[service]
        return (
            f"You're booked: {label} on {_fmt_slot(appt.slot)} with "
            f"{appt.slot.advisor_name}. Your confirmation code is "
            f"{' '.join(appt.confirmation_code)}. We'll text a reminder."
        )


# ---- VAPI payload parsing -------------------------------------------------

def parse_tool_calls(message: dict) -> list[tuple[str, str, dict]]:
    """Extract (tool_call_id, function_name, arguments) from a VAPI message.
    Handles both `toolCallList` and `toolCalls` spellings, and arguments that
    arrive as either a dict or a JSON string."""
    calls = message.get("toolCallList") or message.get("toolCalls") or []
    out: list[tuple[str, str, dict]] = []
    for c in calls:
        fn = c.get("function", {})
        raw_args = fn.get("arguments", {})
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                raw_args = {}
        out.append((c.get("id", ""), fn.get("name", ""), raw_args))
    return out
