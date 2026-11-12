import { router } from 'expo-router';
import { ChevronRight, Plus, UserPlus } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, RefreshControl, ScrollView, Share, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { toast } from 'sonner-native';
import { MoneyText } from '@/components/MoneyText';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import {
  useActiveMembership,
  useBalance,
  useCategories,
  useCreateInvitation,
  useHousehold,
  usePeriods,
  useRecentExpenses,
} from './api';
import { activeMembers, ErrorScreen, ExpenseRow, LoadingScreen, memberName } from './components';
import { periodDates } from './dates';
import { OnboardingScreen } from './OnboardingScreen';
import { StartPeriodButton } from './StartPeriodButton';

/** Expenses shown in the "recent" card. */
const RECENT_COUNT = 5;

export function HomeScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const householdId = me.data?.household_id;
  const household = useHousehold(householdId);
  // "current" = the latest period: the open one, or the last closed one until someone
  // starts the next period.
  const balance = useBalance(householdId, 'current');
  const expenses = useRecentExpenses(householdId, 'current', RECENT_COUNT);
  const categories = useCategories(householdId);
  const invite = useCreateInvitation(householdId ?? '');
  const periods = usePeriods(householdId);
  useRefreshOnFocus(householdId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    me.refetch,
    household.refetch,
    balance.refetch,
    expenses.refetch,
    categories.refetch,
    periods.refetch,
  );

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.data) return <OnboardingScreen />;
  if (household.isPending || balance.isPending) return <LoadingScreen />;
  if (household.isError || balance.isError) {
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void household.refetch();
          void balance.refetch();
        }}
      />
    );
  }

  const h = household.data;
  const locale = currentMoneyLocale();
  const netByMember = new Map(balance.data.balances.map((b) => [b.member_id, b.net_cents]));
  const myNet = netByMember.get(h.my_member_id) ?? 0;
  const period = balance.data.period;
  const categoryNames = new Map((categories.data ?? []).map((c) => [c.id, c.name]));
  const recent = expenses.data?.items ?? [];
  const pastPeriods = (periods.data?.items ?? []).filter((p) => p.seq < period.seq);
  const isOpen = period.status === 'open';
  const dates = periodDates(period, locale, h.timezone);

  const onInvite = () =>
    invite.mutate(undefined, {
      onSuccess: async (inv) => {
        try {
          await Share.share({ message: t('home.inviteMessage', { name: h.name, code: inv.code }) });
        } catch (error) {
          console.warn('Share failed', error);
        }
      },
      onError: () => toast.error(t('home.inviteFailed')),
    });

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <ScrollView
        contentContainerClassName='gap-4 px-4 py-4'
        refreshControl={
          <RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />
        }>
        <View className='flex-row items-center justify-between'>
          <Text className='text-2xl font-bold' role='heading'>
            {h.name}
          </Text>
          <Badge variant='secondary'>
            <Text>{t(`home.period_${period.status as 'open' | 'closed' | 'settled'}`)}</Text>
          </Badge>
        </View>

        <Card>
          <CardHeader>
            <Text className='text-muted-foreground'>
              {t('home.yourBalance', { seq: period.seq })}
            </Text>
            <Text className='text-sm text-muted-foreground'>
              {dates.to
                ? t('period.range', { from: dates.from, to: dates.to })
                : t('period.since', { from: dates.from })}
            </Text>
          </CardHeader>
          <CardContent className='gap-1'>
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
            <Text className='text-sm text-muted-foreground'>
              {t('home.totalSpent', { amount: displayMoney(period.total_cents, locale) })}
            </Text>
            <Button
              variant='outline'
              className='mt-3'
              onPress={() =>
                router.push({ pathname: '/period/[seq]', params: { seq: String(period.seq) } })
              }>
              <Text>{t(isOpen ? 'period.viewPeriod' : 'period.viewPayments')}</Text>
              <Icon as={ChevronRight} size={18} />
            </Button>
          </CardContent>
        </Card>

        {isOpen ? (
          <Button size='lg' onPress={() => router.push('/expense/new')}>
            <Icon as={Plus} size={20} />
            <Text>{t('expenses.add')}</Text>
          </Button>
        ) : (
          <View className='gap-2'>
            <Text className='text-center text-sm text-muted-foreground'>
              {t('period.noOpenPeriod', { seq: period.seq })}
            </Text>
            <StartPeriodButton householdId={h.id} latest={period} />
          </View>
        )}

        <Card>
          <CardHeader className='flex-row items-center justify-between'>
            <CardTitle>{t('home.members')}</CardTitle>
            <Button variant='ghost' size='sm' disabled={invite.isPending} onPress={onInvite}>
              <Icon as={UserPlus} size={18} />
              <Text>{t('home.invite')}</Text>
            </Button>
          </CardHeader>
          <CardContent>
            {activeMembers(h).map((m) => {
              const net = netByMember.get(m.id) ?? 0;
              return (
                <View key={m.id} className='flex-row items-center justify-between py-2'>
                  <Text>{memberName(h, m.id, t)}</Text>
                  <MoneyText
                    cents={net}
                    tone={net > 0 ? 'positive' : net < 0 ? 'negative' : 'muted'}
                  />
                </View>
              );
            })}
          </CardContent>
        </Card>

        {recent.length > 0 ? (
          <Card>
            <CardHeader className='flex-row items-center justify-between'>
              <CardTitle>{t('home.recent')}</CardTitle>
              <Button variant='link' size='sm' onPress={() => router.push('/expenses')}>
                <Text>{t('home.seeAll')}</Text>
              </Button>
            </CardHeader>
            <CardContent>
              {recent.map((e, i) => (
                <View key={e.id}>
                  {i > 0 ? <Separator /> : null}
                  <ExpenseRow
                    expense={e}
                    household={h}
                    categoryName={e.category_id ? categoryNames.get(e.category_id) : undefined}
                    t={t}
                  />
                </View>
              ))}
            </CardContent>
          </Card>
        ) : null}

        {pastPeriods.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>{t('period.pastPeriods')}</CardTitle>
            </CardHeader>
            <CardContent>
              {pastPeriods.map((p, i) => (
                <View key={p.id}>
                  {i > 0 ? <Separator /> : null}
                  <Pressable
                    accessibilityRole='button'
                    onPress={() =>
                      router.push({ pathname: '/period/[seq]', params: { seq: String(p.seq) } })
                    }
                    className='flex-row items-center gap-3 py-3 active:opacity-70'>
                    <View className='flex-1 gap-0.5'>
                      <Text>{t('period.title', { seq: p.seq })}</Text>
                      <Text className='text-sm text-muted-foreground'>
                        {(() => {
                          const d = periodDates(p, locale, h.timezone);
                          return d.to
                            ? t('period.range', { from: d.from, to: d.to })
                            : t('period.since', { from: d.from });
                        })()}
                      </Text>
                    </View>
                    <Badge variant={p.status === 'settled' ? 'default' : 'secondary'}>
                      <Text>{t(`home.period_${p.status}`)}</Text>
                    </Badge>
                    <MoneyText cents={p.total_cents} />
                    <Icon as={ChevronRight} size={18} className='text-muted-foreground' />
                  </Pressable>
                </View>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}
