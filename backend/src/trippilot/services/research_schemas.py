"""Strict public and provider-normalized research contracts."""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ResearchRequest(ResearchModel):
    destination: str = Field(min_length=2, max_length=100)
    question: str = Field(min_length=3, max_length=300)
    synthesize: bool = False

    @field_validator("destination")
    @classmethod
    def destination_label(cls, value: str) -> str:
        value = value.strip()
        if (
            len(value) < 2
            or not all(c.isalnum() or c in " -'(),./" for c in value)
            or ":" in value
            or ".." in value
            or value.startswith("/")
        ):
            raise ValueError("Use a guide title, not a URL or command")
        return value

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        if len(value.strip()) < 3 or any(ord(c) < 32 for c in value):
            raise ValueError("Use a plain-text research question")
        return value.strip()


class Guide(ResearchModel):
    title: str = Field(min_length=1, max_length=200)
    revision: int = Field(gt=0)
    retrieved_at: AwareDatetime
    text: str = Field(min_length=1, max_length=150_000)


class Passage(ResearchModel):
    id: str = Field(pattern=r"^p[0-9]+$")
    text: str = Field(min_length=1, max_length=2500)
    source_title: str = Field(min_length=1, max_length=200)
    source_url: str = Field(
        pattern=r"^https://en\.wikivoyage\.org/w/index\.php\?oldid=[0-9]+$"
    )
    retrieved_at: AwareDatetime
    revision: int = Field(gt=0)


class Claim(ResearchModel):
    text: str = Field(min_length=1, max_length=800)
    citations: list[str] = Field(min_length=1, max_length=4)


class GeneratedAnswer(ResearchModel):
    claims: list[Claim] = Field(max_length=4)

    def check_citations(self, passages: tuple[Passage, ...]) -> Self:
        valid = {p.id for p in passages}
        if any(not set(c.citations) <= valid for c in self.claims):
            raise ValueError("Unknown citation")
        return self


class ResearchResponse(ResearchModel):
    status: Literal["evidence", "generated", "no_evidence", "unavailable"]
    passages: tuple[Passage, ...] = Field(max_length=4)
    claims: tuple[Claim, ...] = Field(max_length=4)
    notice: str
    generation_note: Literal[
        "not_requested", "not_configured", "completed", "failed", "no_evidence"
    ]
    attribution: str = "Wikivoyage contributors · CC BY-SA 4.0"


NOTICE = (
    "External guide research, not a validated itinerary. Sources may be outdated "
    "or incorrect. Verify prices, hours and availability directly. Nothing is booked."
)
