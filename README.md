# TripPilot

TripPilot is a portfolio project for a constraint-aware AI travel-planning
assistant. Its initial audience is university students arranging affordable
short trips around Canada and nearby US destinations.

This repository contains the product and engineering foundation for the first
MVP, the Milestone 1 deterministic domain core, the Milestone 2 validated mock
travel-data provider, and the Milestone 3 deterministic itinerary planner. It
intentionally contains no HTTP API, live provider, or frontend implementation.

## First MVP

The MVP accepts one origin, one destination city, inclusive destination-local
travel dates for a one-to-four-day trip, one or more travellers, an all-in trip
budget and currency, interests, travel pace, and an earliest acceptable activity
time. It generates a proposed itinerary using mock travel data and checks it
with deterministic validation code. Transport arrival and departure define the
usable activity window on partial days.

The all-in budget covers all travellers and includes transport to and from the
destination, accommodation, activities, mock meal estimates, and explicit fees
or taxes. Category totals remain visible. Scheduled activities, meals, and
transport block calendar time; accommodation stays are represented separately
and do not participate in overlap validation.

The MVP does not provide bookings, payments, authentication, multi-city travel,
live flight or hotel data, visa advice, RAG, MCP, multiple runtime agents,
background workers, or production deployment.

## Engineering principles

- Enforce money, time, duration, and other hard constraints with deterministic
  code.
- Reserve LLM use for interpretation, planning, research, and explanation.
- Treat every itinerary as a proposal and never imply that a booking occurred.
- Keep travel-data and future LLM providers behind interfaces.
- Validate strict schemas at every system boundary.
- Add tests for every domain rule and avoid unnecessary dependencies.

## Technical foundation

- MVP backend: a `pyproject.toml`-based Python 3.14 package using FastAPI, strict
  Pydantic boundary schemas, frozen domain dataclasses where framework
  independence is useful, JSON mock fixtures, and pytest
- Later: PostgreSQL, Next.js, Docker, and a hosted LLM API

## Repository layout

```text
.
├── AGENTS.md
├── README.md
├── backend/
│   ├── src/trippilot/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── providers/
│   │   └── services/
│   └── tests/
│       ├── contract/
│       ├── integration/
│       └── unit/
├── data/mock/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DESIGN_SYSTEM.md
│   ├── EVALUATION_PLAN.md
│   ├── PRD.md
│   └── SECURITY.md
└── frontend/                 # Reserved for the later Next.js client
```

Empty directories are retained with `.gitkeep` files. The proposed implementation
sequence begins with the domain schemas and deterministic validator described in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Documentation

- [Product requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Evaluation plan](docs/EVALUATION_PLAN.md)
- [Security](docs/SECURITY.md)
- [Design system](docs/DESIGN_SYSTEM.md)
- [Contributor and agent guidance](AGENTS.md)

## Status

Milestones 1 through 3 provide the Python package, strict domain and provider
boundary schemas, deterministic itinerary validator, a versioned synthetic JSON
snapshot, an offline mock provider adapter, and a bounded deterministic planning
service with structured success and failure results. No database, external
provider, HTTP API, LLM, frontend, or deployment configuration has been added.
