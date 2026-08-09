# Coordinator V3 diagnostic result

Date: 2026-08-10

Decision: **do not authorize a full V3 batch**

## Frozen configuration

- Protocol: `coordinator-eval-v3`
- Code revision: `d27e4bab3de5b62c80380a675235d97d8c5bb8ab`
- Requested and returned model: `gpt-5.6-terra`
- Prompt: `trippilot-coordinator-prompt-v2`
- Reasoning effort: `low`
- Scope: five runs each of `preference-shorter-transfers` and
  `preference-conflicting`
- V2 run-observability contract, 400-output-token ceiling, no tools, one bounded
  repair, and deterministic fallback

The manifest preserved every V2 request profile, case, candidate ID, and
candidate-set digest. Only the evaluation contract version and reasoning effort
changed. The exact revision passed 337 backend tests, Ruff formatting and lint,
strict Pyright, offline manifest validation, and diff and tracked-file secret
checks before model egress.

The ignored local checkpoint was written atomically after every run. Strict
loading confirmed ten unique revision-bound records, and a canary scan found no
preference notes, prompts, contexts, provider snapshots, itineraries,
authorization data, or API-key fields.

## Reliability and operations

| Measure | Result |
| --- | ---: |
| First-attempt strict selections | 10/10 (100%) |
| Deterministic fallbacks or abstentions | 0/10 |
| Hard-constraint-valid selected candidates | 10/10 (100%) |
| Cost-complete runs | 10/10 (100%) |
| End-to-end coordinator median | 3,032.5 ms |
| End-to-end coordinator p95 / maximum | 4,089 ms |
| Total estimated model cost | US$0.042582 |
| Mean estimated model cost | US$0.0042582 |
| Maximum estimated model cost | US$0.005976 |
| Input / output tokens | 10,755 / 1,756 |

All diagnostic operational measures remained inside the frozen provisional
gates. Cost uses the official GPT-5.6 Terra rates rechecked immediately before
the run: US$2.00 per million input tokens and US$12.00 per million output tokens.

## Ranking result

| Scenario | Selection distribution | Different from control |
| --- | --- | ---: |
| Shorter transfers | `candidate_04`: 5/5 | 5/5 |
| Conflicting preferences | `candidate_01`: 5/5 | 0/5 |

Low reasoning removed the V2 shorter-transfer variance: the strict minimum-
transfer `candidate_04` increased from two of five V2 selections to five of five
V3 diagnostic selections. This is useful ranking-precision evidence.

It did not unlock the conflicting-preference case. All five runs selected
`candidate_01`, the fixed-ranker control and final order tie-breaker. V2 had only
20 preference selections different from control, while its frozen quality gate
requires at least 24 reviewer wins. Under the predeclared diagnostic projection,
the conflicting case needed at least four non-control selections to make that
threshold plausible without relying on untested changes elsewhere; it produced
zero.

This narrow result does not prove how the six untested V3 preference cases would
behave. It does show that the tested reasoning change preserved V2's selection-
difference ceiling in these two cases rather than supplying the missing four
potential wins. A full 100-run V3 batch is therefore not justified by the
diagnostic evidence.

## Decision and next step

Keep the deterministic planner as the product path and keep the coordinator
experiment disabled by default. Do not run or score a full V3 batch. Any future
paid version must first propose a materially different, pre-registered ranking
contract or candidate signal that can distinguish conflicting trade-offs; a
reasoning-effort change alone is insufficient evidence.
