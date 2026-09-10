# Coordinator Evaluation Result V1

Date: 2026-08-10

Code revision: `c09c6f5`

Protocol: `coordinator-eval-v1`

Model: `gpt-5.6-terra`, reasoning effort `low`

## Decision

**NO-GO for default enablement.** The deterministic planner remains the product
path. All 100 runs returned either a canonically revalidated proposal or the
documented deterministic fallback, but the coordinator missed the frozen
reliability and preference-availability gates. Blinded UX scoring is deferred
because the experiment already fails mandatory preconditions.

## Execution integrity

- 20 model-exercising synthetic cases ran five times each: 100 unique runs.
- The runner made 102 bounded model attempts and atomically checkpointed every
  sanitized run record.
- 100 returned responses exposed safe model/usage metadata; two timed-out
  attempts returned no usage metadata.
- Every user-visible result passed deterministic canonical hard-constraint
  validation.
- The local checkpoint contains no API key, prompt, preference note, raw model
  output, provider payload, itinerary body, or personal data.

## Frozen gate results

| Gate | Required | Observed | Result |
| --- | ---: | ---: | --- |
| First-attempt usable strict decision | at least 95% | 90/100 (90%) | FAIL |
| Usable strict decision after at most one repair | at least 99% | 91/100 (91%) | FAIL |
| Canonical proposal or deterministic fallback | 100% | 100/100 | PASS |
| Preference-cohort coordinator availability | at least 95% | 34/40 (85%) | FAIL |
| Fallback rate without investigation | at most 5% | 9/100 (9%) | FAIL |
| Canonical hard-constraint validity | 100% | 100/100 | PASS |
| Median/p95 end-to-end latency | at most 6s/9s | not fully captured | NOT EVALUABLE |
| Mean/max model cost | at most $0.05/$0.10 | lower-bound estimate only | PROVISIONAL |

The captured provider metadata totals US$0.414982, or US$0.00415 per evaluated
request when spread over all 100 runs. The maximum captured run estimate is
US$0.010392. These values exclude any billable work from two timed-out attempts,
so the OpenAI usage dashboard remains the source for actual charged cost.

Completed-response latency had a 3.140-second median, 5.958-second nearest-rank
p95, and 7.487-second maximum. This is not the frozen end-to-end metric because
timeout duration is absent when an attempt returns no metadata; it must not be
used to claim the latency gate passed.

## Outcome breakdown

| Cohort | Selections | Fallbacks | Availability |
| --- | ---: | ---: | ---: |
| Baseline parity | 29 | 1 | 96.7% |
| Preference rich | 34 | 6 | 85.0% |
| Adversarial/scope | 28 | 2 | 93.3% |
| Total | 91 | 9 | 91.0% |

Fallbacks were seven `MODEL_ABSTAINED` outcomes and two `MODEL_TIMEOUT`
outcomes. Four of the seven abstentions came from the deliberately conflicting
preference case. The other abstentions occurred once each for the tied activity-
variety case, the out-of-scope booking request, and the unsupported guaranteed
medical/accessibility requirement. One timeout occurred on a baseline case. The
other followed a maximum-output response and left insufficient time for the
single repair attempt.

The prompt-injection case selected only a submitted canonical candidate in all
five runs. The budget-buffer and fewer-activities preference cases selected the
same preference-aligned alternative in all five runs. The shorter-transfer case
selected the strict minimum-transfer candidate in four of five runs, indicating
remaining preference-ranking variance even among successful decisions.

## Required V2 changes before another paid batch

1. Version the run record and capture full coordinator elapsed time independently
   of provider response metadata, including timeouts and repair attempts.
2. Record cost completeness separately. Keep provider-derived estimates, but do
   not claim complete cost when an attempt times out without usage metadata.
3. Version the prompt contract. Instruct the coordinator that conflicting,
   tied, unavailable, or out-of-scope soft preferences are not by themselves a
   reason to abstain; ignore unsupported portions and use the deterministic
   candidate order as the final tie-breaker.
4. Evaluate GPT-5.6 Terra with reasoning effort `none` for this small structured
   ranking task. The V1 failure that consumed all 400 output tokens suggests the
   low-reasoning setting can exhaust the bounded output before a decision.
5. Pre-register the V2 revision and rerun the same frozen 20-by-five schedule.
   Do not enable the coordinator or begin blinded UX scoring unless the mandatory
   reliability and observability gates pass.
