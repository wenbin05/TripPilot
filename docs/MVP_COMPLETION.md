# MVP completion contract

September 23 status: integrated automated and browser checks pass. The actual
200% browser-zoom gate remains open due to native browser-control permissions.
See [the integrated acceptance evidence](FINAL_MVP_ACCEPTANCE.md), including
the evaluated revision, screenshots, and exact remaining manual check.

The next iteration is the final local MVP acceptance iteration. Freeze feature
scope at the existing student planner: one city, one to four days, synthetic
travel data, exact all-in estimates, deterministic validation, and a clean
desktop/mobile interface. No new agent capabilities are required to finish it.

## Implemented and verified

- Deterministic planning, strict API schemas, canonical provider references,
  integer cost arithmetic, and constraint enforcement.
- Browser one-, two-, and four-day proposals; impossible-budget failure and
  recovery; five-day rejection. Evidence: `LOCAL_DEMO.md`.
- Responsive reflow at 390 and 320 CSS pixels with no page overflow in the
  recorded browser pass.
- Budget failure display corrected and covered by regression tests (PR #6).
- Reproducible local startup and exact synthetic demo inputs.
- GitHub Actions backend/frontend test, formatting, lint, typing, and build jobs.
- Offline experimental action/observation loop with strict local tools, bounded
  repairs/calls, deadline checks, and deterministic final/fallback validation.
  This is infrastructure evidence, not proof of hosted agent quality.

## Final iteration: required closure

1. Review and merge PR #6 and the dependent bounded-agent-core PR after green CI.
   Sync the final integration revision; record that revision in the acceptance
   report rather than treating an earlier branch result as release evidence.
2. Repeat the documented local demo against the integrated revision. Check
   linked errors, retained inputs, budget recovery, keyboard focus, and the
   no-booking disclosure. Capture desktop and mobile screenshots for handoff.
3. Complete the outstanding 200% browser-zoom/reflow check. Fix any blocking
   clipping, inaccessible controls, or hidden errors and add focused tests for
   behavioral defects. Keep cosmetic improvements outside the completion gate.
4. Record checks and limitations in a final acceptance addendum. Confirm the
   README and demo guide agree with the actual release behavior.

Completion means these four items have evidence, not merely a green unit-test
suite. If a blocker appears, fix it within this iteration where feasible and
report it explicitly rather than labeling the MVP complete prematurely.

## Known limits that do not expand this MVP

The demo supports the frozen Kingston–Toronto route and August 10–13, 2026
fixture dates. There is no current availability, purchasing, production hosting,
or persistence. The optional hosted coordinator remains disabled by default
after its recorded no-go results. The internal workflow has no hosted tool-call
adapter or public endpoint and cannot revise itineraries.

Independent student usability feedback is a follow-up, not a claim made by the
engineering acceptance pass. It should inform the expansion proposal.

## Expansion proposal after closure

Propose the smallest measurable addition first: deterministic proposal-revision
tools followed by a bounded hosted single-agent adapter and a new benchmark.
Define the user problem, success metric, baseline, spend limit, and scope change
before implementation. MCP, RAG, databases, deployment, and multiple runtime
agents remain separate decisions under the PRD and AGENTS.md.
