# Deterministic MVP Acceptance Report

## 1. Executive result

**PASS** as of 2026-08-02 (Asia/Kuala_Lumpur).

The complete deterministic TripPilot MVP meets the documented acceptance gates
after one blocking validator defect was found and fixed during this milestone.
The final baseline has 100% hard-constraint compliance for evaluated successful
plans, 100% integer-minor-unit arithmetic agreement, 100% fixture-reference
integrity, 100% required disclosure presence, deterministic repeated results,
and fully passing offline automated test suites.

TripPilot is ready to begin the separately scoped, single coordinator-agent
milestone provided that the deterministic validator remains authoritative and
every proposed agent output must pass it before delivery.

## 2. Revision and fixture

- Initial evaluation base revision: `2427f9abaad4751a40fccf7edd9d813801b139`
- Branch: `agent/milestone-1-domain-validator`
- Final deterministic code revision evaluated after the blocking fix:
  `e35513c34c352986a231aa8c6616eed1bf35ae40`
- Original acceptance-documentation commit:
  `1e87ba7c59179cb1c018c96e8cd7fe08885973dc` (documentation only; not a
  different application-code baseline)
- Fixture: `data/mock/kingston-toronto-v1.json`
- Snapshot version: `2026-08-01.v1`
- Planner: `deterministic-greedy-bounded-v1`

No push was performed during the evaluation itself. The blocking-fix and
original acceptance-documentation commits were subsequently pushed to
`origin/agent/milestone-1-domain-validator`.

## 3. Environment

- Apple arm64 macOS, Darwin 25.5.0
- Python 3.14.2
- pytest 9.1.1
- Ruff 0.16.1
- Node.js 24.13.0
- npm 11.6.2
- FastAPI exercised in-process with `TestClient` and as a local Uvicorn service
- Next.js exercised with Vitest/jsdom, a production build, and the local
  development server in the Codex in-app Chromium browser
- Browser responsive viewport: 390 by 844 CSS pixels
- No API key, token, secret, database, external provider, or network travel API
  was configured or required

## 4. Acceptance-criteria traceability

| # | Acceptance criterion | Relevant implementation | Automated test or manual scenario | Result | Evidence / command | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Strict request validation | `api/schemas.py`, `domain/schemas.py`, FastAPI 422 handler | Missing, malformed, out-of-range, and unknown-field contract cases | PASS | `pytest`; expected-failure scenarios 11–14 and 24 | Frontend response guards are handwritten TypeScript guards, not generated from OpenAPI. |
| 2 | One destination only | Scalar `destination`, origin/destination comparison, trip-length model validator | Same-origin API case and five-day API case | PASS | `test_invalid_request_contract_returns_sanitized_422`; scenarios 11–12 | One fixture destination is intentionally supported. |
| 3 | One-to-four-day inclusive range | Request schemas, validator trip-day calculation, planner date envelope | One-, two-, four-, and five-day cases | PASS | `test_one_and_four_day_trip_boundaries_are_valid`; API scenarios 1–3 and 11 | None. |
| 4 | Offline one-, two-, and four-day plans | `services/planner.py`, JSON mock provider | Representative planner/API integrations | PASS | `test_representative_trip_lengths_are_complete_and_valid`; `test_successful_api_itineraries_pass_the_complete_validator` | Fixture dates are fixed to 2026-08-10 through 2026-08-13. |
| 5 | Deterministic validator behavior | Pure `validate_itinerary` with phase-defined sorting | Twenty repeated validator calls and stable-order unit case | PASS | Acceptance harness; `test_stable_violation_ordering`; `test_repeated_validation_is_identical` | None. |
| 6 | Exact integer-minor-unit arithmetic | `Money`, `_normalized_amount`, validator phase 5 | Seven successful plans plus pricing/arithmetic unit and integration tests | PASS | Acceptance harness; `test_cost_categories_reconcile_exactly`; `test_total_arithmetic_mismatch_is_invalid` | CAD is the only currency in the active fixture. |
| 7 | Budget enforcement | Planner bounded fallback and validator `BUDGET_EXCEEDED` | Exact-budget and impossible-budget cases | PASS | Scenarios 4 and 15; `test_exact_budget_equality_is_valid`; `test_impossible_budget_is_structured_failure` | None. |
| 8 | Earliest-start enforcement | Planner scheduling and validator `ACTIVITY_TOO_EARLY` | Equality at 10:23 and 08:59 failing boundary | PASS | Scenario 7; `test_activity_before_earliest_start_is_invalid` | Earliest time applies to activities, as documented, not meals or boundary transport. |
| 9 | Overlap prevention | Half-open scheduled-item chronology validation | Adjacent, overlap, and accommodation-spans-activity cases | PASS | `test_adjacent_half_open_intervals_do_not_overlap`; `test_genuinely_overlapping_items_are_reported`; scenario 6 | None. |
| 10 | Operating-window enforcement | Planner window scheduling; validator activity and meal checks | Activity conflict plus new meal conflict regression | PASS | `test_activity_outside_operating_hours_is_invalid`; `test_meal_outside_operating_hours_is_invalid` | Blocking defect fixed in this milestone; see section 14. |
| 11 | Transfer-time enforcement | Directed shortest-path planner graph and validator transfer gaps | Insufficient-gap unit case and complete-plan transfer audit | PASS | `test_insufficient_transfer_time_is_invalid`; `test_every_location_change_reserves_shortest_provider_transfer_gap` | The active fixture has a deliberately small directed graph. |
| 12 | Valid provider-record references | Strict fixture schema, provider lookup, validator `RECORD_NOT_FOUND` | 51 references across evaluated successes plus missing-reference unit case | PASS | Acceptance harness; `test_missing_provider_record_is_invalid` | Explicit fee objects are itemized but do not expose their provider fee record ID in the public response. |
| 13 | Accommodation non-time-blocking | Separate `AccommodationStay` model and UI section | Overlapping stay/activity remains validator-clean | PASS | Scenario 6; `test_accommodation_occupancy_can_overlap_scheduled_activity`; frontend test | None. |
| 14 | Mock-data and no-booking disclosures | Service disclosures, API fail-closed check, persistent `EstimateBanner` | Nine success/failure response checks and live browser check | PASS | Acceptance harness; `test_success_and_failure_include_mock_no_booking_disclosures`; browser audit | None. |
| 15 | Provider substitutability | `TravelDataProvider` protocol and dependency injection | Runtime protocol and provider-override tests | PASS | `test_provider_conforms_to_runtime_protocol`; planner/API override tests | Only the JSON adapter is implemented, which is sufficient to prove the boundary. |
| 16 | Complete automated suite offline without secrets | Local fixture, mocked frontend fetch, no credential configuration | Network-rejection tests plus complete suites | PASS | `test_fixture_and_provider_execute_fully_offline`; `test_api_requires_no_network_or_secrets`; `test_planning_uses_no_network_or_secrets`; `npm run test:run` | `npm audit` may contact the npm registry; it is a supply-chain check, not part of the offline application test suite. |

