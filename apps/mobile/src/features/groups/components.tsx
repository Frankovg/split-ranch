import type { TFunction } from 'i18next';
import { router } from 'expo-router';
import { AlertTriangle } from 'lucide-react-native';
import { Pressable, View } from 'react-native';
import { EmptyState } from '@/components/EmptyState';
import { MoneyText } from '@/components/MoneyText';
import { Screen } from '@/components/Screen';
import { Skeleton } from '@/components/ui/skeleton';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { timeLabel } from './dates';
import type { Expense, Group, Member } from './types';

/** Members that still take part in the group (not `left`). */
export function activeMembers(group: Group): Member[] {
  return group.members.filter((m) => m.status === 'active');
}

/** Display name of a member, "You" for the current user, "(left)" for former members. */
export function memberName(group: Group, memberId: string, t: TFunction): string {
  if (memberId === group.my_member_id) return t('home.you');
  const member = group.members.find((m) => m.id === memberId);
  const name = member?.display_name ?? t('home.unnamed');
  return member?.status === 'left' ? t('group.leftName', { name }) : name;
}

/** Display name of the user who created an expense (by user id, not member id). */
export function userName(group: Group, userId: string | null, t: TFunction): string {
  const member = group.members.find((m) => m.user_id === userId);
  return member ? memberName(group, member.id, t) : t('home.unnamed');
}

export function LoadingScreen() {
  return (
    <Screen>
      <Skeleton className='h-32 w-full rounded-xl' />
      <Skeleton className='h-20 w-full rounded-xl' />
      <Skeleton className='h-20 w-full rounded-xl' />
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

/** One expense: description, who paid, who added it and when, category; tap to edit. */
export function ExpenseRow({
  expense,
  group,
  categoryName,
  t,
}: {
  expense: Expense;
  group: Group;
  categoryName?: string;
  t: TFunction;
}) {
  const payer = memberName(group, expense.payer_member_id, t);
  const meta = [
    t('expenses.addedBy', { name: userName(group, expense.created_by_user_id, t) }),
    timeLabel(expense.created_at, currentMoneyLocale(), group.timezone),
    categoryName,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Pressable
      accessibilityRole='button'
      onPress={() => router.push({ pathname: '/expense/[id]', params: { id: expense.id } })}
      className='flex-row items-center gap-3 py-3 active:opacity-70'>
      <View className='flex-1 gap-0.5'>
        <Text className='font-medium' numberOfLines={2}>
          {expense.description}
        </Text>
        <Text className='text-sm text-muted-foreground'>{t('expenses.paidBy', { name: payer })}</Text>
        <Text className='text-xs text-muted-foreground'>{meta}</Text>
      </View>
      <MoneyText cents={expense.amount_cents} />
    </Pressable>
  );
}
