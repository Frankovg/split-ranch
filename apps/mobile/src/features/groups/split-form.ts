/**
 * Pure state helpers for the expense form's split table: equal defaults, the automatic
 * rebalancing of percentages / amounts and the split spec sent to the API.
 */
import { allocate, BASIS_POINTS_TOTAL } from '@split-ranch/domain';
import type { Expense, ExpenseCreateInput } from './types';

/** "Equally", "As parts" (percentages) or "As amount" (exact cents). */
export type SplitMode = 'equal' | 'parts' | 'amount';

export type SplitSpecInput = NonNullable<ExpenseCreateInput['split']>;

export interface SplitFormState {
  /** false = the expense is not split: it only counts for whoever paid it (`personal`). */
  enabled: boolean;
  mode: SplitMode;
  /** Members the expense is split between, in group order. */
  included: string[];
  /** Basis points per included member (mode `parts`). */
  percents: Record<string, number>;
  /** Cents per included member (mode `amount`). */
  amounts: Record<string, number>;
  /** Members whose value the user typed, oldest first; the others absorb the remainder. */
  locked: string[];
}

/** `total` spread as evenly as possible over `ids` (first ids get the leftover cents). */
export function equalValues(total: number, ids: readonly string[]): Record<string, number> {
  if (ids.length === 0) return {};
  const parts = allocate(Math.max(total, 0), ids.map(() => 1));
  return Object.fromEntries(ids.map((id, i) => [id, parts[i] ?? 0]));
}

/** Fresh percentages and amounts for the included members (equal shares, nothing locked). */
export function resetValues(state: SplitFormState, amountCents: number): SplitFormState {
  return {
    ...state,
    percents: equalValues(BASIS_POINTS_TOTAL, state.included),
    amounts: equalValues(amountCents, state.included),
    locked: [],
  };
}

export function initialSplitState(amountCents: number, everyone: string[]): SplitFormState {
  return resetValues(
    { enabled: true, mode: 'equal', included: everyone, percents: {}, amounts: {}, locked: [] },
    amountCents,
  );
}

/**
 * Set one member's value and give what is left of `total` to the members the user did
 * not type (equally). When every member has been typed, the oldest typed one is freed
 * so the sum can still match (two people: typing 40 of 50 gives the other one 10).
 */
export function rebalance(
  values: Record<string, number>,
  ids: readonly string[],
  locked: readonly string[],
  changedId: string,
  value: number,
  total: number,
): { values: Record<string, number>; locked: string[] } {
  let nextLocked = [...locked.filter((id) => id !== changedId && ids.includes(id)), changedId];
  if (nextLocked.length >= ids.length && ids.length > 1) nextLocked = nextLocked.slice(1);
  const free = ids.filter((id) => !nextLocked.includes(id));
  const next: Record<string, number> = { ...values, [changedId]: value };
  const lockedSum = nextLocked.reduce((sum, id) => sum + (next[id] ?? 0), 0);
  Object.assign(next, equalValues(total - lockedSum, free));
  return { values: Object.fromEntries(ids.map((id) => [id, next[id] ?? 0])), locked: nextLocked };
}

export function sumOf(values: Record<string, number>, ids: readonly string[]): number {
  return ids.reduce((sum, id) => sum + (values[id] ?? 0), 0);
}

/** What each included member pays under the current mode (cents). */
export function previewShares(state: SplitFormState, amountCents: number): Record<string, number> {
  const ids = state.included;
  if (ids.length === 0) return {};
  if (state.mode === 'amount') return Object.fromEntries(ids.map((id) => [id, state.amounts[id] ?? 0]));
  if (state.mode === 'parts') {
    const bps = ids.map((id) => state.percents[id] ?? 0);
    if (bps.every((b) => b === 0)) return Object.fromEntries(ids.map((id) => [id, 0]));
    const parts = allocate(Math.max(amountCents, 0), bps);
    return Object.fromEntries(ids.map((id, i) => [id, parts[i] ?? 0]));
  }
  return equalValues(amountCents, ids);
}

export type SplitProblem = 'no_members' | 'percent_sum' | 'amount_sum';

export function splitProblem(state: SplitFormState, amountCents: number | null): SplitProblem | null {
  if (!state.enabled) return null;
  if (state.included.length === 0) return 'no_members';
  if (state.mode === 'parts' && sumOf(state.percents, state.included) !== BASIS_POINTS_TOTAL) return 'percent_sum';
  if (state.mode === 'amount' && amountCents !== null && sumOf(state.amounts, state.included) !== amountCents) {
    return 'amount_sum';
  }
  return null;
}

/** The explicit split spec for the API. */
export function toSplitSpec(state: SplitFormState): SplitSpecInput {
  if (!state.enabled) return { split_type: 'personal' };
  const ids = state.included;
  switch (state.mode) {
    case 'parts':
      return {
        split_type: 'percentages',
        shares: ids.map((id) => ({ member_id: id, basis_points: state.percents[id] ?? 0 })),
      };
    case 'amount':
      return {
        split_type: 'exact',
        shares: ids.map((id) => ({ member_id: id, amount_cents: state.amounts[id] ?? 0 })),
      };
    case 'equal':
      return { split_type: 'equal', shares: ids.map((id) => ({ member_id: id })) };
  }
}

/** True while the table still shows its defaults: everyone, equally, split on. */
export function isDefaultSplit(state: SplitFormState, everyone: readonly string[]): boolean {
  return state.enabled && state.mode === 'equal' && state.included.length === everyone.length;
}

/** The table state that shows how a stored expense is split. */
export function splitStateFromExpense(expense: Expense, everyone: string[]): SplitFormState {
  const base = initialSplitState(expense.amount_cents, everyone);
  if (expense.split_type === 'personal') return { ...base, enabled: false };
  // Keep group order; members who left the group stay in the stored shares.
  const shareIds = expense.shares.map((s) => s.member_id);
  const included = [...everyone.filter((id) => shareIds.includes(id)), ...shareIds.filter((id) => !everyone.includes(id))];
  const withIncluded = resetValues({ ...base, included }, expense.amount_cents);
  if (expense.split_type === 'equal') {
    return expense.participant_mode === 'all' ? base : withIncluded;
  }
  if (expense.split_type === 'percentages') {
    const percents = Object.fromEntries(expense.shares.map((s) => [s.member_id, s.basis_points ?? 0]));
    return { ...withIncluded, mode: 'parts', percents, locked: [...included] };
  }
  // exact, weights and single are shown as the amounts each member pays.
  const amounts = Object.fromEntries(expense.shares.map((s) => [s.member_id, s.exact_cents ?? s.amount_cents]));
  return { ...withIncluded, mode: 'amount', amounts, locked: [...included] };
}

/** A stable signature to tell whether the user changed the split while editing. */
export function splitSignature(state: SplitFormState): string {
  return JSON.stringify(toSplitSpec(state));
}