## 5. Automated checks

Final results after the blocking fix:

| Area | Command | Result |
| --- | --- | --- |
| Backend tests | `cd backend && ../.venv/bin/pytest -q` | PASS — 172 passed in 0.68 s |
| Backend lint | `cd backend && ../.venv/bin/ruff check src tests` | PASS |
| Backend formatting | `cd backend && ../.venv/bin/ruff format --check src tests` | PASS — 25 files already formatted |
| Backend type checking | Configuration inspection | Not configured; no type-check command existed in `pyproject.toml` during the original acceptance run |
| Frontend tests | `cd frontend && npm run test:run` | PASS — 30 passed in 4.76 s |
| Frontend lint | `cd frontend && npm run lint` | PASS |
| Strict TypeScript | `cd frontend && npm run typecheck` | PASS |
| Frontend formatting | `cd frontend && npm run format:check` | PASS |
| Production build | `cd frontend && npm run build` | PASS — static `/` and `/_not-found` generated |
| Production dependency audit | `cd frontend && npm audit --omit=dev` | PASS — 0 vulnerabilities |

The backend and frontend test implementations use local fixtures, in-process
HTTP, and mocked frontend fetch calls. No test requires an external travel
service or a secret. Git inspection found no tracked `.env` file other than
`.env.example`, no tracked database, no tracked dependency/build directory, and
no unexpected generated file.

### Post-acceptance quality-gate addendum

On 2026-08-03, the baseline-quality-gates workstream added strict Pyright
checking. The command
`cd backend && ../.venv/bin/pyright --pythonpath ../.venv/bin/python` passed with
0 errors, 0 warnings, and 0 informational diagnostics. This is post-acceptance
evidence and does not alter the original 2026-08-02 results above.

## 6. End-to-end acceptance scenarios

### Valid scenarios

