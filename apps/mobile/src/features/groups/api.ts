import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/lib/api';
import { queryKeys } from '@/lib/query/client';
import type {
  CategoryCreateInput,
  ExpenseListFilters,
  Expense,
  ExpenseCreateInput,
  ExpenseUpdateInput,
  Payment,
  PaymentCreateInput,
  SummaryFilters,
} from './types';

/** Optimistic-concurrency header: the API rejects the change if the row changed meanwhile. */
const ifMatch = (version: number) => ({ 'if-match': `"${version}"` });

const fetchMe = () => unwrap(api.GET('/v1/me'));

export function useMe() {
  return useQuery({ queryKey: queryKeys.me(), queryFn: fetchMe });
}

export function useGroups() {
  return useQuery({ queryKey: queryKeys.groups(), queryFn: () => unwrap(api.GET('/v1/groups')) });
}

export function useGroup(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.group(groupId ?? ''),
    queryFn: () => unwrap(api.GET('/v1/groups/{group_id}', { params: { path: { group_id: groupId ?? '' } } })),
    enabled: !!groupId,
  });
}

/**
 * Every category of the group, archived ones included so old expenses still show theirs;
 * pickers offer only `selectableCategories`.
 */
export function useCategories(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.categories(groupId ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/v1/groups/{group_id}/categories', {
          params: { path: { group_id: groupId ?? '' }, query: { include_archived: true } },
        }),
      ),
    enabled: !!groupId,
  });
}

export function useBalance(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.balance(groupId ?? ''),
    queryFn: () =>
      unwrap(api.GET('/v1/groups/{group_id}/balance', { params: { path: { group_id: groupId ?? '' } } })),
    enabled: !!groupId,
  });
}

const EXPENSES_PAGE_SIZE = 50;

/**
 * Expenses matching the filters (date range, text), newest first, page by page (cursor
 * pagination). Its own key: infinite data ({ pages, pageParams }) cannot share a cache
 * entry with a plain useQuery.
 */
export function useExpensesInfinite(groupId: string | undefined, filters: ExpenseListFilters) {
  return useInfiniteQuery({
    queryKey: queryKeys.expenses(groupId ?? '', { ...filters, infinite: true }),
    queryFn: ({ pageParam }) =>
      // Unset range ends and the first page's null cursor are left out of the query string.
      unwrap(
        api.GET('/v1/groups/{group_id}/expenses', {
          params: {
            path: { group_id: groupId ?? '' },
            query: { from: filters.from, to: filters.to, q: filters.q, limit: EXPENSES_PAGE_SIZE, cursor: pageParam },
          },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!groupId,
  });
}

/** Total spent and totals per category / payer for the filters (insights). */
export function useSummary(groupId: string | undefined, filters: SummaryFilters) {
  return useQuery({
    queryKey: queryKeys.summary(groupId ?? '', { ...filters }),
    queryFn: () =>
      unwrap(
        api.GET('/v1/groups/{group_id}/summary', {
          params: {
            path: { group_id: groupId ?? '' },
            query: {
              from: filters.from,
              to: filters.to,
              category_id: filters.category_id,
              payer_member_id: filters.payer_member_id,
              mine: filters.mine,
            },
          },
        }),
      ),
    enabled: !!groupId,
  });
}

export function useExpense(groupId: string | undefined, expenseId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.expense(groupId ?? '', expenseId ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/v1/groups/{group_id}/expenses/{expense_id}', {
          params: { path: { group_id: groupId ?? '', expense_id: expenseId ?? '' } },
        }),
      ),
    enabled: !!groupId && !!expenseId,
  });
}

export function usePayments(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.payments(groupId ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/v1/groups/{group_id}/payments', {
          params: { path: { group_id: groupId ?? '' }, query: { limit: 50 } },
        }),
      ),
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
  return useMutation({
    mutationFn: (name: string) => unwrap(api.POST('/v1/groups', { body: { name } })),
    onSuccess: invalidate,
  });
}

export function useAcceptInvitation() {
  const invalidate = useInvalidateMembership();
  return useMutation({
    // Path params are URL-encoded by the client.
    mutationFn: (code: string) => unwrap(api.POST('/v1/invitations/{code}/accept', { params: { path: { code } } })),
    onSuccess: invalidate,
  });
}

