import asyncio
import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from trippilot.api import live
from trippilot.api.app import create_app
from trippilot.api.schemas import TripPlanRequest
from trippilot.providers.geoapify import City, GeoapifyProvider, load_geoapify_key
from trippilot.services.live_planner import LocalAllowance, build_live_draft

BODY = {
    "origin": "Kingston, Ontario",
    "destination": "Toronto, Ontario, Canada",
    "start_date": "2026-10-10",
    "end_date": "2026-10-11",
    "travellers": 1,
    "total_budget_minor": 50000,
    "currency": "CAD",
    "interests": ["nature"],
    "pace": "balanced",
    "earliest_activity_time": "09:00",
}
CITY = {
    "place_id": "city-1",
    "name": "Toronto, Ontario, Canada",
    "timezone": "America/Toronto",
    "lat": 43.65,
    "lon": -79.38,
}


def wire(data):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [], "structuredContent": data, "isError": False},
    }


def handler(request):
    assert str(request.url) == "https://api.geoapify.com/v1/mcp"
    assert request.headers["x-api-key"] == "fakekey"
    args = json.loads(request.content)["params"]
    if args["name"] == "geocode_address":
        assert args["arguments"]["country_codes"] == ["ca", "us"]
        data = {
            "results": [
                {
                    "place_id": "city-1",
                    "formatted": CITY["name"],
                    "timezone": {"name": "America/Toronto"},
                    "result_type": "city",
                    "lat": 43.65,
                    "lon": -79.38,
                }
            ]
        }
    elif args["name"] == "search_places":
        assert args["arguments"]["limit"] == 20
        data = {
            "results": [
                {
                    "place_id": f"place-{i}",
                    "name": f"Park {i}",
                    "formatted": "Toronto",
                    "lat": 43.65,
                    "lon": -79.38,
                }
                for i in range(8)
            ]
        }
    else:
        assert args["name"] == "calculate_route_matrix"
        assert args["arguments"]["mode"] == "walk"
        points = args["arguments"]["sources"]
        n = len(points)
        data = {
            "sources": points,
            "targets": points,
            "units": "metric",
            "distance_units": "meters",
            "time_units": "seconds",
            "sources_to_targets": [
                [
                    {"source_index": i, "target_index": j, "distance": 200, "time": 120}
                    for j in range(n)
                ]
                for i in range(n)
            ],
        }
    return httpx.Response(200, json=wire(data))


def test_real_protocol_adapter_and_draft_unknown_prices():
    provider = GeoapifyProvider("fakekey", httpx.MockTransport(handler))
    result = asyncio.run(
        build_live_draft(
            TripPlanRequest.model_validate(BODY).to_domain("UTC"), provider
        )
    )
    assert result.status == "draft"
    assert len(result.stops) == 6
    assert result.all_in_total_minor is None
    assert result.budget_status == "not_verified"
    assert all(
        s.price_minor is None and s.opening_hours_status == "unverified"
        for s in result.stops
    )


def test_multiple_city_matches_require_disambiguation():
    def ambiguous(request):
        data = handler(request).json()
        data["result"]["structuredContent"]["results"].append(
            {
                "place_id": "city-2",
                "formatted": "Toronto, Other Region",
                "timezone": {"name": "America/Toronto"},
                "result_type": "city",
                "lat": 44.0,
                "lon": -79.0,
            }
        )
        return httpx.Response(200, json=data)

    result = asyncio.run(
        build_live_draft(
            TripPlanRequest.model_validate(BODY).to_domain("UTC"),
            GeoapifyProvider("fakekey", httpx.MockTransport(ambiguous)),
        )
    )
    assert result.status == "ambiguous_destination"
    assert len(result.destination_choices) == 2
    assert not result.stops


@pytest.mark.parametrize("status", [301, 401, 429, 500])
def test_provider_errors_and_redirects_fail_closed(status):
    provider = GeoapifyProvider(
        "fakekey", httpx.MockTransport(lambda _: httpx.Response(status))
    )
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(provider.cities("Toronto"))


