import {
  SUPPORTED_CURRENCIES,
  SUPPORTED_PACES,
  type Currency,
  type CoordinatorPlanRequest,
  type Interest,
  type Pace,
  type TripPlanRequest,
} from "./api-types";

export interface FormValues {
  origin: string;
  destination: string;
  startDate: string;
  endDate: string;
  travellers: string;
  budget: string;
  currency: Currency;
  pace: Pace;
  earliestActivityTime: string;
  interests: Interest[];
  coordinatorOptIn: boolean;
  preferenceNotes: string;
}

export type FieldName =
  | Exclude<keyof FormValues, "interests" | "coordinatorOptIn">
  | "interests"
  | "form";
export type FormErrors = Partial<Record<FieldName, string>>;

export const INITIAL_FORM_VALUES: FormValues = {
  origin: "",
  destination: "",
  startDate: "",
  endDate: "",
  travellers: "1",
  budget: "",
  currency: "CAD",
  pace: "balanced",
  earliestActivityTime: "09:00",
  interests: [],
  coordinatorOptIn: false,
  preferenceNotes: "",
};

export function normalizePreferenceNotes(value: string): string | null {
  const normalized = value.normalize("NFC").replace(/[\r\n\t]/gu, " ");
  for (const character of Array.from(normalized)) {
    const codePoint = character.codePointAt(0)!;
    const isUnpairedSurrogate =
      character.length === 1 && codePoint >= 0xd800 && codePoint <= 0xdfff;
    if (
      codePoint <= 0x1f ||
      (codePoint >= 0x7f && codePoint <= 0x9f) ||
      isUnpairedSurrogate ||
      codePoint === 0x061c ||
      (codePoint >= 0x200e && codePoint <= 0x200f) ||
      (codePoint >= 0x202a && codePoint <= 0x202e) ||
      (codePoint >= 0x2066 && codePoint <= 0x2069)
    ) {
      throw new Error("Preference notes contain unsupported characters.");
    }
  }
  const result = normalized
    .replace(/\p{White_Space}+/gu, " ")
    .replace(/^ +| +$/gu, "");
  if (!result) return null;
  if (Array.from(result).length > 300) {
    throw new Error("Preference notes must be 300 characters or fewer.");
  }
  return result;
}

export function preferenceNoteCodePointCount(value: string): number {
  const normalized = value
    .normalize("NFC")
    .replace(/[\r\n\t]/gu, " ")
    .replace(/\p{White_Space}+/gu, " ")
    .replace(/^ +| +$/gu, "");
  return Array.from(normalized).length;
}

export function parseMoneyToMinorUnits(value: string): number | null {
  const normalized = value.trim();
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(normalized);
  if (!match) return null;
  const whole = Number(match[1]);
  const fraction = Number((match[2] ?? "").padEnd(2, "0"));
  if (!Number.isSafeInteger(whole) || !Number.isSafeInteger(fraction))
    return null;
  const amount = whole * 100 + fraction;
  return Number.isSafeInteger(amount) ? amount : null;
}

function validIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export function validateForm(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  const origin = values.origin.trim();
  const destination = values.destination.trim();
  if (!origin) errors.origin = "Enter an origin.";
  if (!destination) errors.destination = "Enter a destination city.";
  if (
    origin &&
    destination &&
    origin.toLocaleLowerCase() === destination.toLocaleLowerCase()
  ) {
    errors.destination = "Origin and destination must differ.";
  }

  if (!validIsoDate(values.startDate))
    errors.startDate = "Enter a valid start date.";
  if (!validIsoDate(values.endDate)) errors.endDate = "Enter a valid end date.";
  if (!errors.startDate && !errors.endDate) {
    const tripDays =
      (Date.parse(`${values.endDate}T00:00:00Z`) -
        Date.parse(`${values.startDate}T00:00:00Z`)) /
        86_400_000 +
      1;
    if (tripDays < 1 || tripDays > 4) {
      errors.endDate =
        "Trip length must be between one and four inclusive days.";
    }
  }

  const travellers = Number(values.travellers);
  if (
    !/^\d+$/.test(values.travellers) ||
    !Number.isInteger(travellers) ||
    travellers < 1 ||
    travellers > 10
  ) {
    errors.travellers = "Travellers must be a whole number between 1 and 10.";
  }
  const budgetMinor = parseMoneyToMinorUnits(values.budget);
  if (budgetMinor === null || budgetMinor <= 0)
    errors.budget = "Enter a positive budget.";
  if (!(SUPPORTED_CURRENCIES as readonly string[]).includes(values.currency)) {
    errors.currency = "Choose a supported currency.";
  }
  if (!(SUPPORTED_PACES as readonly string[]).includes(values.pace)) {
    errors.pace = "Choose a supported travel pace.";
  }
  if (!values.interests.length)
    errors.interests = "Select at least one interest.";
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(values.earliestActivityTime)) {
    errors.earliestActivityTime = "Enter a valid local time.";
  }
  if (values.coordinatorOptIn) {
    try {
      normalizePreferenceNotes(values.preferenceNotes);
    } catch (error) {
      errors.preferenceNotes =
        error instanceof Error
          ? error.message
          : "Check the extra preference notes.";
    }
  }
  return errors;
}

export function toApiRequest(values: FormValues): TripPlanRequest {
  const amountMinor = parseMoneyToMinorUnits(values.budget);
  if (amountMinor === null)
    throw new Error("Form must be validated before building a request.");
  return {
    origin: values.origin.trim(),
    destination: values.destination.trim(),
    start_date: values.startDate,
    end_date: values.endDate,
    travellers: Number(values.travellers),
    total_budget_minor: amountMinor,
    currency: values.currency,
    interests: values.interests,
    pace: values.pace,
    earliest_activity_time: `${values.earliestActivityTime}:00`,
  };
}

export function toCoordinatorApiRequest(
  values: FormValues,
): CoordinatorPlanRequest {
  return {
    ...toApiRequest(values),
    preference_notes: normalizePreferenceNotes(values.preferenceNotes),
  };
}
