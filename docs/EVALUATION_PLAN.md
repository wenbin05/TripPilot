# Evaluation Plan

## 1. Purpose

Evaluation must show that TripPilot produces useful proposals without violating
hard constraints or misleading users. Deterministic correctness is the release
gate; preference quality is measured separately.

## 2. Evaluation layers

### Schema and domain tests

Use pytest table-driven tests for valid, invalid, and boundary values. Every
hard rule in the PRD receives at least one passing and one failing case. Important
boundaries include one versus four days, adjacent non-overlapping items, exactly
equal all-in budget, earliest-time equality, per-person pricing, inclusive
destination-local dates, partial arrival/departure days, and timezone changes.
Test that scheduled activities, meals, and transport require positive durations;
only explicit non-blocking markers may have zero duration. Test overlap only
among time-blocking scheduled items and confirm that accommodation stays do not
create false overlaps.

### Provider contract tests

Validate every JSON fixture through strict Pydantic fixture schemas before use.
Test stable IDs, valid IANA timezones, non-negative prices, strictly positive
scheduled durations, ordered operating windows, supported currencies, and
references between cities, venues, accommodation, transport, and transfer data.
Run the same behavioral contract against any future provider adapter.

### End-to-end scenarios

Exercise the entire local request-to-response flow using frozen mock snapshots.
The initial suite should include:

| Scenario | Expected focus |
| --- | --- |
| One-day nearby trip | Boundary duration, no accommodation, tight timing |
| Two-day budget trip | Per-person costs, one accommodation night, interests |
| Four-day trip | Maximum duration, multiple days, cost accumulation |
| Exact-budget plan | Total equals budget and remains valid |
| Impossible budget | Clear structured failure; no fabricated valid plan |
| All-in multi-traveller budget | Transport, accommodation, activities, meals, fees/taxes, and traveller pricing reconcile by category |
| Late earliest start | No early activities; pace may be relaxed |
| Partial first/last day | Boundary transport fits the date envelope while activities, meals, and local transfers fit the arrival-to-departure usable window |
| Opening-hours conflict | Validator catches unavailable activity |
| Transfer conflict | Validator catches insufficient travel gap |
| Overlapping scheduled items | Validator returns `ITEM_OVERLAP` |
| Accommodation spans activities | No false overlap because the stay is non-blocking |
| Zero-duration scheduled item | Rejected; explicit non-blocking marker remains valid |
| Currency mismatch | Validator rejects mixed-currency total |

### Future coordinator evaluation

The approved coordinator design is evaluated through the versioned
`coordinator-eval-v1-draft` protocol in `docs/COORDINATOR_EXPERIMENT.md`; freeze
the executable `coordinator-eval-v1` manifest only after deterministic candidate
generation exists. Freeze an immutable model snapshot where available and
always record the returned model,
prompt/contract version, fixture snapshot, candidate set, and generation
parameters. Hosted generations are assessed across repeated runs rather than
claimed to be bitwise deterministic. Validate every selected canonical candidate
deterministically, compare it with the baseline on the same cases, and record
invalid-output, repair, fallback, token, cost, and latency rates. Never use LLM
self-grading as the source of truth for hard constraints.

## 3. Metrics and gates

### Required release gates

- Hard-constraint pass rate for responses marked valid: 100%.
- All-in and category cost arithmetic accuracy: 100%.
- Mock-record reference integrity: 100%.
- Mock-data and no-booking disclosure presence: 100%.
- Offline automated test pass rate: 100%.
- Determinism: repeated validation of identical normalized inputs yields an
  identical ordered report in 100% of runs.

### Quality indicators

- Interest coverage: percentage of requested interests represented.
- Pace fit: percentage meeting the PRD's activity-density target.
- Budget utilization: all-in estimated cost for all travellers divided by
  budget, reported with category totals and remaining buffer.
- Schedule efficiency: transfer time versus activity time.
- Explanation completeness: assumptions, trade-offs, and warnings present.
- Planning success rate and failure reason distribution.

Quality indicators inform iteration and do not permit hard-rule failures.

## 4. Test data

Fixtures must be synthetic or explicitly licensed, small enough for human
review, and versioned. Include normal records and deliberately invalid fixtures
kept only in test directories. Test cases must not contain real user personal
data or secrets.

Each evaluation run records:

- code revision;
- fixture snapshot version;
- scenario ID and normalized request;
- produced itinerary or structured failure;
- validation report; and
- for future agent runs, model/configuration identifiers and token/latency data.

## 5. Adversarial and safety cases

- Prompt-like text embedded in user fields or provider descriptions.
- Attempts to request bookings, payment, visa guarantees, unsafe activities, or
  unsupported destinations.
- Extremely long strings, unexpected fields, malformed dates/times, zero or
  negative money, excessive traveller counts, and zero-duration scheduled items
  disguised as markers.
- Mock records containing instruction-like content or unsupported currencies.
- Proposals that omit disclosures or present estimates as confirmed prices.
- Unknown, stale, homoglyph, or cross-request coordinator candidate IDs.
- Strict-output coercion, extra fields, oversized arrays/prose, refusals,
  truncation, timeouts, provider errors, and missing model configuration.
- Canary preference data appearing in logs, traces, errors, or metadata.

## 6. Manual review rubric

For a small fixed sample, reviewers score from 1–5:

- usefulness for a student traveller;
- clarity and scannability;
- relevance to interests;
- realism of pacing;
- transparency of estimates and assumptions; and
- absence of booking or availability claims.

Record reviewer notes separately from deterministic results. A target of at
least 4.0 average in each category is aspirational for the first agent-enabled
iteration, not a gate for the deterministic core.

## 7. Regression policy

Every discovered domain defect becomes a minimal regression test. Golden outputs
may change only with an explained product or fixture change. A change that lowers
a required gate blocks release until corrected or the PRD is deliberately
revised.
