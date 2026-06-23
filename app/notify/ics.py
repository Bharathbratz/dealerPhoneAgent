"""Build a standard iCalendar (.ics) invite for an appointment.

This is just the calendar payload — channel-agnostic. A notifier decides how to
deliver the link to it. The output is a single VEVENT that Google Calendar, Apple
Calendar, and Outlook all import with one tap, which is why one file covers both
"Google or Apple": the caller's phone routes the .ics to whatever calendar it
uses. Times are emitted in UTC ("Z") so we don't need to ship a VTIMEZONE block.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import dealer
from app.models import SERVICE_LABEL, Appointment


def _esc(text: str) -> str:
    """Escape per RFC 5545 (backslash, semicolon, comma, newline)."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """RFC 5545 line folding: content lines should be <=75 octets, continued
    with CRLF + a leading space. Keeps strict parsers happy on long fields."""
    if len(line) <= 73:
        return line
    out, rest = [line[:73]], line[73:]
    while rest:
        out.append(" " + rest[:72])
        rest = rest[72:]
    return "\r\n".join(out)


def build_ics(appt: Appointment) -> str:
    label = SERVICE_LABEL[appt.service_type]
    summary = f"{label.title()} at {dealer.name}"
    desc = (
        f"Service: {label}. "
        f"Advisor: {appt.slot.advisor_name}. "
        f"Confirmation code: {appt.confirmation_code}. "
        f"Vehicle: {appt.vehicle.describe()}."
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Bharath Kumar Motors//Service Scheduler//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{appt.id}@bharathkumarmotors",
        f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_utc(appt.slot.start)}",
        f"DTEND:{_utc(appt.slot.end)}",
        f"SUMMARY:{_esc(summary)}",
        f"DESCRIPTION:{_esc(desc)}",
        f"LOCATION:{_esc(dealer.address)}",
        f"ORGANIZER;CN={_esc(dealer.name)}:mailto:{dealer.organizer_email}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
