# TripPilot

TripPilot is a portfolio project for a constraint-aware AI travel-planning
assistant. Its initial audience is university students arranging affordable
short trips around Canada and nearby US destinations.

This repository contains the product and engineering foundation for the first
MVP through Milestone 4: the deterministic domain core, validated mock
travel-data provider, bounded deterministic planner, and a local FastAPI
delivery layer. It intentionally contains no live provider or frontend.

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

## Local backend development

Python 3.14 is required. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cd backend
pytest
ruff format --check src tests
ruff check src tests
uvicorn trippilot.api.app:app --reload
```

The API is then available at `http://127.0.0.1:8000`. Open
`http://127.0.0.1:8000/docs` for generated interactive documentation. The local
service uses only the versioned JSON mock snapshot and requires no secrets or
network access while running.

## Documentation

- [Product requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Evaluation plan](docs/EVALUATION_PLAN.md)
- [Security](docs/SECURITY.md)
- [Design system](docs/DESIGN_SYSTEM.md)
- [Contributor and agent guidance](AGENTS.md)

## Status

Milestones 1 through 4 provide the Python package, strict boundary schemas,
deterministic itinerary validator and planner, versioned synthetic JSON snapshot,
offline mock provider, and local FastAPI endpoints. No database, external
provider, LLM, frontend, or deployment configuration has been added.
