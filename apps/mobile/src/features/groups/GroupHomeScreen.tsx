import { router, Stack } from 'expo-router';
import { ArrowLeftRight, ReceiptText } from 'lucide-react-native';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Pressable, RefreshControl, SectionList, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Collapsible, CollapsibleChevron } from '@/components/Collapsible';
import { EmptyState } from '@/components/EmptyState';
import { Fab, FAB_CLEARANCE } from '@/components/Fab';
import { MoneyText } from '@/components/MoneyText';
import { ScreenBackground } from '@/components/ScreenBackground';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import { useBalance, useCategories, useExpensesInfinite, useGroup, useSummary } from './api';
import { categoriesById } from './categories';
import { activeMembers, ErrorScreen, ExpenseRow, LoadingScreen, memberName } from './components';
import { dayHeader, groupByDay } from './dates';
import { GroupHeaderActions } from './GroupHeaderActions';
import { useGroupId } from './route';
import type { Group, GroupBalance } from './types';

/** No date filter: the group home lists every expense, newest first. */
const ALL_EXPENSES = {};

/**
 * One group: a card with my balance, my suggested payments and every member's net, then
 * all the group's expenses grouped by day. The centred "+" adds an expense.
 */
export function GroupHomeScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const group = useGroup(groupId);
  const balance = useBalance(groupId);
  const expenses = useExpensesInfinite(groupId, ALL_EXPENSES);
  const categories = useCategories(groupId);
  const summary = useSummary(groupId, ALL_EXPENSES);
  useRefreshOnFocus(groupId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    group.refetch,
    balance.refetch,
    expenses.refetch,
    categories.refetch,
    summary.refetch,
  );

  if (group.isPending || balance.isPending || expenses.isPending) return <LoadingScreen />;
  if (group.isError || balance.isError || expenses.isError) {
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void group.refetch();
          void balance.refetch();
          void expenses.refetch();
        }}
      />
    );
  }

  const g = group.data;
  const locale = currentMoneyLocale();
  const categoryById = categoriesById(categories.data);
  const sections = groupByDay(expenses.data.pages.flatMap((page) => page.items));
  const loadMore = () => {
    // Guard from the TanStack docs: fetchNextPage while a refetch runs can drop pages.
    if (expenses.hasNextPage && !expenses.isFetching) void expenses.fetchNextPage();
  };

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <Stack.Screen
        options={{ title: g.name, headerRight: () => <GroupHeaderActions groupId={g.id} /> }}
      />
      <ScreenBackground />
      <SectionList
        sections={sections}
        keyExtractor={(e) => e.id}
        stickySectionHeadersEnabled={false}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        contentContainerClassName='px-4 pt-4'
        contentContainerStyle={{ paddingBottom: FAB_CLEARANCE }}
        refreshControl={
          <RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />
        }
        ListHeaderComponent={
          <View className='gap-4 pb-2'>
            <BalanceCard group={g} balance={balance.data} />
            <ExpenseTotals
              mine={
                summary.data?.by_payer.find((p) => p.member_id === g.my_member_id)?.total_cents ?? 0
              }
              total={summary.data?.total_cents}
            />
          </View>
        }
        renderSectionHeader={({ section }) => (
          <Text
            className='pt-4 pb-1 text-sm font-semibold capitalize text-muted-foreground'
            role='heading'
          >
            {dayHeader(section.day, locale)}
          </Text>
        )}
        ItemSeparatorComponent={Separator}
        ListFooterComponent={
          expenses.isFetchingNextPage ? (
            <View className='py-4'>
              <ActivityIndicator />
            </View>
          ) : undefined
        }
        ListEmptyComponent={
          <EmptyState
            icon={ReceiptText}
            title={t('expenses.empty')}
            body={t('expenses.emptyBody')}
          />
        }
        renderItem={({ item }) => (
          <ExpenseRow
            expense={item}
            group={g}
            category={item.category_id ? categoryById.get(item.category_id) : undefined}
            t={t}
          />
        )}
      />
      <Fab
        label={t('expenses.add')}
        onPress={() =>
          router.push({ pathname: '/group/[groupId]/expense/new', params: { groupId: g.id } })
        }
      />
    </SafeAreaView>
  );
}

/**
 * Heading of the expense list: what I paid on the left, the group's total on the right.
 * Both count shared expenses only (personal ones stay out, as in the summary endpoint).
 * Amounts appear once the summary loads so the list never waits for it.
 */
