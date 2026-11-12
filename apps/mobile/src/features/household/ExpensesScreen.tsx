import { router } from 'expo-router';
import { Plus, ReceiptText } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, RefreshControl, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EmptyState } from '@/components/EmptyState';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import {
  useActiveMembership,
  useBalance,
  useCategories,
  useExpensesInfinite,
  useHousehold,
} from './api';
import { ErrorScreen, ExpenseRow, LoadingScreen } from './components';
import { OnboardingScreen } from './OnboardingScreen';

/** Expenses of the current (latest) period, newest first, loaded page by page on scroll. */
export function ExpensesScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const householdId = me.data?.household_id;
  const household = useHousehold(householdId);
  const expenses = useExpensesInfinite(householdId, 'current');
  const balance = useBalance(householdId, 'current');
  const period = balance.data?.period;
  const categories = useCategories(householdId);
  useRefreshOnFocus(householdId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    expenses.refetch,
    balance.refetch,
    categories.refetch,
  );

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.data) return <OnboardingScreen />;
  if (household.isPending || expenses.isPending) return <LoadingScreen />;
  if (household.isError || expenses.isError) {
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void household.refetch();
          void expenses.refetch();
        }}
      />
    );
  }

  const h = household.data;
  const categoryNames = new Map((categories.data ?? []).map((c) => [c.id, c.name]));
  const items = expenses.data.pages.flatMap((page) => page.items);
  const loadMore = () => {
    // Guard from the TanStack docs: fetchNextPage while a refetch runs can drop pages.
    if (expenses.hasNextPage && !expenses.isFetching) void expenses.fetchNextPage();
  };

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <FlatList
        data={items}
        keyExtractor={(e) => e.id}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        ListFooterComponent={
          expenses.isFetchingNextPage ? (
            <View className='py-4'>
              <ActivityIndicator />
            </View>
          ) : undefined
        }
        contentContainerClassName='px-4 py-4'
        refreshControl={
          <RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />
        }
        ListHeaderComponent={
          <View className='gap-3 pb-2'>
            {period ? (
              <Text className='text-lg font-semibold' role='heading'>
                {t('period.title', { seq: period.seq })}
              </Text>
            ) : null}
            {period?.status === 'open' ? (
              <Button onPress={() => router.push('/expense/new')}>
                <Icon as={Plus} size={20} />
                <Text>{t('expenses.add')}</Text>
              </Button>
            ) : null}
          </View>
        }
        ItemSeparatorComponent={Separator}
        ListEmptyComponent={
          <EmptyState icon={ReceiptText} title={t('expenses.empty')} body={t('expenses.emptyBody')} />
        }
        renderItem={({ item }) => (
          <ExpenseRow
            expense={item}
            household={h}
            categoryName={item.category_id ? categoryNames.get(item.category_id) : undefined}
            t={t}
          />
        )}
      />
    </SafeAreaView>
  );
}
