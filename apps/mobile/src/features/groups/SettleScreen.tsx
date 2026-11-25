import { useRef, useState } from 'react';
import * as Crypto from 'expo-crypto';
import { ArrowRight, Check } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { toast } from 'sonner-native';
import { MoneyInput } from '@/components/MoneyInput';
import { MoneyText } from '@/components/MoneyText';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { ScreenBackground } from '@/components/ScreenBackground';
import { currentMoneyLocale } from '@/i18n';
import { apiErrorCode } from '@/lib/api';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import { cn } from '@/lib/utils';
import {
  type PaymentAction,
  useBalance,
  useGroup,
  usePaymentAction,
  usePayments,
  useRecordPayment,
} from './api';
import { ErrorScreen, LoadingScreen, memberName } from './components';
import { instantLabel } from './dates';
import { useGroupId } from './route';
import { checkPartialAmount, halfOf } from './settle-amount';
import type { Group, Payment, PaymentMethod, Suggestion } from './types';

// Order shown in the selector; mirrors the API's PaymentMethod.
const PAYMENT_METHODS: readonly PaymentMethod[] = ['bizum', 'bank_transfer', 'cash', 'other'];
const DEFAULT_METHOD: PaymentMethod = 'bizum';

function isPaymentMethod(value: string): value is PaymentMethod {
  return (PAYMENT_METHODS as readonly string[]).includes(value);
}

function suggestionKey(s: Suggestion): string {
  return `${s.from_member_id}-${s.to_member_id}`;
}

/**
 * Settle up: suggested payments (greedy, after counting payments already sent), recorded in bulk
 * from the selected ones the caller is part of, and the payment list where the receiver confirms
 * or disputes and the payer cancels.
 */
