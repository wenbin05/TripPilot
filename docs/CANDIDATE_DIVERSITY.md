# Deterministic Candidate Diversity

## 1. Purpose and boundary

Milestone 8 implements the first step of the approved coordinator experiment:
bounded deterministic candidate enumeration. It adds no endpoint, model call,
API key, preference-note input, persistence, or frontend behavior.

`enumerate_trip_candidates()` returns either the existing structured planning
failure or an ordered `CandidateSet` containing one to five canonical,
validator-clean candidates. One candidate is a valid generator result; it must
never be duplicated merely to satisfy the future coordinator's two-candidate
minimum. Candidate zero is exactly the proposal returned by the existing
`plan_trip()` traversal for the same normalized request and fixture snapshot.

## 2. Material-difference rule

Every retained pair must satisfy both conditions:

1. The chronological primary-activity source-record sequence differs. This
   captures a changed activity set, repeat count, or ordering and rejects
   presentation-only, meal-only, accommodation-only, and transport-only
   variants.
2. At least one deterministic trade-off differs materially:
   - estimated all-in cost differs by at least the smaller of 500 minor units
     and 5% of the request budget, rounded up;
   - summed minimum local-transfer requirements differ by at least 15 minutes;
   - primary activity count differs by at least one; or
   - the exact eight-interest activity-count vector differs; or
   - the exact morning/afternoon/evening activity-count vector differs.

A daypart difference is material only after condition 1 has already established
a changed primary-activity sequence; moving the same activities cosmetically
does not qualify.

The generator walks the existing stable bounded search order until the
requested limit is reached or the search is exhausted. It validates every
candidate, enforces the all-in budget, compares alternatives pairwise, and
returns fewer candidates rather than weakening these rules.

Local-transfer minutes are the sum of deterministic minimum transfer
requirements between consecutive scheduled located items. They do not include
the duration of inbound or outbound boundary transport.

## 3. Frozen prerequisite cases

The executable regression table in
`backend/tests/unit/test_candidate_generation.py` freezes eight distinct
normalized requests against fixture snapshot `2026-08-01.v1`. Together they
cover:

- one-, two-, and four-day trips;
- relaxed, balanced, and packed pace;
- one and two travellers;
- morning and late earliest-activity times;
- generous and constrained-but-feasible budgets; and
- available interest combinations spanning culture, nature, history,
  nightlife, food, student budget, sport, and shopping.

All eight requests must produce between two and five pairwise materially
different candidates. The constrained two-traveller case uses a 35,000-minor-
unit budget and retains proposals estimated at 33,800 minor units. Each case
also freezes a SHA-256 digest of its ordered activity, cost, local-transfer,
interest-count, and daypart-count metrics so a candidate-set change requires
explicit review. The same suite proves stable repeated output, baseline
selection parity, canonical record and location references, complete
revalidation, exact category reconciliation, budget compliance, the five-item
upper bound, strict limit handling, and preservation of structured failure when
no candidate is possible.

This passes the minimum diversity prerequisite in
`docs/COORDINATOR_EXPERIMENT.md`. The later Milestone 12 preparation freezes the
full `coordinator-eval-v1` manifest after adding strict coordinator schemas, the
preference-note boundary, fixed ranker, and bounded adapter protocol.

## 4. Next work

Strict internal contracts, canonical summary construction, request-scoped IDs,
the isolated experimental API, and the explicit frontend opt-in are now
implemented. The enumerator still intentionally does not create candidate IDs.
The next phase adds one configured hosted-model adapter, deadline-bound
orchestration, retry/fallback handling, and safe operational metadata.
