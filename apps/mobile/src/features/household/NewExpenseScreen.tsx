import * as Crypto from 'expo-crypto';
import { router } from 'expo-router';
import * as React from 'react';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { MoneyInput } from '@/components/MoneyInput';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { MAX_AMOUNT_CENTS } from '@/lib/money';
import { apiErrorCode } from '@/lib/api';
import {
  useActiveMembership,
  useBalance,
  useCategories,
  useCreateExpense,
  useHousehold,
} from './api';
import { activeMembers, ErrorScreen, LoadingScreen, memberName } from './components';
import { todayIso } from './dates';
import type { Household } from './types';

export function NewExpenseScreen() {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const household = useHousehold(me.membership?.household_id);

  if (me.isPending || household.isPending) return <LoadingScreen />;
  if (me.isError || household.isError || !household.data) {
    return <ErrorScreen t={t} onRetry={() => void household.refetch()} />;
  }
  return <NewExpenseForm household={household.data} />;
}

function NewExpenseForm({ household }: { household: Household }) {
  const { t } = useTranslation();
  const members = activeMembers(household);
  const everyone = members.map((m) => m.id);
  const categories = useCategories(household.id);
  const create = useCreateExpense(household.id);
  // New expenses go to the open period; when the latest one is closed, someone must start
  // the next period first.
  const period = useBalance(household.id, 'current').data?.period;
  const noOpenPeriod = period !== undefined && period.status !== 'open';
  // Stable per form: a double tap or a retry reuses the same id (idempotent POST).
  const [expenseId] = React.useState(() => Crypto.randomUUID());

  const [description, setDescription] = React.useState('');
  const [amountCents, setAmountCents] = React.useState<number | null>(null);
  const [payer, setPayer] = React.useState(household.my_member_id);
  const [categoryId, setCategoryId] = React.useState<string>('');
  const [participants, setParticipants] = React.useState<string[]>(everyone);
  const [submitted, setSubmitted] = React.useState(false);

  const amountValid = amountCents !== null && amountCents > 0 && amountCents <= MAX_AMOUNT_CENTS;
  const descriptionValid = description.trim() !== '';
  const valid = amountValid && descriptionValid && participants.length > 0 && !noOpenPeriod;
  const activeCategories = (categories.data ?? []).filter((c) => !c.archived_at);

  const onSave = () => {
    setSubmitted(true);
    if (!valid || amountCents === null) return;
    const allSelected = participants.length === everyone.length;
    create.mutate(
      {
        id: expenseId,
        amount_cents: amountCents,
        description: description.trim(),
        category_id: categoryId || null,
        payer_member_id: payer,
        expense_date: todayIso(),
        // Everyone selected = let the household/category rule decide the split.
        participants: allSelected ? undefined : everyone.filter((id) => participants.includes(id)),
      },
      {
        onSuccess: () => {
          toast.success(t('expenses.saved'));
          router.back();
        },
        onError: (error) =>
          toast.error(
            apiErrorCode(error) === 'no_open_period' ? t('expenses.noOpenPeriod') : t('expenses.saveFailed'),
          ),
      },
    );
  };

  return (
    <Screen>
      <View className="gap-1.5">
        <Label nativeID="expense-amount">{t('expenses.amount')}</Label>
        <MoneyInput
          nativeID="expense-amount"
          size="lg"
          valueCents={amountCents}
          onChangeCents={setAmountCents}
          accessibilityLabel={t('expenses.amount')}
          error={submitted && !amountValid ? t('money.invalid') : undefined}
        />
      </View>

      <View className="gap-1.5">
        <Label nativeID="expense-description">{t('expenses.description')}</Label>
        <Input
          aria-labelledby="expense-description"
          value={description}
          onChangeText={setDescription}
          placeholder={t('expenses.descriptionPlaceholder')}
          maxLength={140}
          className={submitted && !descriptionValid ? 'border-destructive' : undefined}
        />
        {submitted && !descriptionValid ? (
          <Text className="text-sm text-destructive">{t('expenses.descriptionRequired')}</Text>
        ) : null}
      </View>

      <View className="gap-1.5">
        <Label>{t('expenses.payer')}</Label>
        <ToggleGroup
          type="single"
          variant="outline"
          value={payer}
          onValueChange={(v) => v && setPayer(v)}
          className="flex-wrap justify-start gap-2">
          {members.map((m) => (
            <ToggleGroupItem key={m.id} value={m.id} className="rounded-md border-l">
              <Text>{memberName(household, m.id, t)}</Text>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </View>

      {activeCategories.length > 0 ? (
        <View className="gap-1.5">
          <Label>{t('expenses.category')}</Label>
          <ToggleGroup
            type="single"
            variant="outline"
            value={categoryId}
            onValueChange={(v) => setCategoryId(v ?? '')}
            className="flex-wrap justify-start gap-2">
            {activeCategories.map((c) => (
              <ToggleGroupItem key={c.id} value={c.id} className="rounded-md border-l">
                <Text>{c.name}</Text>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </View>
      ) : null}

      {members.length > 1 ? (
        <View className="gap-1.5">
          <Label>{t('expenses.splitBetween')}</Label>
          <ToggleGroup
            type="multiple"
            variant="outline"
            value={participants}
            onValueChange={setParticipants}
            className="flex-wrap justify-start gap-2">
            {members.map((m) => (
              <ToggleGroupItem key={m.id} value={m.id} className="rounded-md border-l">
                <Text>{memberName(household, m.id, t)}</Text>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {submitted && participants.length === 0 ? (
            <Text className="text-sm text-destructive">{t('quick.selectAtLeastOne')}</Text>
          ) : null}
        </View>
      ) : null}

      {noOpenPeriod ? (
        <Text className="text-sm text-destructive">{t('expenses.noOpenPeriod')}</Text>
      ) : null}

      <Button size="lg" disabled={create.isPending || noOpenPeriod} onPress={onSave}>
        <Text>{t('common.save')}</Text>
      </Button>
    </Screen>
  );
}
