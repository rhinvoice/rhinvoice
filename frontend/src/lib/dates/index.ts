/**
 * Calendar dates as ISO strings ("2026-01-05"). Business dates have no time of
 * day, so all arithmetic happens in UTC to avoid daylight saving surprises.
 */
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_MS = 24 * 3600 * 1000;

function toUtc(isoDate: string): number {
  const match = ISO_DATE.exec(isoDate);
  if (match === null) {
    throw new RangeError(`not an ISO date: ${isoDate}`);
  }
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** Today in the user's time zone. */
export function todayIso(now: Date = new Date()): string {
  return `${String(now.getFullYear())}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Whole days from ``from`` to ``to`` (negative when ``to`` is earlier). */
export function daysBetween(from: string, to: string): number {
  return Math.round((toUtc(to) - toUtc(from)) / DAY_MS);
}

/** The first days of the ``count`` months ending with the month of ``today``, oldest first. */
export function monthWindow(today: string, count: number): string[] {
  const end = new Date(toUtc(today));
  return Array.from({ length: count }, (_, index) => {
    const month = new Date(
      Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - (count - 1 - index), 1),
    );
    return `${String(month.getUTCFullYear())}-${pad(month.getUTCMonth() + 1)}-01`;
  });
}

/** The date ``days`` days after ``isoDate`` (before it when negative). */
export function addDays(isoDate: string, days: number): string {
  const date = new Date(toUtc(isoDate) + days * DAY_MS);
  return `${String(date.getUTCFullYear())}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

/** ISO 8601 week number (weeks start on Monday; week 1 holds the first Thursday). */
export function isoWeek(isoDate: string): number {
  const day = toUtc(isoDate);
  const weekday = (new Date(day).getUTCDay() + 6) % 7;
  // The Thursday of the same week decides the year the week belongs to.
  const thursday = new Date(day + (3 - weekday) * DAY_MS);
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  return Math.floor((thursday.getTime() - yearStart) / DAY_MS / 7) + 1;
}
