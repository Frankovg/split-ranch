import { useState } from 'react';
import * as Crypto from 'expo-crypto';
import { useTranslation } from 'react-i18next';
import { RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { toast } from 'sonner-native';
import { MoneyText } from '@/components/MoneyText';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { ScreenBackground } from '@/components/ScreenBackground';
import { currentMoneyLocale } from '@/i18n';
import { apiErrorCode } from '@/lib/api';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import {
  type PaymentAction,
  useActiveMembership,
  useBalance,
  useGroup,
  usePaymentAction,
  usePayments,
  useRecordPayment,
} from './api';
import { ErrorScreen, LoadingScreen, memberName } from './components';
import { GroupsScreen } from './GroupsScreen';
import type { Group, Payment, Suggestion } from './types';

/**
 * Settle up: suggested payments (greedy, after counting payments already sent), record one,
 * and the payment list where the receiver confirms or disputes and the payer cancels.
 */
export function SettleScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const groupId = me.data?.group_id;
  const group = useGroup(groupId);
  const balance = useBalance(groupId);
  const payments = usePayments(groupId);
  useRefreshOnFocus(groupId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(balance.refetch, payments.refetch);

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  if (!me.data) return <GroupsScreen embedded />;
  if (group.isPending || balance.isPending || payments.isPending) return <LoadingScreen />;
  if (group.isError || balance.isError || payments.isError) {
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void balance.refetch();
          void payments.refetch();
        }}
      />
    );
  }
  const g = group.data;
  const live = payments.data.items.filter((p) => p.status !== 'cancelled');

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <ScreenBackground />
      <ScrollView
        contentContainerClassName='gap-4 px-4 py-4'
        refreshControl={<RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />}>
        <Card>
          <CardHeader>
            <CardTitle>{t('settle.suggestions')}</CardTitle>
          </CardHeader>
          <CardContent>
            {balance.data.suggestions.length === 0 ? (
              <Text className='text-muted-foreground'>{t('settle.nothingToPay')}</Text>
            ) : (
              balance.data.suggestions.map((s, i) => (
                <View key={`${s.from_member_id}-${s.to_member_id}`}>
                  {i > 0 ? <Separator /> : null}
                  <SuggestionRow group={g} suggestion={s} />
                </View>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('settle.payments')}</CardTitle>
          </CardHeader>
          <CardContent>
            {live.length === 0 ? <Text className='text-muted-foreground'>{t('settle.noPayments')}</Text> : null}
            {live.map((p, i) => (
              <View key={p.id}>
                {i > 0 ? <Separator /> : null}
                <PaymentRow group={g} payment={p} />
              </View>
            ))}
          </CardContent>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

function SuggestionRow({ group, suggestion }: { group: Group; suggestion: Suggestion }) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const record = useRecordPayment(group.id);
  const [note, setNote] = useState('');
  // Stable per suggestion: a retry reuses the id, so the payment is never recorded twice.
  const [paymentId] = useState(() => Crypto.randomUUID());
  const me = group.my_member_id;
  const iPay = suggestion.from_member_id === me;
  const iReceive = suggestion.to_member_id === me;
  const label = t('settle.suggestion', {
    from: memberName(group, suggestion.from_member_id, t),
    to: memberName(group, suggestion.to_member_id, t),
    amount: displayMoney(suggestion.amount_cents, locale),
  });
  return (
    <View className='gap-2 py-3'>
      <Text className='font-medium'>{label}</Text>
      {iPay || iReceive ? (
        <>
          <Input
            aria-label={t('settle.note')}
            placeholder={t('settle.notePlaceholder')}
            value={note}
            onChangeText={setNote}
            maxLength={280}
          />
          <Button
            disabled={record.isPending}
            onPress={() =>
              record.mutate(
                {
                  id: paymentId,
                  from_member_id: suggestion.from_member_id,
                  to_member_id: suggestion.to_member_id,
                  amount_cents: suggestion.amount_cents,
                  note: note.trim() || undefined,
                },
                {
                  onSuccess: () => toast.success(t(iPay ? 'settle.recordedSent' : 'settle.recordedReceived')),
                  onError: () => toast.error(t('settle.actionFailed')),
                },
              )
            }>
            <Text>{t(iPay ? 'settle.iPaid' : 'settle.iReceived')}</Text>
          </Button>
        </>
      ) : null}
    </View>
  );
}

function PaymentRow({ group, payment }: { group: Group; payment: Payment }) {
  const { t } = useTranslation();
  const action = usePaymentAction(group.id);
  const [disputeNote, setDisputeNote] = useState('');
  const [disputing, setDisputing] = useState(false);
  const me = group.my_member_id;
  const iReceive = payment.to_member_id === me;
  const iPay = payment.from_member_id === me;
  const open = payment.status === 'sent' || payment.status === 'disputed';

  const run = (kind: PaymentAction, note?: string) =>
    action.mutate(
      { payment, action: kind, note },
      {
        onSuccess: () => setDisputing(false),
        onError: (error) =>
          toast.error(
            apiErrorCode(error) === 'payment_state_changed' || apiErrorCode(error) === 'version_conflict'
              ? t('settle.changed')
              : t('settle.actionFailed'),
          ),
      },
    );

  return (
    <View className='gap-2 py-3'>
      <View className='flex-row items-center gap-2'>
        <Text className='flex-1'>
          {t('settle.pays', {
            from: memberName(group, payment.from_member_id, t),
            to: memberName(group, payment.to_member_id, t),
          })}
        </Text>
        <MoneyText cents={payment.amount_cents} />
      </View>
      <View className='flex-row items-center gap-2'>
        <Badge variant={payment.status === 'confirmed' ? 'default' : 'secondary'}>
          <Text>{t(`settle.status_${payment.status}`)}</Text>
        </Badge>
        {payment.note ? <Text className='flex-1 text-sm text-muted-foreground'>{payment.note}</Text> : null}
      </View>
      {open && iReceive ? (
        <View className='flex-row flex-wrap gap-2'>
          <Button size='sm' disabled={action.isPending} onPress={() => run('confirm')}>
            <Text>{t('settle.received')}</Text>
          </Button>
          {payment.status === 'sent' ? (
            <Button size='sm' variant='outline' disabled={action.isPending} onPress={() => setDisputing(true)}>
              <Text>{t('settle.notReceived')}</Text>
            </Button>
          ) : null}
        </View>
      ) : null}
      {disputing ? (
        <View className='gap-2'>
          <Input
            aria-label={t('settle.disputeNote')}
            placeholder={t('settle.disputeNote')}
            value={disputeNote}
            onChangeText={setDisputeNote}
            maxLength={280}
          />
          <Button
            size='sm'
            variant='outline'
            disabled={action.isPending || disputeNote.trim() === ''}
            onPress={() => run('dispute', disputeNote.trim())}>
            <Text>{t('settle.notReceived')}</Text>
          </Button>
        </View>
      ) : null}
      {open && iPay ? (
        <Button size='sm' variant='ghost' disabled={action.isPending} onPress={() => run('cancel')}>
          <Text>{t('settle.cancel')}</Text>
        </Button>
      ) : null}
    </View>
  );
}
