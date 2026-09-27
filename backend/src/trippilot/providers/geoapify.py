"""Read-only, bounded Geoapify MCP adapter. Credentials never enter URLs."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated, Literal, Protocol
from zoneinfo import ZoneInfo

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

ENDPOINT = "https://api.geoapify.com/v1/mcp"
KEY_NAME = "TRIPPILOT_GEOAPIFY_API_KEY"
MAX_BYTES = 500_000


def load_geoapify_key(env_file: Path | None = None) -> str | None:
    """Read only this credential; never source/execute a dotenv file."""
    value = os.environ.get(KEY_NAME)
    if value is None:
        path = env_file or Path(__file__).resolve().parents[3] / ".env"
        try:
            for line in path.read_text().splitlines():
                name, separator, candidate = line.partition("=")
                if separator and name.strip() == KEY_NAME:
                    value = candidate.strip().strip('"').strip("'")
        except OSError:
            return None
    if not value or not value.isascii() or not value.isalnum():
        return None
    return value


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


Label = Annotated[str, Field(min_length=1, max_length=400)]


class Point(StrictRecord):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)


class City(Point):
    place_id: Label
    name: Label
    timezone: str = Field(max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class Place(Point):
    place_id: Label
    name: Label
    address: str = Field(max_length=600)
    category: str = Field(max_length=64)


class MatrixCell(StrictRecord):
    distance: float = Field(ge=0, allow_inf_nan=False)
    time: float = Field(ge=0, allow_inf_nan=False)
    source_index: int = Field(ge=0, le=7)
    target_index: int = Field(ge=0, le=7)


class Matrix(StrictRecord):
    sources: tuple[Point, ...] = Field(min_length=1, max_length=8)
    targets: tuple[Point, ...] = Field(min_length=1, max_length=8)
    sources_to_targets: tuple[tuple[MatrixCell | None, ...], ...] = Field(
        min_length=1, max_length=8
    )
    units: Literal["metric"]
    distance_units: Literal["meters"]
    time_units: Literal["seconds"]


class ToolText(StrictRecord):
    type: Literal["text"]
    text: str = Field(max_length=MAX_BYTES)


class ToolResult(StrictRecord):
    content: tuple[ToolText, ...] = Field(max_length=2)
    structuredContent: dict[str, JsonValue]
    isError: bool = False


class Envelope(StrictRecord):
    jsonrpc: Literal["2.0"]
    id: Literal[1]
    result: ToolResult


class LivePlacesProvider(Protocol):
    async def cities(self, query: str) -> tuple[City, ...]: ...

    async def places(self, city: City, category: str) -> tuple[Place, ...]: ...

    async def matrix(self, places: tuple[Place, ...]) -> Matrix: ...


class GeoapifyProvider:
    def __init__(
        self, key: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._key = key
        self._transport = transport
        self._calls = 0

    async def _call(
        self, name: str, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if name not in {"geocode_address", "search_places", "calculate_route_matrix"}:
            raise ValueError("Tool not allowed")
        self._calls += 1
        if self._calls > 5:
            raise ValueError("Tool budget exhausted")
        # At most one request in flight; below the free-tier 5 requests/sec cap.
        await asyncio.sleep(0.21)
        async with (
            httpx.AsyncClient(
                timeout=3,
                trust_env=False,
                follow_redirects=False,
                transport=self._transport,
            ) as client,
            client.stream(
                "POST",
                ENDPOINT,
                headers={"x-api-key": self._key, "MCP-Protocol-Version": "2025-06-18"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            ) as response,
        ):
            if response.status_code != 200:
                raise ValueError("Location provider unavailable")
            body = bytearray()
            async for block in response.aiter_bytes():
                body.extend(block)
                if len(body) > MAX_BYTES:
                    raise ValueError("Location response too large")
        payload = Envelope.model_validate_json(bytes(body))
        if payload.result.isError:
            raise ValueError("Location tool failed")
        return payload.result.structuredContent

    async def cities(self, query: str) -> tuple[City, ...]:
        data = await self._call(
            "geocode_address",
            {
                "query": query,
                "limit": 5,
                "country_codes": ["ca", "us"],
            },
        )
        results = data.get("results")
        if not isinstance(results, list) or len(results) > 5:
            raise ValueError("Invalid geocoding response")
        cities: dict[str, City] = {}
        for row in results:
            if not isinstance(row, dict) or row.get("result_type") != "city":
                continue
            timezone = row.get("timezone")
            if not isinstance(timezone, dict):
                continue
            # Vendor metadata is extensible; only this strict projection enters
            # the app. No source URLs, instructions, or HTML are acted upon.
            city = City.model_validate(
                {
                    "place_id": row.get("place_id"),
                    "name": row.get("formatted"),
                    "timezone": timezone.get("name"),
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                }
            )
            cities[city.place_id] = city
        return tuple(cities.values())

    async def places(self, city: City, category: str) -> tuple[Place, ...]:
        if category not in CATEGORIES.values():
            raise ValueError("Category not allowed")
        data = await self._call(
            "search_places",
            {
                "category": category,
                "lat": city.lat,
                "lon": city.lon,
                "radius_meters": 5000,
                "limit": 20,
            },
        )
        results = data.get("results")
        if not isinstance(results, list) or len(results) > 20:
            raise ValueError("Invalid places response")
        return tuple(
            Place.model_validate(
                {
                    "place_id": row.get("place_id"),
                    "name": row.get("name"),
                    "address": row.get("formatted", ""),
                    "category": category,
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                }
            )
            for row in results
            if isinstance(row, dict) and row.get("name")
        )

    async def matrix(self, places: tuple[Place, ...]) -> Matrix:
        if not 1 <= len(places) <= 8:
            raise ValueError("Invalid matrix size")
        data = await self._call(
            "calculate_route_matrix",
            {
                "sources": [{"lat": p.lat, "lon": p.lon} for p in places],
                "mode": "walk",
                "units": "metric",
            },
        )
        matrix = Matrix.model_validate_json(json.dumps(data))
        n = len(places)
        if len(matrix.sources) != n or len(matrix.targets) != n:
            raise ValueError("Invalid matrix dimensions")
        if len(matrix.sources_to_targets) != n:
            raise ValueError("Invalid matrix rows")
        for i, row in enumerate(matrix.sources_to_targets):
            if len(row) != n or any(
                cell is not None and (cell.source_index != i or cell.target_index != j)
                for j, cell in enumerate(row)
            ):
                raise ValueError("Invalid matrix indices")
        return matrix


CATEGORIES = {
    "arts_culture": "entertainment.museum",
    "nature": "leisure.park",
    "history": "heritage",
    "food": "catering.restaurant",
    "nightlife": "catering.bar",
    "shopping": "commercial.shopping_mall",
    "sports": "sport",
    "student_budget": "tourism",
}
