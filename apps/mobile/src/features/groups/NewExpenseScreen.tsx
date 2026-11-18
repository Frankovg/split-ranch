import { useState } from 'react';
import * as Crypto from 'expo-crypto';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Alert, View } from 'react-native';
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
  useCategories,
  useCreateExpense,
  useDeleteExpense,
  useExpense,
  useGroup,
  useUpdateExpense,
} from './api';
import { activeMembers, ErrorScreen, LoadingScreen, memberName, userName } from './components';
import { todayIso } from './dates';
import { GroupsScreen } from './GroupsScreen';
import type { Expense, ExpenseUpdateInput, Group } from './types';

/** New expense, or edit/delete an existing one when `expenseId` is given. */
export function NewExpenseScreen({ expenseId }: { expenseId?: string }) {
  const { t } = useTranslation();
  const me = useActiveMembership();
  const group = useGroup(me.data?.group_id);
  const expense = useExpense(me.data?.group_id, expenseId);

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <ErrorScreen t={t} onRetry={() => void me.refetch()} />;
  // No group (e.g. deep link after leaving it): the group query never runs.
  if (!me.data) return <GroupsScreen embedded />;
  if (group.isPending || (expenseId && expense.isPending)) return <LoadingScreen />;
  if (group.isError) return <ErrorScreen t={t} onRetry={() => void group.refetch()} />;
  if (expenseId && expense.isError) return <ErrorScreen t={t} onRetry={() => void expense.refetch()} />;
  return <ExpenseForm group={group.data} expense={expense.data} />;
}

/** The members an equal split names, or everyone when it follows the rule. */
function initialParticipants(expense: Expense | undefined, everyone: string[]): string[] {
  if (!expense || expense.participant_mode === 'all' || expense.split_type !== 'equal') return everyone;
  return expense.shares.map((s) => s.member_id);
}