| # | Scenario | Layer and observed result | Result |
| --- | --- | --- | --- |
| 1 | One-day Kingston-to-Toronto | API/planner success; CAD 93.00; validator-clean | PASS |
| 2 | Two-day budget trip with accommodation | API/planner success; one-night stay; CAD 193.00 | PASS |
| 3 | Four-day maximum trip | API/planner success; three-night stay; CAD 344.00 | PASS |
| 4 | Exact-budget itinerary | Budget and total both 9,300 minor CAD units | PASS |
| 5 | Multiple travellers with per-person pricing | Two-traveller two-day total CAD 386.00; selected per-person amounts multiplied by two | PASS |
| 6 | Accommodation overlaps evening activity | Actual activity/stay interval overlap present; no `ITEM_OVERLAP` | PASS |
| 7 | Earliest-start equality | Activity and earliest time both 10:23; no `ACTIVITY_TOO_EARLY` | PASS |
| 8 | Interest-matched itinerary | Nature-only relaxed request selected `activity-island-walk`; matched interest `nature` | PASS |
| 9 | Valid browser flow and mobile-width layout | Initial browser submission did not reach the planner because local CORS origins were omitted; after restarting FastAPI with explicit local origins, the browser flow completed successfully. The 390×844 responsive check had no horizontal overflow. | PASS after local configuration correction |
| 10 | Repeated identical request | 20/20 API responses semantically identical | PASS |

### Expected-failure scenarios

| # | Scenario | Expected and observed outcome | Result |
| --- | --- | --- | --- |
| 11 | Five-day request | Sanitized 422 `REQUEST_VALIDATION_ERROR` | PASS |
| 12 | Origin equals destination | Sanitized 422 `REQUEST_VALIDATION_ERROR` | PASS |
| 13 | Empty interests | Sanitized 422 `REQUEST_VALIDATION_ERROR` | PASS |
| 14 | Non-positive budget | Sanitized 422 `REQUEST_VALIDATION_ERROR` | PASS |
| 15 | Impossible budget | 200 structured `INSUFFICIENT_BUDGET`; no fabricated success | PASS |
| 16 | Unsupported destination or route | 200 structured `UNSUPPORTED_ROUTE` | PASS |
| 17 | Activity before earliest time | Validator `ACTIVITY_TOO_EARLY` | PASS |
| 18 | Operating-hours conflict | Validator `OUTSIDE_OPERATING_WINDOW` for activity and meal | PASS after fix |
| 19 | Insufficient transfer time | Validator `INSUFFICIENT_TRANSFER_TIME` | PASS |
| 20 | Currency mismatch | Validator `CURRENCY_MISMATCH`; unsupported fixture currency request fails safely | PASS |
| 21 | Missing provider reference | Validator `RECORD_NOT_FOUND` | PASS |
| 22 | Backend unavailable | Frontend converts unexpected transport failure to generic “Proposal unavailable”; inputs are not reset | PASS |
| 23 | Malformed API response | Runtime response guard rejects malformed 200/422 payloads and shows only generic unexpected error | PASS |
| 24 | Unknown request field | Sanitized 422 `REQUEST_VALIDATION_ERROR` | PASS |
| 25 | Prompt-like/malicious text | Treated as a bounded origin label; structured `NO_TRANSPORT_OPTION`; no execution or booking action | PASS |

The initial manual browser submission did not reach the planner: the local
FastAPI service had been started without configured frontend CORS origins, so
the preflight request returned `405`. After FastAPI was restarted with
`TRIPPILOT_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`, a valid
proposed-itinerary flow completed successfully. This was a local startup and
configuration issue, not a deterministic planner failure. Earlier in-app
automation difficulty with native date inputs did not reproduce as a product
defect.

## 7. Determinism results

For one fixed normalized request and fixture snapshot:

- Validator: 20/20 results identical, including ordered violations
- Planner: 20/20 frozen results identical
- API: 20/20 JSON responses identical
- Stable itinerary order: confirmed
- Stable provider-record selection: confirmed
- Stable failure codes: confirmed by repeated unit/API cases
- Stable arithmetic totals: confirmed
- Randomness: none found
- Clock dependence: none found in planning outputs; only test/latency measurement
  clocks are operational

Result: **100% determinism for the evaluation repetitions**.

## 8. Hard-constraint metrics

- Successful plans independently evaluated: 7
- Successful plans passing a fresh complete validator call: 7
- Compliance: **100%**
- Incorrectly marked successful: 0
- External validation repair or retry attempts: 0
- Blocking validator defects found: 1
- Blocking validator defects remaining: 0

The deterministic planner performs bounded candidate enumeration as designed;
that is selection, not post-validation repair. It returns success only when the
validator report is clean.

## 9. Cost-arithmetic metrics

- Successful plans audited: 7
- Exact item/category/total reconciliations: 7/7 (**100%**)
- Integer minor units throughout authoritative domain/provider/API models: PASS
- Per-person multiplication: PASS (one- and two-traveller comparisons)
- Per-group pricing: PASS
- Per-stay/night multiplication: PASS
- Explicit fees/taxes: PASS
- Category subtotals and all-in equality: PASS
- Exact-budget validity: PASS
- Over-budget rejection: PASS

