import { router } from 'expo-router';
import { ArrowLeftRight, ChevronsUpDown, Plus, Settings } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { MoneyText } from '@/components/MoneyText';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import { useActiveMembership, useBalance, useCategories, useGroup, useRecentExpenses } from './api';
import { activeMembers, ErrorScreen, ExpenseRow, LoadingScreen, memberName } from './components';
import { GroupsScreen } from './GroupsScreen';

/** Expenses shown in the "recent" card. */
const RECENT_COUNT = 5;

/** The active group: my running balance, suggested payments, members and recent expenses. */
export function HomeScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const groupId = me.data?.group_id;
  const group = useGroup(groupId);
  const balance = useBalance(groupId);
  const expenses = useRecentExpenses(groupId, RECENT_COUNT);
  const categories = useCategories(groupId);
  useRefreshOnFocus(groupId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    me.refetch,
    group.refetch,
    balance.refetch,
    expenses.refetch,
    categories.refetch,
  );

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.data) return <GroupsScreen embedded />;
  if (group.isPending || balance.isPending) return <LoadingScreen />;
  if (group.isError || balance.isError) {
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void group.refetch();
          void balance.refetch();
        }}
      />
    );
  }

  const g = group.data;
  const locale = currentMoneyLocale();
  const byMember = new Map(balance.data.balances.map((b) => [b.member_id, b]));
  const mine = byMember.get(g.my_member_id);
  const myNet = mine?.net_cents ?? 0;
  const categoryNames = new Map((categories.data ?? []).map((c) => [c.id, c.name]));
  const recent = expenses.data?.items ?? [];
  const mySuggestions = balance.data.suggestions.filter(
    (s) => s.from_member_id === g.my_member_id || s.to_member_id === g.my_member_id,
  );
  // Former members still show while their (zero) balance is part of the history.
  const shown = g.members.filter((m) => m.status === 'active' || (byMember.get(m.id)?.net_cents ?? 0) !== 0);

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <ScrollView
        contentContainerClassName='gap-4 px-4 py-4'
        refreshControl={<RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />}>
        <View className='flex-row items-center gap-2'>
          <Pressable
            accessibilityRole='button'
            accessibilityLabel={t('groups.switch')}
            onPress={() => router.push('/groups')}
            className='flex-1 flex-row items-center gap-2 active:opacity-70'>
            <Text className='text-2xl font-bold' role='heading' numberOfLines={1}>
              {g.name}
            </Text>
            <Icon as={ChevronsUpDown} size={18} className='text-muted-foreground' />
          </Pressable>
          <Button
            variant='ghost'
            size='icon'
            accessibilityLabel={t('group.settings')}
            onPress={() => router.push('/group/settings')}>
            <Icon as={Settings} size={20} />
          </Button>
        </View>

        <Card>
          <CardHeader>
            <Text className='text-muted-foreground'>{t('home.yourBalance')}</Text>
          </CardHeader>
          <CardContent className='gap-1'>
            <MoneyText cents={myNet} size='3xl' tone={myNet > 0 ? 'positive' : myNet < 0 ? 'negative' : 'default'} />
            <Text className='text-muted-foreground'>
              {myNet > 0
                ? t('money.youAreOwed', { amount: displayMoney(myNet, locale) })
                : myNet < 0
                  ? t('money.youOwe', { amount: displayMoney(-myNet, locale) })
                  : t('money.settled')}
            </Text>
            {mine && mine.pending_out_cents + mine.pending_in_cents > 0 ? (
              <Text className='text-sm text-muted-foreground'>
                {t('settle.pendingConfirmation', {
                  amount: displayMoney(mine.pending_out_cents + mine.pending_in_cents, locale),
                })}
              </Text>
            ) : null}
            {mySuggestions.map((s) => (
              <Text key={`${s.from_member_id}-${s.to_member_id}`} className='text-sm'>
                {t('settle.suggestion', {
                  from: memberName(g, s.from_member_id, t),
                  to: memberName(g, s.to_member_id, t),
                  amount: displayMoney(s.amount_cents, locale),
                })}
              </Text>
            ))}
            <Button variant='outline' className='mt-3' onPress={() => router.push('/group/settle')}>
              <Icon as={ArrowLeftRight} size={18} />
              <Text>{t('settle.open')}</Text>
            </Button>
          </CardContent>
        </Card>

        <Button size='lg' onPress={() => router.push('/expense/new')}>
          <Icon as={Plus} size={20} />
          <Text>{t('expenses.add')}</Text>
        </Button>

        <Card>
          <CardHeader>
            <CardTitle>{t('home.members')}</CardTitle>
          </CardHeader>
          <CardContent>
            {shown.map((m) => {
              const net = byMember.get(m.id)?.net_cents ?? 0;
              return (
                <View key={m.id} className='flex-row items-center justify-between py-2'>
                  <Text>{memberName(g, m.id, t)}</Text>
                  <MoneyText cents={net} tone={net > 0 ? 'positive' : net < 0 ? 'negative' : 'muted'} />
                </View>
              );
            })}
            {activeMembers(g).length === 1 ? (
              <Button variant='link' size='sm' onPress={() => router.push('/group/settings')}>
                <Text>{t('group.inviteSomeone')}</Text>
              </Button>
            ) : null}
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
                    group={g}
                    categoryName={e.category_id ? categoryNames.get(e.category_id) : undefined}
                    t={t}
                  />
                </View>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}
