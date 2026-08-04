"use client";

import { useEffect, useRef, useState } from "react";
import { createPlan, ApiRequestError } from "@/lib/api-client";
import {
  SUPPORTED_INTERESTS,
  type Interest,
  type PlanResponse,
} from "@/lib/api-types";
import {
  INITIAL_FORM_VALUES,
  toApiRequest,
  validateForm,
  type FieldName,
  type FormErrors,
  type FormValues,
} from "@/lib/form";
import { formatLocalDate, humanize } from "@/lib/format";
import { EstimateBanner } from "./EstimateBanner";
import { ItineraryResult, PlanningFailure } from "./PlanningResult";

const PACE_DESCRIPTIONS = {
  relaxed: "Usually 1–2 primary activities on a full day",
  balanced: "Usually 2–3 primary activities on a full day",
  packed: "Usually 3–4 primary activities on a full day",
};

const API_TO_FORM_FIELD: Record<string, FieldName> = {
  origin: "origin",
  destination: "destination",
  start_date: "startDate",
  end_date: "endDate",
  travellers: "travellers",
  total_budget_minor: "budget",
  currency: "currency",
  interests: "interests",
  pace: "pace",
  earliest_activity_time: "earliestActivityTime",
};

const SAFE_BACKEND_MESSAGES: Partial<Record<FieldName, string>> = {
  origin: "The backend rejected the origin.",
  destination: "The backend rejected the destination city.",
  startDate: "The backend rejected the start date.",
  endDate: "The backend rejected the date range.",
  travellers: "The backend requires 1–10 travellers.",
  budget: "The backend requires a positive budget.",
  currency: "The backend rejected this currency.",
  interests: "The backend requires supported interests.",
  pace: "The backend rejected this travel pace.",
  earliestActivityTime: "The backend rejected this local time.",
};

function describedBy(
  field: FieldName,
  errors: FormErrors,
  hint?: string,
): string | undefined {
  return (
    [hint, errors[field] ? `${field}-error` : undefined]
      .filter(Boolean)
      .join(" ") || undefined
  );
}

function FieldError({
  field,
  errors,
}: {
  field: FieldName;
  errors: FormErrors;
}) {
  return errors[field] ? (
    <p className="fieldError" id={`${field}-error`}>
      {errors[field]}
    </p>
  ) : null;
}

