/** Local date helpers. Dates are "YYYY-MM-DD" calendar days in the group's time zone. */

import type { DateRange, Expense } from './types';

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
 * Today as "YYYY-MM-DD". With `timeZone` (the group's), the calendar day there;
 * otherwise the device's local day.
 */
export function todayIso(timeZone?: string, now: Date = new Date()): string {
  // en-CA formats dates as YYYY-MM-DD.
  return formatter('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).format(now);
}

function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split('-').map(Number);
  return [y!, m!, d!];
}

function iso(y: number, m: number, d: number): string {
  return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

/**
 * The calendar month `offset` months from today in the group's time zone, as an
 * inclusive range: 0 = this month, -1 = last month.
 */
export function monthRange(timeZone: string, offset: number, now: Date = new Date()): Required<DateRange> {
  const [y, m] = parts(todayIso(timeZone, now));
  const index = y * 12 + (m - 1) + offset;
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  // Day 0 of the next month is the last day of this one.
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return { from: iso(year, month, 1), to: iso(year, month, last) };
}

/**
 * The calendar year `offset` years from today in the group's time zone, as an
 * inclusive range: 0 = this year, -1 = last year.
 */
export function yearRange(timeZone: string, offset: number, now: Date = new Date()): Required<DateRange> {
  const [y] = parts(todayIso(timeZone, now));
  const year = y + offset;
  return { from: iso(year, 1, 1), to: iso(year, 12, 31) };
}

/** Short day label, e.g. "7 nov". */
export function dayLabel(isoDate: string, locale: string): string {
  const [y, m, d] = parts(isoDate);
  return formatter(locale, { day: 'numeric', month: 'short' }).format(new Date(y, m - 1, d));
}

/** Day header for the expense list, e.g. "viernes, 7 de noviembre de 2026". */
export function dayHeader(isoDate: string, locale: string): string {
  const [y, m, d] = parts(isoDate);
  return formatter(locale, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(
    new Date(y, m - 1, d),
  );
}

/** Month label, e.g. "noviembre de 2026". */
export function monthLabel(isoDate: string, locale: string): string {
  const [y, m] = parts(isoDate);
  return formatter(locale, { month: 'long', year: 'numeric' }).format(new Date(y, m - 1, 1));
}

/** Time of an instant in the group's time zone, e.g. "18:42". */
export function timeLabel(instant: string, locale: string, timeZone: string): string {
  return formatter(locale, { hour: '2-digit', minute: '2-digit', timeZone }).format(new Date(instant));
}

/** Day and time of an instant in the group's time zone, e.g. "18 nov 2026, 18:42". */
export function instantLabel(instant: string, locale: string, timeZone: string): string {
  return formatter(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  }).format(new Date(instant));
}

export interface DaySection {
  day: string;
  data: Expense[];
}

/** Groups expenses (already sorted newest day first) into one section per `expense_date`. */
export function groupByDay(expenses: readonly Expense[]): DaySection[] {
  const sections: DaySection[] = [];
  for (const expense of expenses) {
    const last = sections[sections.length - 1];
    if (last && last.day === expense.expense_date) last.data.push(expense);
    else sections.push({ day: expense.expense_date, data: [expense] });
  }
  return sections;
}
