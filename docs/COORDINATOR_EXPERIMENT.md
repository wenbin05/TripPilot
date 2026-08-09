# Single Coordinator Experiment Contract

## 1. Decision and hypothesis

Milestone 7 approves a design and evaluation contract for one optional,
coordinator-assisted planning experiment. It does not add an LLM dependency,
API key, hosted-model call, or runtime agent.

The experiment tests this hypothesis:

> For students whose priorities are not fully expressed by interest and pace
> controls, one coordinator can select a more preference-aligned option than a
> fixed deterministic ranker choosing from the same bounded, valid candidate
> set, without weakening correctness, safety, or transparency.

The coordinator ranks; it does not invent. Deterministic code remains
authoritative for candidate generation, dates, schedules, transfers, opening
hours, money, budget enforcement, provenance, validation, and disclosures.

## 2. Product scope

The experiment stays within the one-city, one-to-four-day mock-data MVP. It may:

- accept optional soft-preference notes;
- receive between two and five canonical, validator-clean candidates generated
  for the normalized request and frozen fixture snapshot;
- select one candidate or abstain through a strict structured response; and
- return bounded preference-interpretation tags while the server derives all
  candidate facts and trade-offs for presentation.

It may not create or edit itinerary items, calculate costs, change structured
request fields, relax a hard constraint, use live data, browse, access files,
book, pay, send messages, persist memory, or spawn another runtime agent.
Authentication, persistence, RAG, MCP, background work, specialist agents, live
providers, and production deployment remain out of scope.

When the current deterministic planner succeeds, its itinerary is included in
the candidate set. Its structured failure remains only a regression reference
when it does not succeed. Candidates are materially different only when their
primary activity set or ordering differs and there is at least one measurable cost,
transfer, pace, interest-coverage, or daypart-allocation trade-off; a daypart
difference alone never qualifies, and cosmetic differences do not qualify. The
experiment is meaningful only if at least eight frozen evaluation
requests produce two or more materially different, validator-clean candidates.
If the candidate generator cannot meet that prerequisite, implementation pauses
and candidate diversity is addressed deterministically first.

## 3. User-input contract

`preference_notes` is an optional string of at most 300 Unicode code points
after normalization. Normalize to NFC, replace CR, LF, and TAB with spaces,
then reject remaining U+0000–001F, U+007F–009F, unpaired surrogate code points
U+D800–DFFF, U+061C, U+200E–200F, U+202A–202E, and U+2066–2069 before collapsing
repeated allowed whitespace and trimming once at ingress. Whitespace-only
input is omitted; over-limit input is rejected rather than truncated. Frontend
validation and its counter use `Array.from(normalizedValue).length`; the backend
remains authoritative. Browser `maxlength` is only assistance because it counts
UTF-16 code units. Interests remain required.

Notes express soft ranking preferences only. Structured dates, destination,
travellers, budget, currency, interests, pace, and earliest activity time remain
authoritative. Notes cannot add a second city or turn booking, payment, visa,
safety, medical, dietary, mobility, accessibility, or current-availability
requests into supported requirements. A static scope warning is always visible
beside the field; no model or heuristic classifies the note. The coordinator
must not imply that unsupported content was satisfied.

Hosted-model processing must be an explicit local experiment opt-in. The UI
must state that notes may be processed by a hosted model, must discourage
personal or sensitive information, and must preserve the notes in browser form
state after all outcomes. Notes are not stored in local storage or on the server.

## 4. Bounded orchestration

The future implementation follows this synchronous flow:

1. Validate and normalize the public request.
2. Generate up to five candidates in deterministic code and validate each. If
   fewer than two remain, skip the model and return the fixed-ranker selection
   or the deterministic structured failure.
3. Bind opaque candidate IDs to the normalized request and fixture snapshot in
   service-owned request memory.
4. Send only the strict coordinator context and candidate summaries defined
   below to one hosted-model adapter.
5. Strictly parse a selection or abstention response.
6. Resolve the selected ID from the service-owned map and re-run the complete
   deterministic validator against the canonical candidate.
7. Return the canonical candidate, server-authored disclosures, and bounded
   presentation metadata. Never trust model-echoed itinerary facts.
