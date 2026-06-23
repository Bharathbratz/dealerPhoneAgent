# Dealer service-scheduling agent (Phase 1)

The shippable wedge: an inbound phone agent that books service appointments,
built on the existing VAPI + ElevenLabs voice stack with a **surface-agnostic
action layer** underneath so the in-cabin and telematics surfaces can reuse it
later. VAPI handles the call and the voice; this service is the brain + action
layer it calls.

## Architecture

```
VAPI (phone call + ElevenLabs voice)
        |  tool calls (HTTP)
        v
app/surfaces/vapi.py        <- the ONLY file that knows VAPI exists
        |  domain objects
        v
app/actions/scheduling.py   <- surface-agnostic action layer ("the moat")
        |  DMSAdapter interface
        v
app/dms/mock.py             <- one adapter per DMS vendor (swap via config)
```

The discipline that makes this a platform and not three rebuilds: the surface
adapter does formatting and VAPI-specifics; the action layer returns `Slot` and
`Appointment` objects and never knows what called it. When the in-cabin or
telematics surface arrives, you add a sibling in `app/surfaces/` and the action
layer is untouched. Every `Appointment` carries a `source` field for exactly
this reason.

## What's implemented

- Three tools: `find_service_slots`, `check_service_availability`,
  `book_service_appointment`, plus `request_human_advisor`.
- VAPI custom-tools contract: replies 200 with
  `{"results":[{"toolCallId","result"}]}`, single-line string results, handles
  arguments as object OR JSON string, echoes `toolCallId` exactly.
- Safety rails shipped in v1, not deferred: input validation, business-hours
  guard, idempotency (same caller + service + time never double-books), an
  immutable audit trail, and conservative human-escalation (recalls,
  diagnostics, "get me a person", distress signals).
- A mock DMS so the whole thing runs end-to-end with zero credentials, behind
  the `DMSAdapter` interface that marks the exact integration seam.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q                      # 13 tests, action layer + webhook
```

Quick smoke test:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/_audit  # everything the agent did this session
```

## Wire it to VAPI

1. Expose the server publicly (e.g. `ngrok http 8000` or `vapi listen`).
2. In VAPI, create the four Custom Tools from `vapi/tools.json`, setting each
   tool's `server.url` to `https://<your-tunnel>/vapi/tool-calls`.
3. Paste `vapi/assistant_system_prompt.md` into the assistant, attach the tools,
   set the voice provider to ElevenLabs, and buy/assign a phone number.
4. Call the number.

## Going to a real DMS (Phase 1 -> revenue)

Add one file under `app/dms/` implementing the four `DMSAdapter` methods against
the design partner's Service Appointments API, register it in `_build_dms`, and
set `DMS_PROVIDER` to its name. CDK, Reynolds & Reynolds are all the same
pattern -- one file each. No scheduling logic changes.

## Webhook auth

The `/vapi/tool-calls` endpoint verifies the shared secret VAPI sends in the
`x-vapi-secret` header. Set `VAPI_SERVER_SECRET` (and the same value on each
VAPI tool) for any internet-reachable deployment. When the env var is unset the
endpoint stays open, so local/mock dev needs no configuration.

## Production checklist (deliberately scoped out of this build)

- Swap the in-memory stores for Postgres + Redis.
- Per-dealer config from a DB instead of `app/config.py`.
- Call-recording consent and PII handling per jurisdiction.
- A failure-taxonomy dashboard fed by `/_audit` to raise containment safely.
