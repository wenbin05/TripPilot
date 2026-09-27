"""Bounded, fixed-origin external guide reader. No arbitrary URL fetches."""

from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field

from trippilot.services.research_schemas import Guide, ResearchRequest

API_URL = "https://en.wikivoyage.org/w/api.php"
MAX_BYTES = 1_000_000


class GuideProvider(Protocol):
    async def fetch(self, destination: str) -> Guide: ...


class WikiRedirect(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    from_title: str = Field(alias="from", max_length=200)
    to: str = Field(max_length=200)
    tofragment: str | None = Field(default=None, max_length=200)


class ParsedGuide(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=200)
    pageid: int
    revid: int = Field(gt=0)
    text: str = Field(max_length=MAX_BYTES)
    redirects: list[WikiRedirect] = Field(
        default_factory=list[WikiRedirect], max_length=10
    )


class ParseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    parse: ParsedGuide


class GuideText(HTMLParser):
    """Keep text, discard active markup; HTML is never sent to the browser."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "li", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


class WikivoyageProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def fetch(self, destination: str) -> Guide:
        # Validate again for callers outside the HTTP API.
        title = ResearchRequest(destination=destination, question="guide").destination
        async with (
            httpx.AsyncClient(
                timeout=3,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
                headers={
                    "User-Agent": "TripPilot/0.2 (https://github.com/wenbin05/TripPilot)"
                },
            ) as client,
            client.stream(
                "GET",
                API_URL,
                params={
                    "action": "parse",
                    "page": title,
                    "prop": "text|revid",
                    "format": "json",
                    "formatversion": "2",
                    "redirects": "1",
                },
            ) as response,
        ):
            response.raise_for_status()
            body = bytearray()
            async for block in response.aiter_bytes():
                body.extend(block)
                if len(body) > MAX_BYTES:
                    raise ValueError("Guide exceeds source limit")
        payload = ParseEnvelope.model_validate_json(bytes(body))
        parser = GuideText()
        parser.feed(payload.parse.text)
        text = "\n".join(
            " ".join(line.split())
            for line in "".join(parser.parts).splitlines()
            if line.strip()
        )
        return Guide(
            title=payload.parse.title,
            revision=payload.parse.revid,
            retrieved_at=datetime.now(UTC),
            text=text,
        )
