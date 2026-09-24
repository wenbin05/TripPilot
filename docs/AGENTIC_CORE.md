# Bounded agentic core

Approved direction: September 23, 2026. The product remains a one-city,
one-to-four-day proposed student trip with deterministic hard constraints.

## Stages

Completion priority: finish the local MVP using `MVP_COMPLETION.md` before
starting stages 2–4. Those stages are expansion proposals, not remaining MVP
requirements. The offline foundation can ship as internal experimental code.

1. Offline foundation (this slice): an injected decision adapter requests local
   tools, receives structured observations, and chooses its next action. Tools
   inspect canonical candidate metrics and invoke the complete validator.
2. Planning tools: deterministic candidate revision with locked hard constraints
   and evidence-bearing activity lookup through the mock provider interface.
   Define what the agent can improve beyond the existing candidate set before
   spending on hosted evaluation.
3. Hosted adapter: explicit tool schemas, serial calls, provider cancellation,
   token/cost caps, and sanitized metadata. Freeze a new evaluation manifest and
   spending limit before a paid run. Do not silently reuse V3 approval.
4. Optional public integration only after measured benefit and safety gates.
   MCP and retrieval are subsequent, separately specified additions.

The first slice is workflow infrastructure, not evidence of intelligent planning
or a replacement for the failed ranking experiment. It cannot create or revise
an itinerary yet. No model, SDK, MCP, database, API route, or UI change is added.

## Offline contract

The server creates canonical candidates and opaque request-local IDs using the
existing enumerator and context builder. The adapter sees IDs, normalized
preferences, and accumulated observations, never mutable domain objects.
Exactly one action is accepted per step:

- `inspect_candidate(candidate_id)` returns the canonical summary (integer cost,
  remaining budget, activity/interest metrics, and transfer minutes).
- `validate_candidate(candidate_id)` returns the complete deterministic
  validator's validity and closed violation codes.
- `finish(candidate_id)` requires a prior successful validation observation for
  that exact ID, then independently revalidates before returning it.

All action fields are required, unexpected fields and unknown actions are
rejected, candidate IDs are resolved only within this request, and JSON is
limited to 2 KiB with duplicate-key and non-finite-number rejection. State and
tool observations use frozen extra-forbid Pydantic schemas. Observations stay
in memory and are not logs.

The loop allows at most five adapter calls and four tool calls. One malformed
action or unknown/unvalidated candidate is recoverable through a stable error
observation; a second ends the run. Exceptions and late adapter/tool returns
produce stable fallback codes without exposing raw content. A supplied absolute
monotonic deadline is checked before and after each adapter/tool execution.
This synchronous offline harness cannot interrupt a hanging adapter; a hosted
adapter must enforce its transport timeout before it can be integrated.

Fallback is candidate zero only if freshly validator-clean for the supplied
request. Otherwise the result is a structured failure with no itinerary.
Per-run counters record adapter steps, tools, and invalid actions. No notes,
raw model output, exceptions, or chain-of-thought appear in returned diagnostics.

## Evaluation gates

Offline tests cover the multi-step success path, argument rejection, unknown
IDs, one repair, repeated errors, tool and adapter failures, step/tool exhaustion,
deadline expiry, unvalidated finish, and invalid fallback. All returned
candidates must pass the real domain validator. Existing API regressions remain
green and no automated test may require a key or model network access.

Before hosted evaluation, register scenarios and expected tool behavior for
budget conflicts, opening hours, transfer constraints, missing data, injection,
and outages. Compare against the deterministic planner on identical inputs.
Report task success, hard-constraint failures, invalid tool arguments, recovery,
step counts, latency and cost. Offline scripted success is not a quality score.

The application owns execution and returns tool observations, following the
[official function-calling flow](https://developers.openai.com/api/docs/guides/function-calling).
Hard-rule arithmetic and validation always remain deterministic Python.
