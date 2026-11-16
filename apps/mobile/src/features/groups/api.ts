import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { queryKeys } from '@/lib/query/client';
import { usePreferencesStore } from '@/stores/preferences';
import type {
  Category,
  DateRange,
  Expense,
  ExpenseCreateInput,
  ExpenseUpdateInput,
  Group,
  GroupBalance,
  Invitation,
  Me,
  Membership,
  Page,
  Payment,
  PaymentCreateInput,
  Summary,
} from './types';

const json = (body: unknown, method = 'POST'): RequestInit => ({ method, body: JSON.stringify(body) });
const ifMatch = (version: number) => ({ 'If-Match': `"${version}"` });

export function useMe() {
  return useQuery({ queryKey: queryKeys.me(), queryFn: () => apiFetch<Me>('/me') });
}

/** The chosen group if the user still belongs to it, else their first group, else null. */
export function pickMembership(me: Me, activeGroupId: string | null): Membership | null {
  return me.memberships.find((m) => m.group_id === activeGroupId) ?? me.memberships[0] ?? null;
}

/**
 * The group shown in the app: the one picked in the group list (persisted), falling back
 * to the first group. `data` is null when the user has no group yet.
 */
export function useActiveMembership() {
  const activeGroupId = usePreferencesStore((s) => s.activeGroupId);
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: () => apiFetch<Me>('/me'),
    select: (me: Me) => pickMembership(me, activeGroupId),
  });
}

export function useGroups() {
  return useQuery({ queryKey: queryKeys.groups(), queryFn: () => apiFetch<Group[]>('/groups') });
}

export function useGroup(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.group(groupId ?? ''),
    queryFn: () => apiFetch<Group>(`/groups/${groupId}`),
    enabled: !!groupId,
  });
}

export function useCategories(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.categories(groupId ?? ''),
    queryFn: () => apiFetch<Category[]>(`/groups/${groupId}/categories`),
    enabled: !!groupId,
  });
}

export function useBalance(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.balance(groupId ?? ''),
    queryFn: () => apiFetch<GroupBalance>(`/groups/${groupId}/balance`),
    enabled: !!groupId,
  });
}

function rangeParams(range: DateRange, extra: Record<string, string> = {}): URLSearchParams {
  const params = new URLSearchParams(extra);
  if (range.from) params.set('from', range.from);
  if (range.to) params.set('to', range.to);
  return params;
}

/** The newest `limit` expenses (the Home "recent" card). */
export function useRecentExpenses(groupId: string | undefined, limit: number) {
  return useQuery({
    queryKey: queryKeys.expenses(groupId ?? '', { limit }),
    queryFn: () => apiFetch<Page<Expense>>(`/groups/${groupId}/expenses?limit=${limit}`),
    enabled: !!groupId,
  });
}

const EXPENSES_PAGE_SIZE = 50;

/**
 * Expenses in a date range, newest first, page by page (cursor pagination). Its own key:
 * infinite data ({ pages, pageParams }) cannot share a cache entry with a plain useQuery.
 */
