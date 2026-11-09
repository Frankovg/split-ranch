/** Local date helpers. Periods are numbered and started by hand, not calendar months. */

import type { Period } from './types';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** Today as "YYYY-MM-DD" in the device's local time zone. */
export function todayIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Short day label, e.g. "7 nov". */
export function dayLabel(iso: string, locale: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y!, m! - 1, d!).toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}

/** Short label of an instant in the household time zone, e.g. "7 nov 2026". */
export function instantLabel(iso: string, locale: string, timeZone: string): string {
  return new Date(iso).toLocaleDateString(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone,
  });
}

/** Dates a period covers: start, and close when it is no longer open. */
export function periodDates(
  period: Pick<Period, 'started_at' | 'closed_at' | 'status'>,
  locale: string,
  timeZone: string,
): { from: string; to: string | null } {
  return {
    from: instantLabel(period.started_at, locale, timeZone),
    to: period.status !== 'open' && period.closed_at ? instantLabel(period.closed_at, locale, timeZone) : null,
  };
}
