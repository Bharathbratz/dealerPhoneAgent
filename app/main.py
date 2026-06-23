"""FastAPI entrypoint.

Wires the configured DMS adapter into the action layer, and exposes the single
webhook VAPI calls. Everything returns HTTP 200 (VAPI ignores other statuses) and
tool results are single-line strings, per VAPI's custom-tools contract.

Run:  uvicorn app.main:app --reload --port 8000
Then point your VAPI tool's server URL at  https://<tunnel>/vapi/tool-calls
"""

from __future__ import annotations

import hmac

from fastapi import FastAPI, HTTPException, Request, Response

from app.actions.scheduling import SchedulingService
from app.config import DMS_PROVIDER, NOTIFY_PROVIDER, VAPI_SERVER_SECRET
from app.dms.base import DMSAdapter
from app.dms.mock import MockDMS
from app.notify.base import MockNotifier, Notifier
from app.notify.ics import build_ics
from app.store import AuditLog, IdempotencyStore
from app.surfaces.vapi import VapiSurface, parse_tool_calls


def _build_dms() -> DMSAdapter:
    if DMS_PROVIDER == "mock":
        return MockDMS()
    if DMS_PROVIDER == "tekion":
        from app.dms.tekion import TekionDMS  # imported lazily; needs creds

        raise RuntimeError(
            "DMS_PROVIDER=tekion but the Tekion adapter is not wired yet."
        )
    raise RuntimeError(f"Unknown DMS_PROVIDER: {DMS_PROVIDER}")


def _build_notifier() -> Notifier:
    if NOTIFY_PROVIDER == "mock":
        return MockNotifier()
    raise RuntimeError(f"Unknown NOTIFY_PROVIDER: {NOTIFY_PROVIDER}")


audit = AuditLog()
idempotency = IdempotencyStore()
service = SchedulingService(_build_dms(), idempotency, audit, _build_notifier())
surface = VapiSurface(service)


def _caller_number(message: dict) -> str | None:
    """The inbound caller's number from VAPI's payload (caller ID). Lets us skip
    asking the caller to dictate it and address the invite to their phone."""
    customer = (message.get("call") or {}).get("customer") or {}
    return customer.get("number")

app = FastAPI(title="Dealer Service-Scheduling Agent", version="0.1.0")


def _verify_vapi_secret(request: Request) -> None:
    """Reject calls that don't carry our shared secret.

    VAPI signs every server request with the secret configured on the tool
    (sent as the ``x-vapi-secret`` header). Without this check anyone who learns
    the public webhook URL could book or cancel on the dealer's behalf, so it's
    a real authorization boundary, not a nicety.

    If ``VAPI_SERVER_SECRET`` is unset (local/mock dev), verification is skipped
    so the agent stays runnable with zero configuration. Set the env var in any
    deployment that's reachable from the internet.
    """
    if not VAPI_SERVER_SECRET:
        return
    presented = request.headers.get("x-vapi-secret", "")
    # Constant-time compare to avoid leaking the secret via timing.
    if not hmac.compare_digest(presented, VAPI_SERVER_SECRET):
        raise HTTPException(status_code=401, detail="invalid VAPI secret")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "dms": DMS_PROVIDER, "auth": bool(VAPI_SERVER_SECRET)}


@app.post("/vapi/tool-calls")
async def vapi_tool_calls(request: Request) -> dict:
    _verify_vapi_secret(request)
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type", "")

    # Tool invocations: do the work, return matching results.
    if msg_type in ("tool-calls", "function-call", "tool_calls"):
        caller_number = _caller_number(message)
        results = []
        for tool_call_id, name, args in parse_tool_calls(message):
            result_text = surface.handle(name, args, caller_number=caller_number)
            results.append({"toolCallId": tool_call_id, "result": result_text})
        return {"results": results}

    # Lifecycle events (status updates, end-of-call reports): log and ack.
    if msg_type == "end-of-call-report":
        audit.record(
            "call_ended",
            ended_reason=message.get("endedReason"),
            duration=message.get("durationSeconds"),
        )
    return {"received": True}


@app.get("/appointments/{appointment_id}.ics")
def appointment_ics(appointment_id: str) -> Response:
    """Serve the calendar invite. This is the link we text/email the caller;
    opening it on their phone adds the appointment to Google or Apple Calendar."""
    appt = service.get_appointment(appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="appointment not found")
    return Response(
        content=build_ics(appt),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{appointment_id}.ics"'
        },
    )


@app.get("/_audit")
def get_audit() -> dict:
    """Debug/QA view of every action the agent took this process."""
    return {"events": audit.events()}
