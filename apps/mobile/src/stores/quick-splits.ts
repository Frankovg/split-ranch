import * as Crypto from 'expo-crypto';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import * as model from '@/features/quick-splits/model';
import type { QuickEvent, QuickExpense, QuickMode, QuickParticipant } from '@/features/quick-splits/types';
import { zustandStorage } from '@/lib/storage';

/**
 * Local-only Quick splits (works signed out, fully offline). Persisted in MMKV.
 * All updates delegate to the pure functions in features/quick-splits/model.ts.
 */
interface QuickSplitsState {
  events: Record<string, QuickEvent>;
  createEvent: (title: string) => string;
  deleteEvent: (id: string) => void;
  setTitle: (id: string, title: string) => void;
  setMode: (id: string, mode: QuickMode) => void;
  addParticipant: (id: string, name: string) => boolean;
  updateParticipant: (id: string, participantId: string, patch: Partial<Omit<QuickParticipant, 'id'>>) => void;
  removeParticipant: (id: string, participantId: string) => boolean;
  setTotalAmount: (id: string, cents: number | null) => void;
  toggleExcluded: (id: string, participantId: string) => void;
  setWeight: (id: string, participantId: string, weight: number) => void;
  setTotalPayer: (id: string, payerId: string | null) => void;
  upsertExpense: (id: string, expense: Omit<QuickExpense, 'id'> & { id?: string }) => void;
  removeExpense: (id: string, expenseId: string) => void;
  setMe: (id: string, participantId: string | null) => void;
  togglePaid: (id: string, participantId: string) => void;
}

const now = () => new Date().toISOString();

export const useQuickSplitsStore = create<QuickSplitsState>()(
  persist(
    (set, get) => {
      /** Apply a pure update to one event; returns whether it changed. */
      const update = (id: string, fn: (e: QuickEvent) => QuickEvent): boolean => {
        const current = get().events[id];
        if (!current) return false;
        const next = fn(current);
        if (next === current) return false;
        set((s) => ({ events: { ...s.events, [id]: next } }));
        return true;
      };

      return {
        events: {},
        createEvent: (title) => {
          const id = Crypto.randomUUID();
          set((s) => ({ events: { ...s.events, [id]: model.createQuickEvent(id, title, now()) } }));
          return id;
        },
        deleteEvent: (id) =>
          set((s) => {
            const { [id]: _removed, ...events } = s.events;
            return { events };
          }),
        setTitle: (id, title) => void update(id, (e) => model.setTitle(e, title, now())),
        setMode: (id, mode) => void update(id, (e) => model.setMode(e, mode, now())),
        addParticipant: (id, name) =>
          update(id, (e) => model.addParticipant(e, Crypto.randomUUID(), name, now())),
        updateParticipant: (id, participantId, patch) =>
          void update(id, (e) => model.updateParticipant(e, participantId, patch, now())),
        removeParticipant: (id, participantId) =>
          update(id, (e) => model.removeParticipant(e, participantId, now())),
        setTotalAmount: (id, cents) => void update(id, (e) => model.setTotalAmount(e, cents, now())),
        toggleExcluded: (id, participantId) =>
          void update(id, (e) => model.toggleExcluded(e, participantId, now())),
        setWeight: (id, participantId, weight) =>
          void update(id, (e) => model.setWeight(e, participantId, weight, now())),
        setTotalPayer: (id, payerId) => void update(id, (e) => model.setTotalPayer(e, payerId, now())),
        upsertExpense: (id, expense) =>
          void update(id, (e) =>
            model.upsertExpense(e, { ...expense, id: expense.id ?? Crypto.randomUUID() }, now()),
          ),
        removeExpense: (id, expenseId) => void update(id, (e) => model.removeExpense(e, expenseId, now())),
        setMe: (id, participantId) => void update(id, (e) => model.setMe(e, participantId, now())),
        togglePaid: (id, participantId) =>
          void update(id, (e) => model.togglePaid(e, participantId, now())),
      };
    },
    {
      name: 'quick-splits',
      storage: createJSONStorage(() => zustandStorage),
      version: 2,
      partialize: (s) => ({ events: s.events }),
      migrate: (persisted, version) => {
        const state = (persisted ?? {}) as { events?: Record<string, unknown> };
        if (version < 2) {
          const events = Object.fromEntries(
            Object.entries(state.events ?? {}).map(([k, v]) => [k, model.migrateEventV1(v)]),
          );
          return { events } as Pick<QuickSplitsState, 'events'>;
        }
        return state as Pick<QuickSplitsState, 'events'>;
      },
    },
  ),
);

/** Events sorted by last update, newest first. Use with useMemo (it returns a new array). */
export function sortEvents(events: Record<string, QuickEvent>): QuickEvent[] {
  return Object.values(events).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}
