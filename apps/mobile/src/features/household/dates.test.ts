import { describe, expect, it } from 'vitest';
import { dayLabel, periodDates, todayIso } from './dates';

describe('todayIso', () => {
  // 23:30 UTC on the 12th is already the 13th in Madrid (UTC+1) and still the 12th in Buenos Aires.
  const lateUtc = new Date('2026-11-12T23:30:00Z');

  it('uses the given time zone, not the device one', () => {
    expect(todayIso('Europe/Madrid', lateUtc)).toBe('2026-11-13');
    expect(todayIso('America/Argentina/Buenos_Aires', lateUtc)).toBe('2026-11-12');
    expect(todayIso('UTC', lateUtc)).toBe('2026-11-12');
  });

  it('formats as YYYY-MM-DD with zero padding', () => {
    expect(todayIso('UTC', new Date('2026-01-05T12:00:00Z'))).toBe('2026-01-05');
  });
});

describe('cached formatters', () => {
  it('return stable output across calls and configs', () => {
    expect(dayLabel('2026-11-07', 'en-IE')).toBe(dayLabel('2026-11-07', 'en-IE'));
    const period = { started_at: '2026-11-01T10:00:00Z', closed_at: null, status: 'open' as const };
    const madrid = periodDates(period, 'en-IE', 'Europe/Madrid');
    const tokyo = periodDates(period, 'en-IE', 'Asia/Tokyo');
    expect(madrid.to).toBeNull();
    // Different time zones must not share a cached formatter.
    expect(periodDates({ ...period, started_at: '2026-11-01T20:00:00Z' }, 'en-IE', 'Asia/Tokyo').from).not.toBe(
      periodDates({ ...period, started_at: '2026-11-01T20:00:00Z' }, 'en-IE', 'Europe/Madrid').from,
    );
    expect(tokyo.from).toBe(madrid.from);
  });
});
