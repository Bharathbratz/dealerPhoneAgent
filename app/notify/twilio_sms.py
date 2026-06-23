"""Twilio SMS notifier — texts the caller their calendar invite link.

One implementation of the Notifier interface. Uses Twilio's REST API directly
via httpx (no extra SDK dependency). The caller gets a short SMS with the
appointment and a tap-to-add .ics link that works on both Google and Apple.

Needs three env vars (see .env.example):
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
On a Twilio trial account you can only text numbers you've verified, and the body
gets a trial prefix — both fine for testing with your own phone.
"""

from __future__ import annotations

import os

import httpx

from app.config import dealer
from app.models import SERVICE_LABEL, Appointment
from app.notify.base import Notifier

_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class TwilioNotifier(Notifier):
    def __init__(self) -> None:
        self.sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
        if not (self.sid and self.token and self.from_number):
            raise RuntimeError(
                "NOTIFY_PROVIDER=twilio but TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN "
                "/ TWILIO_FROM_NUMBER are not all set."
            )

    def _body(self, appt: Appointment) -> str:
        label = SERVICE_LABEL[appt.service_type]
        when = appt.slot.start.astimezone(dealer.timezone).strftime(
            "%a %b %-d at %-I:%M %p"
        )
        return (
            f"{dealer.name}: your {label} is booked for {when} "
            f"(code {appt.confirmation_code}). Add it to your calendar: "
            f"{self.ics_url(appt)}"
        )

    def send_invite(self, appt: Appointment) -> dict:
        to = appt.customer.phone
        resp = httpx.post(
            _API.format(sid=self.sid),
            auth=(self.sid, self.token),
            data={"To": to, "From": self.from_number, "Body": self._body(appt)},
            timeout=15,
        )
        resp.raise_for_status()
        return {
            "channel": "sms",
            "to": to,
            "ics_url": self.ics_url(appt),
            "status": resp.json().get("status", "queued"),
        }