8. On abstention or any model, schema, deadline, configuration, selection, or
   validation failure, return the fixed ranker's canonical selection. If the
   candidate generator produced no valid candidate, return the deterministic
   planner's structured result or failure.

The model has no tools and no direct network, provider, filesystem,
code-execution, booking, payment, or communication access. The server may make
requests only through one configured hosted-model adapter to its allowlisted
provider destination. All other experiment egress is prohibited. Application
code owns orchestration; there is no autonomous loop.

The service establishes one absolute deadline for the existing ten-second HTTP
limit and reserves the final two seconds for call cancellation, deterministic
fallback, revalidation, and serialization. No model attempt may begin or
continue into that reserve, and a retry never resets the deadline. At most two
model calls are allowed: the first attempt and one retry for an allowlisted
strict-parse error, schema error, or unknown candidate ID. A refusal immediately
falls back and its text is never echoed. Retry feedback contains stable codes
and IDs only and never raw exceptions, prompts, provider text, or weakened
constraints. Calls are neither parallel nor continued in the background.

Before implementation, the selected adapter must also define and test an input
context cap, an output-token cap, and a server-side spend cap. Stable experiment
fallback codes are `MODEL_NOT_CONFIGURED`, `MODEL_TIMEOUT`,
`MODEL_RATE_LIMITED`, `MODEL_PROVIDER_ERROR`, `MODEL_REFUSAL`,
`MODEL_OUTPUT_INVALID`, `MODEL_ABSTAINED`, `UNKNOWN_CANDIDATE`,
`CANDIDATE_REVALIDATION_FAILED`, and `DEADLINE_RESERVE_REACHED`. Public messages
remain generic.

## 5. Strict model boundary

The model receives one closed request context. Hard constraints are omitted
because every candidate is already valid:

```text
CoordinatorContext
  contract_version: literal "coordinator-context-v1"
  interests: 1..8 unique Interest enum values
  pace: relaxed | balanced | packed
  preference_notes: normalized string of 0..300 Unicode code points | null
  candidates: 2..5 unique CandidateSummary values
```

Preference notes are delimited as untrusted data by the adapter. The context
contains no arbitrary request or provider prose.

Each model-facing candidate uses this closed, size-bounded summary; no raw
provider title, description, source label, or arbitrary prose is included:

```text
CandidateSummary
  contract_version: literal "candidate-summary-v1"
  candidate_id: ASCII string matching [A-Za-z0-9_-]{1,64}
  total_estimated_cost_minor: integer 0..9223372036854775807
  remaining_budget_minor: integer 0..9223372036854775807
  primary_activity_count: integer 0..16
  distinct_primary_activity_count: integer 0..16
  total_transfer_minutes: integer 0..5760
  activity_interest_counts: exact map of the eight Interest enums to 0..16
  requested_interest_coverage_count: integer 0..8
  daypart_activity_counts: exact map morning/afternoon/evening to 0..16
  accommodation_style_tags: 0..2 values from quiet, social
  transport_mode_tags: 1..2 values from coach, train
```

All values are derived from canonical records by deterministic code. Candidate
IDs are opaque, request-scoped, and rejected before lookup if they contain
Unicode, homoglyphs, or fail the pattern. Dayparts use destination-local activity
start times: morning `[00:00, 12:00)`, afternoon `[12:00, 18:00)`, and evening
`[18:00, 24:00)`. `distinct_primary_activity_count` counts unique canonical
activity source IDs, so a repeated visit counts once; user-facing copy calls
this "most distinct activities." `requested_interest_coverage_count` counts
unique structured requested interests whose exact activity count is greater
than zero; unrequested interests do not count. Daypart counts sum to
`primary_activity_count`, and the distinct count cannot exceed it.

The future model boundary uses a strict schema equivalent to:

```text
CoordinatorDecision
  contract_version: literal "coordinator-decision-v1"
  status: "selection" | "abstention"
  selected_candidate_id: ASCII [A-Za-z0-9_-]{1,64} | null
  interpreted_preference_tags: 0..5 values from:
    lower_cost, larger_budget_buffer, fewer_activities, more_activities,
    shorter_transfers, activity_variety, daytime_focus, evening_focus
  prioritized_interests: 0..3 values from the request's Interest enums
  abstention_reason: null | no_preference_signal |
    conflicting_preferences | insufficient_candidate_difference
```

