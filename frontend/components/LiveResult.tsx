"use client";

import { useEffect, useRef } from "react";
import type { LiveDraft, BudgetEstimate } from "@/lib/live-planner";
import { COST_LABELS, type CostCategory } from "@/lib/live-inputs";
import { formatLocalDate } from "@/lib/format";

function EnteredBudget({ estimate }: { estimate: BudgetEstimate }) {
  const money = (minor: number) =>
    new Intl.NumberFormat("en", {
      style: "currency",
      currency: estimate.currency,
    }).format(minor / 100);
  return (
    <aside className="liveGaps" aria-label="Entered cost check">
      <h3>
        {estimate.status === "over_entered_estimate"
          ? "Entered costs exceed your budget"
          : estimate.status === "incomplete"
            ? "Cost estimate incomplete"
            : "Within budget based on your estimates"}
      </h3>
      <p>
        Your estimates for all travellers, for the whole trip. Not provider
        quotes; actual prices and availability remain unverified.
      </p>
      <dl className="reviewGrid">
        {(Object.entries(COST_LABELS) as [CostCategory, string][]).map(
          ([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>
                {estimate.categories[key] === null
                  ? "Unknown"
                  : money(estimate.categories[key])}
              </dd>
            </div>
          ),
        )}
      </dl>
      <p>
        Known subtotal: {money(estimate.known_subtotal_minor)} · Budget:{" "}
        {money(estimate.budget_minor)}
      </p>
      <p>
        Entered all-in estimate:{" "}
        {estimate.estimated_total_minor === null
          ? "Unknown — add missing categories"
          : money(estimate.estimated_total_minor)}
      </p>
      {estimate.remaining_minor !== null && (
        <p>
          {estimate.remaining_minor >= 0
            ? "Estimated amount remaining"
            : "Estimated amount over budget"}
          : {money(Math.abs(estimate.remaining_minor))}
        </p>
      )}
    </aside>
  );
}

export function LiveResult({ result }: { result: LiveDraft }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [result]);
  const days = [...new Set(result.stops.map((s) => s.day))];
  const time = (value: string) =>
    new Intl.DateTimeFormat("en", {
      timeZone: result.city?.timezone,
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value));
  return (
    <section
      className="liveResult plannerShell"
      tabIndex={-1}
      ref={ref}
      aria-labelledby="live-result-title"
    >
      <p className="eyebrow">Live source data · No mock fallback</p>
      <h2 id="live-result-title">
        {result.status === "draft"
          ? `Your draft for ${result.city?.name}`
          : "Live draft needs attention"}
      </h2>
      <p>{result.notice}</p>
      {result.budget_estimate && (
        <EnteredBudget estimate={result.budget_estimate} />
      )}
      {result.travel_window && (
        <aside className="liveGaps">
          <h3>Travel window based on your times</h3>
          <p>
            Ready after arrival:{" "}
            {formatLocalDate(result.travel_window.available_from.slice(0, 10))},{" "}
            {time(result.travel_window.available_from)}. Finish before
            departure:{" "}
            {formatLocalDate(result.travel_window.available_until.slice(0, 10))}
            , {time(result.travel_window.available_until)}.
          </p>
          <p>
            A {result.travel_window.transfer_buffer_minutes}-minute buffer is
            reserved each way. This is your allowance, not a verified
            station/airport transfer.
          </p>
        </aside>
      )}
      {result.destination_choices.length > 0 && (
        <ul>
          {result.destination_choices.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
      {result.status === "draft" && (
        <>
          <aside className="liveGaps">
            <h3>
              {result.budget_estimate
                ? "Provider prices and availability still unverified"
                : "Budget not verified · Total unknown"}
            </h3>
            <p>
              These are still needed before this can be a complete, feasible
              trip:
            </p>
            <ul>
              {result.missing.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </aside>
          <p>
            Times are local to {result.city?.timezone}.{" "}
            {result.travel_window
              ? "Visits respect your entered travel window; transport itself is not booked or scheduled."
              : "First/last-day travel is not included."}
          </p>
          {days.map((day) => (
            <section className="liveDay" key={day}>
              <h3>{formatLocalDate(day)}</h3>
              <ol>
                {result.stops
                  .filter((s) => s.day === day)
                  .map((s) => (
                    <li key={s.place.place_id}>
                      {s.walking_minutes_from_previous !== null && (
                        <p className="hint">
                          Walk from previous stop: about{" "}
                          {s.walking_minutes_from_previous} min. A 30-minute
                          break is also reserved.
                        </p>
                      )}
                      <p className="eyebrow">
                        {time(s.start)} – {time(s.end)} · Estimated visit
                      </p>
                      <h4>{s.place.name}</h4>
                      <p>{s.place.address}</p>
                      <p className="hint">
                        Opening hours unverified · Price unknown
                      </p>
                      <a
                        href={`https://www.openstreetmap.org/?mlat=${s.place.lat}&mlon=${s.place.lon}#map=17/${s.place.lat}/${s.place.lon}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View location on OpenStreetMap
                      </a>
                    </li>
                  ))}
              </ol>
            </section>
          ))}
          <p className="hint">
            Retrieved{" "}
            {result.retrieved_at
              ? new Date(result.retrieved_at).toLocaleString()
              : ""}
            . Places can change; verify with the venue.
          </p>
        </>
      )}
      <p className="hint">
        <a href="https://www.geoapify.com/" target="_blank" rel="noreferrer">
          Geoapify
        </a>{" "}
        ·{" "}
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          © OpenStreetMap contributors (ODbL)
        </a>
      </p>
    </section>
  );
}
