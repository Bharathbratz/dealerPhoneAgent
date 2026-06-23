"""The action layer — the reusable core ("the moat").

This is the part that must never know which surface called it. The phone surface
calls `book(...)`; later the in-cabin and telematics surfaces call the same
`book(...)`. Keeping this clean is what makes the combined platform real instead
of three copies of the same logic.

Everything here returns domain objects (Slot, Appointment), never strings. Voice
phrasing is the surface's job, not the action layer's.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from app.dms.base import DMSAdapter, SlotUnavailable
from app.models import (
    Appointment,
    Customer,
    ServiceType,
    Slot,
    Source,
    Vehicle,
)
from app.notify.base import MockNotifier, Notifier
from app.safety import ValidationError, assert_within_hours
from app.store import AuditLog, IdempotencyStore


class SchedulingService:
    def __init__(
        self,
        dms: DMSAdapter,
        idempotency: IdempotencyStore,
        audit: AuditLog,
        notifier: Notifier | None = None,
    ) -> None:
        self.dms = dms
        self.idempotency = idempotency
        self.audit = audit
        self.notifier = notifier or MockNotifier()
        self._by_id: dict[str, Appointment] = {}

    def get_appointment(self, appointment_id: str) -> Appointment | None:
        """Look up a confirmed appointment (used to serve its .ics invite)."""
        return self._by_id.get(appointment_id)

    # ---- read paths -------------------------------------------------------

    def find_slots(
        self,
        service_type: ServiceType,
        date_from: datetime,
        date_to: datetime,
        limit: int = 3,
    ) -> list[Slot]:
        slots = self.dms.get_open_slots(service_type, date_from, date_to)
        self.audit.record(
            "find_slots",
            service_type=service_type.value,
            returned=min(len(slots), limit),
        )
        return slots[:limit]

    def check_availability(
        self, service_type: ServiceType, desired_start: datetime
    ) -> tuple[Slot | None, list[Slot]]:
        """Return (exact_match_or_None, up_to_2_alternatives_same_day)."""
        window_end = desired_start + timedelta(hours=1)
        same_start = self.dms.get_open_slots(service_type, desired_start, window_end)
        exact = next(
            (s for s in same_start if s.start == desired_start), None
        )

        day_start = desired_start.replace(hour=0, minute=0)
        day_end = desired_start.replace(hour=23, minute=59)
        same_day = self.dms.get_open_slots(service_type, day_start, day_end)
        alternatives = [s for s in same_day if s.start != desired_start][:2]

        self.audit.record(
            "check_availability",
            service_type=service_type.value,
            desired=desired_start.isoformat(),
            available=exact is not None,
        )
        return exact, alternatives

    # ---- write path -------------------------------------------------------

    def book(
        self,
        customer: Customer,
        vehicle: Vehicle,
        service_type: ServiceType,
        slot: Slot,
        source: Source = Source.PHONE,
    ) -> Appointment:
        assert_within_hours(slot)

        # Idempotency: same caller + service + start = same booking, always.
        idem_key = self._idem_key(customer.phone, service_type, slot.start)
        existing_id = self.idempotency.get(idem_key)
        if existing_id and existing_id in self._by_id:
            self.audit.record("book_idempotent_hit", appointment_id=existing_id)
            return self._by_id[existing_id]

        try:
            reservation_id = self.dms.reserve_slot(slot)
            appt = self.dms.create_appointment(
                reservation_id, customer, vehicle, service_type, slot, source
            )
        except SlotUnavailable as e:
            self.audit.record("book_slot_unavailable", detail=str(e))
            raise

        self._by_id[appt.id] = appt
        self.idempotency.put(idem_key, appt.id)
        self.audit.record(
            "book_confirmed",
            appointment_id=appt.id,
            confirmation_code=appt.confirmation_code,
            source=source.value,
        )

        # Send the calendar invite. A delivery failure must never undo a booking
        # that already succeeded, so swallow and audit it.
        try:
            delivery = self.notifier.send_invite(appt)
            self.audit.record(
                "invite_sent",
                appointment_id=appt.id,
                channel=delivery.get("channel"),
                to=delivery.get("to"),
            )
        except Exception as e:  # noqa: BLE001 - notification is best-effort
            self.audit.record("invite_failed", appointment_id=appt.id, detail=str(e))

        return appt

    @staticmethod
    def _idem_key(phone: str, service_type: ServiceType, start: datetime) -> str:
        raw = f"{phone}|{service_type.value}|{start.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()
