"""Provider protocol shaped around TripPilot planning needs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from trippilot.domain import Interest

from .records import (
    AccommodationOptionRecord,
    ActivityRecord,
    DestinationRecord,
    FeeRecord,
    MealOptionRecord,
    OperatingWindowRecord,
    ProviderRecord,
    SnapshotMetadata,
    TransferEstimateRecord,
    TransportOptionRecord,
)


@runtime_checkable
class TravelDataProvider(Protocol):
    """Read-only travel candidates from one internally normalized snapshot."""

    def get_snapshot_metadata(self) -> SnapshotMetadata: ...

    def get_destination(self, destination: str) -> DestinationRecord | None: ...

    def list_transport_options(
        self, origin: str, destination: str
    ) -> tuple[TransportOptionRecord, ...]: ...

    def list_accommodation_options(
        self, destination_id: str
    ) -> tuple[AccommodationOptionRecord, ...]: ...

    def list_activities(
        self, destination_id: str, interests: tuple[Interest, ...] = ()
    ) -> tuple[ActivityRecord, ...]: ...

    def list_meal_options(
        self, destination_id: str
    ) -> tuple[MealOptionRecord, ...]: ...

    def get_record(self, record_id: str) -> ProviderRecord | None: ...

    def get_operating_windows(
        self, record_id: str
    ) -> tuple[OperatingWindowRecord, ...]: ...

    def list_fees(self, record_id: str) -> tuple[FeeRecord, ...]: ...

    def get_transfer_estimate(
        self, from_location_id: str, to_location_id: str
    ) -> TransferEstimateRecord | None: ...
