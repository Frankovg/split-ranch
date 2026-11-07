/** Local calendar helpers. Periods are calendar months ("YYYY-MM"). */

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** Today as "YYYY-MM-DD" in the device's local time zone. */
export function todayIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Current month as "YYYY-MM" in the device's local time zone. */
export function currentMonth(now: Date = new Date()): string {
  return todayIso(now).slice(0, 7);
}

/** Display name of a month, e.g. "noviembre de 2026". */
export function monthLabel(month: string, locale: string): string {
  const [y, m] = month.split('-').map(Number);
  return new Date(y!, m! - 1, 1).toLocaleDateString(locale, { month: 'long', year: 'numeric' });
}

/** Short day label, e.g. "7 nov". */
export function dayLabel(iso: string, locale: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y!, m! - 1, d!).toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}