export function useExpensesInfinite(groupId: string | undefined, range: DateRange) {
  return useInfiniteQuery({
    queryKey: queryKeys.expenses(groupId ?? '', { ...range, infinite: true }),
    queryFn: ({ pageParam }) => {
      const params = rangeParams(range, { limit: String(EXPENSES_PAGE_SIZE) });
      if (pageParam) params.set('cursor', pageParam);
      return apiFetch<Page<Expense>>(`/groups/${groupId}/expenses?${params.toString()}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!groupId,
  });
}

/** Total spent and totals per category / payer for the same range as the list. */
export function useSummary(groupId: string | undefined, range: DateRange) {
  return useQuery({
    queryKey: queryKeys.summary(groupId ?? '', { ...range }),
    queryFn: () => apiFetch<Summary>(`/groups/${groupId}/summary?${rangeParams(range).toString()}`),
    enabled: !!groupId,
  });
}

export function useExpense(groupId: string | undefined, expenseId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.expense(groupId ?? '', expenseId ?? ''),
    queryFn: () => apiFetch<Expense>(`/groups/${groupId}/expenses/${expenseId}`),
    enabled: !!groupId && !!expenseId,
  });
}

export function usePayments(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.payments(groupId ?? ''),
    queryFn: () => apiFetch<Page<Payment>>(`/groups/${groupId}/payments?limit=50`),
    enabled: !!groupId,
  });
}

/** Any expense or payment change can alter balances, lists and totals: refresh the group. */
function useInvalidateGroup(groupId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: queryKeys.group(groupId) });
}

/** Membership changes also change `/me` and the group list. */
function useInvalidateMembership() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.me() }),
      qc.invalidateQueries({ queryKey: queryKeys.groups() }),
    ]);
  };
}

export function useCreateGroup() {
  const invalidate = useInvalidateMembership();
  const setActiveGroupId = usePreferencesStore((s) => s.setActiveGroupId);
  return useMutation({
    mutationFn: (name: string) => apiFetch<Group>('/groups', json({ name })),
    onSuccess: async (group) => {
      setActiveGroupId(group.id);
      await invalidate();
    },
  });
}

export function useAcceptInvitation() {
  const invalidate = useInvalidateMembership();
  const setActiveGroupId = usePreferencesStore((s) => s.setActiveGroupId);
  return useMutation({
    mutationFn: (code: string) => apiFetch<Group>(`/invitations/${encodeURIComponent(code)}/accept`, json({})),
    onSuccess: async (group) => {
      setActiveGroupId(group.id);
      await invalidate();
    },
  });
}

export function useCreateInvitation(groupId: string) {
  return useMutation({
    mutationFn: () => apiFetch<Invitation>(`/groups/${groupId}/invitations`, json({})),
  });
}

export function useRenameGroup(groupId: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateMembership();
  return useMutation({
    mutationFn: (name: string) => apiFetch<Group>(`/groups/${groupId}`, json({ name }, 'PATCH')),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: queryKeys.group(groupId) });
      await invalidate();
    },
  });
}

export function useLeaveGroup(groupId: string) {
  const invalidate = useInvalidateMembership();
  return useMutation({
    mutationFn: () => apiFetch<null>(`/groups/${groupId}/members/me/leave`, json({})),
    onSuccess: invalidate,
  });
}

export function useRemoveMember(groupId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => apiFetch<Group>(`/groups/${groupId}/members/${memberId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.group(groupId) }),
  });
}

export function useDeleteGroup(groupId: string) {
  const invalidate = useInvalidateMembership();
  return useMutation({
    mutationFn: (confirmName: string) =>
      apiFetch<null>(`/groups/${groupId}`, json({ confirm_name: confirmName }, 'DELETE')),
    onSuccess: invalidate,
  });
}

export function useCreateExpense(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    // The client-generated `input.id` makes the POST idempotent: a retry returns the
    // stored expense instead of creating a duplicate.
    mutationFn: (input: ExpenseCreateInput) => apiFetch<Expense>(`/groups/${groupId}/expenses`, json(input)),
    onSuccess: invalidate,
  });
}

export function useUpdateExpense(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    mutationFn: ({ expense, changes }: { expense: Expense; changes: ExpenseUpdateInput }) =>
      apiFetch<Expense>(`/groups/${groupId}/expenses/${expense.id}`, {
        ...json(changes, 'PATCH'),
        headers: ifMatch(expense.version),
      }),
    onSettled: invalidate,
  });
}

export function useDeleteExpense(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    mutationFn: (expense: Expense) =>
      apiFetch<null>(`/groups/${groupId}/expenses/${expense.id}`, {
        method: 'DELETE',
        headers: ifMatch(expense.version),
      }),
    onSettled: invalidate,
  });
}

export function useRecordPayment(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    // Client-generated id: a retry returns the stored payment (no double payment).
    mutationFn: (input: PaymentCreateInput) => apiFetch<Payment>(`/groups/${groupId}/payments`, json(input)),
    onSettled: invalidate,
  });
}

export type PaymentAction = 'confirm' | 'dispute' | 'cancel';

export function usePaymentAction(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    mutationFn: ({ payment, action, note }: { payment: Payment; action: PaymentAction; note?: string }) =>
      apiFetch<Payment>(`/groups/${groupId}/payments/${payment.id}/${action}`, {
        ...json(note ? { note } : {}),
        headers: ifMatch(payment.version),
      }),
    onSettled: invalidate,
  });
}
