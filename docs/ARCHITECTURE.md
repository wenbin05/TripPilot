# Architecture

## 1. Architectural stance

The MVP is a modular monolith with a deterministic domain core and a thin
Next.js client. FastAPI and Pydantic form the authoritative delivery and schema
boundary; pure Python performs all hard constraint checks. Mock provider
adapters supply every travel record. No external network access, database,
container, or LLM is required for the local MVP.

## 2. Logical flow

```text
Browser -> Next.js single-page client
  -> FastAPI route
  -> strict request schema
  -> planning service
       -> TravelDataProvider interface -> mock fixtures
       -> future Planner interface      -> deterministic baseline, then one agent
  -> deterministic itinerary validator
  -> strict response schema
  -> Client
```

The planning service may retry or repair a proposal synchronously later. A plan
is returned as valid only after deterministic validation succeeds.

## 3. Repository boundaries

```text
backend/src/trippilot/
├── api/          HTTP routes, dependency wiring, request/response translation
├── domain/       entities, value objects, rules, validator, domain errors
├── providers/    provider protocols and mock adapters
└── services/     use-case orchestration and planning workflow

backend/tests/
├── unit/         pure domain and service rule tests
├── contract/     schemas, fixture validity, and provider conformance
└── integration/  API-to-mock-provider flows

data/mock/        versioned, human-reviewable travel fixtures
frontend/         Next.js App Router UI, explicit API types, display-only grouping
```

Dependency direction is `api -> services -> domain`; providers implement
protocols owned at an inward-facing boundary. The domain must not import
FastAPI, provider SDKs, persistence libraries, or LLM libraries.

## 4. Core model

Core modelling decisions:

- `TripRequest`: normalized user constraints.
- `Money`: non-negative integer `amount_minor` and ISO currency.
- `TimeWindow`: timezone-aware start (inclusive) and end (exclusive).
- `ProviderRecord`: versioned mock source record with stable ID.
- `ScheduledItem`: a time-blocking activity, meal, or transport segment with a
  strictly positive duration, source reference, location, pricing basis, and
  estimated cost.
- `AccommodationStay`: a separately modelled stay with check-in/check-out facts,
  number of nights, pricing basis, and estimated cost. It does not block the
  itinerary calendar and is excluded from overlap validation.
- `NonBlockingMarker`: an explicitly non-blocking event such as an informational
  checkpoint. It may have zero duration and is excluded from overlap validation.
- `Itinerary`: ordered scheduled items, accommodation stays, optional markers,
  category cost breakdown, all-in total, assumptions, and disclosures.
- `Violation`: stable code, message, severity, and affected field/item IDs.
- `ValidationReport`: `is_valid` plus an ordered collection of violations.
- `CanonicalCandidate`: one validator-clean itinerary plus the exact provider
  snapshot required for independent revalidation.
- `CandidateSet`: one to five ordered canonical candidates bound to one fixture
  snapshot and deterministic generator version.

Use strict Pydantic models that reject unknown fields at API, provider, fixture,
and future LLM boundaries. Use frozen domain dataclasses where framework
independence is useful.

## 5. Deterministic validator

The validator is a pure function of normalized request, itinerary, and provider
snapshot. It performs no I/O and returns all detected violations in stable
order. Proposed validation phases:

1. Structural integrity and referential checks.
2. Inclusive destination-local date, timezone, strictly positive scheduled
   duration, arrival, and departure checks.
3. Ordering and overlap checks for time-blocking scheduled items only, followed
   by earliest-start, opening-hours, and transfer-time checks.
4. Traveller/pricing-basis and currency checks.
5. Exact subtotal, fee, total, and budget checks.
6. Required disclosure and provenance checks at the response boundary.

Use stable machine-readable codes such as `TRIP_LENGTH_OUT_OF_RANGE`,
`ITEM_OVERLAP`, `ACTIVITY_TOO_EARLY`, `INSUFFICIENT_TRANSFER_TIME`,
`CURRENCY_MISMATCH`, and `BUDGET_EXCEEDED`.

## 6. Money, dates, and timezones

- Represent money in integer minor units. Currency conversion is outside MVP.
- Define start and end dates as inclusive destination-local calendar days.
- Represent the corresponding trip-date envelope as the half-open interval
  `[start_date 00:00, end_date + 1 day 00:00)` in the destination timezone.
- Use arrival transport completion as the beginning of the usable activity
  window on the first partial day and departure transport start as its end on
  the last partial day.
