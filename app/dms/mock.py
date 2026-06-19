"""In-memory mock DMS.

Lets the whole agent run end-to-end today with zero external credentials, which
is exactly what you want for a design-partner demo and for automated tests. It
generates a realistic open-slot grid from the dealer's hours and advisors, and
enforces no-double-booking so the idempotency and reservation paths are real.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta

from app.config import dealer
from app.dms.base import DMSAdapter, SlotUnavailable
from app.models import (
    Appointment,
    Customer,
    ServiceType,
    Slot,
    Source,
    Vehicle,
)


def _conf_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars for voice
    return "".join(secrets.choice(alphabet) for _ in range(4))


class MockDMS(DMSAdapter):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        # (advisor_id, start_iso) that are taken (held or booked).
        self._taken: set[tuple[str, str]] = set()
        self._reservations: dict[str, tuple[str, datetime]] = {}
        self._appointments: dict[str, Appointment] = {}
        # Seed one known returning customer for the lookup path.
        self._customers: dict[str, Customer] = {
            "+15125550123": Customer(name="Sam Rivera", phone="+15125550123"),
        }

    def _is_open_day(self, d: datetime) -> bool:
        return d.weekday() in dealer.work_days

    def get_open_slots(
        self, service_type: ServiceType, date_from: datetime, date_to: datetime
    ) -> list[Slot]:
        with self._lock:
            slots: list[Slot] = []
            day = date_from.astimezone(dealer.timezone).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = date_to.astimezone(dealer.timezone)
            step = timedelta(minutes=dealer.slot_granularity_min)
            while day <= end:
                if self._is_open_day(day):
                    for hour in range(dealer.open_hour, dealer.close_hour):
                        start = day.replace(hour=hour)
                        if start < date_from.astimezone(dealer.timezone):
                            continue
                        for adv_id, adv_name in dealer.advisors:
                            if (adv_id, start.isoformat()) in self._taken:
                                continue
                            slots.append(
                                Slot(
                                    start=start,
                                    end=start + step,
                                    advisor_id=adv_id,
                                    advisor_name=adv_name,
                                )
                            )
                            break  # one advisor per time block is enough to offer
                day += timedelta(days=1)
            return slots

    def reserve_slot(self, slot: Slot, hold_seconds: int = 120) -> str:
        with self._lock:
            key = (slot.advisor_id, slot.start.isoformat())
            if key in self._taken:
                raise SlotUnavailable(slot.start.isoformat())
            self._taken.add(key)
            rid = "res_" + secrets.token_hex(6)
            self._reservations[rid] = (slot.advisor_id, slot.start)
            return rid

    def create_appointment(
        self,
        reservation_id: str,
        customer: Customer,
        vehicle: Vehicle,
        service_type: ServiceType,
        slot: Slot,
        source: Source,
    ) -> Appointment:
        with self._lock:
            if reservation_id not in self._reservations:
                raise SlotUnavailable("reservation expired")
            appt = Appointment(
                id="appt_" + secrets.token_hex(6),
                confirmation_code=_conf_code(),
                dealer_id=dealer.dealer_id,
                customer=customer,
                vehicle=vehicle,
                service_type=service_type,
                slot=slot,
                source=source,
            )
            self._appointments[appt.id] = appt
            del self._reservations[reservation_id]  # hold becomes a booking
            return appt

    def find_customer_by_phone(self, phone: str) -> Customer | None:
        with self._lock:
            return self._customers.get(phone)
