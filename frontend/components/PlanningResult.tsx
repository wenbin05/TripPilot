import type {
  AccommodationStay,
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

function ConstraintSummary({ request }: { request: NormalizedRequest }) {
  return (
    <section
      className="resultSection"
      aria-labelledby="result-constraints-title"
    >
      <h2 id="result-constraints-title">Your constraints</h2>
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
    </section>
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
        <p>The deterministic validator found no hard-constraint violations.</p>
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

function ScheduledItemCard({
  item,
  timeZone,
}: {
  item: ScheduledItem;
  timeZone: string;
}) {
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
        <p className="eyebrow">
          {humanize(item.kind)}
          {item.transport_role ? ` · ${humanize(item.transport_role)}` : ""}
        </p>
        <h4>{item.title}</h4>
        <dl className="itemMeta">
          <div>
            <dt>Location</dt>
            <dd>{item.location_id ?? "Not supplied"}</dd>
          </div>
          <div>
            <dt>Estimated cost</dt>
            <dd>{formatMoney(item.estimated_cost)}</dd>
          </div>
          {item.source_record_id ? (
            <div>
              <dt>Mock source</dt>
              <dd>{item.source_record_id}</dd>
            </div>
          ) : null}
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
      <dl className="itemMeta">
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
          <dd>{stay.location_id ?? "Not supplied"}</dd>
        </div>
        <div>
          <dt>Estimated cost</dt>
          <dd>{formatMoney(stay.estimated_cost)}</dd>
        </div>
        {stay.source_record_id ? (
          <div>
            <dt>Mock source</dt>
            <dd>{stay.source_record_id}</dd>
          </div>
        ) : null}
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

function DetailList({ title, values }: { title: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <section className="resultSection">
      <h2>{title}</h2>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </section>
  );
}

export function ItineraryResult({ result }: { result: PlanningSuccess }) {
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
    <div className="results" aria-live="polite">
      <header className="resultHeader">
        <p className="eyebrow">Proposed itinerary</p>
        <h1>{result.request.destination}</h1>
        <p>
          Times shown in {timeZone}. Estimates come from fixture{" "}
          {result.fixture_snapshot_version}.
        </p>
      </header>
      <ValidationNotice report={result.validation_report} />
      <ConstraintSummary request={result.request} />
      <div className="resultLayout">
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
          <DetailList
            title="Matched interests"
            values={[result.matched_interests.map(humanize).join(", ")]}
          />
          <DetailList
            title="Planning rationale"
            values={result.planning_rationale}
          />
          <DetailList title="Assumptions" values={result.assumptions} />
          <DetailList title="Warnings" values={result.warnings} />
          {result.proposed_itinerary.non_blocking_markers.length ? (
            <section className="resultSection">
              <h2>Informational markers</h2>
              <ul>
                {result.proposed_itinerary.non_blocking_markers.map(
                  (marker) => (
                    <li key={marker.marker_id}>{marker.title}</li>
                  ),
                )}
              </ul>
            </section>
          ) : null}
        </div>
        <aside className="summaryRail">
          <CostBreakdown
            costs={result.cost_breakdown}
            request={result.request}
          />
          <section className="versionCard" aria-label="Plan versions">
            <h2>Proposal details</h2>
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
          </section>
        </aside>
      </div>
    </div>
  );
}

export function PlanningFailure({ result }: { result: PlanningFailureType }) {
  return (
    <div className="results" aria-live="polite">
      <header className="resultHeader failureHeader">
        <p className="eyebrow">Planning result</p>
        <h1>Could not create a valid plan</h1>
        <p>{result.explanation}</p>
      </header>
      <ValidationNotice report={result.validation_report} />
      <ConstraintSummary request={result.request} />
      {result.relevant_constraints.length ? (
        <section
          className="resultSection"
          aria-labelledby="review-constraints-title"
        >
          <h2 id="review-constraints-title">Constraints to review</h2>
          <p>
            Adjust the form using only the constraints identified by the
            planner:
          </p>
          <ul>
            {result.relevant_constraints.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <DetailList title="Assumptions" values={result.assumptions} />
      <DetailList title="Warnings" values={result.warnings} />
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
