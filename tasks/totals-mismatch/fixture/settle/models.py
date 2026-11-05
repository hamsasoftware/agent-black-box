from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    event_id: str
    merchant_id: str
    kind: str  # "charge", "refund" or "refund_reversal"
    currency: str
    amount_minor: int
    occurred_at: datetime  # timezone-aware, UTC
    received_at: datetime  # timezone-aware, UTC
    status: str


@dataclass(frozen=True)
class Merchant:
    merchant_id: str
    name: str
    timezone: str
    currency: str  # settlement currency
    fee_bps: int
    fixed_fee_minor: int


@dataclass(frozen=True)
class Line:
    """One event after conversion into the merchant's settlement currency."""

    kind: str
    amount_minor: int


@dataclass(frozen=True)
class Payout:
    merchant_id: str
    day: str  # YYYY-MM-DD, the settlement day
    currency: str
    charges_minor: int
    refunds_minor: int
    fee_minor: int
    net_minor: int
