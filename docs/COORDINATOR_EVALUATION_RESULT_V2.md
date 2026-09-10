# Coordinator Evaluation Result V2

Date: 2026-08-10

Code revision: `9541c6e`

Protocol: `coordinator-eval-v2`

Model: `gpt-5.6-terra`, reasoning effort `none`

## Decision

**NO-GO for default enablement.** V2 passes every frozen reliability,
availability, hard-constraint, latency, cost, and observability gate. It cannot
pass the frozen coordinator-win quality gate, however, because only 20 of 40
preference-rich selections differ from the fixed-ranker control. Identical
canonical outputs are reviewer ties, so the mathematical maximum is 20 wins
against a required 24. The deterministic planner remains the product path.

## Execution integrity

- 20 model-exercising synthetic cases ran five times each: 100 unique runs.
- Every run produced a strict selection on its first and only model attempt.
- Every selected canonical candidate passed deterministic hard-constraint
  revalidation.
- Every attempt returned safe usage metadata, so cost completeness is 100%.
- Full coordinator elapsed time was captured independently of provider metadata.
- The ignored local checkpoint contains no API key, prompt, preference note, raw
  model output, provider payload, itinerary body, or personal data.
- The offline regression baseline remained green at 331 tests before execution.

## Frozen operational gates

| Gate | Required | Observed | Result |
| --- | ---: | ---: | --- |
| First-attempt usable strict decision | at least 95% | 100/100 | PASS |
| Usable strict decision after repair | at least 99% | 100/100 | PASS |
| Canonical proposal or deterministic fallback | 100% | 100/100 | PASS |
| Preference-cohort coordinator availability | at least 95% | 40/40 | PASS |
| Fallback rate without investigation | at most 5% | 0/100 | PASS |
| Canonical hard-constraint validity | 100% | 100/100 | PASS |
| Median end-to-end latency | at most 6s | 1.569s | PASS |
| P95 end-to-end latency | at most 9s | 2.946s | PASS |
| Mean model cost | at most US$0.05 | US$0.002917 | PASS |
| Maximum run cost | at most US$0.10 | US$0.003370 | PASS |
| Complete cost metadata | required for cost claim | 100/100 | PASS |

Total captured and complete model cost was US$0.291696. Maximum end-to-end
coordinator elapsed time was 3.964 seconds. The 100 responses used 105,210 input
tokens and 6,773 output tokens, and every returned model identifier was
`gpt-5.6-terra`.

## Cohort results

| Cohort | Selections | Fallbacks | Availability |
| --- | ---: | ---: | ---: |
| Baseline parity | 30 | 0 | 100% |
| Preference rich | 40 | 0 | 100% |
| Adversarial/scope | 30 | 0 | 100% |
| Total | 100 | 0 | 100% |

All five prompt-injection runs selected only the submitted `candidate_01`.
Out-of-scope booking, multi-city, visa, live-availability, and unsupported
guarantee requests also remained inside the candidate-selection boundary.

## Quality gate impossibility

The fixed ranker selects `candidate_01`. Within the 40 preference-rich runs:

- 20 coordinator selections were identical to the fixed-ranker candidate;
- 20 selected a different candidate; and
- therefore at most 20 comparisons can be coordinator wins.

The frozen gate requires at least 24 wins, and reviewer ties do not count. Even
if two independent reviewers scored every different selection as a coordinator
win, V2 would still fail 20 to 24. Blinded scoring is therefore deferred rather
than consuming reviewer time on a version that cannot pass.

The explicit shorter-transfer case also selected the strict minimum-transfer
candidate in only two of five runs. The other three selections still improved
over the fixed-ranker control but were not the metric optimum. This supports the
conclusion that reasoning effort `none` improved reliability and efficiency at
the cost of some ranking precision.

## V1 to V2 comparison

| Metric | V1 | V2 |
| --- | ---: | ---: |
| First-attempt selection | 90% | 100% |
| Post-repair selection | 91% | 100% |
| Preference availability | 85% | 100% |
| Fallback rate | 9% | 0% |
| Complete cost runs | 98% | 100% |
| Captured total cost | at least US$0.414982 | US$0.291696 |
| Output tokens | 18,087 | 6,773 |

V1 lacked complete elapsed and cost data for timeout attempts, so its latency
and total-cost values are not directly comparable. V2's cost is complete.

## Recommended next experiment

Do not weaken or retroactively revise the frozen V2 gate. If another iteration
is approved, isolate the reasoning-quality hypothesis:

1. preserve prompt V2's no-abstention, unsupported-preference, and final
   tie-break rules;
2. preserve the V2 cases, candidates, hard limits, elapsed-time measurement, and
   cost-completeness fields;
3. restore Terra reasoning effort `low` under a versioned V3 manifest;
4. first run a paid diagnostic on the conflicting-preference and shorter-
   transfer cases before authorizing another full 100-run batch; and
5. proceed to two-reviewer blinded scoring only if the observed selection mix
   makes at least 24 wins mathematically possible while operational gates remain
   credible.
