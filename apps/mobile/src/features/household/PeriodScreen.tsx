import { type ReactNode, useState } from 'react';
import { router, Stack } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Alert, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { toast } from 'sonner-native';
import { MoneyText } from '@/components/MoneyText';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import {
  useActiveMembership,
  useBalance,
  useClosePeriod,
  useHousehold,
  usePeriods,
  useReopenPeriod,
  useSettlement,
  useTransferAction,
} from './api';
import { activeMembers, ErrorScreen, LoadingScreen, memberName } from './components';
import { periodDates } from './dates';
import { OnboardingScreen } from './OnboardingScreen';
import { StartPeriodButton } from './StartPeriodButton';
import type { Household, Period, PeriodKey, Transfer } from './types';

/** One period: balances, close, settlement transfers (sent → confirmed), next period, reopen. */
export function PeriodScreen({ periodKey }: { periodKey: PeriodKey }) {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const householdId = me.data?.household_id;
  const household = useHousehold(householdId);
  const balance = useBalance(householdId, periodKey);
  const settlement = useSettlement(householdId, periodKey);
  const periods = usePeriods(householdId);
  useRefreshOnFocus(householdId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    balance.refetch,
    settlement.refetch,
    periods.refetch,
  );
  const loaded = settlement.data?.period;
  const title = loaded ? t('period.title', { seq: loaded.seq }) : '';
  // Only the latest period can be reopened or followed by a new one.
  const latestSeq = periods.data?.items[0]?.seq;

  let body: ReactNode;
  if (me.isPending) {
    body = <LoadingScreen />;
  } else if (me.isError) {
    body = <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  } else if (!me.data) {
    // No household (e.g. deep link after leaving it): the period queries never run.
    body = <OnboardingScreen />;
  } else if (household.isPending || balance.isPending || settlement.isPending) {
    body = <LoadingScreen />;
  } else if (household.isError || balance.isError || settlement.isError) {
    body = (
      <ErrorScreen
        t={t}
        onRetry={() => {
          if (household.isError) void household.refetch();
          if (balance.isError) void balance.refetch();
          if (settlement.isError) void settlement.refetch();
        }}
      />
    );
  } else {
    const h = household.data;
    const period = settlement.data.period;
    const isLatest = latestSeq === undefined || latestSeq === period.seq;
    const balanceByMember = new Map(balance.data.balances.map((b) => [b.member_id, b]));
    const locale = currentMoneyLocale();
    body = (
      <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
        <ScrollView
          contentContainerClassName='gap-4 px-4 py-4'
          keyboardShouldPersistTaps='handled'
          refreshControl={
            <RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />
          }>
          <SummaryCard household={h} period={period} title={title} />

          <Card>
            <CardHeader>
              <CardTitle>{t('period.balances')}</CardTitle>
            </CardHeader>
            <CardContent>
              {activeMembers(h).map((m, i) => {
                const b = balanceByMember.get(m.id);
                const net = b?.net_cents ?? 0;
                return (
                  <View key={m.id}>
                    {i > 0 ? <Separator /> : null}
                    <View className='flex-row items-center gap-3 py-3'>
                      <View className='flex-1 gap-0.5'>
                        <Text className='font-medium'>{memberName(h, m.id, t)}</Text>
                        <Text className='text-sm text-muted-foreground'>
                          {t('period.paidOwed', {
                            paid: displayMoney(b?.paid_cents ?? 0, locale),
                            owed: displayMoney(b?.owed_cents ?? 0, locale),
                          })}
                        </Text>
                      </View>
                      <MoneyText
                        cents={net}
                        tone={net > 0 ? 'positive' : net < 0 ? 'negative' : 'muted'}
                      />
                    </View>
                  </View>
                );
              })}
            </CardContent>
          </Card>

          {period.status === 'open' ? (
            <CloseSection household={h} period={period} title={title} />
          ) : (
            <>
              <TransfersCard household={h} transfers={settlement.data.transfers} period={period} />
              {isLatest ? (
                <StartPeriodButton
                  householdId={h.id}
                  latest={period}
                  onStarted={() => router.dismissTo('/')}
                />
              ) : null}
              {isLatest ? <ReopenSection household={h} period={period} /> : null}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title }} />
      {body}
    </>
  );
}

function SummaryCard({ household, period, title }: { household: Household; period: Period; title: string }) {
  const { t } = useTranslation();
  const dates = periodDates(period, currentMoneyLocale(), household.timezone);
  return (
    <Card>
      <CardHeader className='flex-row items-center justify-between'>
        <CardTitle>{title}</CardTitle>
        <Badge variant={period.status === 'settled' ? 'default' : 'secondary'}>
          <Text>{t(`home.period_${period.status}`)}</Text>
        </Badge>
      </CardHeader>
      <CardContent className='gap-1'>
        <Text className='text-muted-foreground'>{t('period.total')}</Text>
        <MoneyText cents={period.total_cents} size='3xl' />
        <Text className='text-sm text-muted-foreground'>
          {dates.to
            ? t('period.range', { from: dates.from, to: dates.to })
            : t('period.since', { from: dates.from })}
        </Text>
        {period.status === 'open' ? (
          <Text className='text-sm text-muted-foreground'>{t('period.manualClose')}</Text>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CloseSection({ household, period, title }: { household: Household; period: Period; title: string }) {
  const { t } = useTranslation();
  // Any member closes the period; the settlement is computed right away.
  const close = useClosePeriod(household.id, period.seq);
  const onClose = () =>
    Alert.alert(t('period.closeTitle', { title }), t('period.closeBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('period.closeNow'),
        onPress: () => close.mutate(undefined, { onError: () => toast.error(t('period.closeFailed')) }),
      },
    ]);
  return (
    <Button variant='outline' disabled={close.isPending} onPress={onClose}>
      <Text>{t('period.closeNow')}</Text>
    </Button>
  );
}

function TransfersCard({
  household,
  transfers,
  period,
}: {
  household: Household;
  transfers: Transfer[];
  period: Period;
}) {
  const { t } = useTranslation();
  const action = useTransferAction(household.id);
  const visible = transfers.filter((tr) => tr.status !== 'cancelled');
  const run = (transferId: string, kind: 'sent' | 'confirm') =>
    action.mutate({ transferId, action: kind }, { onError: () => toast.error(t('period.actionFailed')) });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('period.payments')}</CardTitle>
      </CardHeader>
      <CardContent className='gap-1'>
        {visible.length === 0 ? <Text className='text-muted-foreground'>{t('period.noPayments')}</Text> : null}
        {visible.map((tr, i) => {
          const iPay = tr.from_member_id === household.my_member_id;
          const iReceive = tr.to_member_id === household.my_member_id;
          const canSend = iPay && (tr.status === 'pending' || tr.status === 'disputed');
          const canConfirm = iReceive && tr.status !== 'confirmed';
          return (
            <View key={tr.id}>
              {i > 0 ? <Separator /> : null}
              <View className='gap-2 py-3'>
                <View className='flex-row items-center gap-3'>
                  <View className='flex-1 gap-1'>
                    <Text className='font-medium'>
                      {t('period.pays', {
                        from: memberName(household, tr.from_member_id, t),
                        to: memberName(household, tr.to_member_id, t),
                      })}
                    </Text>
                    <Badge
                      variant={tr.status === 'confirmed' ? 'default' : 'outline'}
                      className='self-start'>
                      <Text>{t(`period.status_${tr.status}`)}</Text>
                    </Badge>
                  </View>
                  <MoneyText cents={tr.amount_cents} size='lg' />
                </View>
                {canSend ? (
                  <Button size='sm' disabled={action.isPending} onPress={() => run(tr.id, 'sent')}>
                    <Text>{t('period.markSent')}</Text>
                  </Button>
                ) : null}
                {canConfirm ? (
                  <Button size='sm' disabled={action.isPending} onPress={() => run(tr.id, 'confirm')}>
                    <Text>{t('period.confirmReceived')}</Text>
                  </Button>
                ) : null}
              </View>
            </View>
          );
        })}
        {period.status === 'settled' ? (
          <Text className='pt-2 text-sm text-muted-foreground'>{t('period.settledNote')}</Text>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ReopenSection({ household, period }: { household: Household; period: Period }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const reopen = useReopenPeriod(household.id, period.seq);

  if (household.my_role !== 'admin') return null;
  if (period.locked) {
    return <Text className='text-center text-sm text-muted-foreground'>{t('period.lockedNote')}</Text>;
  }
  if (!open) {
    return (
      <Button variant='ghost' onPress={() => setOpen(true)}>
        <Text>{t('period.reopen')}</Text>
      </Button>
    );
  }
  return (
    <Card>
      <CardContent className='gap-3 pt-6'>
        <Input
          value={reason}
          onChangeText={setReason}
          placeholder={t('period.reopenReason')}
          accessibilityLabel={t('period.reopenReason')}
          maxLength={280}
        />
        <Button
          variant='outline'
          disabled={reopen.isPending || reason.trim().length < 5}
          onPress={() =>
            reopen.mutate(reason.trim(), {
              onSuccess: () => {
                setOpen(false);
                setReason('');
              },
              onError: () => toast.error(t('period.reopenFailed')),
            })
          }>
          <Text>{t('period.reopen')}</Text>
        </Button>
      </CardContent>
    </Card>
  );
}
