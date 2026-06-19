"""Action-layer tests. These exercise the surface-agnostic core directly."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.actions.scheduling import SchedulingService
from app.config import dealer
from app.dms.base import SlotUnavailable
from app.dms.mock import MockDMS
from app.models import Customer, ServiceType, Vehicle
from app.safety import ValidationError
from app.store import AuditLog, IdempotencyStore


def _svc() -> SchedulingService:
    return SchedulingService(MockDMS(), IdempotencyStore(), AuditLog())


def _next_workday_at(hour: int) -> datetime:
    d = datetime.now(dealer.timezone) + timedelta(days=1)
    while d.weekday() not in dealer.work_days:
        d += timedelta(days=1)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def test_find_slots_returns_offers():
    svc = _svc()
    start = _next_workday_at(0)
    slots = svc.find_slots(ServiceType.OIL_CHANGE, start, start + timedelta(days=2))
    assert len(slots) == 3
    assert all(s.advisor_name for s in slots)


def test_check_availability_exact_and_alternatives():
    svc = _svc()
    desired = _next_workday_at(9)
    exact, alts = svc.check_availability(ServiceType.TIRE_ROTATION, desired)
    assert exact is not None
    assert exact.start == desired
    assert len(alts) <= 2
    assert all(a.start != desired for a in alts)


def test_book_creates_appointment_with_code():
    svc = _svc()
    desired = _next_workday_at(10)
    exact, _ = svc.check_availability(ServiceType.OIL_CHANGE, desired)
    appt = svc.book(
        Customer(name="Pat", phone="+15125551111"),
        Vehicle(year=2021, make="Toyota", model="RAV4"),
        ServiceType.OIL_CHANGE,
        exact,
    )
    assert appt.status.value == "booked"
    assert len(appt.confirmation_code) == 4


def test_book_is_idempotent():
    svc = _svc()
    desired = _next_workday_at(11)
    exact, _ = svc.check_availability(ServiceType.OIL_CHANGE, desired)
    cust = Customer(name="Pat", phone="+15125551111")
    veh = Vehicle(make="Toyota")
    a1 = svc.book(cust, veh, ServiceType.OIL_CHANGE, exact)
    a2 = svc.book(cust, veh, ServiceType.OIL_CHANGE, exact)
    assert a1.id == a2.id  # same intent never double-books


def test_double_book_by_different_caller_is_blocked():
    svc = _svc()
    desired = _next_workday_at(12)
    exact, _ = svc.check_availability(ServiceType.OIL_CHANGE, desired)
    svc.book(Customer(name="A", phone="+15125550001"), Vehicle(), ServiceType.OIL_CHANGE, exact)
    # Second caller, same concrete slot -> the bay is taken.
    exact2, _ = svc.check_availability(ServiceType.OIL_CHANGE, desired)
    # Only one advisor capacity per block in seed; the second advisor may exist,
    # so book until the slot/advisor is exhausted and expect it to raise.
    with pytest.raises(SlotUnavailable):
        # Force the exact same advisor+start that was just taken.
        svc.book(
            Customer(name="B", phone="+15125550002"),
            Vehicle(),
            ServiceType.OIL_CHANGE,
            exact,
        )


def test_booking_outside_hours_rejected():
    svc = _svc()
    # 3 AM is outside service hours.
    bad = _next_workday_at(3)
    exact, _ = svc.check_availability(ServiceType.OIL_CHANGE, bad)
    # No exact slot off-hours; fabricate a slot to hit the guard directly.
    from app.models import Slot

    slot = Slot(start=bad, end=bad + timedelta(hours=1), advisor_id="adv_1", advisor_name="Maria")
    with pytest.raises(ValidationError):
        svc.book(Customer(name="X", phone="+15125550003"), Vehicle(), ServiceType.OIL_CHANGE, slot)
