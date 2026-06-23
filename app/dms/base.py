"""The DMS adapter interface.

Every DMS vendor (e.g. CDK, Reynolds & Reynolds) gets one implementation of this
interface. The action layer depends only on this abstract class, so adding a
vendor never touches scheduling logic — you write one new adapter and flip a
config flag. This is the seam that lets the same agent serve dealers on
different back-office systems.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.models import (
    Appointment,
    Customer,
    ServiceType,
    Slot,
    Source,
    Vehicle,
)


class SlotUnavailable(Exception):
    """Raised when a slot that looked open is taken at reservation time."""


class DMSAdapter(ABC):
    @abstractmethod
    def get_open_slots(
        self, service_type: ServiceType, date_from: datetime, date_to: datetime
    ) -> list[Slot]:
        ...

    @abstractmethod
    def reserve_slot(self, slot: Slot, hold_seconds: int = 120) -> str:
        """Place a short hold so the bay can't be taken mid-conversation.
        Returns a reservation id. Raises SlotUnavailable if already taken."""
        ...

    @abstractmethod
    def create_appointment(
        self,
        reservation_id: str,
        customer: Customer,
        vehicle: Vehicle,
        service_type: ServiceType,
        slot: Slot,
        source: Source,
    ) -> Appointment:
        ...

    @abstractmethod
    def find_customer_by_phone(self, phone: str) -> Customer | None:
        ...
