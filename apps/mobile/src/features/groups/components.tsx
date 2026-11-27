import type { TFunction } from 'i18next';
import { router } from 'expo-router';
import { AlertTriangle } from 'lucide-react-native';
import { Pressable, View } from 'react-native';
import { EmptyState } from '@/components/EmptyState';
import { MoneyText } from '@/components/MoneyText';
import { Screen } from '@/components/Screen';
import { Icon } from '@/components/ui/icon';
import { Skeleton } from '@/components/ui/skeleton';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { categoryIcon, categoryLabel } from './categories';
import { timeLabel } from './dates';
import type { Category, Expense, Group, Member } from './types';

/** Members that still take part in the group (not `left`). */
export function activeMembers(group: Group): Member[] {
  return group.members.filter((m) => m.status === 'active');
}

/**
 * Display name of a member: "You" for the current user, "(left)" for members who left and
 * "Former member" for those who deleted their account (they have no name any more).
 */
export function memberName(group: Group, memberId: string, t: TFunction): string {
  if (memberId === group.my_member_id) return t('home.you');
  const member = group.members.find((m) => m.id === memberId);
  if (member?.account_deleted) return t('group.formerMember');
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

/** One expense: category icon, description, who paid, who added it and when; tap to edit. */
export function ExpenseRow({
  expense,
  group,
  category,
  t,
}: {
  expense: Expense;
  group: Group;
  /** The expense's category; undefined = "Other" (no category). */
  category?: Category;
  t: TFunction;
}) {
  const payer = memberName(group, expense.payer_member_id, t);
  const meta = [
    t('expenses.addedBy', { name: userName(group, expense.created_by_user_id, t) }),
    timeLabel(expense.created_at, currentMoneyLocale(), group.timezone),
  ].join(' · ');
  return (
    <Pressable
      accessibilityRole='button'
      onPress={() =>
        router.navigate({ pathname: '/group/[groupId]/expense/[id]', params: { groupId: group.id, id: expense.id } })
      }
      className='flex-row items-center gap-3 py-3 active:opacity-70'>
      <View
        accessible
        accessibilityLabel={category ? categoryLabel(category, t) : t('categories.other')}
        className='size-10 items-center justify-center rounded-full bg-primary/15'>
        <Icon as={categoryIcon(category)} size={20} className='text-primary' />
      </View>
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
