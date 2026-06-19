"""Domain models for the dealer service-scheduling agent.

These are surface-agnostic on purpose. Nothing here knows about VAPI, phones,
the in-cabin head unit, or telematics. A phone call and a telematics event both
end up producing the same `Appointment`. That is the whole platform thesis:
build the action layer once, let each surface adapt onto it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Source(str, Enum):
    """Which input surface triggered the action. The action layer treats them
    identically; this field exists only for attribution and analytics."""

    PHONE = "phone"
    IN_CABIN = "in_cabin"
    TELEMATICS = "telematics"


class ServiceType(str, Enum):
    OIL_CHANGE = "oil_change"
    TIRE_ROTATION = "tire_rotation"
    BRAKE_INSPECTION = "brake_inspection"
    DIAGNOSTIC = "diagnostic"
    MULTI_POINT_INSPECTION = "multi_point_inspection"
    RECALL = "recall"
    OTHER = "other"


# Minutes of bay time each service needs. v1 keeps everything to clean hour
# blocks; real durations get wired in once the DMS exposes labor-op times.
SERVICE_DURATION_MIN: dict[ServiceType, int] = {
    ServiceType.OIL_CHANGE: 60,
    ServiceType.TIRE_ROTATION: 60,
    ServiceType.BRAKE_INSPECTION: 60,
    ServiceType.DIAGNOSTIC: 60,
    ServiceType.MULTI_POINT_INSPECTION: 60,
    ServiceType.RECALL: 60,
    ServiceType.OTHER: 60,
}

# Human-readable labels for voice responses.
SERVICE_LABEL: dict[ServiceType, str] = {
    ServiceType.OIL_CHANGE: "oil change",
    ServiceType.TIRE_ROTATION: "tire rotation",
    ServiceType.BRAKE_INSPECTION: "brake inspection",
    ServiceType.DIAGNOSTIC: "diagnostic",
    ServiceType.MULTI_POINT_INSPECTION: "multi-point inspection",
    ServiceType.RECALL: "recall service",
    ServiceType.OTHER: "service",
}


class AppointmentStatus(str, Enum):
    BOOKED = "booked"
    CANCELLED = "cancelled"


class Customer(BaseModel):
    name: str
    phone: str


class Vehicle(BaseModel):
    year: int | None = None
    make: str | None = None
    model: str | None = None
    vin: str | None = None
    mileage: int | None = None

    def describe(self) -> str:
        parts = [str(p) for p in (self.year, self.make, self.model) if p]
        return " ".join(parts) if parts else "your vehicle"


class Slot(BaseModel):
    start: datetime
    end: datetime
    advisor_id: str
    advisor_name: str


class Appointment(BaseModel):
    id: str
    confirmation_code: str
    dealer_id: str
    customer: Customer
    vehicle: Vehicle
    service_type: ServiceType
    slot: Slot
    status: AppointmentStatus = AppointmentStatus.BOOKED
    source: Source = Source.PHONE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