def test_source_size_and_strict_protocol():
    for response in (
        httpx.Response(200, content=b"x" * 500001),
        httpx.Response(200, json={**wire({"results": []}), "unexpected": True}),
    ):
        provider = GeoapifyProvider(
            "fakekey", httpx.MockTransport(lambda _, result=response: result)
        )
        with pytest.raises(ValueError):
            asyncio.run(provider.cities("Toronto"))


def test_only_allowlisted_categories_and_bounded_calls():
    provider = GeoapifyProvider("fakekey", httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="Category"):
        asyncio.run(provider.places(City.model_validate(CITY), "arbitrary"))

    async def run():
        for _ in range(5):
            await provider.cities("Toronto")
        with pytest.raises(ValueError, match="budget"):
            await provider.cities("Toronto")

    asyncio.run(run())


def test_key_loading_is_narrow_and_environment_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("TRIPPILOT_GEOAPIFY_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('OTHER_SECRET=not-used\nTRIPPILOT_GEOAPIFY_API_KEY="fakekey"\n')
    assert load_geoapify_key(env) == "fakekey"
    monkeypatch.setenv("TRIPPILOT_GEOAPIFY_API_KEY", "envkey")
    assert load_geoapify_key(env) == "envkey"
    monkeypatch.setenv("TRIPPILOT_GEOAPIFY_API_KEY", "$(do-not-execute)")
    assert load_geoapify_key(env) is None


def test_api_never_exposes_errors_or_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(live, "load_geoapify_key", lambda: "fakekey")
    monkeypatch.setattr(live, "allowance", LocalAllowance())

    async def broken(*args):
        raise RuntimeError("fakekey sensitive upstream content")

    monkeypatch.setattr(live, "build_live_draft", broken)
    response = TestClient(create_app()).post("/api/v1/itineraries/live-plan", json=BODY)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["stops"] == []
    assert "fakekey" not in response.text


def test_not_configured_and_daily_allowance(monkeypatch):
    monkeypatch.setattr(live, "load_geoapify_key", lambda: None)
    client = TestClient(create_app())
    assert (
        "not configured"
        in client.post("/api/v1/itineraries/live-plan", json=BODY).json()["notice"]
    )
    allowance = LocalAllowance()
    assert all(allowance.reserve() for _ in range(20))
    assert not allowance.reserve()
    monkeypatch.setattr(live, "load_geoapify_key", lambda: "fakekey")
    monkeypatch.setattr(live, "allowance", allowance)
    assert (
        "allowance"
        in client.post("/api/v1/itineraries/live-plan", json=BODY).json()["notice"]
    )


def test_request_rejects_extra_and_invalid_dates():
    client = TestClient(create_app())
    for body in ({**BODY, "api_key": "fakekey"}, {**BODY, "end_date": "2026-10-20"}):
        assert (
            client.post("/api/v1/itineraries/live-plan", json=body).status_code == 422
        )


@pytest.mark.parametrize("defect", ["index", "dimensions", "units", "negative"])
def test_invalid_route_matrix_is_rejected(defect):
    def malformed(request):
        response = handler(request)
        payload = response.json()
        data = payload["result"]["structuredContent"]
        if "sources_to_targets" in data:
            if defect == "index":
                data["sources_to_targets"][0][1]["target_index"] = 0
            elif defect == "dimensions":
                data["sources_to_targets"].pop()
            elif defect == "units":
                data["time_units"] = "minutes"
            else:
                data["sources_to_targets"][0][1]["time"] = -1
        return httpx.Response(200, json=payload)

    with pytest.raises(ValueError):
        asyncio.run(
            build_live_draft(
                TripPlanRequest.model_validate(BODY).to_domain("UTC"),
                GeoapifyProvider("fakekey", httpx.MockTransport(malformed)),
            )
        )
