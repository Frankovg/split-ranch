import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';

/** A persisted cache older than this is discarded on restore (docs/05 "State and data"). */
export const CACHE_MAX_AGE = 24 * 60 * 60 * 1000;

/** Bump when response shapes or query keys change, to discard every persisted cache. */
export const CACHE_BUSTER = '1';

/**
 * Shared QueryClient, persisted to MMKV by PersistQueryClientProvider (app/_layout.tsx).
 * `gcTime` must be >= `CACHE_MAX_AGE`, or restored queries are garbage-collected early.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: CACHE_MAX_AGE,
      staleTime: 30_000,
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2,
    },
  },
});

/** Query key factory (docs/05). Everything of a group lives under ['group', id]. */
export const queryKeys = {
  me: () => ['me'] as const,
  groups: () => ['groups'] as const,
  group: (groupId: string) => ['group', groupId] as const,
  categories: (groupId: string) => ['group', groupId, 'categories'] as const,
  balance: (groupId: string) => ['group', groupId, 'balance'] as const,
  payments: (groupId: string) => ['group', groupId, 'payments'] as const,
  summary: (groupId: string, filters: Record<string, unknown> = {}) =>
    ['group', groupId, 'summary', filters] as const,
  expenses: (groupId: string, filters: Record<string, unknown> = {}) =>
    ['group', groupId, 'expenses', filters] as const,
  expense: (groupId: string, expenseId: string) => ['group', groupId, 'expense', expenseId] as const,
};