- Validate inbound and outbound transport against the inclusive trip-date
  envelope, not against the usable activity window that those segments define.
  Validate activities, meals, and local transfers against both the date envelope
  and the usable activity window.
- Require IANA timezone names on mock cities and timezone-aware itinerary
  timestamps.
- Require strictly positive durations for scheduled activities, meals, and
  transport. Permit zero duration only for explicit `NonBlockingMarker` values.
- Treat scheduled-item intervals as half-open `[start, end)` so adjacent items do
  not overlap. Accommodation stays and non-blocking markers are excluded from
  overlap validation.
- Make transfer time an explicit scheduled item or validate the gap between
  consecutive located items against mock transfer data.

## 7. Budget model

The request budget is one all-in estimated total for all travellers in a single
currency. The authoritative deterministic calculation includes transport to
and from the destination, accommodation, activities, mock meal estimates, and
explicit fees or taxes. Per-person and per-group provider prices are normalized
against traveller count before aggregation. Visible category totals must sum
exactly to the all-in total, which must not exceed the request budget.

## 8. Provider interfaces

Define narrow protocols according to domain needs, not vendor responses. An
initial `TravelDataProvider` should expose destination metadata, transport,
accommodation, activities, operating windows, prices, and transfer estimates from a
versioned snapshot. The mock adapter reads versioned JSON fixtures and validates
them through strict Pydantic fixture schemas at load time.

Future live adapters translate external responses into the same internal
records. Provider-specific identifiers and raw payloads remain outside the
domain model except for traceable source metadata.

## 9. Planning and future agent boundary

The Milestone 3 baseline planner is deterministic and bounded. It:

1. filters transport, accommodation, activity, and meal records by route,
   destination, trip date, currency, and stay length;
2. considers at most 32 transport/accommodation combinations ordered by fixed
   all-traveller cost, boundary travel duration, and stable record IDs;
3. enumerates at most 5,000 activity-and-meal agenda variants per day, trying
   the pace target before smaller activity counts;
4. ranks feasible daily agendas by activity count, requested-interest matches,
   normalized cost, shortest-path transfer minutes, and stable record IDs, then
   retries the same bounded agenda space cost-first when the preferred agenda is
   over budget;
5. schedules records at the earliest legal instant within destination-local
   operating windows and reserves gaps for the shortest directed path through
   supplied transfer estimates;
6. includes one mock meal estimate per usable destination day, normalizes
   provider prices and attached fees using integer minor units, and preserves
   category totals; and
7. returns success only after the complete deterministic validator reports no
   violations.

The planner may reuse an activity record on different trip days when the small
fixture cannot otherwise approach the requested pace. It never repeats the same
activity within one day. Pace and interest coverage remain soft preferences;
missing transfer paths, operating-window conflicts, request boundaries, and the
all-in budget are never relaxed.

Expected inability to plan is represented by frozen structured results rather
than exceptions. Stable failure codes distinguish invalid requests, unsupported
routes, missing transport or accommodation, infeasible activity sets,
insufficient budget, validator rejection, and incomplete provider data. Results
include the validation report, relevant constraints, fixture snapshot version,
planner identifier, assumptions, and no-booking disclosures. Provider-boundary
exceptions are converted to a generic incomplete-data failure without exposing
the provider exception message.

Milestone 7 approves the design contract for one optional coordinator
experiment. Deterministic code generates two to five validator-clean canonical
candidates. The coordinator may interpret bounded soft-preference notes, select
one candidate ID or abstain, and return controlled preference-interpretation
tags. Factual selection summaries are derived by deterministic code. The model
does not assemble an itinerary or emit authoritative prose, timestamps, money,
provider facts, or disclosures.

The service binds candidate IDs to the normalized request and fixture snapshot,
strictly parses the decision, resolves the canonical candidate, and runs the
complete validator again. The coordinator cannot waive constraints, calculate
totals, access providers or unrestricted tools, spawn runtime agents, or claim
booking success. The service owns a single allowlisted retry and deterministic
fallback. `docs/COORDINATOR_EXPERIMENT.md` is the detailed experiment contract.

Milestone 8 adds an internal service-only candidate enumerator. It walks the
same stable, bounded transport/accommodation, pace-profile, and agenda-ranking
order as the standard planner; candidate zero therefore remains the existing
`/plan` selection. Alternatives are admitted only when the primary-activity
sequence differs and a deterministic cost, local-transfer, activity-count, or
interest-count trade-off crosses the frozen materiality rule. Every retained
candidate is budget-checked and revalidated against its own canonical provider
snapshot. The generator returns one candidate when only one qualifies and never
pads the set. No public API or frontend contract changes in this milestone.

