import { parseMoneyToMinorUnits } from "./form";

export const COST_LABELS = {
  transport: "Transport (return journey and local travel)",
  accommodation: "Accommodation (whole stay)",
  activities: "Activities (whole trip)",
  meals: "Meals (whole trip)",
  fees_taxes: "Fees and taxes (not already included)",
} as const;
export type CostCategory = keyof typeof COST_LABELS;
export type EnteredCosts = Record<CostCategory, number | null>;
export type LiveOptions = {
  arrivalTime: string;
  departureTime: string;
  bufferMinutes: string;
  costs: Record<CostCategory, string>;
};
export const INITIAL_LIVE_OPTIONS: LiveOptions = {
  arrivalTime: "",
  departureTime: "",
  bufferMinutes: "60",
  costs: {
    transport: "",
    accommodation: "",
    activities: "",
    meals: "",
    fees_taxes: "",
  },
};
export type LiveInputs = {
  travel_times: {
    arrival_time: string;
    departure_time: string;
    transfer_buffer_minutes: number;
  } | null;
  cost_estimates: EnteredCosts | null;
};

export function toLiveInputs(options: LiveOptions): LiveInputs {
  let travel_times: LiveInputs["travel_times"] = null;
  if (options.arrivalTime || options.departureTime) {
    const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
    if (!clock.test(options.arrivalTime) || !clock.test(options.departureTime))
      throw new Error(
        "Enter both arrival and departure times, or leave both blank.",
      );
    if (
      !/^\d+$/.test(options.bufferMinutes) ||
      Number(options.bufferMinutes) > 240
    )
      throw new Error(
        "Transfer buffer must be a whole number from 0 to 240 minutes.",
      );
    travel_times = {
      arrival_time: options.arrivalTime,
      departure_time: options.departureTime,
      transfer_buffer_minutes: Number(options.bufferMinutes),
    };
  }
  const cost_estimates: EnteredCosts = {
    transport: null,
    accommodation: null,
    activities: null,
    meals: null,
    fees_taxes: null,
  };
  let anyCost = false;
  for (const category of Object.keys(COST_LABELS) as CostCategory[]) {
    const text = options.costs[category].trim();
    if (!text) continue;
    const amount = parseMoneyToMinorUnits(text);
    if (amount === null || amount > 1_000_000_000_000)
      throw new Error(
        `${COST_LABELS[category]}: enter a non-negative amount with at most two decimal places (maximum 10 billion).`,
      );
    cost_estimates[category] = amount;
    anyCost = true;
  }
  return { travel_times, cost_estimates: anyCost ? cost_estimates : null };
}
