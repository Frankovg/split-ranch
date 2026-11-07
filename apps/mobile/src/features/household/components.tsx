import type { TFunction } from 'i18next';
import { AlertTriangle } from 'lucide-react-native';
import { View } from 'react-native';
import { EmptyState } from '@/components/EmptyState';
import { MoneyText } from '@/components/MoneyText';
import { Screen } from '@/components/Screen';
import { Skeleton } from '@/components/ui/skeleton';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { dayLabel } from './dates';
import type { Expense, Household, Member } from './types';

/** Members that still take part in the household (not `left`). */
export function activeMembers(household: Household): Member[] {
  return household.members.filter((m) => m.status !== 'left');
}

/** Display name of a member, "You" for the current user. */
export function memberName(household: Household, memberId: string, t: TFunction): string {
  if (memberId === household.my_member_id) return t('home.you');
  const member = household.members.find((m) => m.id === memberId);
  return member?.display_name ?? t('home.unnamed');
}

export function LoadingScreen() {
  return (
    <Screen>
      <Skeleton className="h-32 w-full rounded-xl" />
      <Skeleton className="h-20 w-full rounded-xl" />
      <Skeleton className="h-20 w-full rounded-xl" />
    </Screen>
  );
}

export function ErrorScreen({ t, onRetry }: { t: TFunction; onRetry: () => void }) {
  return (
    <Screen>
      <EmptyState
        icon={AlertTriangle}
        title={t('common.error')}
        action={{ label: t('common.retry'), onPress: onRetry }}
      />
    </Screen>
  );
}

export function ExpenseRow({
  expense,
  household,
  categoryName,
  t,
}: {
  expense: Expense;
  household: Household;
  categoryName?: string;
  t: TFunction;
}) {
  const payer = memberName(household, expense.payer_member_id, t);
  const meta = [dayLabel(expense.expense_date, currentMoneyLocale()), categoryName]
    .filter(Boolean)
    .join(' · ');
  return (
    <View className="flex-row items-center gap-3 py-3">
      <View className="flex-1 gap-0.5">
        <Text className="font-medium" numberOfLines={2}>
          {expense.description}
        </Text>
        <Text className="text-sm text-muted-foreground">
          {t('expenses.paidBy', { name: payer })} · {meta}
        </Text>
      </View>
      <MoneyText cents={expense.amount_cents} />
    </View>
  );
}
