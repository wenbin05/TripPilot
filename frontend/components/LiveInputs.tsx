import {
  COST_LABELS,
  type CostCategory,
  type LiveOptions,
} from "@/lib/live-inputs";

export function LiveInputs({
  options,
  onChange,
  currency,
}: {
  options: LiveOptions;
  onChange: (options: LiveOptions) => void;
  currency: string;
}) {
  return (
    <details className="formSection liveInputs">
      <summary>Travel times and cost estimates (optional)</summary>
      <fieldset className="fieldGrid">
        <legend>Arrival and departure</legend>
        <p className="hint">
          Use destination-local times: arrival on your start date and departure
          on your end date. Both are needed to check the travel window.
        </p>
        <div className="field">
          <label htmlFor="arrivalTime">Arrival time on first day</label>
          <input
            id="arrivalTime"
            type="time"
            value={options.arrivalTime}
            onChange={(e) =>
              onChange({ ...options, arrivalTime: e.target.value })
            }
          />
        </div>
        <div className="field">
          <label htmlFor="departureTime">Departure time on last day</label>
          <input
            id="departureTime"
            type="time"
            value={options.departureTime}
            onChange={(e) =>
              onChange({ ...options, departureTime: e.target.value })
            }
          />
        </div>
        <div className="field">
          <label htmlFor="transferBuffer">
            Transfer buffer each way (minutes)
          </label>
          <input
            id="transferBuffer"
            type="number"
            min="0"
            max="240"
            step="1"
            value={options.bufferMinutes}
            onChange={(e) =>
              onChange({ ...options, bufferMinutes: e.target.value })
            }
            aria-describedby="buffer-hint"
          />
          <p id="buffer-hint" className="hint">
            60 minutes is a starting assumption, not a calculated
            station/airport route. Adjust for your journey. Visits start after
            the arrival buffer and finish before the departure buffer.
          </p>
        </div>
      </fieldset>
      <fieldset className="fieldGrid">
        <legend>Your cost estimates ({currency})</legend>
        <p className="hint">
          Enter category totals for all travellers for the entire trip—not per
          person or per night. These are your estimates, not provider quotes.
          Leave unknown costs blank; enter 0 only when you expect no cost. Avoid
          counting taxes twice.
        </p>
        {(Object.entries(COST_LABELS) as [CostCategory, string][]).map(
          ([category, label]) => (
            <div className="field" key={category}>
              <label htmlFor={`cost-${category}`}>{label}</label>
              <input
                id={`cost-${category}`}
                inputMode="decimal"
                value={options.costs[category]}
                placeholder="Unknown"
                onChange={(e) =>
                  onChange({
                    ...options,
                    costs: { ...options.costs, [category]: e.target.value },
                  })
                }
              />
            </div>
          ),
        )}
      </fieldset>
    </details>
  );
}