Selection requires a known candidate ID and `abstention_reason: null`.
Abstention requires `selected_candidate_id: null` and a non-null reason. An
abstention uses the fixed-ranker selection, reports
`approach: deterministic_fallback` with `MODEL_ABSTAINED`, and is never counted
as coordinator-assisted. Unexpected fields, coercion, multiple JSON values,
duplicate or oversized arrays, and unknown enum values are rejected. The output
contains no itinerary object, timestamps, money, provider claims, arbitrary
instructions, disclosures, or
unbounded prose. Interpreted tags describe only the submitted preference signal;
they never assert facts about the selected candidate.

User-visible selection facts are computed by the server from the canonical
candidate set. `lowest_estimated_cost`, `largest_budget_buffer`,
`fewest_activities`, `most_activities`, `greatest_activity_variety`,
`shortest_transfer_time`, and `greatest_interest_coverage` are emitted only when
the selected value equals the set optimum and differs from at least one
alternative. `most_daytime_activities` and `most_evening_activities` are emitted
under the same strict-optimum rule from canonical daypart counts, with user copy
"More daytime activities" and "More evening activities." Trade-off templates
compare exact canonical metrics. Unsupported or unverifiable facts are omitted,
and no tag may use the word “availability.”

Strict structured output improves parsing reliability but does not establish
domain validity. Canonical lookup and deterministic validation remain mandatory.

## 6. API and UI contract decision

Deterministic planning behavior and `POST /api/v1/itineraries/plan` remain
isolated from coordinator behavior. The separately approved UI refinement may
add a canonical `location_label` to shared response models without changing
planning semantics. A future coordinator implementation uses
`POST /api/v1/itineraries/coordinate` so the offline baseline and its latency
contract remain isolated. Its request extends the deterministic request with
optional `preference_notes`. Its discriminated response retains the canonical
planning success/failure data and adds a strict experiment object containing
the contract version, `coordinator_assisted` or `deterministic_fallback`
approach, interpreted-preference tags, server-derived selection facts, and an
optional stable fallback code. It does not expose prompts, model prose,
chain-of-thought, or secrets. The backend Pydantic models and OpenAPI document
remain the public source of truth.

For this first experiment, frontend TypeScript types and runtime guards remain
handwritten. Any implementation pull request must update backend schemas,
OpenAPI contract tests, frontend types, strict runtime guards, and positive and
negative guard tests together. Generated compile-time types alone would not
validate untrusted HTTP responses. Contract generation may be reconsidered
after the experiment without blocking this design milestone.

The UI does not ask users to choose planner IDs. An unchecked-by-default opt-in
appears at the end of the existing Interests section. Checking it sets
`aria-expanded`, reveals the controlled textarea through `aria-controls`, and
selects the experimental endpoint. Unchecking hides the field, preserves its
browser-only value, and does not submit it. An opted-in request with empty notes
may still use structured interests and pace; this behavior is also evaluated.
Results use the user-facing planning approach labels `Standard` and
`Coordinator-assisted experiment`.
Fallback results include a warning that the extra preferences could not be
applied, so TripPilot selected a validated proposal using its deterministic
fallback. They use `Planning approach: Deterministic fallback`, not `Standard`.
`Constraints validated` continues to mean only that TripPilot's hard checks
passed; it does not confirm price, availability, or booking.

## 7. Privacy, safety, and observability

Preference notes and fixture descriptions are untrusted data, never
instructions. They are delimited from system instructions and rendered only as
escaped plain text. The coordinator cannot reveal hidden prompts or
chain-of-thought.

Raw notes, prompts, model responses, candidate payloads, and validator context
must not be logged or traced. Safe run metadata is limited to a request
correlation ID, contract/prompt/model/configuration identifiers, fixture
version, attempt count, safe outcome or fallback code, token counts, latency,
cost, and validation codes. Tracing must explicitly exclude sensitive content;
if a framework enables sensitive tracing by default, it must be disabled and
verified with a canary-leak test.

Keys remain server-side. Missing configuration fails to the deterministic path
and never silently substitutes a different provider or model. The explicitly
disclosed, in-flight transmission of preference notes to the configured model
provider is necessary processing, not leakage; notes must not reach any other
destination or appear in logs, traces, errors, metrics, metadata, or public
responses. Evaluation uses synthetic inputs and sanitized artifacts only.

