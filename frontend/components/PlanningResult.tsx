"use client";

import { useEffect, useRef } from "react";
import type {
  AccommodationStay,
  CoordinatorExperiment,
  CostBreakdown as CostBreakdownType,
  NormalizedRequest,
  PlanningFailure as PlanningFailureType,
  PlanningSuccess,
  ScheduledItem,
  ValidationReport,
} from "@/lib/api-types";
import {
  destinationDateKey,
  formatDestinationDay,
  formatDestinationTime,
  formatLocalDate,
  formatMoney,
  humanize,
} from "@/lib/format";

function tripDayCount(request: NormalizedRequest): number {
  const [startYear, startMonth, startDay] = request.start_date
    .split("-")
    .map(Number);
  const [endYear, endMonth, endDay] = request.end_date.split("-").map(Number);
  return (
    Math.round(
      (Date.UTC(endYear, endMonth - 1, endDay) -
        Date.UTC(startYear, startMonth - 1, startDay)) /
        86_400_000,
    ) + 1
  );
}

function useResultHeadingFocus() {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);
  return headingRef;
}

function ConstraintSummary({ request }: { request: NormalizedRequest }) {
  return (
    <details className="technicalDetails constraintDetails">
      <summary>Trip details and preferences</summary>
      <dl className="summaryGrid">
        <div>
          <dt>Route</dt>
          <dd>
            {request.origin} → {request.destination}
          </dd>
        </div>
        <div>
          <dt>Dates</dt>
          <dd>
            {formatLocalDate(request.start_date)} –{" "}
            {formatLocalDate(request.end_date)}
          </dd>
        </div>
        <div>
          <dt>Travellers</dt>
          <dd>{request.travellers}</dd>
        </div>
        <div>
          <dt>All-in budget</dt>
          <dd>{formatMoney(request.budget)}</dd>
        </div>
        <div>
          <dt>Pace</dt>
          <dd>{humanize(request.pace)}</dd>
        </div>
        <div>
          <dt>Earliest activity</dt>
          <dd>
            {request.earliest_activity_time.slice(0, 5)} destination-local time
          </dd>
        </div>
        <div className="summaryWide">
          <dt>Interests</dt>
          <dd>{request.interests.map(humanize).join(", ")}</dd>
        </div>
      </dl>
    </details>
  );
}

