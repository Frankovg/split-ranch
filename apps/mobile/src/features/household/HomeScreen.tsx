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
import {
  useActiveMembership,
  useBalance,
  useCategories,
  useCreateInvitation,
  useExpenses,
  useHousehold,
  usePeriods,
} from './api';
import { activeMembers, ErrorScreen, ExpenseRow, LoadingScreen, memberName } from './components';
import { currentMonth, monthLabel } from './dates';
import { OnboardingScreen } from './OnboardingScreen';

export function HomeScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const householdId = me.membership?.household_id;
  const month = currentMonth();
  const household = useHousehold(householdId);
  const balance = useBalance(householdId, month);
  const expenses = useExpenses(householdId, month);
  const categories = useCategories(householdId);
  const invite = useCreateInvitation(householdId ?? '');
  const periods = usePeriods(householdId);

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.membership) return <OnboardingScreen />;
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
  const myNet = balance.data.balances.find((b) => b.member_id === h.my_member_id)?.net_cents ?? 0;
  const period = balance.data.period;
  const categoryName = (id: string | null) => categories.data?.find((c) => c.id === id)?.name;
  const recent = (expenses.data?.items ?? []).slice(0, 5);
  const pastMonths = (periods.data?.items ?? []).filter((p) => p.month < month);
  const refreshing = household.isRefetching || balance.isRefetching || expenses.isRefetching;

  const onInvite = () =>
    invite.mutate(undefined, {
      onSuccess: (inv) =>
        void Share.share({ message: t('home.inviteMessage', { name: h.name, code: inv.code }) }),
      onError: () => toast.error(t('home.inviteFailed')),
    });

  return (
    <SafeAreaView edges={['bottom']} className="flex-1 bg-background">
      <ScrollView
        contentContainerClassName="gap-4 px-4 py-4"
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              void me.refetch();
              void household.refetch();
              void balance.refetch();
              void expenses.refetch();
            }}
          />
        }>
        <View className="flex-row items-center justify-between">
          <Text className="text-2xl font-bold" role="heading">
            {h.name}
          </Text>
          <Badge variant="secondary">
            <Text>{t(`home.period_${period.status as 'open' | 'closed' | 'settled'}`)}</Text>
          </Badge>
        </View>

        <Card>
          <CardHeader>
            <Text className="text-muted-foreground">
              {t('home.yourBalance', { month: monthLabel(month, locale) })}
            </Text>
          </CardHeader>
          <CardContent className="gap-1">
            <MoneyText
              cents={myNet}
              size="3xl"
              tone={myNet > 0 ? 'positive' : myNet < 0 ? 'negative' : 'default'}
            />
            <Text className="text-muted-foreground">
              {myNet > 0
                ? t('money.youAreOwed', { amount: displayMoney(myNet, locale) })
                : myNet < 0
                  ? t('money.youOwe', { amount: displayMoney(-myNet, locale) })
                  : t('money.settled')}
            </Text>
            <Text className="text-sm text-muted-foreground">
              {t('home.totalSpent', { amount: displayMoney(period.total_cents, locale) })}
            </Text>
            <Button
              variant="outline"
              className="mt-3"
              onPress={() => router.push({ pathname: '/period/[month]', params: { month } })}>
              <Text>{t('period.viewMonth')}</Text>
              <Icon as={ChevronRight} size={18} />
            </Button>
          </CardContent>
        </Card>

        <Button size="lg" onPress={() => router.push('/expense/new')}>
          <Icon as={Plus} size={20} />
          <Text>{t('expenses.add')}</Text>
        </Button>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>{t('home.members')}</CardTitle>
            <Button variant="ghost" size="sm" disabled={invite.isPending} onPress={onInvite}>
              <Icon as={UserPlus} size={18} />
              <Text>{t('home.invite')}</Text>
            </Button>
          </CardHeader>
          <CardContent>
            {activeMembers(h).map((m) => {
              const net = balance.data.balances.find((b) => b.member_id === m.id)?.net_cents ?? 0;
              return (
                <View key={m.id} className="flex-row items-center justify-between py-2">
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
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>{t('home.recent')}</CardTitle>
              <Button variant="link" size="sm" onPress={() => router.push('/expenses')}>
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
                    categoryName={categoryName(e.category_id)}
                    t={t}
                  />
                </View>
              ))}
            </CardContent>
          </Card>
        ) : null}

        {pastMonths.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>{t('period.pastMonths')}</CardTitle>
            </CardHeader>
            <CardContent>
              {pastMonths.map((p, i) => (
                <View key={p.id}>
                  {i > 0 ? <Separator /> : null}
                  <Pressable
                    accessibilityRole="button"
                    onPress={() =>
                      router.push({ pathname: '/period/[month]', params: { month: p.month } })
                    }
                    className="flex-row items-center gap-3 py-3 active:opacity-70">
                    <Text className="flex-1 capitalize">{monthLabel(p.month, locale)}</Text>
                    <Badge variant={p.status === 'settled' ? 'default' : 'secondary'}>
                      <Text>{t(`home.period_${p.status}`)}</Text>
                    </Badge>
                    <MoneyText cents={p.total_cents} />
                    <Icon as={ChevronRight} size={18} className="text-muted-foreground" />
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
