import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The query client module imports ApiError from the API client, which pulls in Supabase.
vi.mock('@/lib/api', () => ({ ApiError: class ApiError extends Error {} }));

const { queryKeys } = await import('@/lib/query/client');
const { invalidateExpenseChange, invalidatePaymentChange } = await import('./invalidation');

const G = 'group-1';
const OTHER = 'group-2';

const keys = {
  group: queryKeys.group(G),
  categories: queryKeys.categories(G),
  categoryPresets: queryKeys.categoryPresets(G),
  splitRules: queryKeys.splitRules(G),
  balance: queryKeys.balance(G),
  payments: queryKeys.payments(G),
  homeSummary: queryKeys.summary(G, { from: undefined }),
  insightsSummary: queryKeys.summary(G, { from: '2026-01-01', mine: true }),
  homeExpenses: queryKeys.expenses(G, { infinite: true }),
  searchExpenses: queryKeys.expenses(G, { q: 'pizza', infinite: true }),
  expense: queryKeys.expense(G, 'expense-1'),
  otherBalance: queryKeys.balance(OTHER),
  otherExpenses: queryKeys.expenses(OTHER, { infinite: true }),
};

let qc: QueryClient;

beforeEach(() => {
  qc = new QueryClient();
  for (const key of Object.values(keys)) qc.setQueryData(key, {});
});

function invalidated() {
  return Object.entries(keys)
    .filter(([, key]) => qc.getQueryState(key)?.isInvalidated)
    .map(([name]) => name)
    .sort();
}

describe('invalidateExpenseChange', () => {
  it('invalidates balance, expense lists, summaries and details of the group only', async () => {
    await invalidateExpenseChange(qc, G);
    expect(invalidated()).toEqual(
      ['balance', 'expense', 'homeExpenses', 'homeSummary', 'insightsSummary', 'searchExpenses'].sort(),
    );
  });
});

describe('invalidatePaymentChange', () => {
  it('invalidates balance and payments of the group only', async () => {
    await invalidatePaymentChange(qc, G);
    expect(invalidated()).toEqual(['balance', 'payments']);
  });
});
