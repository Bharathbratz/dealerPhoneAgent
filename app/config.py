"""Configuration: dealer hours/timezone and which DMS adapter is live.

In production this comes from a per-dealer record in a database (each dealer has
its own hours, advisors, and DMS vendor). For v1 it's a single dealer in code.
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo


class DealerConfig:
    dealer_id: str = "dealer_001"
    name: str = "Bharath Kumar Motors Limited"
    timezone: ZoneInfo = ZoneInfo("America/Chicago")

    # Service department hours (24h clock, local time).
    open_hour: int = 8
    close_hour: int = 17
    # 0 = Monday ... 6 = Sunday. Closed Sundays.
    work_days: tuple[int, ...] = (0, 1, 2, 3, 4, 5)

    slot_granularity_min: int = 60

    # Service advisors / bays available per time block.
    advisors: tuple[tuple[str, str], ...] = (
        ("adv_1", "Maria"),
        ("adv_2", "Devon"),
    )


# Which DMS adapter backs the action layer. "mock" runs fully offline; "tekion"
# is the real integration seam (stubbed until credentials exist).
DMS_PROVIDER = os.getenv("DMS_PROVIDER", "mock")

# Shared secret VAPI signs requests with; verify in production.
VAPI_SERVER_SECRET = os.getenv("VAPI_SERVER_SECRET", "")

dealer = DealerConfig()
