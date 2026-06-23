"""Calendar-invite flow: .ics generation, notifier, caller-ID, hosted endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.actions.scheduling import SchedulingService
from app.config import dealer
from app.dms.mock import MockDMS
from app.main import app
from app.models import Customer, ServiceType, Vehicle
from app.notify.ics import build_ics
from app.store import AuditLog, IdempotencyStore

client = TestClient(app)


def _next_workday_at(hour: int) -> datetime:
    d = datetime.now(dealer.timezone) + timedelta(days=1)
    while d.weekday() not in dealer.work_days:
        d += timedelta(days=1)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def _booked():
    svc = SchedulingService(MockDMS(), IdempotencyStore(), AuditLog())
    exact, _ = svc.check_availability(ServiceType.OIL_CHANGE, _next_workday_at(9))
    appt = svc.book(
        Customer(name="Pat", phone="+15125551234"),
        Vehicle(year=2021, make="Toyota", model="RAV4"),
        ServiceType.OIL_CHANGE,
        exact,
    )
    return svc, appt


def test_ics_is_valid_vevent():
    _, appt = _booked()
    ics = build_ics(appt)
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert "BEGIN:VEVENT" in ics and "END:VCALENDAR" in ics
    assert "\r\n" in ics  # iCalendar requires CRLF
    assert f"UID:{appt.id}@bharathkumarmotors" in ics
    assert "SUMMARY:Oil Change at Bharath Kumar Motors Limited" in ics
    assert appt.confirmation_code in ics  # code carried in the invite
    assert "DTSTART:" in ics and "DTEND:" in ics


def test_booking_sends_invite_and_is_retrievable():
    svc, appt = _booked()
    # MockNotifier recorded a send to the customer's number.
    assert svc.notifier.sent[-1]["to"] == "+15125551234"
    assert svc.notifier.sent[-1]["ics_url"].endswith(f"/appointments/{appt.id}.ics")
    # Audit shows it, and the appointment is retrievable for the .ics endpoint.
    assert any(e["action"] == "invite_sent" for e in svc.audit.events())
    assert svc.get_appointment(appt.id) is appt


def test_webhook_uses_caller_id_over_dictated_number():
    date = _next_workday_at(10).strftime("%Y-%m-%d")
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"customer": {"number": "+15129990000"}},  # caller ID
            "toolCallList": [
                {
                    "id": "tc_cal",
                    "function": {
                        "name": "book_service_appointment",
                        "arguments": {
                            "service_type": "oil_change",
                            "date": date,
                            "time": "10:00",
                            "customer_name": "Caller",
                            "phone": "+10000000000",  # dictated; should be ignored
                        },
                    },
                }
            ],
        }
    }
    r = client.post("/vapi/tool-calls", json=payload)
    assert r.status_code == 200
    assert "booked" in r.json()["results"][0]["result"].lower()

    events = client.get("/_audit").json()["events"]
    invite = [e for e in events if e["action"] == "invite_sent"][-1]
    assert invite["to"] == "+15129990000"  # caller ID won, not the dictated number


def test_ics_endpoint_serves_calendar():
    date = _next_workday_at(11).strftime("%Y-%m-%d")
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"customer": {"number": "+15127778888"}},
            "toolCallList": [
                {
                    "id": "tc_cal2",
                    "function": {
                        "name": "book_service_appointment",
                        "arguments": {
                            "service_type": "tire_rotation",
                            "date": date,
                            "time": "11:00",
                            "customer_name": "Caller",
                        },
                    },
                }
            ],
        }
    }
    client.post("/vapi/tool-calls", json=payload)
    appt_id = [
        e for e in client.get("/_audit").json()["events"]
        if e["action"] == "book_confirmed"
    ][-1]["appointment_id"]

    r = client.get(f"/appointments/{appt_id}.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in r.text

    assert client.get("/appointments/nope.ics").status_code == 404
