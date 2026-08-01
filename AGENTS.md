# AGENTS.md

These instructions apply to the entire repository.

## Product boundaries

TripPilot's first MVP plans a one-to-four-day trip to exactly one destination
city for university students. Preserve the scope in `docs/PRD.md`. Do not add
bookings, payments, authentication, multi-city travel, live travel APIs, visa
advice, RAG, MCP, multiple runtime agents, background workers, or production
deployment unless the product scope is explicitly revised.

Never state or imply that a reservation, purchase, or booking has been made.
Use language such as “proposed,” “estimated,” and “verify before purchase.”

## Engineering rules

- Put domain rules in pure, deterministic Python under
  `backend/src/trippilot/domain/`.
- Use LLMs only for interpretation, planning, research, and explanation. Never
  delegate arithmetic, budget enforcement, time-overlap checks, trip-length
  validation, or other hard constraints to an LLM.
- Define strict Pydantic schemas at API, provider, fixture, and future LLM
  boundaries and reject unexpected fields. Use frozen domain dataclasses where
  framework independence is useful.
- Use a `pyproject.toml`-based Python package, pytest, and versioned JSON mock
  fixtures validated through strict fixture schemas.
- Access mock and future external data through interfaces under `providers/`;
  domain code must not depend on a vendor SDK or HTTP client.
- Keep orchestration in `services/` and HTTP concerns in `api/`.
- Store all timestamps with explicit timezone information. Store money as an
  integer number of minor units plus an ISO 4217 currency code; do not use
  binary floating point for monetary calculations.
- Treat trip dates as inclusive destination-local calendar days. Arrival and
  departure transport define the usable activity window on partial days.
- Model time-blocking scheduled items separately from accommodation stays.
  Overlap validation applies only to scheduled items. Activities, meals, and
  transport require strictly positive durations; only explicitly modelled
  non-blocking markers may have zero duration.
- Treat the budget as the all-in estimated total for all travellers, including
  transport to/from the destination, accommodation, activities, mock meals, and
  explicit fees or taxes. Preserve visible category totals.
- Keep generated itinerary claims traceable to provider records or marked as
  estimates.
- Add a focused pytest for every domain rule and every bug fix.
- Prefer the Python standard library and existing dependencies. Explain any new
  dependency in the pull request or change summary.

## Change workflow

1. Read the relevant documents in `docs/` before changing behavior.
2. Update the PRD and architecture when a change alters scope or boundaries.
3. Implement the smallest coherent change.
4. Run formatting, static checks, and the relevant tests once tooling exists.
5. Report what changed, what was verified, and any remaining risk.

Do not commit secrets, personal data, API keys, generated environments, or local
databases. Use `.env.example` for documented variable names and safe placeholders.
