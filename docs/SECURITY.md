# Security and Safety

## 1. Scope and threat model

The first MVP is local, unauthenticated, uses mock data, performs no booking or
payment, and has no production deployment. Its main risks are malformed input,
misleading travel claims, accidental secret exposure, unsafe future LLM output,
and architectural coupling that makes later external integrations difficult to
control.

This document is engineering guidance, not a claim of production readiness.

## 2. Data handling

- Collect only trip-planning inputs required by the PRD.
- Do not request passport numbers, government IDs, payment details, precise home
  addresses, credentials, or sensitive demographic data.
- Do not log full request bodies by default. Redact secrets and user-provided
  free text if structured logging is added.
- Keep MVP requests in memory only. Define retention and deletion policies before
  adding PostgreSQL or analytics.
- Use synthetic or licensed mock fixtures; never seed them with personal data.

## 3. Secrets and configuration

- Commit only `.env.example`, never `.env` or real credentials.
- Keep future provider and hosted-LLM keys server-side.
- Fail closed when required configuration is missing; never silently substitute
  a production provider.
- Rotate any credential that appears in source, logs, screenshots, issues, or
  chat history.

## 4. Input and output controls

- Apply strict Pydantic schemas, length bounds, enums, numeric bounds, and
  rejection of unexpected fields at system boundaries.
- Normalize dates, currencies, identifiers, and timezones once at ingress.
- Set request size and execution time limits when the HTTP layer is implemented.
- Return generic public errors with stable codes; keep internal details out of
  responses.
- Treat all user text and provider content as untrusted data, not instructions.
- Escape rendered content in the future web client; do not render arbitrary HTML.

## 5. LLM safety boundary

No LLM is needed for the deterministic MVP. Before adding the future single
coordinator:

- give it only the minimum schema-validated context;
- use structured output with strict parsing and size limits;
- prevent direct network, filesystem, booking, payment, and code-execution access;
- validate all proposals with deterministic code before returning them;
- cap retries, tokens, and time synchronously;
- separate system instructions from untrusted user/provider text;
- do not expose hidden prompts or chain-of-thought; and
- log only the safe operational metadata defined by the experiment contract.

For the first coordinator experiment, the model may only select or abstain among
two to five deterministic, validator-clean candidate IDs bound to the request
and fixture snapshot. It emits controlled preference-interpretation tags, not
an itinerary, factual selection claims, money, timestamps, provider facts,
arbitrary prose, or disclosures. Selection facts are derived deterministically.
The service resolves the canonical candidate and revalidates it. Malformed
output, refusal, timeout, missing configuration, unknown IDs, or validation
failure always use the deterministic fallback.

Do not log or trace raw preference notes, prompts, model responses, provider
payloads, candidate bodies, or validator context. If an SDK enables tracing or
sensitive trace content by default, disable it explicitly and prove the control
with a canary-leak test. Keep any model key server-side and never silently swap
models or providers when configuration is missing.

The only experiment network egress is the server's configured hosted-model
adapter to an allowlisted provider destination. The model receives no tools and
has no direct egress. Candidate summaries contain strict derived facts and
stable IDs only, never raw provider titles, descriptions, or source labels.

Prompt injection is possible even in external travel descriptions. Provider data
must never grant authority or override system and domain rules.

## 6. Travel-specific safety and claims

- Label prices, hours, routes, and availability as mock estimates.
- State explicitly that nothing has been booked or reserved.
- Do not provide visa or immigration advice in the MVP. For later cross-border
  features, direct users to current official authorities without guaranteeing
  eligibility.
- Do not guarantee safety, accessibility, weather, opening hours, or availability.
- Avoid presenting time-sensitive emergency or health information from stale
  fixtures.
- Reject requests that require unsupported transactions rather than simulating a
  successful transaction.

## 7. Dependency and supply-chain hygiene

- Start with the minimum direct dependencies: FastAPI, Pydantic, an ASGI server
  for local development, and pytest when implementation begins.
- Pin or lock dependencies using the packaging approach selected by the team.
- Review transitive dependencies and automate vulnerability scanning before any
  deployment.
- Keep provider SDKs in adapters and prefer standard HTTP clients if an SDK adds
  excessive surface area.

## 8. Future controls before production

Authentication, authorization, rate limits, abuse controls, CSRF/CORS policy,
TLS, secure headers, encrypted persistence, backups, audit trails, monitoring,
incident response, regional/privacy review, and provider contractual review are
all required design work before production. They are intentionally not
implemented in the first MVP.

## 9. Reporting vulnerabilities

Until a public security channel exists, report suspected vulnerabilities
privately to the repository owner. Do not include live secrets or exploitable
personal data in public issues.
