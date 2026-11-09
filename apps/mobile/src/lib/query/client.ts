import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';

/**
 * Shared QueryClient. TODO: add @tanstack/query-async-storage-persister backed by
 * MMKV once household queries exist (docs/05 "State and data").
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2,
    },
  },
});

/** Query key factory (docs/05). */
export const queryKeys = {
  me: () => ['me'] as const,
  households: () => ['households'] as const,
  household: (householdId: string) => ['household', householdId] as const,
  categories: (householdId: string) => ['household', householdId, 'categories'] as const,
  balance: (householdId: string, period: string) =>
    ['household', householdId, 'balance', period] as const,
  periods: (householdId: string) => ['household', householdId, 'periods'] as const,
  settlement: (householdId: string, period: string) =>
    ['household', householdId, 'settlement', period] as const,
  expenses: (householdId: string, filters: Record<string, unknown> = {}) =>
    ['household', householdId, 'expenses', filters] as const,
};
