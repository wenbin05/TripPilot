"""Request-local lexical RAG: retrieve evidence, optionally synthesize, cite."""

import asyncio
import math
import re
from collections import Counter
from typing import Protocol

from trippilot.providers.wikivoyage import GuideProvider, WikivoyageProvider
from trippilot.services.research_schemas import (
    NOTICE,
    GeneratedAnswer,
    Guide,
    Passage,
    ResearchRequest,
    ResearchResponse,
)

STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "in",
        "on",
        "at",
        "to",
        "of",
        "for",
        "and",
        "or",
        "is",
        "are",
        "what",
        "where",
        "can",
        "i",
        "with",
    ]
)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+", text.casefold()) if t not in STOP]


def retrieve(guide: Guide, question: str) -> tuple[Passage, ...]:
    """BM25 over bounded overlapping chunks; stable ordering and no zero-score hits."""
    words = guide.text.split()
    chunks = [" ".join(words[i : i + 120])[:2500] for i in range(0, len(words), 100)]
    counts = [Counter(tokens(c)) for c in chunks]
    query = set(tokens(question))
    average = sum(sum(c.values()) for c in counts) / max(1, len(counts))
    scored: list[tuple[float, int]] = []
    for index, count in enumerate(counts):
        score = 0.0
        for term in query:
            frequency = count[term]
            if not frequency:
                continue
            documents = sum(term in c for c in counts)
            inverse = math.log(1 + (len(counts) - documents + 0.5) / (documents + 0.5))
            normalizer = 1.2 * (0.25 + 0.75 * sum(count.values()) / max(1, average))
            score += inverse * frequency * 2.2 / (frequency + normalizer)
        if score > 0:
            scored.append((score, index))
    selected = sorted(scored, key=lambda pair: (-pair[0], pair[1]))[:4]
    return tuple(
        Passage(
            id=f"p{index}",
            text=chunks[index],
            source_title=guide.title,
            source_url=f"https://en.wikivoyage.org/w/index.php?oldid={guide.revision}",
            revision=guide.revision,
            retrieved_at=guide.retrieved_at,
        )
        for _, index in selected
    )


class AnswerGenerator(Protocol):
    async def generate(
        self, request: ResearchRequest, passages: tuple[Passage, ...]
    ) -> GeneratedAnswer: ...


class ResearchService:
    def __init__(
        self,
        provider: GuideProvider | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.provider = provider or WikivoyageProvider()
        self.generator = generator

    async def research(self, request: ResearchRequest) -> ResearchResponse:
        try:
            async with asyncio.timeout(4):
                guide = await self.provider.fetch(request.destination)
            passages = retrieve(guide, request.question)
        except Exception:
            return ResearchResponse(
                status="unavailable",
                passages=(),
                claims=(),
                notice=NOTICE,
                generation_note="no_evidence",
            )
        if not passages:
            return ResearchResponse(
                status="no_evidence",
                passages=(),
                claims=(),
                notice=NOTICE,
                generation_note="no_evidence",
            )
        note = "not_requested" if not request.synthesize else "not_configured"
        if request.synthesize and self.generator is not None:
            try:
                async with asyncio.timeout(4):
                    generated = await self.generator.generate(request, passages)
                generated.check_citations(passages)
                if not generated.claims:
                    raise ValueError("Abstained")
                return ResearchResponse(
                    status="generated",
                    passages=passages,
                    claims=tuple(generated.claims),
                    notice=NOTICE,
                    generation_note="completed",
                )
            except Exception:
                note = "failed"
        return ResearchResponse(
            status="evidence",
            passages=passages,
            claims=(),
            notice=NOTICE,
            generation_note=note,
        )
