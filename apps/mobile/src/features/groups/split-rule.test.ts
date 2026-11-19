import { describe, expect, it } from 'vitest';
import { previewShares } from './split-form';
import {
  ruleFormFromRule,
  ruleMembersChanged,
  ruleProblem,
  ruleSignature,
  splitStateFromRule,
  toRule,
} from './split-rule';
import type { SplitRule } from './types';

const custom = (shares: [string, number][]): SplitRule => ({
  split_type: 'percentages',
  shares: shares.map(([member_id, basis_points]) => ({ member_id, basis_points })),
});

describe('rule form', () => {
  it('opens an equal rule as equal parts', () => {
    const form = ruleFormFromRule({ split_type: 'equal' }, ['a', 'b']);
    expect(form.mode).toBe('equal');
    expect(toRule(form, ['a', 'b'])).toEqual({ split_type: 'equal' });
  });

  it('opens a percentages rule with its values and round-trips it', () => {
    const rule = custom([
      ['a', 6000],
      ['b', 4000],
    ]);
    const form = ruleFormFromRule(rule, ['a', 'b']);
    expect(form).toMatchObject({ mode: 'custom', percents: { a: 6000, b: 4000 } });
    expect(ruleSignature(toRule(form, ['a', 'b']))).toBe(ruleSignature(rule));
    expect(ruleMembersChanged(rule, ['a', 'b'])).toBe(false);
  });

  it('drops members who left and starts new members at 0 %', () => {
    const rule = custom([
      ['a', 6000],
      ['gone', 4000],
    ]);
    const form = ruleFormFromRule(rule, ['a', 'new']);
    expect(form.percents).toEqual({ a: 6000, new: 0 });
    expect(ruleMembersChanged(rule, ['a', 'new'])).toBe(true);
    expect(ruleProblem(form, ['a', 'new'])).toBe('percent_sum');
  });

  it('a custom rule names every member and must add up to 100 %', () => {
    const form = { mode: 'custom' as const, percents: { a: 7000, b: 3000, c: 0 }, locked: [] };
    expect(ruleProblem(form, ['a', 'b', 'c'])).toBeNull();
    expect(toRule(form, ['a', 'b', 'c'])).toEqual(
      custom([
        ['a', 7000],
        ['b', 3000],
        ['c', 0],
      ]),
    );
    expect(ruleProblem({ ...form, percents: { a: 7000, b: 2000, c: 0 } }, ['a', 'b', 'c'])).toBe('percent_sum');
  });

  it('opens other rule types as equal parts', () => {
    expect(ruleFormFromRule({ split_type: 'personal' }, ['a']).mode).toBe('equal');
  });
});

describe('new expense split from the rule', () => {
  it('starts equally under an equal rule', () => {
    const state = splitStateFromRule({ split_type: 'equal' }, ['a', 'b']);
    expect(state.mode).toBe('equal');
    expect(state.included).toEqual(['a', 'b']);
  });

  it('starts as parts with the rule percentages', () => {
    const state = splitStateFromRule(
      custom([
        ['a', 6000],
        ['b', 4000],
      ]),
      ['a', 'b'],
    );
    expect(state.mode).toBe('parts');
    expect(previewShares(state, 5000)).toEqual({ a: 3000, b: 2000 });
  });

  it('scales the percentages back to 100 % when someone in the rule left', () => {
    const state = splitStateFromRule(
      custom([
        ['a', 5000],
        ['b', 2500],
        ['gone', 2500],
      ]),
      ['a', 'b', 'new'],
    );
    expect(state.percents).toEqual({ a: 6667, b: 3333, new: 0 });
  });

  it('falls back to equal when nobody in the rule is left', () => {
    expect(splitStateFromRule(custom([['gone', 10000]]), ['a', 'b']).mode).toBe('equal');
  });
});
