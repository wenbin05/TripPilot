# TripPilot

TripPilot is a portfolio project for a constraint-aware AI travel-planning
assistant. Its initial audience is university students arranging affordable
short trips around Canada and nearby US destinations.

This repository contains the product and engineering foundation for the first
MVP through Milestone 10: the deterministic domain core, validated mock
travel-data provider, bounded deterministic planner, local FastAPI delivery
layer, responsive Next.js planning interface, and a recorded passing
deterministic acceptance baseline, plus internal validator-clean candidate
enumeration, strict internal coordinator contracts, and an isolated coordinator
opt-in path that currently returns an explicit deterministic fallback. It
intentionally contains no live provider, hosted-model runtime, persistence, or
booking functionality.

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
- MVP frontend: Next.js 16, React 19, strict TypeScript, CSS, Vitest, and Testing
  Library
- Later: PostgreSQL, Docker, and a hosted LLM API

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
│   ├── CANDIDATE_DIVERSITY.md
│   ├── COORDINATOR_EXPERIMENT.md
│   ├── DESIGN_SYSTEM.md
│   ├── EVALUATION_PLAN.md
│   ├── PRD.md
│   ├── PRODUCT_UX_BENCHMARK.md
│   └── SECURITY.md
└── frontend/                 # Next.js App Router MVP client
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
pyright --pythonpath ../.venv/bin/python
uvicorn trippilot.api.app:app --reload
```

The API is then available at `http://127.0.0.1:8000`. Open
`http://127.0.0.1:8000/docs` for generated interactive documentation. The local
service uses only the versioned JSON mock snapshot and requires no secrets or
network access while running.

## Local frontend development

Node.js 20.19 or newer and npm are required. Install dependencies and configure
the public backend URL:

```bash
cd frontend
npm install
cp ../.env.example .env.local
npm run dev
```

The frontend is then available at `http://localhost:3000`. The committed safe
default is `NEXT_PUBLIC_TRIPPILOT_API_BASE_URL=http://127.0.0.1:8000`.

Run the frontend checks from `frontend/`:

```bash
npm run test:run
npm run lint
npm run typecheck
npm run format:check
npm run build
```

Frontend tests use mocked API responses and need no running backend, network
access, secrets, or user data.

## Full local MVP

In one terminal, start FastAPI from the repository root with explicit local
browser origins:

```bash
source .venv/bin/activate
export TRIPPILOT_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
uvicorn trippilot.api.app:app --reload
```

In another terminal:

```bash
cd frontend
cp ../.env.example .env.local  # first run only
npm install                    # first run only
npm run dev
```

Open `http://localhost:3000`, enter a supported mock trip such as Kingston,
Ontario to Toronto, Ontario on fixture dates beginning 2026-08-10, and create a
proposed itinerary. CORS is disabled when `TRIPPILOT_CORS_ORIGINS` is unset and
rejects wildcard configuration.

## Documentation

- [Product requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Candidate diversity evidence](docs/CANDIDATE_DIVERSITY.md)
- [Single coordinator experiment contract](docs/COORDINATOR_EXPERIMENT.md)
- [Coordinator V3 diagnostic result](docs/COORDINATOR_EVALUATION_DIAGNOSTIC_V3.md)
- [Evaluation plan](docs/EVALUATION_PLAN.md)
- [Product and UX benchmark](docs/PRODUCT_UX_BENCHMARK.md)
- [Security](docs/SECURITY.md)
- [Design system](docs/DESIGN_SYSTEM.md)
- [Deterministic MVP acceptance report](docs/DETERMINISTIC_MVP_ACCEPTANCE.md)
- [Contributor and agent guidance](AGENTS.md)

## Status

Milestones 1 through 6 provide the Python package, strict boundary schemas,
deterministic itinerary validator and planner, versioned synthetic JSON snapshot,
offline mock provider, local FastAPI endpoints, a responsive one-page Next.js
client, and the passing deterministic acceptance baseline documented in
`docs/DETERMINISTIC_MVP_ACCEPTANCE.md`. No database, external provider, LLM,
authentication, booking, or deployment configuration has been added.

Milestone 7 defines the bounded product, UX, architecture, security, and
evaluation contract for a future optional single-coordinator experiment.
Milestone 8 implements only its deterministic candidate-enumeration prerequisite
and proves eight frozen requests have pairwise material alternatives. Milestone
9 adds strict internal context, summary, decision, retry, parsing, and adapter
contracts without implementing an adapter. Milestone 10 adds canonical summary
construction, request-scoped candidate IDs, the isolated `/coordinate` contract,
and a collapsed-by-default frontend opt-in. Milestone 11 adds one direct,
tool-free GPT-5.6 Terra Responses adapter behind explicit local server
configuration. Without it, the endpoint reports `MODEL_NOT_CONFIGURED` and
returns the validated deterministic fallback. API keys remain server-side and
are never committed.

The current frozen coordinator V3 diagnostic manifest can be validated without an API key
or network egress from `backend/`:

```bash
python -m trippilot.evaluation
```

This checks all 26 synthetic cases and the complete 100-run schedule; it does
not contact a hosted model. V3 preserves the V2 prompt, cases, candidate digests,
elapsed-time measurement, and cost-completeness contract while restoring Terra
reasoning effort to `low` for a narrow ranking-quality diagnostic.

The approved paid V3 diagnostic is limited to two named scenarios and ten total
runs. It requires the server-side key in the process environment, a clean Git
revision, a local checkpoint path, and the billing acknowledgement flag:

```bash
cd backend
set -a
source .env
set +a
python -m trippilot.evaluation \
  --live-output ../tmp/evaluation/coordinator-v3-diagnostic.json \
  --code-revision <clean-git-revision> \
  --acknowledge-paid-api \
  --scenario preference-conflicting \
  --scenario preference-shorter-transfers
```

The ignored checkpoint is atomically replaced after every completed run and can
be resumed with the same command. It contains only strict sanitized run records.
A full 100-run V3 evaluation requires separate approval.

The ten-run V3 diagnostic is now complete. It passed all operational measures
and selected the strict minimum-transfer candidate in five of five runs, but the
conflicting-preference case selected the deterministic control in five of five
runs. The result does not justify a full paid V3 batch; see
`docs/COORDINATOR_EVALUATION_DIAGNOSTIC_V3.md`.
