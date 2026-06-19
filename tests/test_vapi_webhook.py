"""Webhook tests — simulate the exact payload VAPI POSTs for tool calls."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import dealer
from app.main import app

client = TestClient(app)


def _next_workday_date(hour: int) -> tuple[str, str]:
    d = datetime.now(dealer.timezone) + timedelta(days=2)
    while d.weekday() not in dealer.work_days:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d"), f"{hour:02d}:00"


def _tool_call(name: str, args: dict, call_id: str = "tc_1") -> dict:
    return {
        "message": {
            "type": "tool-calls",
            "toolCallList": [
                {"id": call_id, "function": {"name": name, "arguments": args}}
            ],
        }
    }


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_find_slots_webhook_shape():
    date, _ = _next_workday_date(9)
    r = client.post(
        "/vapi/tool-calls",
        json=_tool_call("find_service_slots", {"service_type": "oil_change", "date": date}),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["toolCallId"] == "tc_1"  # id echoed back exactly
    assert "oil change" in body["results"][0]["result"]


def test_arguments_as_json_string():
    # VAPI often sends arguments as a JSON-encoded string, not an object.
    import json

    date, time = _next_workday_date(10)
    payload = _tool_call(
        "check_service_availability",
        json.dumps({"service_type": "tire_rotation", "date": date, "time": time}),
    )
    r = client.post("/vapi/tool-calls", json=payload)
    assert r.status_code == 200
    assert "tire rotation" in r.json()["results"][0]["result"].lower()


def test_book_webhook_returns_confirmation():
    date, time = _next_workday_date(11)
    r = client.post(
        "/vapi/tool-calls",
        json=_tool_call(
            "book_service_appointment",
            {
                "service_type": "oil_change",
                "date": date,
                "time": time,
                "customer_name": "Jordan Lee",
                "phone": "+15125559876",
                "vehicle_make": "Honda",
                "vehicle_model": "Civic",
            },
        ),
    )
    assert r.status_code == 200
    result = r.json()["results"][0]["result"]
    assert "booked" in result.lower()
    assert "confirmation code" in result.lower()


def test_webhook_open_when_no_secret_configured():
    # Default (no VAPI_SERVER_SECRET) stays open so mock/local dev needs no setup.
    date, _ = _next_workday_date(9)
    r = client.post(
        "/vapi/tool-calls",
        json=_tool_call("find_service_slots", {"service_type": "oil_change", "date": date}),
    )
    assert r.status_code == 200


def test_webhook_rejects_missing_or_wrong_secret(monkeypatch):
    monkeypatch.setattr(main_module, "VAPI_SERVER_SECRET", "s3cret")
    date, _ = _next_workday_date(9)
    payload = _tool_call("find_service_slots", {"service_type": "oil_change", "date": date})

    # No header -> rejected.
    assert client.post("/vapi/tool-calls", json=payload).status_code == 401
    # Wrong header -> rejected.
    r = client.post("/vapi/tool-calls", json=payload, headers={"x-vapi-secret": "nope"})
    assert r.status_code == 401
    # Correct header -> allowed.
    r = client.post("/vapi/tool-calls", json=payload, headers={"x-vapi-secret": "s3cret"})
    assert r.status_code == 200


def test_recall_escalates_to_human():
    date, time = _next_workday_date(13)
    r = client.post(
        "/vapi/tool-calls",
        json=_tool_call(
            "book_service_appointment",
            {"service_type": "recall", "date": date, "time": time, "phone": "+15125550000"},
        ),
    )
    assert r.status_code == 200
    assert "advisor" in r.json()["results"][0]["result"].lower()
