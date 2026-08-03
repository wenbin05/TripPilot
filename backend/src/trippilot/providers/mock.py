"""Offline JSON implementation of the travel-data provider contract."""

from __future__ import annotations

from pathlib import Path

from trippilot.domain import Interest

from .records import (
    AccommodationOptionRecord,
    ActivityRecord,
    DestinationRecord,
    FeeRecord,
    FixtureSnapshot,
    MealOptionRecord,
    OperatingWindowRecord,
    ProviderRecord,
    SnapshotMetadata,
    TransferEstimateRecord,
    TransportOptionRecord,
)


class JsonMockTravelDataProvider:
    """Load and query one strict, immutable fixture snapshot from local JSON."""

    def __init__(self, fixture_path: str | Path) -> None:
        path = Path(fixture_path)
        self._snapshot = FixtureSnapshot.model_validate_json(path.read_text("utf-8"))
        self._records = tuple(
            sorted(self._snapshot.records, key=lambda record: record.record_id)
        )
        self._by_id = {record.record_id: record for record in self._records}

    def get_snapshot_metadata(self) -> SnapshotMetadata:
        return self._snapshot.metadata

    def get_destination(self, destination: str) -> DestinationRecord | None:
        query = destination.strip().casefold()
        return next(
            (
                record
                for record in self._records
                if isinstance(record, DestinationRecord)
                and query
                in {
                    record.record_id.casefold(),
                    record.city.casefold(),
                    f"{record.city}, {record.region}".casefold(),
                }
            ),
            None,
        )

    def list_transport_options(
        self, origin: str, destination: str
    ) -> tuple[TransportOptionRecord, ...]:
        normalized_origin = origin.strip().casefold()
        normalized_destination = destination.strip().casefold()
        return tuple(
            record
            for record in self._records
            if isinstance(record, TransportOptionRecord)
            and record.origin.casefold() == normalized_origin
            and record.destination.casefold() == normalized_destination
        )

    def list_accommodation_options(
        self, destination_id: str
    ) -> tuple[AccommodationOptionRecord, ...]:
        return tuple(
            record
            for record in self._records
            if isinstance(record, AccommodationOptionRecord)
            and record.destination_id == destination_id
        )

    def list_activities(
        self, destination_id: str, interests: tuple[Interest, ...] = ()
    ) -> tuple[ActivityRecord, ...]:
        requested = set(interests)
        return tuple(
            record
            for record in self._records
            if isinstance(record, ActivityRecord)
            and record.destination_id == destination_id
            and (not requested or requested.intersection(record.interests))
        )

    def list_meal_options(self, destination_id: str) -> tuple[MealOptionRecord, ...]:
        return tuple(
            record
            for record in self._records
            if isinstance(record, MealOptionRecord)
            and record.destination_id == destination_id
        )

    def get_record(self, record_id: str) -> ProviderRecord | None:
        return self._by_id.get(record_id)

    def get_operating_windows(
        self, record_id: str
    ) -> tuple[OperatingWindowRecord, ...]:
        return tuple(
            record
            for record in self._records
            if isinstance(record, OperatingWindowRecord)
            and record.applies_to_record_id == record_id
        )

    def list_fees(self, record_id: str) -> tuple[FeeRecord, ...]:
        return tuple(
            record
            for record in self._records
            if isinstance(record, FeeRecord)
            and record.applies_to_record_id == record_id
        )

    def get_transfer_estimate(
        self, from_location_id: str, to_location_id: str
    ) -> TransferEstimateRecord | None:
        return next(
            (
                record
                for record in self._records
                if isinstance(record, TransferEstimateRecord)
                and record.from_location_id == from_location_id
                and record.to_location_id == to_location_id
            ),
            None,
        )
