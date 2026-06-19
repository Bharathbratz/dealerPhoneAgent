"""Tekion DMS adapter — the real-integration seam.

Stubbed until Tekion API credentials exist. The point of checking this in now is
to prove the boundary: when a design partner runs on Tekion, you implement these
four methods against Tekion's Service Appointments API and flip DMS_PROVIDER.
No scheduling logic changes. The same file pattern repeats for CDK and Reynolds.
"""

from __future__ import annotations

from datetime import datetime

from app.dms.base import DMSAdapter
from app.models import Appointment, Customer, ServiceType, Slot, Source, Vehicle

_NOT_WIRED = (
    "Tekion adapter not wired yet. Implement against the Tekion Service "
    "Appointments API and set DMS_PROVIDER=tekion. Until then DMS_PROVIDER=mock."
)


class TekionDMS(DMSAdapter):
    def __init__(self, api_key: str, dealer_ref: str, base_url: str) -> None:
        self.api_key = api_key
        self.dealer_ref = dealer_ref
        self.base_url = base_url
        # self.session = httpx.Client(base_url=base_url, headers={...})

    def get_open_slots(
        self, service_type: ServiceType, date_from: datetime, date_to: datetime
    ) -> list[Slot]:
        # GET /service/appointments/availability?dealer=...&from=...&to=...
        # Map labor-op codes -> service_type, response shifts -> Slot.
        raise NotImplementedError(_NOT_WIRED)

    def reserve_slot(self, slot: Slot, hold_seconds: int = 120) -> str:
        # POST /service/appointments/holds
        raise NotImplementedError(_NOT_WIRED)

    def create_appointment(
        self,
        reservation_id: str,
        customer: Customer,
        vehicle: Vehicle,
        service_type: ServiceType,
        slot: Slot,
        source: Source,
    ) -> Appointment:
        # POST /service/appointments  (confirms the hold)
        raise NotImplementedError(_NOT_WIRED)

    def find_customer_by_phone(self, phone: str) -> Customer | None:
        # GET /crm/customers?phone=...
        raise NotImplementedError(_NOT_WIRED)