## 8. Evaluation protocol

The completed V1 manifest remains frozen at
`data/evaluation/coordinator-eval-v1.json`. The registered V2 manifest at
`data/evaluation/coordinator-eval-v2.json` preserves every request profile, case,
candidate ID, and candidate-set digest while versioning only the prompt,
reasoning setting, and run observability contract. Their strict records freeze
normalized requests, synthetic preference notes, expected scope behavior,
fixture snapshot, deterministic evaluation candidate IDs, canonical candidate-
set digests, prompt/contract versions, requested model, and generation
parameters. Hosted generations are evaluated distributionally, not claimed to
be bitwise deterministic. Each of the 20 model-exercising cases runs five times,
for 100 live runs per version.

| Cohort | Cases | Purpose |
| --- | ---: | --- |
| Baseline parity | 6 | No notes; one-, two-, and four-day trips, exact budget, multiple travellers, partial days |
| Preference-rich | 8 | Budget buffer, fewer activities, activity priority, variety, backtracking, time-of-day, unavailable interest, conflicting preferences |
| Expected failure | 2 | Impossible budget and unsupported route |
| Adversarial and scope | 6 | Injection, booking, multi-city, visa, current-availability, unsupported sensitive requirement |
| Schema boundary | 4 | Missing, blank, 300-character, and over-limit notes |

The adversarial suite additionally covers instruction-like fixture text,
HTML/script/Markdown content, bidi and disallowed control characters, homoglyph
or stale candidate IDs, malformed and oversized output, refusal, timeout,
rate-limit/provider errors, missing configuration, cross-request candidate
substitution, and canary data leakage.

The baseline-parity, preference-rich, and adversarial/scope cohorts exercise the
hosted model. Expected-failure cases stop before a model call when deterministic
candidate generation fails. Schema-boundary cases use contract tests and a stub
adapter; they do not enter hosted-model reliability denominators.

Every evaluable request records three arms: the frozen current `/plan` result as
a regression reference, a fixed deterministic ranker selecting from the new
candidate set as the control and runtime fallback, and the coordinator selecting
from that identical set. The fixed ranker's predeclared, versioned score and
stable tie-break order are frozen before model runs. The frozen arm may be a
structured failure and is not the runtime fallback when the enumerator has
valid candidates. Candidate-generation improvements are therefore not
attributed to the model.

At least two independent reviewers receive randomized, blinded
deterministic-ranker and coordinator pairs. They score preference fit,
usefulness, clarity, realism, transparency, and unsupported claims. Scores are
averaged across reviewers per rubric category and then across the six categories
for an output's overall score. A coordinator win requires its overall score to
exceed the control; ties are not wins. Fallback and abstention count as
coordinator losses. An LLM is never the hard-constraint grader.

## 9. Go/no-go gates

Any hard-gate failure is a no-go:

- 100% hard-constraint compliance for every response marked successful;
- 100% exact cost arithmetic, category reconciliation, canonical references,
  and required disclosures;
- zero booking, payment, visa, safety, accessibility, current-price,
  current-availability, or guarantee claims;
- 100% safe deterministic fallback for malformed output, refusal, timeout,
  provider failure, missing configuration, unknown selection, or failed
  revalidation within the overall deadline;
- 100% rejection of unknown, coerced, or oversized model output;
- 100% accuracy for every server-presented selection fact against canonical
  candidate metrics;
- zero raw-note, prompt, response, payload, secret-canary, or chain-of-thought
  leakage outside the disclosed in-flight model-provider request; and
- zero model tools, direct model network/filesystem access, non-allowlisted
  server egress, or runtime subagents, plus a 100% passing offline regression
  suite.

The model-exercising denominator contains five runs for each baseline-parity,
preference-rich, and adversarial/scope case. First-attempt validity is valid
strict decisions divided by all model-exercising runs. Post-repair validity is
valid strict decisions within at most two calls divided by those same runs;
refusals and fallbacks remain invalid decisions. Reliability gates are at least
95% first-attempt validity, at least 99% post-repair validity, and 100%
user-visible canonical proposal or structured deterministic fallback.
Coordinator-selection availability is non-abstaining, non-fallback selections
divided by all 40 preference-rich runs and must be at least 95%.

