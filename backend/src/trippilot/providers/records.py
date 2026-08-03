"""Strict internal travel-provider records and fixture boundary schemas."""

# pyright: reportIncompatibleVariableOverride=false
# Frozen Pydantic discriminator subclasses intentionally narrow record_type.

from __future__ import annotations

from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic import model_validator as pydantic_model_validator

from trippilot.domain import Currency, Interest, PricingBasis

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RecordId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]


class ProviderSchema(BaseModel):
    """Base for provider and fixture boundaries: strict, frozen, no extras."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RecordType(StrEnum):
    DESTINATION = "destination"
    LOCATION = "location"
    TRANSPORT = "transport"
    ACCOMMODATION = "accommodation"
    ACTIVITY = "activity"
    MEAL = "meal"
    OPERATING_WINDOW = "operating_window"
    TRANSFER = "transfer"
    FEE = "fee"


class LocationKind(StrEnum):
    CITY = "city"
    TRANSIT = "transit"
    ZONE = "zone"
    VENUE = "venue"
    ACCOMMODATION = "accommodation"
    MEAL = "meal"


class TransportMode(StrEnum):
    TRAIN = "train"
    COACH = "coach"


class PriceRecord(ProviderSchema):
    amount_minor: int = Field(ge=0)
    currency: Currency
    basis: PricingBasis


class SnapshotMetadata(ProviderSchema):
    snapshot_version: NonEmptyString
    source_label: NonEmptyString
    scenario_id: RecordId
    generated_at: datetime
    supported_currencies: tuple[Currency, ...] = Field(min_length=1)

    @field_validator("generated_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @pydantic_model_validator(mode="after")
    def require_unique_currencies(self) -> Self:
        if len(set(self.supported_currencies)) != len(self.supported_currencies):
            raise ValueError("supported currencies must be unique")
        return self


class BaseRecord(ProviderSchema):
    record_id: RecordId
    record_type: RecordType
    source_label: NonEmptyString
    snapshot_version: NonEmptyString
    location_id: RecordId
    currency: Currency


class DestinationRecord(BaseRecord):
    record_type: Literal[RecordType.DESTINATION]
    city: NonEmptyString
    region: NonEmptyString
    country_code: Literal["CA", "US"]
    timezone: NonEmptyString

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            return ZoneInfo(value).key
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be a valid IANA name") from error


class LocationRecord(BaseRecord):
    record_type: Literal[RecordType.LOCATION]
    name: NonEmptyString
    kind: LocationKind
    timezone: NonEmptyString
    zone: NonEmptyString

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            return ZoneInfo(value).key
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be a valid IANA name") from error


class TransportOptionRecord(BaseRecord):
    record_type: Literal[RecordType.TRANSPORT]
    title: NonEmptyString
    mode: TransportMode
    origin: NonEmptyString
    destination: NonEmptyString
    origin_location_id: RecordId
    destination_location_id: RecordId
    departure_at: datetime
    arrival_at: datetime
    price: PriceRecord
    tags: tuple[NonEmptyString, ...] = ()

    @field_validator("departure_at", "arrival_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transport timestamps must be timezone-aware")
        return value

    @pydantic_model_validator(mode="after")
    def require_positive_duration_and_matching_currency(self) -> Self:
        if self.arrival_at.astimezone(UTC) <= self.departure_at.astimezone(UTC):
            raise ValueError("transport duration must be positive")
        if self.price.currency != self.currency:
            raise ValueError("transport price currency must match record currency")
        return self


class AccommodationOptionRecord(BaseRecord):
    record_type: Literal[RecordType.ACCOMMODATION]
    title: NonEmptyString
    destination_id: RecordId
    check_in_time: time
    check_out_time: time
    minimum_nights: int = Field(ge=1, le=4)
    maximum_nights: int = Field(ge=1, le=4)
    nightly_price: PriceRecord
    tags: tuple[NonEmptyString, ...] = ()

    @field_validator("check_in_time", "check_out_time")
    @classmethod
    def require_local_wall_clock(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("check-in and check-out rules must be local wall times")
        return value

    @pydantic_model_validator(mode="after")
    def require_valid_stay_rules(self) -> Self:
        if self.maximum_nights < self.minimum_nights:
            raise ValueError("maximum_nights cannot be less than minimum_nights")
        if self.check_in_time == self.check_out_time:
            raise ValueError("check-in and check-out times must differ")
        if self.nightly_price.currency != self.currency:
            raise ValueError("accommodation price currency must match record currency")
        return self


class ActivityRecord(BaseRecord):
    record_type: Literal[RecordType.ACTIVITY]
    title: NonEmptyString
    destination_id: RecordId
    duration_minutes: int = Field(gt=0)
    price: PriceRecord
    interests: tuple[Interest, ...] = Field(min_length=1)
    operating_window_ids: tuple[RecordId, ...] = Field(min_length=1)

    @pydantic_model_validator(mode="after")
    def require_matching_currency(self) -> Self:
        if self.price.currency != self.currency:
            raise ValueError("activity price currency must match record currency")
        return self


class MealOptionRecord(BaseRecord):
    record_type: Literal[RecordType.MEAL]
    title: NonEmptyString
    destination_id: RecordId
    duration_minutes: int = Field(gt=0)
    price: PriceRecord
    tags: tuple[NonEmptyString, ...] = Field(min_length=1)
    operating_window_ids: tuple[RecordId, ...] = Field(min_length=1)

    @pydantic_model_validator(mode="after")
    def require_matching_currency(self) -> Self:
        if self.price.currency != self.currency:
            raise ValueError("meal price currency must match record currency")
        return self


class OperatingWindowRecord(BaseRecord):
    record_type: Literal[RecordType.OPERATING_WINDOW]
    applies_to_record_id: RecordId
    weekdays: tuple[int, ...] = Field(
        min_length=1, description="Local weekdays using Monday=0 through Sunday=6."
    )
    local_start_time: time
    local_end_time: time

    @field_validator("weekdays")
    @classmethod
    def require_valid_unique_weekdays(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(isinstance(day, bool) or not 0 <= day <= 6 for day in value):
            raise ValueError("weekdays must be integers from 0 through 6")
        if len(set(value)) != len(value):
            raise ValueError("weekdays must be unique")
        return value

    @field_validator("local_start_time", "local_end_time")
    @classmethod
    def require_local_wall_clock(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("operating windows must use local wall times")
        return value

    @pydantic_model_validator(mode="after")
    def require_ordered_window(self) -> Self:
        if self.local_end_time <= self.local_start_time:
            raise ValueError("operating window end must be after start")
        return self


class TransferEstimateRecord(BaseRecord):
    record_type: Literal[RecordType.TRANSFER]
    from_location_id: RecordId
    to_location_id: RecordId
    duration_minutes: int = Field(ge=0)
    mode: Literal["walk", "transit"]


class FeeRecord(BaseRecord):
    record_type: Literal[RecordType.FEE]
    title: NonEmptyString
    applies_to_record_id: RecordId
    price: PriceRecord
    fee_kind: Literal["tax", "fee"]

    @pydantic_model_validator(mode="after")
    def require_matching_currency(self) -> Self:
        if self.price.currency != self.currency:
            raise ValueError("fee currency must match record currency")
        return self


ProviderRecord = Annotated[
    DestinationRecord
    | LocationRecord
    | TransportOptionRecord
    | AccommodationOptionRecord
    | ActivityRecord
    | MealOptionRecord
    | OperatingWindowRecord
    | TransferEstimateRecord
    | FeeRecord,
    Field(discriminator="record_type"),
]


class FixtureSnapshot(ProviderSchema):
    metadata: SnapshotMetadata
    records: tuple[ProviderRecord, ...] = Field(min_length=1)

    @pydantic_model_validator(mode="after")
    def validate_snapshot_contract(self) -> Self:
        ids = [record.record_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError("fixture record IDs must be unique")
        if any(
            record.snapshot_version != self.metadata.snapshot_version
            for record in self.records
        ):
            raise ValueError("all records must match the fixture snapshot version")
        supported = set(self.metadata.supported_currencies)
        if any(record.currency not in supported for record in self.records):
            raise ValueError("record currency is not supported by this snapshot")

        by_id = {record.record_id: record for record in self.records}
        location_ids = {
            record.record_id
            for record in self.records
            if isinstance(record, LocationRecord)
        }
        destination_ids = {
            record.record_id
            for record in self.records
            if isinstance(record, DestinationRecord)
        }
        transfer_routes: set[tuple[str, str]] = set()
        for record in self.records:
            if record.location_id not in location_ids:
                raise ValueError(
                    f"record {record.record_id} references a missing location"
                )
            if isinstance(record, (TransportOptionRecord, TransferEstimateRecord)):
                referenced = (
                    (record.origin_location_id, record.destination_location_id)
                    if isinstance(record, TransportOptionRecord)
                    else (record.from_location_id, record.to_location_id)
                )
                if any(value not in location_ids for value in referenced):
                    raise ValueError(
                        f"record {record.record_id} references a missing location"
                    )
            if (
                isinstance(
                    record,
                    (AccommodationOptionRecord, ActivityRecord, MealOptionRecord),
                )
                and record.destination_id not in destination_ids
            ):
                raise ValueError(
                    f"record {record.record_id} references a missing destination"
                )
            if isinstance(record, (ActivityRecord, MealOptionRecord)):
                if len(set(record.operating_window_ids)) != len(
                    record.operating_window_ids
                ):
                    raise ValueError(
                        f"record {record.record_id} repeats an operating window"
                    )
                for window_id in record.operating_window_ids:
                    window = by_id.get(window_id)
                    if not isinstance(window, OperatingWindowRecord):
                        raise ValueError(
                            f"record {record.record_id} references a missing window"
                        )
                    if window.applies_to_record_id != record.record_id:
                        raise ValueError(
                            f"window {window_id} applies to a different record"
                        )
                    if (
                        window.location_id != record.location_id
                        or window.currency != record.currency
                    ):
                        raise ValueError(
                            f"window {window_id} must match its target location "
                            "and currency"
                        )
            if isinstance(record, OperatingWindowRecord):
                target = by_id.get(record.applies_to_record_id)
                if not isinstance(target, (ActivityRecord, MealOptionRecord)):
                    raise ValueError(
                        f"window {record.record_id} references an invalid record"
                    )
            if isinstance(record, TransferEstimateRecord):
                route = (record.from_location_id, record.to_location_id)
                if route in transfer_routes:
                    raise ValueError("transfer routes must be unique and directional")
                transfer_routes.add(route)
            if (
                isinstance(record, FeeRecord)
                and record.applies_to_record_id not in by_id
            ):
                raise ValueError(f"fee {record.record_id} references a missing record")
            if isinstance(record, FeeRecord):
                target = by_id[record.applies_to_record_id]
                if not isinstance(
                    target,
                    (
                        TransportOptionRecord,
                        AccommodationOptionRecord,
                        ActivityRecord,
                        MealOptionRecord,
                    ),
                ):
                    raise ValueError(
                        f"fee {record.record_id} must apply to a priced option"
                    )
                if (
                    record.location_id != target.location_id
                    or record.currency != target.currency
                ):
                    raise ValueError(
                        f"fee {record.record_id} must match its target location "
                        "and currency"
                    )
        return self
