from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from trippilot.domain import Currency, Interest, PricingBasis
from trippilot.providers import (
    AccommodationOptionRecord,
    ActivityRecord,
    FeeRecord,
    FixtureSnapshot,
    JsonMockTravelDataProvider,
    LocationRecord,
    MealOptionRecord,
    OperatingWindowRecord,
    TransferEstimateRecord,
    TransportOptionRecord,
    TravelDataProvider,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"
INVALID_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def provider() -> JsonMockTravelDataProvider:
    return JsonMockTravelDataProvider(FIXTURE_PATH)


def _payload() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text("utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "invalid-snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _record(payload: dict[str, Any], record_id: str) -> dict[str, Any]:
    return next(
        record for record in payload["records"] if record["record_id"] == record_id
    )


def _prices(record: object) -> tuple[object, ...]:
    values = []
    for field in ("price", "nightly_price"):
        value = getattr(record, field, None)
        if value is not None:
            values.append(value)
    return tuple(values)


def test_complete_fixture_snapshot_loads(provider: JsonMockTravelDataProvider) -> None:
    assert provider.get_destination("Toronto") is not None
    assert provider.list_transport_options("Kingston, Ontario", "Toronto, Ontario")
    assert provider.list_accommodation_options("dest-toronto")
    assert provider.list_activities("dest-toronto")
    assert provider.list_meal_options("dest-toronto")


def test_snapshot_metadata_is_stable(provider: JsonMockTravelDataProvider) -> None:
    metadata = provider.get_snapshot_metadata()

    assert metadata.snapshot_version == "2026-08-01.v1"
    assert metadata.scenario_id == "kingston-toronto"
    assert metadata.supported_currencies == (Currency.CAD,)
    assert metadata.generated_at.utcoffset() is not None


def test_query_results_have_stable_order(provider: JsonMockTravelDataProvider) -> None:
    first = provider.list_activities("dest-toronto")
    second = provider.list_activities("dest-toronto")

    assert first == second
    assert [record.record_id for record in first] == sorted(
        record.record_id for record in first
    )


def test_record_ids_are_globally_unique() -> None:
    snapshot = FixtureSnapshot.model_validate_json(FIXTURE_PATH.read_text("utf-8"))
    ids = [record.record_id for record in snapshot.records]

    assert len(ids) == len(set(ids))


def test_records_use_supported_currencies_and_non_negative_money() -> None:
    snapshot = FixtureSnapshot.model_validate_json(FIXTURE_PATH.read_text("utf-8"))
    supported = set(snapshot.metadata.supported_currencies)

    for record in snapshot.records:
        assert record.currency in supported
        for price in _prices(record):
            assert price.currency in supported
            assert price.amount_minor >= 0


def test_destination_and_locations_use_valid_iana_timezones(
    provider: JsonMockTravelDataProvider,
) -> None:
    records = [provider.get_destination("Toronto, Ontario")]
    snapshot = FixtureSnapshot.model_validate_json(FIXTURE_PATH.read_text("utf-8"))
    records.extend(
        record for record in snapshot.records if isinstance(record, LocationRecord)
    )

    for record in records:
        assert record is not None
        assert ZoneInfo(record.timezone).key == "America/Toronto"


def test_operating_windows_are_valid_and_linked(
    provider: JsonMockTravelDataProvider,
) -> None:
    for activity in provider.list_activities("dest-toronto"):
        windows = provider.get_operating_windows(activity.record_id)
        assert windows
        assert all(
            window.local_start_time < window.local_end_time for window in windows
        )
        assert all(
            window.applies_to_record_id == activity.record_id for window in windows
        )


def test_accommodation_rules_are_valid(provider: JsonMockTravelDataProvider) -> None:
    options = provider.list_accommodation_options("dest-toronto")

    assert all(isinstance(option, AccommodationOptionRecord) for option in options)
    assert all(option.minimum_nights <= option.maximum_nights for option in options)
    assert all(option.check_in_time != option.check_out_time for option in options)


def test_pricing_basis_parses_per_person_and_per_group(
    provider: JsonMockTravelDataProvider,
) -> None:
    records = (
        *provider.list_transport_options("Kingston, Ontario", "Toronto, Ontario"),
        *provider.list_accommodation_options("dest-toronto"),
        *provider.list_activities("dest-toronto"),
        *provider.list_meal_options("dest-toronto"),
    )
    bases = {price.basis for record in records for price in _prices(record)}

    assert bases == {PricingBasis.PER_PERSON, PricingBasis.PER_GROUP}


def test_record_lookup_returns_typed_record(
    provider: JsonMockTravelDataProvider,
) -> None:
    record = provider.get_record("activity-gallery")

    assert isinstance(record, ActivityRecord)
    assert not isinstance(record, dict)


def test_missing_record_returns_none(provider: JsonMockTravelDataProvider) -> None:
    assert provider.get_record("missing-record") is None
    assert provider.get_destination("missing-destination") is None


def test_transfer_lookup_returns_typed_estimate(
    provider: JsonMockTravelDataProvider,
) -> None:
    estimate = provider.get_transfer_estimate(
        "loc-toronto-terminal", "loc-civic-gallery"
    )

    assert isinstance(estimate, TransferEstimateRecord)
    assert estimate.duration_minutes == 18


def test_missing_transfer_returns_none(provider: JsonMockTravelDataProvider) -> None:
    assert provider.get_transfer_estimate("loc-island-park", "loc-sports-yard") is None


def test_fees_for_selected_records_are_typed_and_stably_ordered(
    provider: JsonMockTravelDataProvider,
) -> None:
    first = provider.list_fees("activity-gallery")
    second = provider.list_fees("activity-gallery")

    assert first == second
    assert [fee.record_id for fee in first] == ["fee-gallery-service"]
    assert all(isinstance(fee, FeeRecord) for fee in first)
    assert provider.list_fees("missing-record") == ()


@pytest.mark.parametrize(
    "fixture_name",
    [
        "duplicate-ids.json",
        "invalid-reference.json",
        "negative-price.json",
        "unknown-field.json",
    ],
)
def test_static_invalid_fixtures_are_rejected(fixture_name: str) -> None:
    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(INVALID_FIXTURES / fixture_name)


def test_negative_duration_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    _record(payload, "activity-gallery")["duration_minutes"] = -1

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_negative_transfer_duration_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    _record(payload, "transfer-terminal-gallery")["duration_minutes"] = -1

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_currency_not_supported_by_snapshot_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    record = _record(payload, "activity-gallery")
    record["currency"] = "USD"
    record["price"]["currency"] = "USD"

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_floating_point_money_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    _record(payload, "activity-gallery")["price"]["amount_minor"] = 1800.0

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_duplicate_directional_transfer_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    duplicate = dict(_record(payload, "transfer-terminal-gallery"))
    duplicate["record_id"] = "transfer-terminal-gallery-duplicate"
    payload["records"].append(duplicate)

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


@pytest.mark.parametrize("record_id", ["window-gallery", "fee-gallery-service"])
def test_attached_record_location_must_match_target(
    tmp_path: Path, record_id: str
) -> None:
    payload = _payload()
    _record(payload, record_id)["location_id"] = "loc-history-hall"

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_fee_must_apply_to_a_priced_option(tmp_path: Path) -> None:
    payload = _payload()
    _record(payload, "fee-gallery-service")["applies_to_record_id"] = "loc-toronto"

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_duplicate_operating_window_reference_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    activity = _record(payload, "activity-gallery")
    activity["operating_window_ids"].append("window-gallery")

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


@pytest.mark.parametrize(
    ("record_id", "field", "value"),
    [
        ("transport-in-coach-aug10", "departure_at", "2026-08-10T07:00:00"),
        ("loc-toronto", "timezone", "Not/A_Real_Zone"),
        ("window-gallery", "local_end_time", "10:00:00"),
        ("window-gallery", "weekdays", [-1]),
        ("window-gallery", "weekdays", [7]),
        ("stay-campus-lodge", "maximum_nights", 0),
        ("transport-in-coach-aug10", "arrival_at", "2026-08-10T07:00:00-04:00"),
    ],
)
def test_invalid_time_and_accommodation_values_are_rejected(
    tmp_path: Path, record_id: str, field: str, value: object
) -> None:
    payload = _payload()
    _record(payload, record_id)[field] = value

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_accommodation_maximum_cannot_be_below_minimum(tmp_path: Path) -> None:
    payload = _payload()
    stay = _record(payload, "stay-campus-lodge")
    stay["minimum_nights"] = 2
    stay["maximum_nights"] = 1

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_invalid_pricing_basis_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    _record(payload, "activity-gallery")["price"]["basis"] = "per_ticket"

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_snapshot_version_inconsistency_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    _record(payload, "activity-gallery")["snapshot_version"] = "different-version"

    with pytest.raises(ValidationError):
        JsonMockTravelDataProvider(_write_payload(tmp_path, payload))


def test_provider_conforms_to_runtime_protocol(
    provider: JsonMockTravelDataProvider,
) -> None:
    assert isinstance(provider, TravelDataProvider)


def test_fixture_and_provider_execute_fully_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden in provider contract tests")

    monkeypatch.setattr(socket, "socket", reject_network)
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)

    assert provider.list_activities("dest-toronto", (Interest.NATURE,))


def test_all_expected_internal_record_types_are_present() -> None:
    snapshot = FixtureSnapshot.model_validate_json(FIXTURE_PATH.read_text("utf-8"))

    expected = {
        AccommodationOptionRecord,
        ActivityRecord,
        FeeRecord,
        LocationRecord,
        MealOptionRecord,
        OperatingWindowRecord,
        TransferEstimateRecord,
        TransportOptionRecord,
    }
    assert expected.issubset({type(record) for record in snapshot.records})
