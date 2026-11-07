import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { queryKeys } from '@/lib/query/client';
import type {
  Category,
  Expense,
  ExpenseCreateInput,
  Household,
  Invitation,
  Me,
  Page,
  Period,
  PeriodBalance,
  Settlement,
  Transfer,
} from './types';

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export function useMe() {
  return useQuery({ queryKey: queryKeys.me(), queryFn: () => apiFetch<Me>('/me') });
}

/** The household shown in the app: first membership that is not `left`. */
export function useActiveMembership() {
  const me = useMe();
  const membership = me.data?.memberships.find((m) => m.status !== 'left') ?? null;
  return { ...me, membership };
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

export function useBalance(householdId: string | undefined, month: string) {
  return useQuery({
    queryKey: queryKeys.balance(householdId ?? '', month),
    queryFn: () => apiFetch<PeriodBalance>(`/households/${householdId}/periods/${month}/balance`),
    enabled: !!householdId,
  });
}

export function useExpenses(householdId: string | undefined, month: string) {
  return useQuery({
    queryKey: queryKeys.expenses(householdId ?? '', { month }),
    queryFn: () =>
      apiFetch<Page<Expense>>(`/households/${householdId}/expenses?period=${month}&limit=100`),
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

export function useSettlement(householdId: string | undefined, month: string) {
  return useQuery({
    queryKey: queryKeys.settlement(householdId ?? '', month),
    queryFn: () => apiFetch<Settlement>(`/households/${householdId}/periods/${month}/settlement`),
    enabled: !!householdId,
  });
}

/** Any period or transfer change can alter balances, snapshots and lists: refresh the household. */
function useInvalidateHousehold(householdId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: queryKeys.household(householdId) });
}

export function useClosePeriod(householdId: string, month: string) {
  const invalidate = useInvalidateHousehold(householdId);
  return useMutation({
    mutationFn: () => apiFetch<Period>(`/households/${householdId}/periods/${month}/close`, json({})),
    onSettled: invalidate,
  });
}

export function useReopenPeriod(householdId: string, month: string) {
  const invalidate = useInvalidateHousehold(householdId);
  return useMutation({
    mutationFn: (reason: string) =>
      apiFetch<Period>(`/households/${householdId}/periods/${month}/reopen`, json({ reason })),
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
    mutationFn: (input: ExpenseCreateInput) =>
      apiFetch<Expense>(`/households/${householdId}/expenses`, {
        ...json(input),
        // Same id as the body: a retried POST returns the stored expense instead of a duplicate.
        headers: { 'Idempotency-Key': input.id },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['household', householdId] }),
  });
}
