"""Typed travel-provider contracts and offline mock implementation."""

from .mock import JsonMockTravelDataProvider
from .protocol import TravelDataProvider
from .records import (
    AccommodationOptionRecord,
    ActivityRecord,
    DestinationRecord,
    FeeRecord,
    FixtureSnapshot,
    LocationKind,
    LocationRecord,
    MealOptionRecord,
    OperatingWindowRecord,
    PriceRecord,
    ProviderRecord,
    RecordType,
    SnapshotMetadata,
    TransferEstimateRecord,
    TransportMode,
    TransportOptionRecord,
)

__all__ = [
    "AccommodationOptionRecord",
    "ActivityRecord",
    "DestinationRecord",
    "FeeRecord",
    "FixtureSnapshot",
    "JsonMockTravelDataProvider",
    "LocationKind",
    "LocationRecord",
    "MealOptionRecord",
    "OperatingWindowRecord",
    "PriceRecord",
    "ProviderRecord",
    "RecordType",
    "SnapshotMetadata",
    "TransferEstimateRecord",
    "TransportMode",
    "TransportOptionRecord",
    "TravelDataProvider",
]
