import { describe, expect, it } from 'vitest';
import {
  equalValues,
  initialSplitState,
  previewShares,
  rebalance,
  splitProblem,
  toSplitSpec,
} from './split-form';

describe('equalValues', () => {
  it('splits evenly and gives leftover cents to the first members', () => {
    expect(equalValues(5000, ['a', 'b'])).toEqual({ a: 2500, b: 2500 });
    expect(equalValues(1000, ['a', 'b', 'c'])).toEqual({ a: 334, b: 333, c: 333 });
  });

  it('never goes negative', () => {
    expect(equalValues(-10, ['a', 'b'])).toEqual({ a: 0, b: 0 });
  });
});

describe('rebalance', () => {
  it('gives the remainder to the other member (50 total, 40 typed)', () => {
    const r = rebalance({ a: 2500, b: 2500 }, ['a', 'b'], [], 'a', 4000, 5000);
    expect(r.values).toEqual({ a: 4000, b: 1000 });
    expect(r.locked).toEqual(['a']);
  });

  it('frees the oldest typed member when everyone has been typed', () => {
    const first = rebalance({ a: 2500, b: 2500 }, ['a', 'b'], [], 'a', 4000, 5000);
    const second = rebalance(first.values, ['a', 'b'], first.locked, 'b', 3000, 5000);
    expect(second.values).toEqual({ a: 2000, b: 3000 });
    expect(second.locked).toEqual(['b']);
  });

  it('spreads the remainder over the untyped members', () => {
    const r = rebalance(equalValues(9000, ['a', 'b', 'c']), ['a', 'b', 'c'], [], 'a', 5000, 9000);
    expect(r.values).toEqual({ a: 5000, b: 2000, c: 2000 });
  });

  it('leaves the others at zero when the typed value exceeds the total', () => {
    const r = rebalance({ a: 2500, b: 2500 }, ['a', 'b'], [], 'a', 6000, 5000);
    expect(r.values).toEqual({ a: 6000, b: 0 });
  });
});

describe('split spec and validation', () => {
  it('percentages must add up to 100 %', () => {
    const state = { ...initialSplitState(5000, ['a', 'b']), mode: 'parts' as const, percents: { a: 7000, b: 2000 } };
    expect(splitProblem(state, 5000)).toBe('percent_sum');
    expect(splitProblem({ ...state, percents: { a: 7000, b: 3000 } }, 5000)).toBeNull();
  });

  it('amounts must add up to the total', () => {
    const state = { ...initialSplitState(5000, ['a', 'b']), mode: 'amount' as const, amounts: { a: 4000, b: 500 } };
    expect(splitProblem(state, 5000)).toBe('amount_sum');
  });

  it('previews percentages in cents', () => {
    const state = { ...initialSplitState(5000, ['a', 'b']), mode: 'parts' as const, percents: { a: 7000, b: 3000 } };
    expect(previewShares(state, 5000)).toEqual({ a: 3500, b: 1500 });
  });

  it('builds the API spec for each mode', () => {
    const base = initialSplitState(5000, ['a', 'b']);
    expect(toSplitSpec({ ...base, enabled: false })).toEqual({ split_type: 'personal' });
    expect(toSplitSpec({ ...base, included: ['a'] })).toEqual({ split_type: 'equal', shares: [{ member_id: 'a' }] });
    expect(toSplitSpec({ ...base, mode: 'amount' })).toEqual({
      split_type: 'exact',
      shares: [
        { member_id: 'a', amount_cents: 2500 },
        { member_id: 'b', amount_cents: 2500 },
      ],
    });
  });
});