export function TripPlanner() {
  const [values, setValues] = useState<FormValues>(INITIAL_FORM_VALUES);
  const [errors, setErrors] = useState<FormErrors>({});
  const [status, setStatus] = useState<"idle" | "loading" | "unexpected">(
    "idle",
  );
  const [result, setResult] = useState<PlanResponse | null>(null);
  const [errorFocusRequest, setErrorFocusRequest] = useState(0);
  const errorSummaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (errorFocusRequest > 0) errorSummaryRef.current?.focus();
  }, [errorFocusRequest]);

  function update<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({
      ...current,
      [field]: undefined,
      form: undefined,
    }));
  }

  function toggleInterest(interest: Interest) {
    update(
      "interests",
      values.interests.includes(interest)
        ? values.interests.filter((value) => value !== interest)
        : [...values.interests, interest],
    );
  }

  function focusErrors() {
    setErrorFocusRequest((current) => current + 1);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clientErrors = validateForm(values);
    if (Object.keys(clientErrors).length) {
      setErrors(clientErrors);
      setStatus("idle");
      focusErrors();
      return;
    }

    setErrors({});
    setResult(null);
    setStatus("loading");
    try {
      const response = await createPlan(toApiRequest(values));
      setResult(response);
      setStatus("idle");
    } catch (error) {
      if (
        error instanceof ApiRequestError &&
        error.kind === "validation" &&
        error.validation
      ) {
        const backendErrors: FormErrors = {};
        for (const detail of error.validation.details) {
          const apiField = detail.location.find(
            (part): part is string => typeof part === "string",
          );
          const field = apiField ? API_TO_FORM_FIELD[apiField] : undefined;
          if (field) backendErrors[field] = SAFE_BACKEND_MESSAGES[field];
          else
            backendErrors.form =
              "The backend rejected this combination of trip details.";
        }
        if (!Object.keys(backendErrors).length)
          backendErrors.form = "The backend rejected the trip details.";
        setErrors(backendErrors);
        setStatus("idle");
        focusErrors();
      } else {
        setStatus("unexpected");
      }
    }
  }

  const errorEntries = Object.entries(errors).filter(
    (entry): entry is [FieldName, string] => Boolean(entry[1]),
  );

  return (
    <>
      <div className="siteHeader">
        <a className="brand" href="#planner">
          TripPilot
        </a>
        <span>Deterministic student trip planner</span>
      </div>
      <EstimateBanner />
      <div className="plannerShell" id="planner">
        <header className="hero">
          <p className="eyebrow">One city · One to four days</p>
          <h1>Plan around what matters.</h1>
          <p>
            Set the essentials once. TripPilot builds a clear, budget-aware
            proposal and checks every hard constraint.
          </p>
        </header>

        <form
          className="plannerForm"
          onSubmit={submit}
          noValidate
          aria-busy={status === "loading"}
        >
          {errorEntries.length ? (
            <div
              className="errorSummary"
              role="alert"
              tabIndex={-1}
              ref={errorSummaryRef}
            >
              <h2>Check your trip details</h2>
              <p>
                Fix the following{" "}
                {errorEntries.length === 1 ? "issue" : "issues"}:
              </p>
              <ul>
                {errorEntries.map(([field, message]) => (
                  <li key={field}>
                    {field === "form" ? (
                      message
                    ) : (
                      <a href={`#${field}`}>{message}</a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="plannerFormLayout">
            <div className="plannerFields">
              <section
                className="formSection"
                aria-labelledby="trip-details-title"
              >
                <div className="sectionHeading">
                  <span>1</span>
                  <div>
                    <h2 id="trip-details-title">Trip details</h2>
                    <p>
                      Plain place labels only—there is no live autocomplete.
                    </p>
                  </div>
                </div>
                <div className="fieldGrid">
                  <div className="field">
                    <label htmlFor="origin">Origin</label>
                    <input
                      id="origin"
                      value={values.origin}
                      onChange={(event) => update("origin", event.target.value)}
                      aria-invalid={Boolean(errors.origin)}
                      aria-describedby={describedBy(
                        "origin",
                        errors,
                        "origin-hint",
                      )}
                      placeholder="Kingston, Ontario"
                    />
                    <p className="hint" id="origin-hint">
                      Where the trip starts and returns.
                    </p>
                    <FieldError field="origin" errors={errors} />
                  </div>
                  <div className="field">
                    <label htmlFor="destination">Destination city</label>
                    <input
                      id="destination"
                      value={values.destination}
                      onChange={(event) =>
                        update("destination", event.target.value)
                      }
                      aria-invalid={Boolean(errors.destination)}
                      aria-describedby={describedBy(
                        "destination",
                        errors,
                        "destination-hint",
                      )}
                      placeholder="Toronto, Ontario"
                    />
                    <p className="hint" id="destination-hint">
                      Exactly one destination city.
                    </p>
                    <FieldError field="destination" errors={errors} />
                  </div>
                  <div className="field">
                    <label htmlFor="startDate">Start date</label>
                    <input
                      id="startDate"
                      type="date"
                      value={values.startDate}
                      onChange={(event) =>
                        update("startDate", event.target.value)
                      }
                      aria-invalid={Boolean(errors.startDate)}
                      aria-describedby={describedBy(
                        "startDate",
                        errors,
                        "date-hint",
                      )}
                    />
                    <p className="hint" id="date-hint">
                      Dates are inclusive at the destination.
                    </p>
                    <FieldError field="startDate" errors={errors} />
                  </div>
                  <div className="field">
                    <label htmlFor="endDate">End date</label>
                    <input
                      id="endDate"
                      type="date"
                      value={values.endDate}
                      onChange={(event) =>
                        update("endDate", event.target.value)
                      }
                      aria-invalid={Boolean(errors.endDate)}
                      aria-describedby={describedBy(
                        "endDate",
                        errors,
                        "end-date-hint",
                      )}
                    />
                    <p className="hint" id="end-date-hint">
                      One to four days including both dates.
                    </p>
                    <FieldError field="endDate" errors={errors} />
                  </div>
                  <div className="field fieldNarrow">
                    <label htmlFor="travellers">Number of travellers</label>
                    <input
                      id="travellers"
                      type="number"
                      min="1"
                      max="10"
                      step="1"
                      inputMode="numeric"
                      value={values.travellers}
                      onChange={(event) =>
                        update("travellers", event.target.value)
                      }
                      aria-invalid={Boolean(errors.travellers)}
                      aria-describedby={describedBy(
                        "travellers",
                        errors,
                        "travellers-hint",
                      )}
                    />
                    <p className="hint" id="travellers-hint">
                      Between 1 and 10.
                    </p>
                    <FieldError field="travellers" errors={errors} />
                  </div>
                </div>
              </section>

              <section
                className="formSection"
                aria-labelledby="constraints-title"
              >
                <div className="sectionHeading">
                  <span>2</span>
                  <div>
                    <h2 id="constraints-title">Constraints</h2>
                    <p>The budget is the estimated total for all travellers.</p>
                  </div>
                </div>
                <div className="fieldGrid">
                  <div className="field moneyField">
                    <label htmlFor="budget">Total budget</label>
                    <div className="moneyControls">
                      <input
                        id="budget"
                        inputMode="decimal"
                        value={values.budget}
                        onChange={(event) =>
                          update("budget", event.target.value)
                        }
                        aria-invalid={Boolean(errors.budget)}
                        aria-describedby={describedBy(
                          "budget",
                          errors,
                          "budget-hint",
                        )}
                        placeholder="250.00"
                      />
                      <select
                        id="currency"
                        aria-label="Currency"
                        value={values.currency}
                        onChange={(event) =>
                          update(
                            "currency",
                            event.target.value as FormValues["currency"],
                          )
                        }
                        aria-invalid={Boolean(errors.currency)}
                        aria-describedby={describedBy("currency", errors)}
                      >
                        <option value="CAD">CAD</option>
                        <option value="USD">USD</option>
                      </select>
                    </div>
                    <p className="hint" id="budget-hint">
                      Include transport, stay, activities, meals, fees, and
                      taxes.
                    </p>
                    <FieldError field="budget" errors={errors} />
                    <FieldError field="currency" errors={errors} />
                  </div>
                  <fieldset
                    className="field paceField"
                    aria-describedby={errors.pace ? "pace-error" : "pace-hint"}
                  >
                    <legend>Travel pace</legend>
                    <p className="hint" id="pace-hint">
                      A planning target, not a hard validity rule.
                    </p>
                    <div className="paceOptions">
                      {(["relaxed", "balanced", "packed"] as const).map(
                        (pace) => (
                          <label className="radioOption" key={pace}>
                            <input
                              id={pace === values.pace ? "pace" : undefined}
                              type="radio"
                              name="pace"
                              value={pace}
                              checked={values.pace === pace}
                              onChange={() => update("pace", pace)}
                            />
                            <span>
                              <strong>{humanize(pace)}</strong>
                              <small>{PACE_DESCRIPTIONS[pace]}</small>
                            </span>
                          </label>
                        ),
                      )}
                    </div>
                    <FieldError field="pace" errors={errors} />
                  </fieldset>
                  <div className="field fieldNarrow">
                    <label htmlFor="earliestActivityTime">
                      Earliest acceptable activity time
                    </label>
                    <input
                      id="earliestActivityTime"
                      type="time"
                      value={values.earliestActivityTime}
                      onChange={(event) =>
                        update("earliestActivityTime", event.target.value)
                      }
                      aria-invalid={Boolean(errors.earliestActivityTime)}
                      aria-describedby={describedBy(
                        "earliestActivityTime",
                        errors,
                        "time-hint",
                      )}
                    />
                    <p className="hint" id="time-hint">
                      Local wall-clock time at the destination.
                    </p>
                    <FieldError field="earliestActivityTime" errors={errors} />
                  </div>
                </div>
              </section>

              <section
                className="formSection"
                aria-labelledby="interests-title"
              >
                <div className="sectionHeading">
                  <span>3</span>
                  <div>
                    <h2 id="interests-title">Interests</h2>
                    <p>
                      Select at least one. Use Tab to move and Space to toggle.
                    </p>
                  </div>
                </div>
                <fieldset
                  className="interestField"
                  aria-invalid={Boolean(errors.interests)}
                  aria-describedby={
                    errors.interests ? "interests-error" : undefined
                  }
                >
                  <legend className="srOnly">Trip interests</legend>
                  <div className="interestGrid">
                    {SUPPORTED_INTERESTS.map((interest) => (
                      <label className="interestOption" key={interest}>
                        <input
                          id={interest === "food" ? "interests" : undefined}
                          type="checkbox"
                          checked={values.interests.includes(interest)}
                          onChange={() => toggleInterest(interest)}
                        />
                        <span>{humanize(interest)}</span>
                      </label>
                    ))}
                  </div>
                  <FieldError field="interests" errors={errors} />
                </fieldset>
              </section>
            </div>

            <section className="reviewSection" aria-labelledby="review-title">
              <div className="sectionHeading">
                <span>4</span>
                <div>
                  <h2 id="review-title">Review and submit</h2>
                  <p>One clear proposal. Nothing is booked.</p>
                </div>
              </div>
              <dl className="reviewGrid">
                <div>
                  <dt>Route</dt>
                  <dd>
                    {values.origin.trim() || "Not entered"} →{" "}
                    {values.destination.trim() || "Not entered"}
                  </dd>
                </div>
                <div>
                  <dt>Dates</dt>
                  <dd>
                    {values.startDate
                      ? formatLocalDate(values.startDate)
                      : "Not entered"}{" "}
                    –{" "}
                    {values.endDate
                      ? formatLocalDate(values.endDate)
                      : "Not entered"}
                  </dd>
                </div>
                <div>
                  <dt>Travellers</dt>
                  <dd>{values.travellers || "Not entered"}</dd>
                </div>
                <div>
                  <dt>Budget</dt>
                  <dd>
                    {values.currency} {values.budget || "Not entered"}
                  </dd>
                </div>
                <div>
                  <dt>Pace / earliest time</dt>
                  <dd>
                    {humanize(values.pace)} ·{" "}
                    {values.earliestActivityTime || "Not entered"}
                  </dd>
                </div>
                <div>
                  <dt>Interests</dt>
                  <dd>
                    {values.interests.length
                      ? values.interests.map(humanize).join(", ")
                      : "None selected"}
                  </dd>
                </div>
              </dl>
              <button
                className="primaryButton"
                type="submit"
                disabled={status === "loading"}
              >
                Create proposed itinerary
              </button>
            </section>
          </div>
        </form>

        <div className="planningStatus" aria-live="polite" aria-atomic="true">
          {status === "loading" ? (
            <div className="loadingCard" role="status">
              <span className="spinner" aria-hidden="true" />
              <div>
                <h2>Creating your proposal</h2>
                <p>Checking your trip details, timing, and estimated costs…</p>
              </div>
            </div>
          ) : null}
          {status === "unexpected" ? (
            <div className="unexpectedError" role="alert">
              <h2>Proposal unavailable</h2>
              <p>
                TripPilot could not create a proposal right now. Please try
                again.
              </p>
            </div>
          ) : null}
        </div>
      </div>
      {result?.status === "success" ? (
        <ItineraryResult result={result} />
      ) : null}
      {result?.status === "planning_failure" ? (
        <PlanningFailure result={result} />
      ) : null}
      <footer>
        <p>
          TripPilot MVP · Offline mock travel data · No accounts, payments, or
          booking actions
        </p>
      </footer>
    </>
  );
}