## 10. API delivery layer

Milestone 4 exposes `GET /health` and `POST /api/v1/itineraries/plan` from the
application entry point `trippilot.api.app:app`. The planning request is a strict
flat JSON object using integer `total_budget_minor` plus `currency`; destination
timezone is resolved from the provider snapshot rather than accepted as an
untrusted user input.

The planning endpoint has a stable discriminated envelope. A success uses
`status: "success"` and includes the normalized request, proposed itinerary,
cost breakdown, validation report, matched interests, planning rationale,
assumptions, warnings, fixture snapshot version, planner identifier, and
mock-data/no-booking disclosures. An expected inability to plan uses
`status: "planning_failure"`
with a stable failure code, generic explanation, relevant constraints,
validation report, identifiers, assumptions, warnings, and the same disclosures.

Both validator-clean success and expected planning failure return `200`. A body
that fails the public schema returns a sanitized `422`; only an unexpected
application-boundary failure returns a generic `500`. This resolves the earlier
open question about `200` versus a conflict-style status for planning failures.
Public errors never include raw exceptions, prompts, provider payloads, stack
traces, fixture contents, or filesystem paths.

The local HTTP boundary caps request bodies at 32 KiB and total request handling
at 10 seconds. These are local safety limits rather than production readiness
claims; production rate limits and operational controls remain future work.

### API contract ownership

The backend Pydantic models and generated OpenAPI document are authoritative for
the public HTTP contract. The frontend currently maintains handwritten
TypeScript types and runtime guards. Until a generated runtime-validation
approach is approved, every public API change must update the backend schema and
contract tests, the corresponding TypeScript types and runtime guards, and
positive and negative frontend guard tests in the same pull request.

Unknown response fields remain a known difference: backend response schemas
forbid them, while the current frontend guards accept them. Generated
compile-time types alone are insufficient because untrusted HTTP responses still
require runtime checks.

For the first coordinator experiment, handwritten frontend runtime guards are
retained. Deterministic planning behavior and its endpoint path remain
unchanged; a future coordinator implementation uses a separate experimental
endpoint. Its implementation must update backend schemas and contract tests,
frontend types and runtime guards,
and positive and negative guard tests atomically. Contract generation remains a
later decision rather than a dependency of the experiment.

The separately approved benchmark-driven UI refinement requires a shared,
additive, server-authored human-readable
location label alongside the canonical `location_id` for scheduled items and
accommodation. This is an additive public-contract change and must follow the
same atomic backend schema/OpenAPI/frontend guard/test workflow. Labels come
from canonical provider records, never model output. The UI keeps the label in
the primary scan path and moves raw IDs into expandable provenance details with
an explicit item-to-source mapping.

## 11. Persistence and deployment

There is no persistence in the first MVP. Requests, proposals, and validation
reports live only in browser state and for the duration of an API request.
PostgreSQL may later persist normalized plans and provider snapshots behind
repository interfaces. Docker, hosted LLMs, and production deployment are later
architecture decisions and should not shape the domain API beyond clean
boundaries.

## 12. Test strategy

- Table-driven unit tests for every domain rule and boundary condition.
- Contract tests for Pydantic schemas, mock fixture validation, and provider
  protocol behavior.
- Integration tests from API request through mock provider to validated response.
- Golden scenarios for representative trips; assert semantics and invariants,
  not fragile prose.
- Property-based testing may be considered later, but is not an initial
  dependency requirement.

## 13. Initial technical decisions

- Package the backend as a `pyproject.toml`-based Python project.
- Use strict Pydantic schemas at all system boundaries.
- Use frozen domain dataclasses where framework independence is useful.
- Store mock provider data as JSON and validate it through strict fixture
  schemas before domain use.
- Use pytest for unit, contract, and integration tests.

## 14. Proposed implementation sequence

1. Establish the `pyproject.toml`-based Python package and pytest configuration.
2. Implement `Money`, date/time primitives, strict request/response schemas, and
   their tests.
3. Implement validator rules one at a time with failing-then-passing unit tests.
4. Define the provider protocol and a small strict-schema-validated JSON fixture
   set.
5. Add a deterministic planning service and integration scenarios.
6. Add the FastAPI route and error mapping. (Milestone 4 complete.)
7. Add the thin Next.js planning and results interface. (Milestone 5 complete.)
8. Evaluate the deterministic MVP before considering the coordinator agent.

## 15. Architecture decisions that can wait

- Exact supported Python version and build backend within `pyproject.toml`.
