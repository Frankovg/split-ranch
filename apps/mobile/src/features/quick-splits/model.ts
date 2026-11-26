import type { QuickEvent, QuickExpense, QuickMode, QuickParticipant } from './types';

/**
 * Pure, immutable updates for a Quick split event. The Zustand store wraps these;
 * ids and timestamps are injected so the functions stay deterministic and testable.
 */

export const MAX_WEIGHT = 99;

export function createQuickEvent(id: string, title: string, now: string): QuickEvent {
  return {
    id,
    title,
    createdAt: now,
    updatedAt: now,
    mode: 'total',
    participants: [],
    total: { amountCents: null, excludedIds: [], weights: {}, payerId: null, payerAmounts: null },
    expenses: [],
    meId: null,
    paidIds: [],
  };
}

function touch(event: QuickEvent, now: string, patch: Partial<QuickEvent>): QuickEvent {
  return { ...event, ...patch, updatedAt: now };
}

export function normaliseName(name: string): string {
  return name.trim().replace(/\s+/g, ' ');
}

/** True when another participant already uses this name (case-insensitive). */
export function isDuplicateName(event: QuickEvent, name: string, exceptId?: string): boolean {
  const n = normaliseName(name).toLocaleLowerCase();
  return event.participants.some((p) => p.id !== exceptId && p.name.toLocaleLowerCase() === n);
}

export function addParticipant(event: QuickEvent, id: string, name: string, now: string): QuickEvent {
  const clean = normaliseName(name);
  if (clean === '' || isDuplicateName(event, clean)) return event;
  return touch(event, now, { participants: [...event.participants, { id, name: clean }] });
}

export function updateParticipant(
  event: QuickEvent,
  id: string,
  patch: Partial<Omit<QuickParticipant, 'id'>>,
  now: string,
): QuickEvent {
  const name = patch.name !== undefined ? normaliseName(patch.name) : undefined;
  if (name !== undefined && (name === '' || isDuplicateName(event, name, id))) return event;
  return touch(event, now, {
    participants: event.participants.map((p) =>
      p.id === id ? { ...p, ...patch, ...(name !== undefined ? { name } : {}) } : p,
    ),
  });
}

/** True when this participant paid (all or part of) the itemised expense. */
export function isExpensePayer(expense: QuickExpense, id: string): boolean {
  return expense.payerAmounts ? (expense.payerAmounts[id] ?? 0) > 0 : expense.payerId === id;
}

/** A participant who paid an itemised expense cannot be removed until that expense changes. */
export function canRemoveParticipant(event: QuickEvent, id: string): boolean {
  return !event.expenses.some((e) => isExpensePayer(e, id));
}

export function removeParticipant(event: QuickEvent, id: string, now: string): QuickEvent {
  if (!canRemoveParticipant(event, id)) return event;
  const { [id]: _removed, ...weights } = event.total.weights;
  let payerAmounts = event.total.payerAmounts;
  if (payerAmounts) {
    const { [id]: _paid, ...rest } = payerAmounts;
    payerAmounts = rest;
  }
  return touch(event, now, {
    participants: event.participants.filter((p) => p.id !== id),
    total: {
      ...event.total,
      excludedIds: event.total.excludedIds.filter((x) => x !== id),
      weights,
      payerId: event.total.payerId === id ? null : event.total.payerId,
      payerAmounts,
    },
    expenses: event.expenses.map((e) => ({
      ...e,
      participantIds: e.participantIds.filter((x) => x !== id),
    })),
    meId: event.meId === id ? null : event.meId,
    paidIds: event.paidIds.filter((x) => x !== id),
  });
}

/** Mark which participant is the phone's owner; null clears it. Unknown ids are ignored. */
export function setMe(event: QuickEvent, id: string | null, now: string): QuickEvent {
  if (id !== null && !event.participants.some((p) => p.id === id)) return event;
  if (event.meId === id) return event;
  return touch(event, now, { meId: id });
}

/** Manual "has paid" / "owes" switch for one participant. */
export function togglePaid(event: QuickEvent, id: string, now: string): QuickEvent {
  if (!event.participants.some((p) => p.id === id)) return event;
  const paidIds = event.paidIds.includes(id)
    ? event.paidIds.filter((x) => x !== id)
    : [...event.paidIds, id];
  return touch(event, now, { paidIds });
}

export function setTitle(event: QuickEvent, title: string, now: string): QuickEvent {
  return touch(event, now, { title });
}