export function useCreateInvitation(groupId: string) {
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST('/v1/groups/{group_id}/invitations', { params: { path: { group_id: groupId } } })),
  });
}

export function useRenameGroup(groupId: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateMembership();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(api.PATCH('/v1/groups/{group_id}', { params: { path: { group_id: groupId } }, body: { name } })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: queryKeys.group(groupId) });
      await invalidate();
    },
  });
}

export function useLeaveGroup(groupId: string) {
  const invalidate = useInvalidateMembership();
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST('/v1/groups/{group_id}/members/me/leave', { params: { path: { group_id: groupId } } })),
    onSuccess: invalidate,
  });
}

export function useRemoveMember(groupId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) =>
      unwrap(
        api.DELETE('/v1/groups/{group_id}/members/{member_id}', {
          params: { path: { group_id: groupId, member_id: memberId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.group(groupId) }),
  });
}

export function useDeleteGroup(groupId: string) {
  const invalidate = useInvalidateMembership();
  return useMutation({
    mutationFn: (confirmName: string) =>
      unwrap(
        api.DELETE('/v1/groups/{group_id}', {
          params: { path: { group_id: groupId } },
          body: { confirm_name: confirmName },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useCreateCategory(groupId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CategoryCreateInput) =>
      unwrap(api.POST('/v1/groups/{group_id}/categories', { params: { path: { group_id: groupId } }, body: input })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.categories(groupId) }),
  });
}

export function useCreateExpense(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    // The client-generated `input.id` makes the POST idempotent: a retry returns the
    // stored expense instead of creating a duplicate.
    mutationFn: (input: ExpenseCreateInput) =>
      unwrap(api.POST('/v1/groups/{group_id}/expenses', { params: { path: { group_id: groupId } }, body: input })),
    onSuccess: invalidate,
  });
}

export function useUpdateExpense(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    mutationFn: ({ expense, changes }: { expense: Expense; changes: ExpenseUpdateInput }) =>
      unwrap(
        api.PATCH('/v1/groups/{group_id}/expenses/{expense_id}', {
          params: { path: { group_id: groupId, expense_id: expense.id }, header: ifMatch(expense.version) },
          body: changes,
        }),
      ),
    onSettled: invalidate,
  });
}

export function useDeleteExpense(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    mutationFn: (expense: Expense) =>
      unwrap(
        api.DELETE('/v1/groups/{group_id}/expenses/{expense_id}', {
          params: { path: { group_id: groupId, expense_id: expense.id }, header: ifMatch(expense.version) },
        }),
      ),
    onSettled: invalidate,
  });
}

export function useRecordPayment(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    // Client-generated id: a retry returns the stored payment (no double payment).
    mutationFn: (input: PaymentCreateInput) =>
      unwrap(api.POST('/v1/groups/{group_id}/payments', { params: { path: { group_id: groupId } }, body: input })),
    onSettled: invalidate,
  });
}

export type PaymentAction = 'confirm' | 'dispute' | 'cancel';

function postPaymentAction(groupId: string, payment: Payment, action: PaymentAction, note?: string) {
  const params = {
    path: { group_id: groupId, payment_id: payment.id },
    header: ifMatch(payment.version),
  };
  switch (action) {
    case 'confirm':
      return api.POST('/v1/groups/{group_id}/payments/{payment_id}/confirm', { params, body: { note } });
    case 'cancel':
      return api.POST('/v1/groups/{group_id}/payments/{payment_id}/cancel', { params, body: { note } });
    case 'dispute':
      // A dispute needs a note; an empty one is rejected by the API like a missing one.
      return api.POST('/v1/groups/{group_id}/payments/{payment_id}/dispute', { params, body: { note: note ?? '' } });
  }
}

export function usePaymentAction(groupId: string) {
  const invalidate = useInvalidateGroup(groupId);
  return useMutation({
    mutationFn: ({ payment, action, note }: { payment: Payment; action: PaymentAction; note?: string }) =>
      unwrap(postPaymentAction(groupId, payment, action, note)),
    onSettled: invalidate,
  });
}
