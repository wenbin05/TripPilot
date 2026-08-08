from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from trippilot.api.app import app, create_app
from trippilot.api.dependencies import get_planner, get_provider
from trippilot.domain import Severity, ValidationReport, Violation, ViolationCode
from trippilot.providers import LocationRecord
from trippilot.services import PlanningSuccess, plan_trip


class BrokenActivityProvider:
    def __init__(self, provider: object) -> None:
        self._provider = provider

    def __getattr__(self, name: str) -> object:
        return getattr(self._provider, name)

    def list_activities(self, destination_id: str) -> tuple[object, ...]:
        raise RuntimeError("fixture failure at /private/mock-fixture.json")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def request_body(
    *,
    end_date: str = "2026-08-10",
    budget: int = 100_000,
    destination: str = "Toronto, Ontario",
) -> dict[str, object]:
    return {
        "origin": "Kingston, Ontario",
        "destination": destination,
        "start_date": "2026-08-10",
        "end_date": end_date,
        "travellers": 1,
        "total_budget_minor": budget,
        "currency": "CAD",
        "interests": ["arts_culture", "nature", "student_budget"],
        "pace": "balanced",
        "earliest_activity_time": "09:00:00",
    }


@pytest.mark.parametrize("end_date", ["2026-08-10", "2026-08-11", "2026-08-13"])
def test_successful_api_itineraries_pass_the_complete_validator(
    client: TestClient, end_date: str
) -> None:
    response = client.post(
        "/api/v1/itineraries/plan", json=request_body(end_date=end_date)
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["validation_report"] == {"is_valid": True, "violations": []}
    assert payload["proposed_itinerary"]["scheduled_items"]
    assert (
        payload["cost_breakdown"]["total_estimated_cost"]["amount_minor"]
        <= (payload["request"]["budget"]["amount_minor"])
    )
    assert payload["fixture_snapshot_version"] == "2026-08-01.v1"
    assert payload["planner_id"]
    assert payload["planning_rationale"]


def test_success_uses_canonical_provider_location_labels(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/itineraries/plan", json=request_body(end_date="2026-08-11")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    provider = get_provider()
    located_items = (
        *payload["proposed_itinerary"]["scheduled_items"],
        *payload["proposed_itinerary"]["accommodation_stays"],
    )
    assert located_items
    for item in located_items:
        location = provider.get_record(item["location_id"])
        assert isinstance(location, LocationRecord)
        assert item["location_label"] == location.name

    assert {
        item["location_label"]
        for item in payload["proposed_itinerary"]["scheduled_items"]
    } >= {"Toronto Central Transit Hall"}
    assert payload["proposed_itinerary"]["accommodation_stays"][0][
        "location_label"
    ] in {"Campus Corner Lodge", "Harbour Study Hostel"}


def test_exact_budget_remains_a_valid_success(client: TestClient) -> None:
    first = client.post("/api/v1/itineraries/plan", json=request_body()).json()
    exact_budget = first["cost_breakdown"]["total_estimated_cost"]["amount_minor"]

    response = client.post(
        "/api/v1/itineraries/plan", json=request_body(budget=exact_budget)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert (
        response.json()["cost_breakdown"]["total_estimated_cost"]["amount_minor"]
        == exact_budget
    )


def test_impossible_budget_is_a_structured_200_failure(client: TestClient) -> None:
    response = client.post("/api/v1/itineraries/plan", json=request_body(budget=1))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planning_failure"
    assert payload["failure_code"] == "INSUFFICIENT_BUDGET"
    assert payload["validation_report"]["is_valid"] is False
    assert payload["fixture_snapshot_version"]


def test_unsupported_route_is_a_structured_200_failure(client: TestClient) -> None:
    response = client.post(
        "/api/v1/itineraries/plan",
        json=request_body(destination="Montreal, Quebec"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planning_failure"
    assert payload["failure_code"] == "UNSUPPORTED_ROUTE"


def test_success_and_failure_include_mock_no_booking_disclosures(
    client: TestClient,
) -> None:
    responses = (
        client.post("/api/v1/itineraries/plan", json=request_body()),
        client.post("/api/v1/itineraries/plan", json=request_body(budget=1)),
    )

    for response in responses:
        disclosure = " ".join(response.json()["disclosures"]).casefold()
        assert "mock" in disclosure
        assert "nothing has been booked" in disclosure
        assert "verify" in disclosure


def test_identical_requests_have_stable_response_structure(client: TestClient) -> None:
    first = client.post("/api/v1/itineraries/plan", json=request_body())
    second = client.post("/api/v1/itineraries/plan", json=request_body())

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_coordinator_endpoint_returns_explicit_validated_fallback(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/itineraries/coordinate",
        json={
            **request_body(end_date="2026-08-11"),
            "preference_notes": "Prefer varied daytime activities",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["validation_report"] == {"is_valid": True, "violations": []}
    assert payload["planner_id"] == "trippilot-fixed-ranker-v1"
    assert payload["experiment"]["contract_version"] == "coordinator-experiment-v1"
    assert payload["experiment"]["approach"] == "deterministic_fallback"
    assert payload["experiment"]["fallback_code"] == "MODEL_NOT_CONFIGURED"
    assert payload["experiment"]["interpreted_preference_tags"] == []
    assert set(payload["experiment"]["selection_facts"]) <= {
        "lowest_estimated_cost",
        "largest_budget_buffer",
        "fewest_activities",
        "most_activities",
        "greatest_activity_variety",
        "shortest_transfer_time",
        "greatest_interest_coverage",
        "most_daytime_activities",
        "most_evening_activities",
    }
    assert "Prefer varied" not in response.text
    assert "candidate_" not in response.text
    assert any(
        "extra preferences" in warning.casefold() for warning in payload["warnings"]
    )


def test_coordinator_planning_failure_has_no_model_fallback_claim(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/itineraries/coordinate",
        json={**request_body(budget=1), "preference_notes": None},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planning_failure"
    assert payload["experiment"] == {
        "contract_version": "coordinator-experiment-v1",
        "approach": "deterministic_fallback",
        "interpreted_preference_tags": [],
        "selection_facts": [],
        "fallback_code": None,
    }


def test_provider_failure_is_sanitized_without_exception_details(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_provider] = lambda: BrokenActivityProvider(
        get_provider()
    )
    response = client.post(
        "/api/v1/itineraries/plan",
        json=request_body(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["failure_code"] == "PROVIDER_DATA_INCOMPLETE"
    assert "RuntimeError" not in response.text
    assert "/private" not in response.text


def test_unexpected_internal_failure_returns_generic_500(client: TestClient) -> None:
    def broken_planner(request: object, provider: object) -> object:
        raise RuntimeError("secret detail at /private/fixture.json")

    app.dependency_overrides[get_planner] = lambda: broken_planner
    response = client.post("/api/v1/itineraries/plan", json=request_body())

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "error_code": "INTERNAL_ERROR",
        "explanation": "The request could not be completed due to an internal error.",
    }
    assert "RuntimeError" not in response.text
    assert "/private" not in response.text


def test_request_timeout_returns_generic_500() -> None:
    limited_app = create_app(request_timeout_seconds=0.01)

    def slow_planner(request: object, provider: object) -> object:
        time.sleep(0.05)
        return plan_trip(request, provider)  # type: ignore[arg-type]

    limited_app.dependency_overrides[get_planner] = lambda: slow_planner
    with TestClient(limited_app, raise_server_exceptions=False) as limited_client:
        response = limited_client.post("/api/v1/itineraries/plan", json=request_body())

    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"


def test_invalid_success_result_fails_closed(client: TestClient) -> None:
    def invalid_success(request: object, provider: object) -> PlanningSuccess:
        result = plan_trip(request, provider)  # type: ignore[arg-type]
        assert isinstance(result, PlanningSuccess)
        return replace(
            result,
            validation_report=ValidationReport(
                (
                    Violation(
                        code=ViolationCode.BUDGET_EXCEEDED,
                        message="private invalid candidate detail",
                        severity=Severity.ERROR,
                    ),
                )
            ),
        )

    app.dependency_overrides[get_planner] = lambda: invalid_success
    response = client.post("/api/v1/itineraries/plan", json=request_body())

    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"
    assert "private invalid candidate detail" not in response.text


def test_missing_required_disclosures_fails_closed(client: TestClient) -> None:
    def undisclosed_success(request: object, provider: object) -> PlanningSuccess:
        result = plan_trip(request, provider)  # type: ignore[arg-type]
        assert isinstance(result, PlanningSuccess)
        return replace(result, disclosures=())

    app.dependency_overrides[get_planner] = lambda: undisclosed_success
    response = client.post("/api/v1/itineraries/plan", json=request_body())

    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"
    assert "disclosure" not in response.text.casefold()


def test_api_requires_no_network_or_secrets(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in tuple(os.environ):
        if any(token in name for token in ("API_KEY", "TOKEN", "SECRET")):
            monkeypatch.delenv(name, raising=False)

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    get_provider.cache_clear()

    response = client.post("/api/v1/itineraries/plan", json=request_body())

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_development_cors_allows_only_an_explicit_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIPPILOT_CORS_ORIGINS", "http://localhost:3000")
    cors_app = create_app()
    with TestClient(cors_app) as cors_client:
        allowed = cors_client.options(
            "/api/v1/itineraries/plan",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        blocked = cors_client.options(
            "/api/v1/itineraries/plan",
            headers={
                "Origin": "http://example.test",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked.headers


@pytest.mark.parametrize("origin", ["*", "https://example.test"])
def test_cors_rejects_non_local_configuration(origin: str) -> None:
    with pytest.raises(ValueError, match="local"):
        create_app(cors_origins=(origin,))
