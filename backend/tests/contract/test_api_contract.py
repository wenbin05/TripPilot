from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from trippilot.api.app import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def valid_request() -> dict[str, object]:
    return {
        "origin": "Kingston, Ontario",
        "destination": "Toronto, Ontario",
        "start_date": "2026-08-10",
        "end_date": "2026-08-10",
        "travellers": 1,
        "total_budget_minor": 100_000,
        "currency": "CAD",
        "interests": ["arts_culture", "nature", "student_budget"],
        "pace": "balanced",
        "earliest_activity_time": "09:00:00",
    }


def test_health_contract(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "trippilot-api"}


@pytest.mark.parametrize(
    ("change", "missing"),
    [
        ({"end_date": "2026-08-09"}, None),
        ({"end_date": "2026-08-14"}, None),
        ({"start_date": "2026-02-30"}, None),
        ({"unexpected": "rejected"}, None),
        ({"currency": "EUR"}, None),
        ({"pace": "rushed"}, None),
        ({"interests": []}, None),
        ({"interests": ["nature"] * 9}, None),
        ({"interests": ["not_an_interest"]}, None),
        ({"travellers": 0}, None),
        ({"travellers": 11}, None),
        ({"travellers": True}, None),
        ({"total_budget_minor": 0}, None),
        ({"total_budget_minor": -1}, None),
        ({"earliest_activity_time": "25:00:00"}, None),
        ({"earliest_activity_time": "09:00:00+00:00"}, None),
        ({}, "destination"),
        ({}, "origin"),
    ],
)
def test_invalid_request_contract_returns_sanitized_422(
    client: TestClient, change: dict[str, object], missing: str | None
) -> None:
    body = valid_request()
    body.update(change)
    if missing is not None:
        body.pop(missing)

    response = client.post("/api/v1/itineraries/plan", json=body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error_code"] == "REQUEST_VALIDATION_ERROR"
    assert payload["details"]
    assert "input" not in payload
    assert "traceback" not in response.text.casefold()


def test_documented_upper_bound_request_reaches_planning(client: TestClient) -> None:
    body = valid_request()
    body.update(
        {
            "end_date": "2026-08-13",
            "travellers": 10,
            "total_budget_minor": 1_000_000,
            "earliest_activity_time": "00:00:00",
        }
    )

    response = client.post("/api/v1/itineraries/plan", json=body)

    assert response.status_code == 200
    assert response.json()["status"] in {"success", "planning_failure"}


def test_request_body_size_limit_returns_sanitized_422(client: TestClient) -> None:
    body = valid_request()
    body["unexpected"] = "private-value" * 4_000

    response = client.post("/api/v1/itineraries/plan", json=body)

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_VALIDATION_ERROR"
    assert "private-value" not in response.text


def test_openapi_documents_stable_plan_envelope(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/itineraries/plan"]["post"]
    assert "200" in operation["responses"]
    assert "422" in operation["responses"]


def test_openapi_requires_canonical_location_labels(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    for schema_name in ("ScheduledItemResponse", "AccommodationStayResponse"):
        schema = schemas[schema_name]
        assert "location_label" in schema["required"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["location_label"]["anyOf"] == [
            {"type": "string", "maxLength": 200, "minLength": 1},
            {"type": "null"},
        ]
