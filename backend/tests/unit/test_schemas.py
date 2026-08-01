from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from trippilot.domain import Interest, Pace, PricingBasis
from trippilot.domain.schemas import (
    AccommodationStaySchema,
    MoneySchema,
    NonBlockingMarkerSchema,
    PricingSchema,
    TimeWindowSchema,
    TripRequestSchema,
)


def test_strict_schema_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        MoneySchema.model_validate(
            {"amount_minor": 100, "currency": "CAD", "unexpected": True}
        )


def test_strict_schema_rejects_coercion() -> None:
    with pytest.raises(ValidationError):
        MoneySchema.model_validate({"amount_minor": "100", "currency": "CAD"})


def test_money_schema_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        MoneySchema.model_validate({"amount_minor": -1, "currency": "CAD"})


def test_time_window_boundary_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        TimeWindowSchema(start=datetime(2026, 8, 10, 9), end=datetime(2026, 8, 10, 10))


def test_time_window_boundary_rejects_zero_duration() -> None:
    value = datetime(2026, 8, 10, 9, tzinfo=ZoneInfo("America/Toronto"))

    with pytest.raises(ValidationError):
        TimeWindowSchema(start=value, end=value)


def test_time_window_boundary_uses_absolute_time_across_dst_fold() -> None:
    zone = ZoneInfo("America/New_York")

    schema = TimeWindowSchema(
        start=datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0),
        end=datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1),
    )

    assert schema.end.fold == 1


def test_zero_duration_marker_is_accepted_at_boundary() -> None:
    value = datetime(2026, 8, 10, 9, tzinfo=ZoneInfo("America/Toronto"))

    schema = NonBlockingMarkerSchema(
        marker_id="checkpoint", title="Checkpoint", start=value, end=value
    )

    assert schema.to_domain().window.start == schema.to_domain().window.end


def test_accommodation_boundary_rejects_reversed_stay() -> None:
    zone = ZoneInfo("America/Toronto")

    with pytest.raises(ValidationError):
        AccommodationStaySchema(
            stay_id="hotel",
            title="Hotel",
            check_in=datetime(2026, 8, 11, 11, tzinfo=zone),
            check_out=datetime(2026, 8, 10, 15, tzinfo=zone),
            number_of_nights=1,
            location_id="hotel",
            estimated_cost=MoneySchema(amount_minor=10_000, currency="CAD"),
            source_record_id="hotel",
            pricing=PricingSchema(
                basis=PricingBasis.PER_GROUP,
                unit_price=MoneySchema(amount_minor=10_000, currency="CAD"),
            ),
        )


def test_request_schema_converts_to_domain() -> None:
    schema = TripRequestSchema(
        origin="Toronto",
        destination="Montreal",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 11),
        travellers=2,
        budget=MoneySchema(amount_minor=50_000, currency="CAD"),
        interests=(Interest.FOOD,),
        pace=Pace.BALANCED,
        earliest_activity_time=time(9),
        destination_timezone="America/Toronto",
    )

    domain = schema.to_domain()

    assert domain.destination == "Montreal"
    assert domain.budget.amount_minor == 50_000
    assert domain.destination_timezone == ZoneInfo("America/Toronto").key


def test_request_schema_accepts_valid_json_boundary_values() -> None:
    schema = TripRequestSchema.model_validate_json(
        """{
          "origin": "Toronto",
          "destination": "Montreal",
          "start_date": "2026-08-10",
          "end_date": "2026-08-11",
          "travellers": 2,
          "budget": {"amount_minor": 50000, "currency": "CAD"},
          "interests": ["food"],
          "pace": "balanced",
          "earliest_activity_time": "09:00:00",
          "destination_timezone": "America/Toronto"
        }"""
    )

    assert schema.interests == (Interest.FOOD,)


@pytest.mark.parametrize(
    "change",
    [
        {"destination": "Toronto"},
        {"end_date": date(2026, 8, 14)},
        {"budget": MoneySchema(amount_minor=0, currency="CAD")},
        {"destination_timezone": "Not/A_Real_Zone"},
    ],
)
def test_request_schema_rejects_semantically_invalid_input(
    change: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "origin": "Toronto",
        "destination": "Montreal",
        "start_date": date(2026, 8, 10),
        "end_date": date(2026, 8, 11),
        "travellers": 2,
        "budget": MoneySchema(amount_minor=50_000, currency="CAD"),
        "interests": (Interest.FOOD,),
        "pace": Pace.BALANCED,
        "earliest_activity_time": time(9),
        "destination_timezone": "America/Toronto",
    }
    values.update(change)

    with pytest.raises(ValidationError):
        TripRequestSchema.model_validate(values)
