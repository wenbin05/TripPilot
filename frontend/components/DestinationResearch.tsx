"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { researchDestination, type ResearchResponse } from "@/lib/research";

export function DestinationResearch() {
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  return (
    <section className="research-shell">
      <nav aria-label="TripPilot navigation">
        <Link href="/">← Mock itinerary planner</Link>
      </nav>
      <p className="eyebrow">TRIPPILOT · EXTERNAL RESEARCH</p>
      <h1>Explore with evidence.</h1>
      <p>
        Ask about a destination. Read relevant passages from its live Wikivoyage
        guide, with sources you can inspect.
      </p>
      <aside className="research-notice">
        Research is separate from the mock itinerary planner. It does not
        validate prices, opening hours or availability. Nothing is booked.
      </aside>
      <form
        className="research-card"
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          const data = new FormData(event.currentTarget);
          setBusy(true);
          setError("");
          setResult(null);
          try {
            setResult(
              await researchDestination(
                String(data.get("destination")),
                String(data.get("question")),
                data.get("synthesize") === "on",
              ),
            );
          } catch {
            setError(
              "Research could not be loaded. Check the guide title and backend connection, then try again.",
            );
          } finally {
            setBusy(false);
            requestAnimationFrame(() => heading.current?.focus());
          }
        }}
      >
        <label htmlFor="research-destination">Destination guide</label>
        <input
          id="research-destination"
          name="destination"
          placeholder="Toronto, Montreal, or Paris"
          minLength={2}
          maxLength={100}
          required
        />
        <p className="helper">
          Use an English Wikivoyage page title, including a district if useful.
          No fixed city list or trip dates.
        </p>
        <label htmlFor="research-question">
          What would you like to explore?
        </label>
        <textarea
          id="research-question"
          name="question"
          placeholder="Museums, parks and public transport"
          minLength={3}
          maxLength={300}
          rows={3}
          required
        />
        <details>
          <summary>Optional AI summary</summary>
          <label>
            <input type="checkbox" name="synthesize" /> Generate a cited summary
            if the server is configured
          </label>
          <p>
            Your question and retrieved passages will be sent to OpenAI. This
            may incur API charges. Evidence-only research needs no key.
          </p>
        </details>
        <p className="helper">
          The guide title is sent to Wikivoyage. Avoid personal or sensitive
          information.
        </p>
        <button disabled={busy} type="submit">
          {busy ? "Finding evidence…" : "Research destination"}
        </button>
      </form>
      <div aria-live="polite" aria-busy={busy}>
        {(result || error) && (
          <h2 ref={heading} tabIndex={-1}>
            Research results
          </h2>
        )}
        {error && <p role="alert">{error}</p>}
        {result && (
          <>
            <p>{result.notice}</p>
            {result.status === "unavailable" && (
              <p role="alert">
                The source could not be loaded. Check the exact guide title or
                try again later. No substitute facts were invented.
              </p>
            )}
            {result.status === "no_evidence" && (
              <p>
                No matching passages were found. Try more specific words or a
                district guide.
              </p>
            )}
            {result.generation_note === "not_configured" && (
              <p>AI summary is not configured. Showing source evidence only.</p>
            )}
            {result.generation_note === "failed" && (
              <p>
                AI summary was unavailable or rejected. Showing source evidence
                only.
              </p>
            )}
            {result.status === "generated" && (
              <section className="research-card">
                <h3>AI synthesis · verify against sources</h3>
                <p>
                  Citation IDs were checked; factual support is not
                  automatically guaranteed.
                </p>
                {result.claims.map((claim, i) => (
                  <p key={i}>
                    {claim.text}{" "}
                    {claim.citations.map((id) => (
                      <a key={id} href={`#evidence-${id}`}>
                        [{id}]{" "}
                      </a>
                    ))}
                  </p>
                ))}
              </section>
            )}
            {result.passages.map((p) => (
              <article
                className="research-card"
                key={p.id}
                id={`evidence-${p.id}`}
              >
                <h3>
                  {p.source_title} <small>· {p.id}</small>
                </h3>
                <blockquote>{p.text}</blockquote>
                <a href={p.source_url} target="_blank" rel="noreferrer">
                  Read cited revision ↗
                </a>
                <p className="helper">
                  Retrieved {new Date(p.retrieved_at).toLocaleString()} ·
                  Revision {p.revision}
                </p>
              </article>
            ))}
            {result.passages.length > 0 && (
              <p>
                {result.attribution} · Excerpts are reformatted.{" "}
                <a href="https://creativecommons.org/licenses/by-sa/4.0/">
                  License
                </a>
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