function ExpenseForm({ group, expense }: { group: Group; expense?: Expense }) {
  const { t } = useTranslation();
  const members = activeMembers(group);
  const everyone = members.map((m) => m.id);
  const categories = useCategories(group.id);
  const create = useCreateExpense(group.id);
  const update = useUpdateExpense(group.id);
  const remove = useDeleteExpense(group.id);
  // Stable per form: a double tap or a retry reuses the same id (idempotent POST).
  const [newId] = useState(() => Crypto.randomUUID());
  const editing = expense !== undefined;
  const readOnly = editing && !expense.can_edit;

  const [description, setDescription] = useState(expense?.description ?? '');
  const [amountCents, setAmountCents] = useState<number | null>(expense?.amount_cents ?? null);
  const [payer, setPayer] = useState(expense?.payer_member_id ?? group.my_member_id);
  const [categoryId, setCategoryId] = useState<string>(expense?.category_id ?? '');
  const startParticipants = initialParticipants(expense, everyone);
  const [participants, setParticipants] = useState<string[]>(startParticipants);
  const [submitted, setSubmitted] = useState(false);

  const amountValid = amountCents !== null && amountCents > 0 && amountCents <= MAX_AMOUNT_CENTS;
  const descriptionValid = description.trim() !== '';
  const valid = amountValid && descriptionValid && participants.length > 0;
  const activeCategories = (categories.data ?? []).filter((c) => !c.archived_at || c.id === categoryId);
  // Only equal splits can be changed here; weights/percentages/exact keep their shares.
  const canChooseParticipants = members.length > 1 && (!editing || expense.split_type === 'equal');
  const busy = create.isPending || update.isPending || remove.isPending;

  const onError = (error: unknown) => {
    const code = apiErrorCode(error);
    if (code === 'member_left') toast.error(t('expenses.memberLeft'));
    else if (code === 'version_conflict') toast.error(t('expenses.conflict'));
    else toast.error(t('expenses.saveFailed'));
  };

  const onSave = () => {
    setSubmitted(true);
    if (!valid || amountCents === null) return;
    const sameMembers =
      participants.length === startParticipants.length && participants.every((p) => startParticipants.includes(p));
    if (!editing) {
      const allSelected = participants.length === everyone.length;
      create.mutate(
        {
          id: newId,
          amount_cents: amountCents,
          description: description.trim(),
          category_id: categoryId || null,
          payer_member_id: payer,
          // The group's calendar day, not the device's (they differ abroad).
          expense_date: todayIso(group.timezone),
          // Everyone selected = let the group/category rule decide the split.
          participants: allSelected ? undefined : everyone.filter((id) => participants.includes(id)),
        },
        {
          onSuccess: () => {
            toast.success(t('expenses.saved'));
            router.back();
          },
          onError,
        },
      );
      return;
    }
    // Send only what changed: any other edit keeps the stored participants and inputs.
    const changes: ExpenseUpdateInput = {};
    if (amountCents !== expense.amount_cents) changes.amount_cents = amountCents;
    if (description.trim() !== expense.description) changes.description = description.trim();
    if ((categoryId || null) !== expense.category_id) changes.category_id = categoryId || null;
    if (payer !== expense.payer_member_id) changes.payer_member_id = payer;
    if (!sameMembers) changes.participants = everyone.filter((id) => participants.includes(id));
    if (Object.keys(changes).length === 0) {
      router.back();
      return;
    }
    update.mutate(
      { expense, changes },
      {
        onSuccess: () => {
          toast.success(t('expenses.saved'));
          router.back();
        },
        onError,
      },
    );
  };

  const onDelete = () => {
    if (!expense) return;
    Alert.alert(t('expenses.deleteTitle'), t('expenses.deleteBody', { description: expense.description }), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: () =>
          remove.mutate(expense, {
            onSuccess: () => {
              toast.success(t('expenses.deleted'));
              router.back();
            },
            onError,
          }),
      },
    ]);
  };

  return (
    <Screen>
      {editing ? (
        <Text className='text-sm text-muted-foreground'>
          {t('expenses.addedBy', { name: userName(group, expense.created_by_user_id, t) })}
          {expense.updated_by_user_id && expense.updated_at !== expense.created_at
            ? ` · ${t('expenses.editedBy', { name: userName(group, expense.updated_by_user_id, t) })}`
            : ''}
        </Text>
      ) : null}

      <View className='gap-1.5'>
        <Label nativeID='expense-amount'>{t('expenses.amount')}</Label>
        <MoneyInput
          nativeID='expense-amount'
          size='lg'
          valueCents={amountCents}
          onChangeCents={setAmountCents}
          accessibilityLabel={t('expenses.amount')}
          error={submitted && !amountValid ? t('money.invalid') : undefined}
        />
      </View>

      <View className='gap-1.5'>
        <Label nativeID='expense-description'>{t('expenses.description')}</Label>
        <Input
          aria-labelledby='expense-description'
          value={description}
          onChangeText={setDescription}
          placeholder={t('expenses.descriptionPlaceholder')}
          maxLength={140}
          editable={!readOnly}
          className={submitted && !descriptionValid ? 'border-destructive' : undefined}
        />
        {submitted && !descriptionValid ? (
          <Text className='text-sm text-destructive'>{t('expenses.descriptionRequired')}</Text>
        ) : null}
      </View>

      <View className='gap-1.5'>
        <Label>{t('expenses.payer')}</Label>
        <ToggleGroup
          type='single'
          variant='outline'
          value={payer}
          onValueChange={(v) => v && setPayer(v)}
          className='flex-wrap justify-start gap-2'>
          {members.map((m) => (
            <ToggleGroupItem key={m.id} value={m.id} className='rounded-sm border-l'>
              <Text>{memberName(group, m.id, t)}</Text>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </View>

      {activeCategories.length > 0 ? (
        <View className='gap-1.5'>
          <Label>{t('expenses.category')}</Label>
          <ToggleGroup
            type='single'
            variant='outline'
            value={categoryId}
            onValueChange={(v) => setCategoryId(v ?? '')}
            className='flex-wrap justify-start gap-2'>
            {activeCategories.map((c) => (
              <ToggleGroupItem key={c.id} value={c.id} className='rounded-sm border-l'>
                <Text>{c.name}</Text>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </View>
      ) : null}

      {canChooseParticipants ? (
        <View className='gap-1.5'>
          <Label>{t('expenses.splitBetween')}</Label>
          <ToggleGroup
            type='multiple'
            variant='outline'
            value={participants}
            onValueChange={setParticipants}
            className='flex-wrap justify-start gap-2'>
            {members.map((m) => (
              <ToggleGroupItem key={m.id} value={m.id} className='rounded-sm border-l'>
                <Text>{memberName(group, m.id, t)}</Text>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {submitted && participants.length === 0 ? (
            <Text className='text-sm text-destructive'>{t('quick.selectAtLeastOne')}</Text>
          ) : null}
        </View>
      ) : null}

      <Button size='lg' disabled={busy || readOnly} onPress={onSave}>
        <Text>{t('common.save')}</Text>
      </Button>
      {editing && !readOnly ? (
        <Button variant='destructive' disabled={busy} onPress={onDelete}>
          <Text>{t('common.delete')}</Text>
        </Button>
      ) : null}
    </Screen>
  );
}
