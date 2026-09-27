import asyncio
import json
from datetime import UTC, datetime

import httpx2 as httpx
import pytest
from mcp import Client
from pydantic import ValidationError

from trippilot.providers.research_openai import OpenAIResearchGenerator
from trippilot.providers.wikivoyage import GuideText, WikivoyageProvider
from trippilot.research_mcp import create_research_server
from trippilot.services.research import ResearchService, retrieve
from trippilot.services.research_schemas import (
    Claim,
    GeneratedAnswer,
    Guide,
    ResearchRequest,
    ResearchResponse,
)

GUIDE = Guide(
    title="Test City",
    revision=42,
    retrieved_at=datetime.now(UTC),
    text="Museums and art galleries surround the park. Public transport uses buses.",
)
REQUEST = ResearchRequest(destination="Test City", question="museums art")


class Source:
    async def fetch(self, destination):
        return GUIDE


@pytest.mark.parametrize(
    "destination",
    ["http://localhost", "../etc/passwd", "x", " ", "City\nX", "Special:Search"],
)
def test_rejects_bad_destination(destination):
    with pytest.raises(ValidationError):
        ResearchRequest(destination=destination, question="museums")


def test_strict_request():
    with pytest.raises(ValidationError):
        ResearchRequest.model_validate(
            {"destination": "Toronto", "question": "parks", "url": "https://evil.test"}
        )
    with pytest.raises(ValidationError):
        ResearchRequest(destination="Toronto", question="   ")


def test_retrieval_cites_exact_revision_and_abstains():
    result = retrieve(GUIDE, "museums")
    assert result[0].source_url.endswith("oldid=42")
    assert result[0].retrieved_at.tzinfo is not None
    assert retrieve(GUIDE, "spaceships") == ()
    assert retrieve(GUIDE, "and the") == ()
    assert result == retrieve(GUIDE, "museums")


def test_chunk_limits_and_ranking():
    guide = GUIDE.model_copy(update={"text": "boring " * 300 + "museums art " * 500})
    result = retrieve(guide, "museums")
    assert len(result) == 4
    assert all(len(p.text.split()) <= 120 and len(p.text) <= 2500 for p in result)
    assert "museums" in result[0].text


def test_source_markup_is_not_executable():
    parser = GuideText()
    parser.feed("<p>Museum</p><script>steal()</script><style>bad</style><p>Park</p>")
    assert "steal" not in "".join(parser.parts)
    assert "bad" not in "".join(parser.parts)


def test_provider_fixed_origin_and_normalization():
    def handler(request):
        assert request.url.host == "en.wikivoyage.org"
        assert request.url.params["page"] == "Test City"
        return httpx.Response(
            200,
            json={
                "parse": {
                    "title": "Test City",
                    "pageid": 1,
                    "revid": 42,
                    "text": "<p>Museums and parks.</p>",
                }
            },
        )

    guide = asyncio.run(
        WikivoyageProvider(httpx.MockTransport(handler)).fetch("Test City")
    )
    assert guide.text == "Museums and parks."
    assert guide.revision == 42


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "http://127.0.0.1/secret"}),
        httpx.Response(429),
        httpx.Response(200, content=b"x" * 1_000_001),
        httpx.Response(200, json={"error": {"code": "missingtitle"}}),
        httpx.Response(
            200,
            json={
                "parse": {
                    "title": "Test",
                    "pageid": 1,
                    "revid": 2,
                    "text": "hi",
                    "unexpected": True,
                }
            },
        ),
    ],
)
def test_source_failures_do_not_invent_evidence(response):
    provider = WikivoyageProvider(httpx.MockTransport(lambda _: response))
    result = asyncio.run(ResearchService(provider).research(REQUEST))
    assert result.status == "unavailable"
    assert not result.passages and not result.claims


def test_evidence_without_model_and_missing_configuration():
    result = asyncio.run(ResearchService(Source()).research(REQUEST))
    assert result.status == "evidence" and result.generation_note == "not_requested"
    result = asyncio.run(
        ResearchService(Source()).research(
            REQUEST.model_copy(update={"synthesize": True})
        )
    )
    assert result.status == "evidence" and result.generation_note == "not_configured"


@pytest.mark.parametrize(
    "citation,expected", [("p0", "generated"), ("invented", "evidence")]
)
def test_synthesis_checks_citations(citation, expected):
    class Generator:
        async def generate(self, request, passages):
            return GeneratedAnswer(
                claims=[Claim(text="A museum is mentioned.", citations=[citation])]
            )

    service = ResearchService(Source(), Generator())
    result = asyncio.run(
        service.research(REQUEST.model_copy(update={"synthesize": True}))
    )
    assert result.status == expected


def test_no_evidence_skips_generation():
    class Generator:
        async def generate(self, *args):
            pytest.fail("Should not generate without evidence")

    result = asyncio.run(
        ResearchService(Source(), Generator()).research(
            REQUEST.model_copy(update={"question": "spaceships", "synthesize": True})
        )
    )
    assert result.status == "no_evidence"


def test_openai_payload_and_cited_generation():
    def handler(request):
        data = json.loads(request.content)
        assert data["store"] is False and data["max_output_tokens"] == 800
        assert data["text"]["format"]["strict"] is True
        assert "untrusted" in data["input"][0]["content"]
        assert "tools" not in data
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "claims": [
                                            {
                                                "text": "Museums appear in the guide.",
                                                "citations": ["p0"],
                                            }
                                        ]
                                    }
                                ),
                            }
                        ]
                    }
                ],
            },
        )

    generator = OpenAIResearchGenerator(
        "test-not-a-key", "test-model", httpx.MockTransport(handler)
    )
    result = asyncio.run(generator.generate(REQUEST, retrieve(GUIDE, "museums")))
    assert result.claims[0].citations == ["p0"]


def test_mcp_client_round_trip_and_tool_inventory():
    async def run():
        async with Client(create_research_server(ResearchService(Source()))) as client:
            inventory = await client.list_tools()
            assert [t.name for t in inventory.tools] == ["research_destination"]
            result = await client.call_tool(
                "research_destination", {"request": REQUEST.model_dump()}
            )
            parsed = ResearchResponse.model_validate_json(
                json.dumps(result.structured_content)
            )
            assert parsed.status == "evidence"
            assert parsed.passages[0].revision == 42

    asyncio.run(run())


@pytest.mark.parametrize(
    "body",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": [{"content": [{"type": "refusal"}]}]},
        {
            "status": "completed",
            "output": [{"content": [{"type": "output_text", "text": "not json"}]}],
        },
        {
            "status": "completed",
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"claims":[{"text":"x","citations":["fake"]}]}',
                        }
                    ]
                }
            ],
        },
    ],
)
def test_generation_failure_preserves_real_evidence(body):
    generator = OpenAIResearchGenerator(
        "test-not-a-key",
        "test-model",
        httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    result = asyncio.run(
        ResearchService(Source(), generator).research(
            REQUEST.model_copy(update={"synthesize": True})
        )
    )
    assert result.status == "evidence"
    assert result.generation_note == "failed"
    assert result.passages and not result.claims


def test_source_timeout_is_sanitized():
    class Slow:
        async def fetch(self, destination):
            raise TimeoutError("sensitive provider detail")

    result = asyncio.run(ResearchService(Slow()).research(REQUEST))
    assert result.status == "unavailable"
    assert "sensitive" not in result.model_dump_json()