function ValidationNotice({ report }: { report: ValidationReport }) {
  return (
    <section
      className={
        report.is_valid ? "validationNotice valid" : "validationNotice invalid"
      }
      aria-labelledby="validation-title"
    >
      <h2 id="validation-title">
        <span aria-hidden="true">{report.is_valid ? "✓" : "!"}</span>{" "}
        {report.is_valid
          ? "Constraints validated"
          : "Could not create a valid plan"}
      </h2>
      {report.is_valid ? (
        <p>
          Hard checks passed. Prices and availability remain estimates, and
          nothing has been booked.
        </p>
      ) : report.violations.length ? (
        <ul>
          {report.violations.map((violation) => (
            <li key={`${violation.code}-${violation.affected_ids.join("-")}`}>
              {violation.message}{" "}
              <span className="technicalCode">{violation.code}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>No validator-clean proposal was available for these constraints.</p>
      )}
    </section>
  );
}

function PlanningApproach({
  experiment,
}: {
  experiment?: CoordinatorExperiment;
}) {
  const label = !experiment
    ? "Standard"
    : experiment.approach === "coordinator_assisted"
      ? "Coordinator-assisted experiment"
      : "Deterministic fallback";
  const description = !experiment
    ? "Selected by TripPilot’s deterministic planner."
    : experiment.approach === "coordinator_assisted"
      ? "A coordinator ranked canonical, validator-clean proposals."
      : "TripPilot selected a validator-clean proposal deterministically.";
  return (
    <aside className="approachNotice" aria-label="Planning approach">
      <strong>Planning approach: {label}</strong>
      <p>{description}</p>
    </aside>
  );
}

function ResultAtAGlance({ result }: { result: PlanningSuccess }) {
  const remaining =
    result.request.budget.amount_minor -
    result.cost_breakdown.total_estimated_cost.amount_minor;
  const days = tripDayCount(result.request);
  return (
    <section className="resultAtGlance" aria-labelledby="glance-title">
      <h2 id="glance-title">Plan at a glance</h2>
      <dl>
        <div>
          <dt>Constraints</dt>
          <dd>
            <span aria-hidden="true">✓</span> Passed
          </dd>
        </div>
        <div>
          <dt>Trip length</dt>
          <dd>
            {days} {days === 1 ? "day" : "days"}
          </dd>
        </div>
        <div>
          <dt>Estimated total</dt>
          <dd>{formatMoney(result.cost_breakdown.total_estimated_cost)}</dd>
        </div>
        <div>
          <dt>Remaining budget</dt>
          <dd>
            {formatMoney({
              amount_minor: remaining,
              currency: result.request.budget.currency,
            })}
          </dd>
        </div>
      </dl>
      <p>
        <strong>Constraints validated.</strong> Hard checks passed; prices and
        availability remain estimates, and nothing has been booked.
      </p>
    </section>
  );
}

function ResultDisclosure({ disclosures }: { disclosures: string[] }) {
  return (
    <aside className="resultDisclosure" aria-label="Proposal disclosure">
      <span aria-hidden="true">ⓘ</span>
      <div>
        <strong>Mock data · Proposed trip only</strong>
        <p>{disclosures.join(" ")}</p>
      </div>
    </aside>
  );
}

function ScheduledItemCard({
  item,
  timeZone,
}: {
  item: ScheduledItem;
  timeZone: string;
}) {
  const icon =
    item.kind === "transport" ? "→" : item.kind === "meal" ? "●" : "◆";
  return (
    <article className="timelineItem">
      <div className="timeRange">
        <time dateTime={item.window.start}>
          {formatDestinationTime(item.window.start, timeZone)}
        </time>
        <span aria-hidden="true">–</span>
        <time dateTime={item.window.end}>
          {formatDestinationTime(item.window.end, timeZone)}
        </time>
      </div>
      <div>
        <p className={`itemKind itemKind-${item.kind}`}>
          <span aria-hidden="true">{icon}</span> {humanize(item.kind)}
          {item.transport_role ? ` · ${humanize(item.transport_role)}` : ""}
        </p>
        <h4>{item.title}</h4>
        <dl className="itemSummary">
          <div>
            <dt>Location</dt>
            <dd>{item.location_label ?? "Not supplied"}</dd>
          </div>
          <div>
            <dt>Estimated cost</dt>
            <dd>{formatMoney(item.estimated_cost)}</dd>
          </div>
        </dl>
      </div>
    </article>
  );
}

function AccommodationCard({
  stay,
  timeZone,
}: {
  stay: AccommodationStay;
  timeZone: string;
}) {
  return (
    <article className="accommodationCard">
      <div>
        <p className="eyebrow">Non-time-blocking stay</p>
        <h3>{stay.title}</h3>
      </div>
      <dl className="itemSummary">
        <div>
          <dt>Stay</dt>
          <dd>
            {stay.number_of_nights} night
            {stay.number_of_nights === 1 ? "" : "s"}
          </dd>
        </div>
        <div>
          <dt>Check-in / check-out</dt>
          <dd>
            {formatDestinationTime(stay.check_in, timeZone)} /{" "}
            {formatDestinationTime(stay.check_out, timeZone)}
          </dd>
        </div>
        <div>
          <dt>Location</dt>
          <dd>{stay.location_label ?? "Not supplied"}</dd>
        </div>
        <div>
          <dt>Estimated cost</dt>
          <dd>{formatMoney(stay.estimated_cost)}</dd>
        </div>
      </dl>
      <p className="nonBlockingNote">
        Shown separately; this stay does not block activity time.
      </p>
    </article>
  );
}

function CostBreakdown({
  costs,
  request,
}: {
  costs: CostBreakdownType;
  request: NormalizedRequest;
}) {
  const categories: Array<
    [string, keyof Omit<CostBreakdownType, "total_estimated_cost">]
  > = [
    ["Transport", "transport"],
    ["Accommodation", "accommodation"],
    ["Activities", "activity"],
    ["Meals", "meal"],
    ["Fees & taxes", "fees_taxes"],
  ];
  const remaining =
    request.budget.amount_minor - costs.total_estimated_cost.amount_minor;
  return (
    <section className="costCard" aria-labelledby="cost-title">
      <h2 id="cost-title">Cost breakdown</h2>
      <dl>
        {categories.map(([label, key]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{formatMoney(costs[key])}</dd>
          </div>
        ))}
        <div className="costTotal">
          <dt>Estimated total</dt>
          <dd>{formatMoney(costs.total_estimated_cost)}</dd>
        </div>
        <div>
          <dt>All-in budget</dt>
          <dd>{formatMoney(request.budget)}</dd>
        </div>
        <div>
          <dt>Remaining budget</dt>
          <dd>
            {formatMoney({
              amount_minor: remaining,
              currency: request.budget.currency,
            })}
          </dd>
        </div>
      </dl>
      <p>
        For all {request.travellers} traveller
        {request.travellers === 1 ? "" : "s"}.
      </p>
    </section>
  );
}

function VisibleWarnings({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <section className="warningList" aria-labelledby="warnings-title">
      <h2 id="warnings-title">Warnings and verification</h2>
      <ul>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </section>
  );
}

function ExpandableDetailList({
  title,
  values,
}: {
  title: string;
  values: string[];
}) {
  if (!values.length || values.every((value) => !value)) return null;
  return (
    <details className="technicalDetails">
      <summary>{title}</summary>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </details>
  );
}

function ProvenanceDetails({ result }: { result: PlanningSuccess }) {
  const sourced = [
    ...result.proposed_itinerary.scheduled_items.map((item) => ({
      key: item.item_id,
      title: item.title,
      label: item.location_label,
      locationId: item.location_id,
      sourceId: item.source_record_id,
    })),
    ...result.proposed_itinerary.accommodation_stays.map((stay) => ({
      key: stay.stay_id,
      title: stay.title,
      label: stay.location_label,
      locationId: stay.location_id,
      sourceId: stay.source_record_id,
    })),
  ];
  return (
    <details className="technicalDetails provenanceDetails">
      <summary>Sources and technical details</summary>
      <ul className="provenanceList">
        {sourced.map((item) => (
          <li key={item.key}>
            <strong>{item.title}</strong>
            <dl>
              <div>
                <dt>Location</dt>
                <dd>{item.label ?? "Not supplied"}</dd>
              </div>
              <div>
                <dt>Location ID</dt>
                <dd>{item.locationId ?? "Not supplied"}</dd>
              </div>
              <div>
                <dt>Mock source</dt>
                <dd>{item.sourceId ?? "Not supplied"}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
      <dl>
        <div>
          <dt>Fixture snapshot</dt>
          <dd>{result.fixture_snapshot_version}</dd>
        </div>
        <div>
          <dt>Planner</dt>
          <dd>{result.planner_id}</dd>
        </div>
      </dl>
    </details>
  );
}

export function ItineraryResult({
  result,
}: {
  result: PlanningSuccess & { experiment?: CoordinatorExperiment };
}) {
  const headingRef = useResultHeadingFocus();
  const timeZone = result.request.destination_timezone ?? "UTC";
  const ordered = [...result.proposed_itinerary.scheduled_items].sort(
    (left, right) =>
      Date.parse(left.window.start) - Date.parse(right.window.start),
  );
  const grouped = new Map<string, ScheduledItem[]>();
  for (const item of ordered) {
    const key = destinationDateKey(item.window.start, timeZone);
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }

  return (
    <div className="results">
      <p className="srOnly" role="status">
        Proposed itinerary ready for {result.request.destination}.
      </p>
      <header className="resultHeader">
        <p className="eyebrow">Proposed itinerary</p>
        <h1 ref={headingRef} tabIndex={-1}>
          {result.request.destination}
        </h1>
        <p className="resultContext">
          {result.request.origin} → {result.request.destination} ·{" "}
          {formatLocalDate(result.request.start_date)} –{" "}
          {formatLocalDate(result.request.end_date)} · Times shown in {timeZone}
        </p>
      </header>
      <PlanningApproach experiment={result.experiment} />
      <ResultAtAGlance result={result} />
      <ResultDisclosure disclosures={result.disclosures} />
      <VisibleWarnings warnings={result.warnings} />
      <div className="resultLayout">
        <aside className="summaryRail">
          <CostBreakdown
            costs={result.cost_breakdown}
            request={result.request}
          />
        </aside>
        <div className="itineraryColumn">
          <section aria-labelledby="daily-plan-title">
            <h2 id="daily-plan-title">Day-by-day plan</h2>
            <div className="dayList">
              {[...grouped.entries()].map(([day, items], index) => (
                <article className="dayCard" key={day}>
                  <header>
                    <p>Day {index + 1}</p>
                    <h3>
                      {formatDestinationDay(items[0].window.start, timeZone)}
                    </h3>
                  </header>
                  <div className="timeline">
                    {items.map((item) => (
                      <ScheduledItemCard
                        key={item.item_id}
                        item={item}
                        timeZone={timeZone}
                      />
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
          {result.proposed_itinerary.accommodation_stays.length ? (
            <section aria-labelledby="stays-title">
              <h2 id="stays-title">Accommodation</h2>
              <div className="stayList">
                {result.proposed_itinerary.accommodation_stays.map((stay) => (
                  <AccommodationCard
                    key={stay.stay_id}
                    stay={stay}
                    timeZone={timeZone}
                  />
                ))}
              </div>
            </section>
          ) : null}
          <ExpandableDetailList
            title="Why this plan"
            values={result.planning_rationale}
          />
          <ExpandableDetailList
            title="Matched interests"
            values={
              result.matched_interests.length
                ? [result.matched_interests.map(humanize).join(", ")]
                : []
            }
          />
          <ExpandableDetailList
            title="Assumptions"
            values={result.assumptions}
          />
          {result.proposed_itinerary.non_blocking_markers.length ? (
            <ExpandableDetailList
              title="Informational markers"
              values={result.proposed_itinerary.non_blocking_markers.map(
                (marker) => marker.title,
              )}
            />
          ) : null}
          <ConstraintSummary request={result.request} />
          <ProvenanceDetails result={result} />
        </div>
      </div>
    </div>
  );
}

export function PlanningFailure({
  result,
}: {
  result: PlanningFailureType & { experiment?: CoordinatorExperiment };
}) {
  const headingRef = useResultHeadingFocus();
  return (
    <div className="results">
      <p className="srOnly" role="status">
        TripPilot could not create a valid plan.
      </p>
      <header className="resultHeader failureHeader">
        <p className="eyebrow">Planning result</p>
        <h1 ref={headingRef} tabIndex={-1}>
          Could not create a valid plan
        </h1>
        <p>{result.explanation}</p>
      </header>
      <PlanningApproach experiment={result.experiment} />
      <ResultDisclosure disclosures={result.disclosures} />
      <ValidationNotice report={result.validation_report} />
      <VisibleWarnings warnings={result.warnings} />
      {result.relevant_constraints.length ? (
        <section
          className="resultSection"
          aria-labelledby="review-constraints-title"
        >
          <h2 id="review-constraints-title">Constraints to review</h2>
          <p>Adjust only the constraints identified by the planner:</p>
          <ul>
            {result.relevant_constraints.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <ConstraintSummary request={result.request} />
      <ExpandableDetailList title="Assumptions" values={result.assumptions} />
      <details className="technicalDetails">
        <summary>Technical details</summary>
        <dl>
          <div>
            <dt>Failure code</dt>
            <dd>{result.failure_code}</dd>
          </div>
          <div>
            <dt>Fixture snapshot</dt>
            <dd>{result.fixture_snapshot_version ?? "Not available"}</dd>
          </div>
          <div>
            <dt>Planner</dt>
            <dd>{result.planner_id}</dd>
          </div>
        </dl>
      </details>
    </div>
  );
}
