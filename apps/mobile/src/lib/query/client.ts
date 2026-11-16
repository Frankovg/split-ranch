import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';

/**
 * Shared QueryClient. TODO: add @tanstack/query-async-storage-persister backed by
 * MMKV (docs/05 "State and data").
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
