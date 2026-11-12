/** Local date helpers. Periods are numbered and started by hand, not calendar months. */

import type { Period } from './types';

// Intl constructors are expensive on Hermes: build each formatter once per config.
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let fmt = formatters.get(key);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat(locale, options);
    formatters.set(key, fmt);
  }
  return fmt;
}

/**
 * Today as "YYYY-MM-DD". With `timeZone` (the household's), the calendar day there;
 * otherwise the device's local day.
 */
export function todayIso(timeZone?: string, now: Date = new Date()): string {
  // en-CA formats dates as YYYY-MM-DD.
  return formatter('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).format(now);
}

/** Short day label, e.g. "7 nov". */
export function dayLabel(iso: string, locale: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return formatter(locale, { day: 'numeric', month: 'short' }).format(new Date(y!, m! - 1, d!));
}

/** Short label of an instant in the household time zone, e.g. "7 nov 2026". */
export function instantLabel(iso: string, locale: string, timeZone: string): string {
  return formatter(locale, { day: 'numeric', month: 'short', year: 'numeric', timeZone }).format(
    new Date(iso),
  );
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
