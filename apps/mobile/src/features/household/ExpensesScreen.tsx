import { router } from 'expo-router';
import { Plus, ReceiptText } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { FlatList, RefreshControl, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EmptyState } from '@/components/EmptyState';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { useActiveMembership, useBalance, useCategories, useExpenses, useHousehold } from './api';
import { ErrorScreen, ExpenseRow, LoadingScreen } from './components';
import { OnboardingScreen } from './OnboardingScreen';

/** Expenses of the current (latest) period, newest first. */
export function ExpensesScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const householdId = me.membership?.household_id;
  const household = useHousehold(householdId);
  const expenses = useExpenses(householdId, 'current');
  const period = useBalance(householdId, 'current').data?.period;
  const categories = useCategories(householdId);

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.membership) return <OnboardingScreen />;
  if (household.isPending || expenses.isPending) return <LoadingScreen />;
  if (household.isError || expenses.isError) {
    return <ErrorScreen t={t} onRetry={() => void expenses.refetch()} />;
  }

  const h = household.data;
  const categoryName = (id: string | null) => categories.data?.find((c) => c.id === id)?.name;

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <FlatList
        data={expenses.data.items}
        keyExtractor={(e) => e.id}
        contentContainerClassName='px-4 py-4'
        refreshControl={
          <RefreshControl refreshing={expenses.isRefetching} onRefresh={() => void expenses.refetch()} />
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
          <ExpenseRow expense={item} household={h} categoryName={categoryName(item.category_id)} t={t} />
        )}
      />
    </SafeAreaView>
  );
}