export function setMode(event: QuickEvent, mode: QuickMode, now: string): QuickEvent {
  return touch(event, now, { mode });
}

export function setTotalAmount(event: QuickEvent, amountCents: number | null, now: string): QuickEvent {
  return touch(event, now, { total: { ...event.total, amountCents } });
}

export function toggleExcluded(event: QuickEvent, id: string, now: string): QuickEvent {
  const excluded = event.total.excludedIds.includes(id)
    ? event.total.excludedIds.filter((x) => x !== id)
    : [...event.total.excludedIds, id];
  return touch(event, now, { total: { ...event.total, excludedIds: excluded } });
}

export function setWeight(event: QuickEvent, id: string, weight: number, now: string): QuickEvent {
  const w = Math.min(MAX_WEIGHT, Math.max(1, Math.round(weight)));
  const weights = { ...event.total.weights };
  if (w === 1) delete weights[id];
  else weights[id] = w;
  return touch(event, now, { total: { ...event.total, weights } });
}

/** One payer (or none) for the whole total; leaves "several payers" mode. */
export function setTotalPayer(event: QuickEvent, payerId: string | null, now: string): QuickEvent {
  return touch(event, now, { total: { ...event.total, payerId, payerAmounts: null } });
}

/**
 * Switch to "several payers". A single payer already chosen starts with the whole total, so
 * the user only has to move part of it to the others.
 */
export function setMultiplePayers(event: QuickEvent, now: string): QuickEvent {
  if (event.total.payerAmounts) return event;
  const { payerId, amountCents } = event.total;
  const payerAmounts: Record<string, number> =
    payerId !== null && amountCents !== null && amountCents > 0 ? { [payerId]: amountCents } : {};
  return touch(event, now, { total: { ...event.total, payerId: null, payerAmounts } });
}

/** How much one participant paid in "several payers" mode; null or 0 clears it. */
export function setPayerAmount(event: QuickEvent, id: string, cents: number | null, now: string): QuickEvent {
  if (!event.total.payerAmounts || !event.participants.some((p) => p.id === id)) return event;
  const { [id]: _old, ...payerAmounts } = event.total.payerAmounts;
  if (cents !== null && cents > 0) payerAmounts[id] = cents;
  return touch(event, now, { total: { ...event.total, payerAmounts } });
}

/**
 * `totalCents` minus what several payers entered for existing participants (positive: still
 * missing, negative: too much).
 */
export function payersGap(
  participants: readonly QuickParticipant[],
  amounts: Readonly<Record<string, number>>,
  totalCents: number,
): number {
  const paid = participants.reduce((acc, p) => acc + (amounts[p.id] ?? 0), 0);
  return totalCents - paid;
}

/** `payersGap` of the total in "several payers" mode; null when not in it or no total yet. */
export function payerAmountsGap(event: QuickEvent): number | null {
  const { payerAmounts, amountCents } = event.total;
  if (!payerAmounts || amountCents === null) return null;
  return payersGap(event.participants, payerAmounts, amountCents);
}

/** Insert or replace an itemised expense (matched by id). */
export function upsertExpense(event: QuickEvent, expense: QuickExpense, now: string): QuickEvent {
  const exists = event.expenses.some((e) => e.id === expense.id);
  return touch(event, now, {
    expenses: exists
      ? event.expenses.map((e) => (e.id === expense.id ? expense : e))
      : [...event.expenses, expense],
  });
}

export function removeExpense(event: QuickEvent, expenseId: string, now: string): QuickEvent {
  return touch(event, now, { expenses: event.expenses.filter((e) => e.id !== expenseId) });
}

/**
 * Persisted-store migration v1 -> v2: adds `meId` / `paidIds` and drops the old payment
 * handles (`paypalMe`, `revolut`) that participants used to carry.
 */
export function migrateEventV1(raw: unknown): QuickEvent {
  const e = raw as QuickEvent & { participants: (QuickParticipant & Record<string, unknown>)[] };
  return {
    ...e,
    participants: e.participants.map((p) => ({ id: p.id, name: p.name })),
    meId: e.meId ?? null,
    paidIds: e.paidIds ?? [],
  };
}

/** Persisted-store migration v2 -> v3: adds `total.payerAmounts` (several payers). */
export function migrateEventV2(raw: unknown): QuickEvent {
  const e = raw as QuickEvent;
  return { ...e, total: { ...e.total, payerAmounts: e.total.payerAmounts ?? null } };
}