export function SettleScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const group = useGroup(groupId);
  const balance = useBalance(groupId);
  const payments = usePayments(groupId);
  useRefreshOnFocus(groupId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(balance.refetch, payments.refetch);

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
        keyboardShouldPersistTaps='handled'
        refreshControl={<RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />}>
        <SuggestionsCard group={g} suggestions={balance.data.suggestions} />

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

/**
 * Who owes whom, plus one shared form (method + note) that records every selected suggestion.
 * Only suggestions the caller pays or receives can be recorded (the API rejects the rest).
 * In a two-person group there is a single suggestion, so no checkbox: it is always included.
 */
function SuggestionsCard({ group, suggestions }: { group: Group; suggestions: Suggestion[] }) {
  const { t } = useTranslation();
  const record = useRecordPayment(group.id);
  const [method, setMethod] = useState<PaymentMethod>(DEFAULT_METHOD);
  const [note, setNote] = useState('');
  // Deselected rather than selected keys: suggestions arriving after a refresh start included.
  const [deselected, setDeselected] = useState<ReadonlySet<string>>(() => new Set());
  // Suggestions paid only in part, keyed like `suggestionKey`; absent means "pay it all" (the default).
  // The value is the typed amount, null while empty or unparseable.
  const [partial, setPartial] = useState<ReadonlyMap<string, number | null>>(() => new Map());
  const [submitting, setSubmitting] = useState(false);
  // Stable id per suggestion and amount: a retry reuses it, so a payment is never recorded twice.
  const paymentIds = useRef(new Map<string, string>());

  const setPartialAmount = (key: string, cents: number | null | undefined) =>
    setPartial((prev) => {
      const next = new Map(prev);
      if (cents === undefined) next.delete(key);
      else next.set(key, cents);
      return next;
    });

  if (suggestions.length === 0) {
    return (
      <Card>
        <CardContent className='py-6'>
          <Text className='text-center text-muted-foreground'>{t('settle.nothingToPay')}</Text>
        </CardContent>
      </Card>
    );
  }

  const me = group.my_member_id;
  const showCheckboxes = group.members.filter((m) => m.status !== 'left').length > 2;
  const isMine = (s: Suggestion) => s.from_member_id === me || s.to_member_id === me;
  const isSelected = (s: Suggestion) => isMine(s) && (!showCheckboxes || !deselected.has(suggestionKey(s)));
  const actionable = suggestions.filter(isMine);
  const selected = suggestions.filter(isSelected);
  // What each selected suggestion records: the full amount unless a valid partial one was typed.
  const amountFor = (s: Suggestion): number | null => {
    const key = suggestionKey(s);
    if (!partial.has(key)) return s.amount_cents;
    const check = checkPartialAmount(partial.get(key) ?? null, s.amount_cents);
    return check.ok ? check.amountCents : null;
  };
  const allValid = selected.every((s) => amountFor(s) !== null);

  const toggle = (s: Suggestion) =>
    setDeselected((prev) => {
      const next = new Set(prev);
      const key = suggestionKey(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const submit = async () => {
    setSubmitting(true);
    const trimmed = note.trim() || undefined;
    const results = await Promise.allSettled(
      selected.map(async (s) => {
        // Validated by `allValid` before the button is enabled.
        const amount = amountFor(s) ?? s.amount_cents;
        const key = `${suggestionKey(s)}-${s.amount_cents}-${amount}`;
        let id = paymentIds.current.get(key);
        if (id === undefined) {
          id = Crypto.randomUUID();
          paymentIds.current.set(key, id);
        }
        await record.mutateAsync({
          id,
          from_member_id: s.from_member_id,
          to_member_id: s.to_member_id,
          amount_cents: amount,
          method,
          note: trimmed,
        });
        // Recorded: an identical suggestion later on (e.g. after a cancel) is a new payment.
        paymentIds.current.delete(key);
        // The next suggestion for this pair (what is still owed) starts again as "pay it all".
        setPartialAmount(suggestionKey(s), undefined);
      }),
    );
    setSubmitting(false);
    if (results.some((r) => r.status === 'rejected')) toast.error(t('settle.actionFailed'));
    else setNote('');
  };

  const only = selected.length === 1 ? selected[0] : undefined;
  // The single-payment label names the amount, so a partial payment is explicit before recording it.
  const onlyAmount = only !== undefined ? amountFor(only) : null;
  const amountText = onlyAmount !== null ? displayMoney(onlyAmount, currentMoneyLocale()) : '';
  const buttonLabel =
    only?.from_member_id === me
      ? onlyAmount !== null
        ? t('settle.iPaidAmount', { amount: amountText })
        : t('settle.iPaid')
      : only?.to_member_id === me
        ? onlyAmount !== null
          ? t('settle.iReceivedAmount', { amount: amountText })
          : t('settle.iReceived')
        : t('settle.recordSelected', { count: selected.length });

  return (
    <Card>
      <CardContent className='pt-2'>
        {suggestions.map((s, i) => (
          <View key={suggestionKey(s)}>
            {i > 0 ? <Separator /> : null}
            <SuggestionRow
              group={group}
              suggestion={s}
              showCheckbox={showCheckboxes}
              mine={isMine(s)}
              checked={isSelected(s)}
              onToggle={() => toggle(s)}
              partialCents={partial.has(suggestionKey(s)) ? (partial.get(suggestionKey(s)) ?? null) : undefined}
              onPartialChange={(cents) => setPartialAmount(suggestionKey(s), cents)}
            />
          </View>
        ))}

        {actionable.length > 0 ? (
          <View className='gap-4'>
            <Separator />
            <View className='gap-1.5'>
              <Label nativeID='settle-method'>{t('settle.method')}</Label>
              <Select
                value={{ value: method, label: t(`settle.method_${method}`) }}
                onValueChange={(option) => {
                  if (option && isPaymentMethod(option.value)) setMethod(option.value);
                }}>
                <SelectTrigger aria-labelledby='settle-method'>
                  <SelectValue placeholder={t('settle.method')} />
                </SelectTrigger>
                <SelectContent>
                  {PAYMENT_METHODS.map((m) => (
                    <SelectItem key={m} value={m} label={t(`settle.method_${m}`)} />
                  ))}
                </SelectContent>
              </Select>
            </View>
            <View className='gap-1.5'>
              <Label>{t('settle.note')}</Label>
              <Input
                aria-label={t('settle.note')}
                placeholder={t('settle.notePlaceholder')}
                value={note}
                onChangeText={setNote}
                maxLength={280}
              />
            </View>
            <Button disabled={submitting || selected.length === 0 || !allValid} onPress={() => void submit()}>
              <Text>{buttonLabel}</Text>
            </Button>
          </View>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SuggestionRow({
  group,
  suggestion,
  showCheckbox,
  mine,
  checked,
  onToggle,
  partialCents,
  onPartialChange,
}: {
  group: Group;
  suggestion: Suggestion;
  showCheckbox: boolean;
  mine: boolean;
  checked: boolean;
  onToggle: () => void;
  /** undefined: paying it all (default); number or null: the partial amount being typed. */
  partialCents: number | null | undefined;
  /** undefined goes back to paying it all. */
  onPartialChange: (cents: number | null | undefined) => void;
}) {
  const { t } = useTranslation();
  const me = group.my_member_id;
  const from = memberName(group, suggestion.from_member_id, t);
  const to = memberName(group, suggestion.to_member_id, t);
  // Coloured from the caller's side: what I owe is negative, what I am owed is positive.
  const tone = suggestion.from_member_id === me ? 'negative' : suggestion.to_member_id === me ? 'positive' : 'muted';
  const canPayPart = mine && checked;
  const iPay = suggestion.from_member_id === me;

  const content = (
    <View className={cn('flex-row items-center gap-3 py-4', showCheckbox && !mine && 'opacity-60')}>
      {showCheckbox ? <CheckboxBox checked={checked} /> : null}
      <View className='flex-1 gap-1'>
        <View className='flex-row flex-wrap items-center gap-x-2'>
          <Text className='text-lg font-semibold'>{from}</Text>
          <Icon as={ArrowRight} size={18} className='text-muted-foreground' />
          <Text className='text-lg font-semibold'>{to}</Text>
        </View>
        {showCheckbox && !mine ? <Text className='text-sm text-muted-foreground'>{t('settle.notYours')}</Text> : null}
      </View>
      <MoneyText cents={suggestion.amount_cents} tone={tone} size='3xl' accessibilityPrefix={`${from} → ${to}`} />
    </View>
  );

  const row =
    !showCheckbox || !mine ? (
      content
    ) : (
      <Pressable
        role='checkbox'
        aria-checked={checked}
        aria-label={t('settle.selectSuggestion', { from, to })}
        onPress={onToggle}
        className='active:opacity-70'>
        {content}
      </Pressable>
    );

  if (!canPayPart) return row;
  return (
    <View>
      {row}
      {partialCents === undefined ? (
        <Button
          variant='link'
          size='sm'
          className='-mt-3 mb-1 self-start px-0'
          onPress={() => onPartialChange(suggestion.amount_cents)}>
          <Text>{iPay ? t('settle.payPart') : t('settle.receivePart')}</Text>
        </Button>
      ) : (
        <PartialAmountEditor
          group={group}
          suggestion={suggestion}
          iPay={iPay}
          valueCents={partialCents}
          onChange={onPartialChange}
        />
      )}
    </View>
  );
}

/**
 * Inline editor for paying only part of a suggestion: the amount (prefilled with all of it),
 * what will still be owed afterwards, and shortcuts for half or going back to all of it.
 */
function PartialAmountEditor({
  group,
  suggestion,
  iPay,
  valueCents,
  onChange,
}: {
  group: Group;
  suggestion: Suggestion;
  iPay: boolean;
  valueCents: number | null;
  onChange: (cents: number | null | undefined) => void;
}) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const owed = suggestion.amount_cents;
  const check = checkPartialAmount(valueCents, owed);
  const debtor = memberName(group, suggestion.from_member_id, t);
  const inputId = `settle-partial-${suggestionKey(suggestion)}`;

  const error = check.ok
    ? undefined
    : check.error === 'tooMuch'
      ? t('settle.amountTooMuch', { amount: displayMoney(owed, locale) })
      : t('settle.amountEmpty');
  const remaining = check.ok
    ? check.remainingCents === 0
      ? t('settle.settlesAll')
      : iPay
        ? t('settle.remainingIOwe', { amount: displayMoney(check.remainingCents, locale) })
        : t('settle.remainingOwedToMe', { name: debtor, amount: displayMoney(check.remainingCents, locale) })
    : undefined;

  return (
    <View className='mb-4 gap-2 rounded-md bg-muted/50 p-3'>
      <Label nativeID={inputId}>{iPay ? t('settle.amountToPay') : t('settle.amountReceived')}</Label>
      <MoneyInput
        nativeID={inputId}
        size='lg'
        valueCents={valueCents}
        onChangeCents={(cents) => onChange(cents)}
        accessibilityLabel={iPay ? t('settle.amountToPay') : t('settle.amountReceived')}
        error={error}
      />
      {remaining ? (
        <Text className='text-sm text-muted-foreground' accessibilityLiveRegion='polite'>
          {remaining}
        </Text>
      ) : null}
      <View className='flex-row flex-wrap gap-2'>
        {owed >= 2 ? (
          <Button size='sm' variant='outline' onPress={() => onChange(halfOf(owed))}>
            <Text>{t('settle.half')}</Text>
          </Button>
        ) : null}
        <Button size='sm' variant='ghost' onPress={() => onChange(undefined)}>
          <Text>{t('settle.allOfIt', { amount: displayMoney(owed, locale) })}</Text>
        </Button>
      </View>
    </View>
  );
}

function CheckboxBox({ checked }: { checked: boolean }) {
  return (
    <View
      className={cn(
        'h-6 w-6 items-center justify-center rounded-md border-2',
        checked ? 'border-primary bg-primary' : 'border-input',
      )}>
      {checked ? <Icon as={Check} size={16} className='text-primary-foreground' /> : null}
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
      <Text className='text-sm text-muted-foreground'>
        {instantLabel(payment.created_at, currentMoneyLocale(), group.timezone)}
        {payment.method ? ` · ${t(`settle.method_${payment.method}`)}` : ''}
      </Text>
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