No binary floating-point value participates in authoritative backend monetary
calculation. Frontend decimal text is converted to safe integer minor units at
the request boundary.

## 10. Provenance and disclosure metrics

- Snapshot: `2026-08-01.v1`
- Scheduled-item and accommodation references checked: 51
- Valid references: 51/51 (**100%**)
- Invalid references found: 0
- Success/planning-failure response disclosures checked: 9
- Required mock-data and nothing-booked disclosures: 9/9 (**100%**)
- Disclosure omission at the API delivery boundary fails closed: confirmed by
  integration test

The public API exposes location identifiers rather than human-readable location
names. This is understandable with surrounding titles and is retained as the
documented non-blocking limitation for this MVP.

## 11. Accessibility and responsive findings

PASS for the documented basic frontend checks:

- All required inputs and supported interest controls have accessible names.
- Native checkbox interest controls are keyboard togglable; the frontend test
  verifies Space toggling.
- Invalid submission moves focus to the error summary.
- Live browser focus outline: 3 px solid blue.
- Invalid fields use `aria-invalid` and `aria-describedby` references to both
  hints and field errors.
- Success, warning, loading, and error states include text and symbols; meaning
  is not color-only.
- The mock/no-booking notice is persistent and sticky.
- React form state is not reset for request validation, structured planning
  failure, malformed response, or backend-unavailable paths. A planning-failure
  retention test passes.
- Destination timezone is displayed and used for grouping/formatting.
- Accommodation is rendered outside the scheduled timeline with explicit
  non-time-blocking text.
- At 390×844, `scrollWidth` and `clientWidth` were both 390; no horizontal
  overflow was present.
- Unexpected failures display a safe generic message.
- No booking, reservation, purchase, or payment action exists.
- No affirmative confirmed, guaranteed, live-price, or “your booking” language
  was found.
- Browser console warnings/errors during the mobile check: 0.

## 12. Latency baseline

- Environment: same-process FastAPI `TestClient` on the arm64 macOS environment
  in section 3
- Requests: rotating one-, two-, and four-day representative API requests
- Warm-up: 3 unmeasured one-day requests
- Measured runs: 30
- Median: **7.214 ms**
- Minimum: **3.934 ms**
- Maximum: **14.006 ms**
- Frontend rendering included: no
- Network transport included: no; in-process ASGI delivery was measured

This is a local baseline, not a release gate. No latency optimization was made.

## 13. Failure classification

### Blocking

One confirmed defect: supplied operating windows were enforced for activities
but not meals. A meal scheduled 15:00–16:00 against a supplied 11:00–14:00
window produced no violation in three repeated checks.

### Important non-blocking

None found.

### Minor / known limitations

- Provider location IDs are displayed instead of human-readable names.
- The fixture intentionally supports only the synthetic Kingston/Toronto route,
  fixed dates, and CAD.
- Local browser integration requires explicit `TRIPPILOT_CORS_ORIGINS`. The
  initial acceptance attempt omitted this configuration and failed before the
  POST reached the planner; the flow passed after the documented startup
  correction.
- The latency baseline excludes browser rendering and real HTTP transport.
- Backend static type checking was not part of the original acceptance run. It
  is addressed by the post-acceptance baseline-quality-gates workstream.

## 14. Blocking defect fixed and regression coverage

The meal operating-window defect was fixed by:

1. applying `OUTSIDE_OPERATING_WINDOW` to both activity and meal scheduled
   items in `domain/validator.py`;
2. including both activity and meal windows in the provider snapshot assembled
   by `services/planner.py`; and
3. adding `test_meal_outside_operating_hours_is_invalid` to
   `tests/unit/test_validator.py`.

Targeted verification passed (the regression, provider-hours integration, and
one-/two-/four-day API validation cases), followed by the full backend and
frontend check matrix. No fixture was changed.

Files changed for the fix and report:

- `backend/src/trippilot/domain/validator.py`
- `backend/src/trippilot/services/planner.py`
- `backend/tests/unit/test_validator.py`
- `docs/DETERMINISTIC_MVP_ACCEPTANCE.md`

## 15. Recommendation

Proceed to planning the first single coordinator-agent milestone. Preserve these
conditions:

- the agent may propose but must not perform authoritative arithmetic or hard
  validation;
- every proposal must cross the existing strict schema and pass the complete
  deterministic validator before being marked successful;
- failure remains structured and disclosures remain mandatory;
- the agent has no booking/payment authority, direct tool access, runtime
  sub-agents, persistence, or live travel-provider access unless a later scoped
  revision explicitly changes those boundaries; and
- compare the future coordinator against this frozen deterministic baseline and
  record invalid-output and repair rates separately.
