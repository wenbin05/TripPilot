import asyncio
import sys
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from mcp import Client, StdioServerParameters

from trippilot.api.app import create_app
from trippilot.research_mcp import create_research_server
from trippilot.services.research import ResearchService
from trippilot.services.research_schemas import Guide


class Source:
    async def fetch(self, destination):
        return Guide(
            title=destination,
            revision=7,
            retrieved_at=datetime.now(UTC),
            text="Museums and parks in the city.",
        )


def test_api_uses_mcp_and_preserves_citations(monkeypatch):
    monkeypatch.setattr(
        "trippilot.api.research.create_research_server",
        lambda: create_research_server(ResearchService(Source())),
    )
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/research",
            json={
                "destination": "Montreal",
                "question": "museums",
                "synthesize": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["passages"][0]["revision"] == 7
        assert response.json()["status"] == "evidence"
        assert (
            client.post(
                "/api/v1/research",
                json={
                    "destination": "http://localhost",
                    "question": "museums",
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/research",
                json={
                    "destination": "Toronto",
                    "question": "museums",
                    "command": "ls",
                },
            ).status_code
            == 422
        )


def test_real_stdio_mcp_handshake_without_network():
    async def run():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "trippilot.research_mcp"]
        )
        async with Client(parameters) as client:
            inventory = await client.list_tools()
            assert [tool.name for tool in inventory.tools] == ["research_destination"]
            result = await client.call_tool(
                "research_destination",
                {
                    "request": {
                        "destination": "http://localhost",
                        "question": "museums",
                    },
                },
            )
            assert result.is_error

    asyncio.run(run())
