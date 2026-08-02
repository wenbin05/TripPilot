import type { Money } from "./api-types";

export function formatMoney(money: Money): string {
  if (!Number.isSafeInteger(money.amount_minor)) return `${money.currency} —`;
  const sign = money.amount_minor < 0 ? "−" : "";
  const absolute = Math.abs(money.amount_minor);
  const whole = Math.floor(absolute / 100).toLocaleString("en-CA");
  const cents = String(absolute % 100).padStart(2, "0");
  return `${sign}${money.currency} ${whole}.${cents}`;
}

export function formatLocalDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat("en-CA", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function destinationDateKey(
  timestamp: string,
  timeZone: string,
): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).format(new Date(timestamp));
}

export function formatDestinationDay(
  timestamp: string,
  timeZone: string,
): string {
  return new Intl.DateTimeFormat("en-CA", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone,
  }).format(new Date(timestamp));
}

export function formatDestinationTime(
  timestamp: string,
  timeZone: string,
): string {
  return new Intl.DateTimeFormat("en-CA", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone,
    timeZoneName: "short",
  }).format(new Date(timestamp));
}

export function humanize(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
