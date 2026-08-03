"""Framework-independent values used by deterministic itinerary validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum


class Currency(StrEnum):
    CAD = "CAD"
    USD = "USD"


class Interest(StrEnum):
    FOOD = "food"
    ARTS_CULTURE = "arts_culture"
    NATURE = "nature"
    HISTORY = "history"
    NIGHTLIFE = "nightlife"
    SHOPPING = "shopping"
    SPORTS = "sports"
    STUDENT_BUDGET = "student_budget"


class Pace(StrEnum):
    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class ItemKind(StrEnum):
    ACTIVITY = "activity"
    MEAL = "meal"
    TRANSPORT = "transport"


class TransportRole(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    LOCAL = "local"


class PricingBasis(StrEnum):
    PER_PERSON = "per_person"
    PER_GROUP = "per_group"


class Severity(StrEnum):
    ERROR = "error"


class ViolationCode(StrEnum):
    """Stable machine-readable codes emitted by the Milestone 1 validator."""

    ORIGIN_REQUIRED = "ORIGIN_REQUIRED"
    DESTINATION_REQUIRED = "DESTINATION_REQUIRED"
    ORIGIN_DESTINATION_SAME = "ORIGIN_DESTINATION_SAME"
    TRIP_LENGTH_OUT_OF_RANGE = "TRIP_LENGTH_OUT_OF_RANGE"
    INVALID_TRAVELLER_COUNT = "INVALID_TRAVELLER_COUNT"
    INVALID_BUDGET = "INVALID_BUDGET"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
    INTEREST_REQUIRED = "INTEREST_REQUIRED"
    MISSING_BOUNDARY_TRANSPORT = "MISSING_BOUNDARY_TRANSPORT"
    INVALID_TIMEZONE = "INVALID_TIMEZONE"
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    INVALID_TIME_WINDOW = "INVALID_TIME_WINDOW"
    ITEM_OUTSIDE_TRIP = "ITEM_OUTSIDE_TRIP"
    INVALID_ACCOMMODATION_STAY = "INVALID_ACCOMMODATION_STAY"
    ITEM_OVERLAP = "ITEM_OVERLAP"
    ACTIVITY_TOO_EARLY = "ACTIVITY_TOO_EARLY"
    OUTSIDE_OPERATING_WINDOW = "OUTSIDE_OPERATING_WINDOW"
    INSUFFICIENT_TRANSFER_TIME = "INSUFFICIENT_TRANSFER_TIME"
    ARRIVAL_DEPARTURE_CONFLICT = "ARRIVAL_DEPARTURE_CONFLICT"
    NEGATIVE_COST = "NEGATIVE_COST"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    PRICING_INCONSISTENT = "PRICING_INCONSISTENT"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(
            self.amount_minor, int
        ):
            raise TypeError("amount_minor must be an integer")
        if self.amount_minor < 0:
            raise ValueError("amount_minor cannot be negative")
        if (
            not isinstance(self.currency, str)
            or len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isalpha()
            or not self.currency.isupper()
        ):
            raise ValueError("currency must be a three-letter uppercase ISO 4217 code")


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class Pricing:
    """The provider price used to derive one normalized all-traveller cost."""

    basis: PricingBasis
    unit_price: Money
    charged_travellers: int | None = None


@dataclass(frozen=True, slots=True)
class TripRequest:
    origin: str
    destination: str
    start_date: date
    end_date: date
    travellers: int
    budget: Money
    interests: tuple[Interest, ...]
    pace: Pace
    earliest_activity_time: time
    destination_timezone: str


@dataclass(frozen=True, slots=True)
class ScheduledItem:
    item_id: str
    title: str
    kind: ItemKind
    window: TimeWindow
    location_id: str | None
    estimated_cost: Money
    source_record_id: str | None
    pricing: Pricing
    transport_role: TransportRole | None = None


@dataclass(frozen=True, slots=True)
class AccommodationStay:
    stay_id: str
    title: str
    check_in: datetime
    check_out: datetime
    number_of_nights: int
    location_id: str | None
    estimated_cost: Money
    source_record_id: str | None
    pricing: Pricing


@dataclass(frozen=True, slots=True)
class ExplicitFee:
    fee_id: str
    title: str
    cost: Money


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    transport: Money
    accommodation: Money
    activity: Money
    meal: Money
    fees_taxes: Money

    def values(self) -> tuple[Money, ...]:
        return (
            self.transport,
            self.accommodation,
            self.activity,
            self.meal,
            self.fees_taxes,
        )


@dataclass(frozen=True, slots=True)
class NonBlockingMarker:
    marker_id: str
    title: str
    window: TimeWindow


@dataclass(frozen=True, slots=True)
class Itinerary:
    scheduled_items: tuple[ScheduledItem, ...]
    accommodation_stays: tuple[AccommodationStay, ...]
    explicit_fees: tuple[ExplicitFee, ...]
    category_totals: CostBreakdown
    total_estimated_cost: Money
    non_blocking_markers: tuple[NonBlockingMarker, ...] = ()


@dataclass(frozen=True, slots=True)
class OperatingWindow:
    record_id: str
    window: TimeWindow


@dataclass(frozen=True, slots=True)
class TransferRequirement:
    from_location_id: str
    to_location_id: str
    minimum_minutes: int


@dataclass(frozen=True, slots=True)
class ProviderSnapshot:
    record_ids: frozenset[str]
    operating_windows: tuple[OperatingWindow, ...] = ()
    transfer_requirements: tuple[TransferRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class Violation:
    code: ViolationCode
    message: str
    affected_ids: tuple[str, ...] = ()
    severity: Severity = Severity.ERROR


@dataclass(frozen=True, slots=True)
class ValidationReport:
    violations: tuple[Violation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations
