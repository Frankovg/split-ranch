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
    total: { amountCents: null, excludedIds: [], weights: {}, payerId: null },
    expenses: [],
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

/** A participant who paid an itemised expense cannot be removed until that expense changes. */
export function canRemoveParticipant(event: QuickEvent, id: string): boolean {
  return !event.expenses.some((e) => e.payerId === id);
}

export function removeParticipant(event: QuickEvent, id: string, now: string): QuickEvent {
  if (!canRemoveParticipant(event, id)) return event;
  const { [id]: _removed, ...weights } = event.total.weights;
  return touch(event, now, {
    participants: event.participants.filter((p) => p.id !== id),
    total: {
      ...event.total,
      excludedIds: event.total.excludedIds.filter((x) => x !== id),
      weights,
      payerId: event.total.payerId === id ? null : event.total.payerId,
    },
    expenses: event.expenses.map((e) => ({
      ...e,
      participantIds: e.participantIds.filter((x) => x !== id),
    })),
  });
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

export function setTotalPayer(event: QuickEvent, payerId: string | null, now: string): QuickEvent {
  return touch(event, now, { total: { ...event.total, payerId } });
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
