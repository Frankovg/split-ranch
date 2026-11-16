import { useState } from 'react';
import { router } from 'expo-router';
import { Plus, ReceiptText } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, RefreshControl, SectionList, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EmptyState } from '@/components/EmptyState';
import { MoneyText } from '@/components/MoneyText';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import { useActiveMembership, useCategories, useExpensesInfinite, useGroup, useSummary } from './api';
import { ErrorScreen, ExpenseRow, LoadingScreen, memberName } from './components';
import { dayHeader, groupByDay, monthLabel, monthRange } from './dates';
import { GroupsScreen } from './GroupsScreen';
import type { DateRange, Group, Summary } from './types';

type RangeKey = 'thisMonth' | 'lastMonth' | 'all';

function rangeFor(key: RangeKey, timeZone: string): DateRange {
  if (key === 'all') return {};
  return monthRange(timeZone, key === 'thisMonth' ? 0 : -1);
}

/** Expenses grouped by day, filtered by month; the header shows that range's totals. */
export function ExpensesScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const groupId = me.data?.group_id;
  const group = useGroup(groupId);
  const [rangeKey, setRangeKey] = useState<RangeKey>('thisMonth');
  const range = group.data ? rangeFor(rangeKey, group.data.timezone) : {};
  const expenses = useExpensesInfinite(group.data ? groupId : undefined, range);
  const summary = useSummary(group.data ? groupId : undefined, range);
  const categories = useCategories(groupId);
  useRefreshOnFocus(groupId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    expenses.refetch,
    summary.refetch,
    categories.refetch,
  );

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.data) return <GroupsScreen embedded />;
  if (group.isPending || expenses.isPending) return <LoadingScreen />;
  if (group.isError || expenses.isError) {
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void group.refetch();
          void expenses.refetch();
        }}
      />
    );
  }

  const g = group.data;
  const locale = currentMoneyLocale();
  const categoryNames = new Map((categories.data ?? []).map((c) => [c.id, c.name]));
  const sections = groupByDay(expenses.data.pages.flatMap((page) => page.items));
  const loadMore = () => {
    // Guard from the TanStack docs: fetchNextPage while a refetch runs can drop pages.
    if (expenses.hasNextPage && !expenses.isFetching) void expenses.fetchNextPage();
  };

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <SectionList
        sections={sections}
        keyExtractor={(e) => e.id}
        stickySectionHeadersEnabled={false}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        contentContainerClassName='px-4 py-4'
        refreshControl={<RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />}
        ListHeaderComponent={
          <View className='gap-3 pb-2'>
            <ToggleGroup
              type='single'
              variant='outline'
              value={rangeKey}
              onValueChange={(v) => v && setRangeKey(v as RangeKey)}
              className='flex-wrap justify-start gap-2'>
              {(['thisMonth', 'lastMonth', 'all'] as const).map((key) => (
                <ToggleGroupItem key={key} value={key} className='rounded-md border-l'>
                  <Text>{t(`expenses.range.${key}`)}</Text>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            {summary.data ? (
              <SummaryCard group={g} summary={summary.data} range={range} categoryNames={categoryNames} />
            ) : null}
            <Button onPress={() => router.push('/expense/new')}>
              <Icon as={Plus} size={20} />
              <Text>{t('expenses.add')}</Text>
            </Button>
          </View>
        }
        renderSectionHeader={({ section }) => (
          <Text className='pt-4 pb-1 text-sm font-semibold capitalize text-muted-foreground' role='heading'>
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
          <EmptyState icon={ReceiptText} title={t('expenses.empty')} body={t('expenses.emptyBody')} />
        }
        renderItem={({ item }) => (
          <ExpenseRow
            expense={item}
            group={g}
            categoryName={item.category_id ? categoryNames.get(item.category_id) : undefined}
            t={t}
          />
        )}
      />
    </SafeAreaView>
  );
}

function SummaryCard({
  group,
  summary,
  range,
  categoryNames,
}: {
  group: Group;
  summary: Summary;
  range: DateRange;
  categoryNames: Map<string, string>;
}) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const title = range.from ? t('expenses.spentIn', { month: monthLabel(range.from, locale) }) : t('expenses.spentAll');
  return (
    <Card>
      <CardContent className='gap-2 pt-4'>
        <Text className='text-muted-foreground'>{title}</Text>
        <MoneyText cents={summary.total_cents} size='3xl' />
        {summary.by_category.slice(0, 4).map((c) => (
          <View key={c.category_id ?? 'none'} className='flex-row justify-between'>
            <Text className='text-sm'>
              {c.category_id ? (categoryNames.get(c.category_id) ?? '—') : t('expenses.noCategory')}
            </Text>
            <Text className='text-sm text-muted-foreground'>{displayMoney(c.total_cents, locale)}</Text>
          </View>
        ))}
        {summary.by_payer.length > 1 ? (
          <Text className='text-sm text-muted-foreground'>
            {summary.by_payer
              .map((p) =>
                t('expenses.payerTotal', {
                  name: memberName(group, p.member_id, t),
                  amount: displayMoney(p.total_cents, locale),
                }),
              )
              .join(' · ')}
          </Text>
        ) : null}
      </CardContent>
    </Card>
  );
}
