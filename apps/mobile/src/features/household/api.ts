import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { queryKeys } from '@/lib/query/client';
import type {
  Category,
  Expense,
  ExpenseCreateInput,
  Household,
  Invitation,
  Me,
  Membership,
  Page,
  Period,
  PeriodBalance,
  PeriodKey,
  Settlement,
  Transfer,
} from './types';

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export function useMe() {
  return useQuery({ queryKey: queryKeys.me(), queryFn: () => apiFetch<Me>('/me') });
}

/** First membership that is not `left`, or null. */
function activeMembershipOf(me: Me): Membership | null {
  return me.memberships.find((m) => m.status !== 'left') ?? null;
}

/**
 * The household shown in the app: `data` is the first membership that is not `left`.
 * Returned as-is (no spread) so TanStack's tracked properties keep re-renders minimal.
 */
export function useActiveMembership() {
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: () => apiFetch<Me>('/me'),
    select: activeMembershipOf,
  });
}

export function useHousehold(householdId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.household(householdId ?? ''),
    queryFn: () => apiFetch<Household>(`/households/${householdId}`),
    enabled: !!householdId,
  });
}

export function useCategories(householdId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.categories(householdId ?? ''),
    queryFn: () => apiFetch<Category[]>(`/households/${householdId}/categories`),
    enabled: !!householdId,
  });
}

export function useBalance(householdId: string | undefined, period: PeriodKey) {
  return useQuery({
    queryKey: queryKeys.balance(householdId ?? '', String(period)),
    queryFn: () => apiFetch<PeriodBalance>(`/households/${householdId}/periods/${period}/balance`),
    enabled: !!householdId,
  });
}

/** The newest `limit` expenses of a period (e.g. the Home "recent" card). */
export function useRecentExpenses(householdId: string | undefined, period: PeriodKey, limit: number) {
  return useQuery({
    queryKey: queryKeys.expenses(householdId ?? '', { period: String(period), limit }),
    queryFn: () =>
      apiFetch<Page<Expense>>(`/households/${householdId}/expenses?period=${period}&limit=${limit}`),
    enabled: !!householdId,
  });
}

const EXPENSES_PAGE_SIZE = 50;

/** Next page: the API cursor plus the period number, pinned from the first page. */
interface ExpensesPageParam {
  cursor: string | null;
  period: PeriodKey;
}

/**
 * All expenses of a period, newest first, loaded page by page (cursor pagination).
 * Its own query key: infinite data ({ pages, pageParams }) cannot share a cache entry
 * with a plain useQuery.
 */
export function useExpensesInfinite(householdId: string | undefined, period: PeriodKey) {
  return useInfiniteQuery({
    queryKey: queryKeys.expenses(householdId ?? '', { period: String(period), infinite: true }),
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ period: String(pageParam.period), limit: String(EXPENSES_PAGE_SIZE) });
      if (pageParam.cursor) params.set('cursor', pageParam.cursor);
      return apiFetch<Page<Expense>>(`/households/${householdId}/expenses?${params.toString()}`);
    },
    initialPageParam: { cursor: null, period } as ExpensesPageParam,
    getNextPageParam: (lastPage, allPages): ExpensesPageParam | undefined => {
      if (!lastPage.next_cursor) return undefined;
      // Later pages ask for the first page's period number: if someone starts a new
      // period meanwhile, "current" would point at it and mix two periods.
      const seq = allPages[0]?.items[0]?.period.seq;
      return { cursor: lastPage.next_cursor, period: seq ?? period };
    },
    enabled: !!householdId,
  });
}

export function usePeriods(householdId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.periods(householdId ?? ''),
    queryFn: () => apiFetch<Page<Period>>(`/households/${householdId}/periods?limit=12`),
    enabled: !!householdId,
  });
}

export function useSettlement(householdId: string | undefined, period: PeriodKey) {
  return useQuery({
    queryKey: queryKeys.settlement(householdId ?? '', String(period)),
    queryFn: () => apiFetch<Settlement>(`/households/${householdId}/periods/${period}/settlement`),
    enabled: !!householdId,
  });
}

/** Any period or transfer change can alter balances, transfers and lists: refresh the household. */
function useInvalidateHousehold(householdId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: queryKeys.household(householdId) });
}

export function useClosePeriod(householdId: string, seq: number) {
  const invalidate = useInvalidateHousehold(householdId);
  return useMutation({
    mutationFn: () => apiFetch<Period>(`/households/${householdId}/periods/${seq}/close`, json({})),
    onSettled: invalidate,
  });
}

/** Any member starts the next period once the latest one is closed. */
export function useStartPeriod(householdId: string) {
  const invalidate = useInvalidateHousehold(householdId);
  return useMutation({
    mutationFn: () => apiFetch<Period>(`/households/${householdId}/periods`, json({})),
    onSettled: invalidate,
  });
}

export function useReopenPeriod(householdId: string, seq: number) {
  const invalidate = useInvalidateHousehold(householdId);
  return useMutation({
    mutationFn: (reason: string) =>
      apiFetch<Period>(`/households/${householdId}/periods/${seq}/reopen`, json({ reason })),
    onSettled: invalidate,
  });
}

export type TransferAction = 'sent' | 'confirm';

export function useTransferAction(householdId: string) {
  const invalidate = useInvalidateHousehold(householdId);
  return useMutation({
    mutationFn: ({ transferId, action }: { transferId: string; action: TransferAction }) =>
      apiFetch<Transfer>(`/households/${householdId}/transfers/${transferId}/${action}`, json({})),
    onSettled: invalidate,
  });
}

export function useCreateHousehold() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => apiFetch<Household>('/households', json({ name })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.me() }),
  });
}

export function useAcceptInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      apiFetch<Household>(`/invitations/${encodeURIComponent(code)}/accept`, json({})),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.me() }),
  });
}

export function useCreateInvitation(householdId: string) {
  return useMutation({
    mutationFn: () => apiFetch<Invitation>(`/households/${householdId}/invitations`, json({})),
  });
}

export function useCreateExpense(householdId: string) {
  const qc = useQueryClient();
  return useMutation({
    // The client-generated `input.id` makes the POST idempotent: a retry returns the
    // stored expense instead of creating a duplicate.
    mutationFn: (input: ExpenseCreateInput) =>
      apiFetch<Expense>(`/households/${householdId}/expenses`, json(input)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['household', householdId] }),
  });
}
