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

### Coordinator evaluation

The completed coordinator V1 is preserved at
`data/evaluation/coordinator-eval-v1.json`; the registered, not-yet-executed V2
is at `data/evaluation/coordinator-eval-v2.json`. V2 preserves all cases and
candidate digests while versioning the prompt, reasoning setting, and
observability fields. Freeze an immutable model snapshot where available and
always record the returned model for each metadata-bearing attempt,
prompt/contract version, fixture snapshot, candidate set, and generation
parameters. Hosted generations are assessed across repeated runs rather than
claimed to be bitwise deterministic. Validate every selected canonical candidate
deterministically, compare it with the baseline on the same cases, and record
invalid-output, repair, fallback, token, cost, and latency rates. Never use LLM
self-grading as the source of truth for hard constraints.

### Candidate-diversity prerequisite

The internal deterministic enumerator is gated by the eight frozen normalized
requests in `backend/tests/unit/test_candidate_generation.py`. Each request must
produce two to five pairwise materially different candidates under the exact
rule in `docs/CANDIDATE_DIVERSITY.md`. Candidate zero must equal the existing
standard planner selection. Every candidate is independently revalidated,
budget-clean, canonically referenced, arithmetically reconciled, and stable
across repeated runs. Fewer than two candidates for any frozen prerequisite case
blocks the later coordinator boundary; candidates are never duplicated to meet
the minimum.

The Milestone 10 boundary suite also verifies canonical-only summary derivation,
request-local opaque candidate IDs, strict selection-fact optima, normalized and
non-echoed preference notes, isolation from `/plan`, explicit no-model fallback,
frontend runtime guards, collapsed opt-in behavior, note preservation, and
responsive disclosure layout.

The Milestone 11 boundary suite additionally verifies the fixed OpenAI endpoint
and model allowlists, no-tools structured request, low reasoning and token caps,
deadline propagation, stable provider-failure mapping, refusal handling, a
single invalid-output repair, canonical selection lookup, full revalidation,
and public deterministic fallback. All automated tests use injected transports
or adapters and perform no hosted-model call. Live repeated-run evaluation is
the next phase and remains a prerequisite to enabling the experiment by default.

The key-free Milestone 12 preparation freezes all 26 protocol cases and 13
normalized request profiles. `python -m trippilot.evaluation` validates the
fixture version, normalization outcomes, expected deterministic failures,
candidate counts and metric digests, and standard-planner/candidate-zero parity
without network access. The 20 hosted cohorts specify five repetitions each,
giving 100 future live runs. Run artifacts contain only stable IDs, revision and
contract identifiers, outcome/fallback codes, hard-validation status, returned
model per metadata-bearing attempt, aggregate token counts, latency, and
estimated cost; they omit notes, prompts,
provider/model payloads, and itinerary bodies.

The live runner requires an explicit paid-API acknowledgement and code revision,
validates the frozen manifest before model egress, and writes an atomic sanitized
checkpoint after each run. A resumed run rejects unknown, duplicate, mismatched,
or cross-revision records before making another model call. The checkpoint is
stored under the ignored local `tmp/` tree rather than committed.

The completed V1 result and no-go decision are recorded in
`docs/COORDINATOR_EVALUATION_RESULT_V1.md`. V1 also demonstrated that summing
provider metadata cannot represent end-to-end latency or complete estimated cost
when an attempt times out without returning usage. A future version must measure
elapsed time independently and expose cost completeness before operational gates
can be evaluated.

V2 records `coordinator_elapsed_ms` from before deterministic case binding until
the final selection or fallback, regardless of provider metadata availability.
`cost_complete` is true only when every attempted model call returned safe usage
metadata. Provider-derived token and cost totals remain estimates and are never
treated as complete when that flag is false.

The completed V2 result is recorded in
`docs/COORDINATOR_EVALUATION_RESULT_V2.md`. V2 passed every operational gate but
is a quality no-go: 20 of 40 preference selections were identical to the fixed-
ranker control, so it cannot reach the frozen threshold of 24 reviewer wins.
Blinded scoring is deferred for V2. A future version must retain the frozen gate
and demonstrate a selection mix capable of passing before reviewer scoring.

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
- for coordinator runs, model/configuration identifiers plus safe token, latency,
  and estimated-cost metadata for each available attempt.

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
- Preference-note control and bidirectional characters, normalization-boundary
  lengths, duplicate JSON keys, non-finite numbers, trailing JSON values,
  oversized raw decisions, missing explicit nulls, and context-invalid IDs or
  prioritized interests.

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