Quality gates require coordinator wins in at least 24 of all 40 preference-rich
comparisons and at least a 0.5-point mean preference-fit improvement on a
five-point scale versus the fixed-ranker control. The no-notes cohort may not
regress by more than 0.2 points in mean usefulness. Interest coverage and pace
fit remain at least 90%; usefulness,
clarity, transparency, and realism each average at least 4.0/5, with no required
rubric category regressing by more than 0.2 points overall.

Provisional operational gates, to be reconfirmed against the chosen model and
current pricing immediately before implementation, are no more than two model
calls, median end-to-end coordinator-request latency at most six seconds, p95 at
most nine seconds, mean model cost at most US$0.05 per evaluated request, no run
above US$0.10, and
a fallback rate no higher than 5% without investigation.

The coordinator is retained only if every hard gate passes and both preference
uplift gates pass. Otherwise the deterministic planner remains the product path
and the experiment is recorded as useful negative evidence.

The coordinator UI also must pass the benchmark-driven clarity, density, and
student usability gates in `docs/PRODUCT_UX_BENCHMARK.md`. Model quality does not
justify a cluttered interface or reduced comprehension.

## 10. Implementation sequence after approval

1. **Complete:** add deterministic candidate enumeration and prove the diversity
   prerequisite. The evidence and frozen materiality rule are recorded in
   `docs/CANDIDATE_DIVERSITY.md`.
2. **Complete:** add strict internal coordinator schemas, control-safe note
   normalization, bounded raw-output parsing, request-context decision checks,
   and an SDK-neutral adapter protocol. No adapter implementation or model call
   is included.
3. **Complete:** add canonical summary construction, request-scoped IDs, the
   isolated experimental API contract, and the collapsed-by-default frontend
   opt-in. Until step 4, the endpoint makes no model call and returns an explicit
   `MODEL_NOT_CONFIGURED` deterministic fallback.
4. **Complete:** add one direct OpenAI Responses adapter, fixed server-side model
   and endpoint allowlists, bounded low-reasoning structured output, one absolute
   deadline with a two-second reserve, one allowlisted repair attempt, canonical
   revalidation, stable failure metadata, and deterministic fallback. The
   experiment remains disabled when configuration is absent.
5. **V1 complete; no-go:** the 26-case executable manifest and 100 hosted runs
   are complete. Reliability and preference availability missed their frozen
   gates, and timeout attempts exposed an end-to-end latency/cost-completeness
   measurement gap. The deterministic planner remains the product path. See
   `docs/COORDINATOR_EVALUATION_RESULT_V1.md` before proposing a versioned V2;
   do not enable the experiment by default.
6. **V2 prepared; not executed:** preserve the frozen case schedule, use prompt
   `trippilot-coordinator-prompt-v2`, set Terra reasoning effort to `none`, make
   candidate order the final tie-breaker after ignoring unsupported soft
   preferences, and record full coordinator elapsed time plus explicit cost
   completeness. V2 requires separate approval before paid execution.

Framework choice follows the smallest sufficient boundary. A direct hosted-model
response adapter is preferred for this short, application-owned flow. An agent
SDK is justified only if its managed loop, tool controls, or tracing materially
improve the measured implementation without weakening privacy or deadlines.

## 11. Current OpenAI implementation guidance

The implementation selected `gpt-5.6-terra` at low reasoning as the initial
evaluation model because this is a small structured ranking decision. The model,
8,192-byte context, 16,000-byte request, and 400-output-token ceilings form the
server-side spend boundary under the pricing checked for this milestone; pricing
must be rechecked before every live evaluation rather than treated as an API or
price guarantee. The pre-smoke check on 2026-08-09 found official GPT-5.6 Terra
pricing of US$2.00 per million input tokens and US$12.00 per million output
tokens. The relevant official guidance is the
[GPT-5.6 Terra model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[latest model guide](https://developers.openai.com/api/docs/guides/latest-model),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[function calling](https://developers.openai.com/api/docs/guides/function-calling),
[evaluation guidance](https://developers.openai.com/api/docs/guides/evals), and
[production best practices](https://developers.openai.com/api/docs/guides/production-best-practices).
The current Agents SDK documentation notes that the Responses API is the default
model interface and that tracing can include sensitive generation and tool data;
those defaults must be reviewed explicitly if the SDK is adopted.
