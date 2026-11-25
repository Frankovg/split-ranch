import { describe, expect, it } from 'vitest';
import { checkPartialAmount, halfOf } from './settle-amount';

describe('checkPartialAmount', () => {
  it('accepts an amount below what is owed and reports what remains', () => {
    expect(checkPartialAmount(2000, 5000)).toEqual({ ok: true, amountCents: 2000, remainingCents: 3000 });
  });

  it('accepts the full amount, leaving nothing', () => {
    expect(checkPartialAmount(5000, 5000)).toEqual({ ok: true, amountCents: 5000, remainingCents: 0 });
  });

  it('rejects an empty, invalid or zero amount', () => {
    expect(checkPartialAmount(null, 5000)).toEqual({ ok: false, error: 'empty' });
    expect(checkPartialAmount(0, 5000)).toEqual({ ok: false, error: 'empty' });
  });

  it('rejects paying more than what is owed', () => {
    expect(checkPartialAmount(5001, 5000)).toEqual({ ok: false, error: 'tooMuch' });
  });
});

describe('halfOf', () => {
  it('rounds down to the cent', () => {
    expect(halfOf(5000)).toBe(2500);
    expect(halfOf(1001)).toBe(500);
  });
});
