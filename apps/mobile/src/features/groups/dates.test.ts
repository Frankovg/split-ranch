import { describe, expect, it } from 'vitest';
import { dayLabel, groupByDay, instantLabel, monthRange, todayIso, yearRange } from './dates';
import type { Expense } from './types';

describe('todayIso', () => {
  it('uses the group time zone, not the device one', () => {
    const lateMadrid = new Date('2026-11-30T23:30:00Z'); // 1 Dec 00:30 in Madrid
    expect(todayIso('Europe/Madrid', lateMadrid)).toBe('2026-12-01');
    expect(todayIso('America/New_York', lateMadrid)).toBe('2026-11-30');
  });
});

describe('instantLabel', () => {
  it('shows the day in the group time zone', () => {
    const lateMadrid = '2026-11-30T23:30:00Z'; // 1 Dec 00:30 in Madrid
    expect(instantLabel(lateMadrid, 'en-GB', 'Europe/Madrid')).toContain('1 Dec 2026');
    expect(instantLabel(lateMadrid, 'en-GB', 'America/New_York')).toContain('30 Nov 2026');
  });
});

describe('monthRange', () => {
  const now = new Date('2026-03-15T12:00:00Z');

  it('gives this month and last month as inclusive ranges', () => {
    expect(monthRange('Europe/Madrid', 0, now)).toEqual({ from: '2026-03-01', to: '2026-03-31' });
    expect(monthRange('Europe/Madrid', -1, now)).toEqual({ from: '2026-02-01', to: '2026-02-28' });
  });

  it('crosses year boundaries and leap years', () => {
    const january = new Date('2028-01-10T12:00:00Z');
    expect(monthRange('Europe/Madrid', -1, january)).toEqual({ from: '2027-12-01', to: '2027-12-31' });
    const march = new Date('2028-03-10T12:00:00Z');
    expect(monthRange('Europe/Madrid', -1, march)).toEqual({ from: '2028-02-01', to: '2028-02-29' });
  });

  it('follows the group time zone at month boundaries', () => {
    const lateMadrid = new Date('2026-11-30T23:30:00Z');
    expect(monthRange('Europe/Madrid', 0, lateMadrid).from).toBe('2026-12-01');
    expect(monthRange('America/New_York', 0, lateMadrid).from).toBe('2026-11-01');
  });
});

describe('dayLabel', () => {
  it('formats a calendar day without shifting it', () => {
    expect(dayLabel('2026-11-07', 'en-GB')).toBe('7 Nov');
  });
});

describe('groupByDay', () => {
  const expense = (id: string, day: string) => ({ id, expense_date: day }) as Expense;

  it('makes one section per day, keeping the order', () => {
    const sections = groupByDay([
      expense('a', '2026-03-07'),
      expense('b', '2026-03-07'),
      expense('c', '2026-03-05'),
    ]);
    expect(sections.map((s) => [s.day, s.data.map((e) => e.id)])).toEqual([
      ['2026-03-07', ['a', 'b']],
      ['2026-03-05', ['c']],
    ]);
  });
});

describe('yearRange', () => {
  it('gives whole calendar years in the group time zone', () => {
    const lateMadrid = new Date('2026-12-31T23:30:00Z'); // 1 Jan 2027 00:30 in Madrid
    expect(yearRange('Europe/Madrid', 0, lateMadrid)).toEqual({ from: '2027-01-01', to: '2027-12-31' });
    expect(yearRange('America/New_York', 0, lateMadrid)).toEqual({ from: '2026-01-01', to: '2026-12-31' });
    expect(yearRange('Europe/Madrid', -2, lateMadrid)).toEqual({ from: '2025-01-01', to: '2025-12-31' });
  });
});