function ExpenseTotals({ mine, total }: { mine: number; total: number | undefined }) {
  const { t } = useTranslation();
  return (
    <View className='flex-row items-end justify-between gap-3'>
      <View className='flex-1 gap-0.5'>
        <Text className='text-sm text-muted-foreground'>{t('expenses.myExpenses')}</Text>
        {total === undefined ? null : (
          <MoneyText cents={mine} size='lg' accessibilityPrefix={t('expenses.myExpenses')} />
        )}
      </View>
      <View className='flex-1 items-end gap-0.5'>
        <Text className='text-sm text-muted-foreground'>{t('expenses.totalExpenses')}</Text>
        {total === undefined ? null : (
          <MoneyText cents={total} size='lg' accessibilityPrefix={t('expenses.totalExpenses')} />
        )}
      </View>
    </View>
  );
}

/**
 * My balance (headline, always visible; tapping it folds the rest), then what is pending,
 * my suggested payments and every member's net.
 */
function BalanceCard({ group, balance }: { group: Group; balance: GroupBalance }) {
  const { t } = useTranslation();
  // Starts folded so the expense list gets the space.
  const [expanded, setExpanded] = useState(false);
  const locale = currentMoneyLocale();
  const byMember = new Map(balance.balances.map((b) => [b.member_id, b]));
  const mine = byMember.get(group.my_member_id);
  const myNet = mine?.net_cents ?? 0;
  const pending = mine ? mine.pending_out_cents + mine.pending_in_cents : 0;
  const mySuggestions = balance.suggestions.filter(
    (s) => s.from_member_id === group.my_member_id || s.to_member_id === group.my_member_id,
  );
  // Former members still show while their (zero) balance is part of the history.
  const shown = group.members.filter(
    (m) => m.status === 'active' || (byMember.get(m.id)?.net_cents ?? 0) !== 0,
  );
  const alone = activeMembers(group).length === 1;

  return (
    <Card className='gap-0 py-0'>
      <Pressable
        role='button'
        aria-expanded={expanded}
        accessibilityHint={t(expanded ? 'home.collapseBalance' : 'home.expandBalance')}
        onPress={() => setExpanded((v) => !v)}
        className='flex-row items-start gap-3 px-4 pt-4 pb-3 active:opacity-70'
      >
        <View className='flex-1 gap-1'>
          <Text className='text-muted-foreground'>{t('home.yourBalance')}</Text>
          <MoneyText
            cents={myNet}
            size='3xl'
            tone={myNet > 0 ? 'positive' : myNet < 0 ? 'negative' : 'default'}
          />
          <Text className='text-muted-foreground'>
            {myNet > 0
              ? t('money.youAreOwed', { amount: displayMoney(myNet, locale) })
              : myNet < 0
                ? t('money.youOwe', { amount: displayMoney(-myNet, locale) })
                : t('money.settled')}
          </Text>
        </View>
        <CollapsibleChevron expanded={expanded} />
      </Pressable>
      <Collapsible expanded={expanded}>
        <CardContent className='gap-1 px-4 pb-3'>
          {pending > 0 ? (
            <Text className='text-sm text-muted-foreground'>
              {t('settle.pendingConfirmation', { amount: displayMoney(pending, locale) })}
            </Text>
          ) : null}
          {mySuggestions.map((s) => (
            <Text key={`${s.from_member_id}-${s.to_member_id}`} className='text-sm'>
              {t('settle.suggestion', {
                from: memberName(group, s.from_member_id, t),
                to: memberName(group, s.to_member_id, t),
                amount: displayMoney(s.amount_cents, locale),
              })}
            </Text>
          ))}
        </CardContent>
        <Separator />
        <CardContent className='px-4 py-2'>
          <Text className='pt-1 pb-1 text-sm font-semibold text-muted-foreground' role='heading'>
            {t('home.members')}
          </Text>
          {shown.map((m) => {
            const net = byMember.get(m.id)?.net_cents ?? 0;
            return (
              <View key={m.id} className='min-h-11 flex-row items-center justify-between gap-3'>
                <Text className='flex-1' numberOfLines={1}>
                  {memberName(group, m.id, t)}
                </Text>
                <MoneyText
                  cents={net}
                  tone={net > 0 ? 'positive' : net < 0 ? 'negative' : 'muted'}
                />
              </View>
            );
          })}
          {alone ? (
            <Button
              variant='link'
              size='sm'
              className='self-start px-0'
              onPress={() =>
                router.push({
                  pathname: '/group/[groupId]/settings',
                  params: { groupId: group.id },
                })
              }
            >
              <Text>{t('group.inviteSomeone')}</Text>
            </Button>
          ) : null}
        </CardContent>
        <View className='px-4 pb-4'>
          <Button
            variant='outline'
            onPress={() =>
              router.push({ pathname: '/group/[groupId]/settle', params: { groupId: group.id } })
            }
          >
            <Icon as={ArrowLeftRight} size={18} />
            <Text>{t('settle.open')}</Text>
          </Button>
        </View>
      </Collapsible>
    </Card>
  );
}
