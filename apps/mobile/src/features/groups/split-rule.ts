/**
 * Pure helpers for the group's default split rule: the settings form ("equal parts" or
 * custom percentages per member) and the starting split of a new expense under that rule.
 */
import { allocate, BASIS_POINTS_TOTAL } from '@split-ranch/domain';
import { equalValues, initialSplitState, sumOf, type SplitFormState } from './split-form';
import type { SplitRule } from './types';

/** "equal" = everyone pays the same; "custom" = a percentage per member. */
export type RuleMode = 'equal' | 'custom';

export interface RuleFormState {
  mode: RuleMode;
  /** Basis points per active member (mode `custom`). */
  percents: Record<string, number>;
  /** Members whose value the user typed, oldest first; the others absorb the remainder. */
  locked: string[];
}

/** Basis points of a percentages rule for the given members (0 for anyone it does not name). */
function rulePercents(rule: SplitRule, ids: readonly string[]): Record<string, number> | null {
  if (rule.split_type !== 'percentages') return null;
  const byId = new Map(rule.shares.map((s) => [s.member_id, s.basis_points]));
  return Object.fromEntries(ids.map((id) => [id, byId.get(id) ?? 0]));
}

/**
 * The settings form for a stored rule. Only "equal" and "percentages" are edited here; any
 * other type (only settable through the API) opens as "equal parts". Members who left are
 * dropped and new members start at 0 %, so the sum may need fixing before saving.
 */
export function ruleFormFromRule(rule: SplitRule | undefined, everyone: readonly string[]): RuleFormState {
  const percents = rule ? rulePercents(rule, everyone) : null;
  if (percents) return { mode: 'custom', percents, locked: [...everyone] };
  return { mode: 'equal', percents: equalValues(BASIS_POINTS_TOTAL, everyone), locked: [] };
}

/** True when a custom rule no longer matches the members (someone joined or left). */
export function ruleMembersChanged(rule: SplitRule | undefined, everyone: readonly string[]): boolean {
  if (rule?.split_type !== 'percentages') return false;
  const named = rule.shares.map((s) => s.member_id);
  return named.length !== everyone.length || named.some((id) => !everyone.includes(id));
}

export type RuleProblem = 'percent_sum';

export function ruleProblem(state: RuleFormState, everyone: readonly string[]): RuleProblem | null {
  if (state.mode === 'custom' && sumOf(state.percents, everyone) !== BASIS_POINTS_TOTAL) return 'percent_sum';
  return null;
}

/**
 * The rule sent to the API. "Equal" names nobody, so it always means every active member
 * (people who join later included); "custom" names every active member, 0 % allowed.
 */
export function toRule(state: RuleFormState, everyone: readonly string[]): SplitRule {
  if (state.mode === 'equal') return { split_type: 'equal' };
  return {
    split_type: 'percentages',
    shares: everyone.map((id) => ({ member_id: id, basis_points: state.percents[id] ?? 0 })),
  };
}

/** A stable signature to tell whether the form differs from the stored rule. */
export function ruleSignature(rule: SplitRule | undefined): string {
  return JSON.stringify(rule ?? { split_type: 'equal' });
}

/**
 * The split table a new expense starts with, so its preview matches what the API applies
 * when the table is left untouched: a percentages rule opens "As parts" with the rule's
 * values over today's members (scaled back to 100 % when someone in it left, as the API
 * does); anything else opens "Equally".
 */
export function splitStateFromRule(rule: SplitRule | undefined, everyone: string[]): SplitFormState {
  const base = initialSplitState(0, everyone);
  const percents = rule ? rulePercents(rule, everyone) : null;
  if (!percents) return base;
  const bps = everyone.map((id) => percents[id] ?? 0);
  // Nobody in the rule is still here: the API falls back to an equal split.
  if (bps.every((b) => b === 0)) return base;
  const scaled = allocate(BASIS_POINTS_TOTAL, bps);
  return {
    ...base,
    mode: 'parts',
    percents: Object.fromEntries(everyone.map((id, i) => [id, scaled[i] ?? 0])),
  };
}
