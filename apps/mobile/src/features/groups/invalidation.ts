import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/query/client';

/**
 * Targeted invalidation after group mutations. Group tabs stay mounted, so their queries
 * are active and every invalidated one is refetched at once: invalidate only what the
 * change can alter, not the whole `['group', id]` tree (members, categories, presets and
 * split rules do not change when an expense or a payment does).
 */

/** An expense was created, edited or deleted: balance, lists, totals and details change. */
export function invalidateExpenseChange(qc: QueryClient, groupId: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: queryKeys.balance(groupId) }),
    qc.invalidateQueries({ queryKey: queryKeys.expenseLists(groupId) }),
    qc.invalidateQueries({ queryKey: queryKeys.summaries(groupId) }),
    qc.invalidateQueries({ queryKey: queryKeys.expenseDetails(groupId) }),
  ]);
}

/** A payment was recorded, confirmed, disputed or cancelled: only balance and payments change. */
export function invalidatePaymentChange(qc: QueryClient, groupId: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: queryKeys.balance(groupId) }),
    qc.invalidateQueries({ queryKey: queryKeys.payments(groupId) }),
  ]);
}
