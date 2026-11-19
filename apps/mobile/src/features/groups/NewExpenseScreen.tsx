import { useState } from 'react';
import * as Crypto from 'expo-crypto';
import { router } from 'expo-router';
import { Plus } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Alert, ScrollView, View } from 'react-native';
import { toast } from 'sonner-native';
import { DateInput } from '@/components/DateInput';
import { MoneyInput } from '@/components/MoneyInput';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { MAX_AMOUNT_CENTS } from '@/lib/money';
import { apiErrorCode } from '@/lib/api';
import { askOnceInContext } from '@/features/notifications/register';
import {
  useCategories,
  useCategoryPresets,
  useCreateExpense,
  useDeleteExpense,
  useExpense,
  useGroup,
  useSplitRules,
  useUpdateExpense,
} from './api';
import { categoryIcon, categoryLabel, selectableCategories, sortByLabel } from './categories';
import { matchCategoryPreset } from './category-presets';
import { activeMembers, ErrorScreen, LoadingScreen, memberName, userName } from './components';
import { todayIso } from './dates';
import { useGroupId } from './route';
import {
  equalValues,
  splitProblem,
  splitSignature,
  splitStateFromExpense,
  toSplitSpec,
} from './split-form';
import { splitStateFromRule } from './split-rule';
import { SplitTable } from './SplitTable';
import type { Expense, ExpenseUpdateInput, Group, SplitRule } from './types';

/** Select value of "Other": the expense has no category. */
const OTHER_CATEGORY = '__other__';

/** New expense, or edit/delete an existing one when `expenseId` is given. */
export function NewExpenseScreen({ expenseId }: { expenseId?: string }) {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const group = useGroup(groupId);
  const expense = useExpense(groupId, expenseId);
  // A new expense starts from the group's default rule. If the rules cannot be loaded it
  // starts "Equally": an untouched table is not sent, so the API still applies the rule.
  const rules = useSplitRules(expenseId ? undefined : groupId);

  if (group.isPending || (expenseId ? expense.isPending : rules.isPending)) {
    return <LoadingScreen />;
  }
  if (group.isError) return <ErrorScreen t={t} onRetry={() => void group.refetch()} />;
  if (expenseId && expense.isError)
    return <ErrorScreen t={t} onRetry={() => void expense.refetch()} />;
  return <ExpenseForm group={group.data} expense={expense.data} defaultRule={rules.data?.default} />;
}

function ExpenseForm({
  group,
  expense,
  defaultRule,
}: {
  group: Group;
  expense?: Expense;
  defaultRule?: SplitRule;
}) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const members = activeMembers(group);
  const everyone = members.map((m) => m.id);
  const categories = useCategories(group.id);
  const presets = useCategoryPresets(group.id);
  const create = useCreateExpense(group.id);
  const update = useUpdateExpense(group.id);
  const remove = useDeleteExpense(group.id);
  // Stable per form: a double tap or a retry reuses the same id (idempotent POST).
  const [newId] = useState(() => Crypto.randomUUID());
  const editing = expense !== undefined;
  const readOnly = editing && !expense.can_edit;
  const today = todayIso(group.timezone);

  const [description, setDescription] = useState(expense?.description ?? '');
  const [amountCents, setAmountCents] = useState<number | null>(expense?.amount_cents ?? null);
  const [payer, setPayer] = useState(expense?.payer_member_id ?? group.my_member_id);
  // The group's calendar day by default, not the device's (they differ abroad).
  const [expenseDate, setExpenseDate] = useState(expense?.expense_date ?? today);
  // '' = "Other" (no category).
  const [categoryId, setCategoryId] = useState<string>(expense?.category_id ?? '');
  // Category presets pick the category of a new expense from its description until the
  // user chooses one by hand; edits never change the stored category on their own.
  const [categoryPicked, setCategoryPicked] = useState(editing);
  const [startSplit] = useState(() =>
    expense ? splitStateFromExpense(expense, everyone) : splitStateFromRule(defaultRule, everyone),
  );
  const [split, setSplit] = useState(startSplit);
  const [submitted, setSubmitted] = useState(false);

  // After "Add category", select the category that appears in the list once it is created.
  // Adjusted during render (react.dev "adjusting state when a prop changes"), not in an effect.
  const [knownCategoryIds, setKnownCategoryIds] = useState<string[] | null>(null);
  const categoryList = categories.data ?? [];
  if (knownCategoryIds) {
    const created = categoryList.find((c) => !c.archived_at && !knownCategoryIds.includes(c.id));
    if (created) {
      setKnownCategoryIds(null);
      setCategoryId(created.id);
      setCategoryPicked(true);
    }
  }

  // Table rows: active members plus anyone who left but is still in a stored share.
  const tableMembers = [...everyone, ...split.included.filter((id) => !everyone.includes(id))];
  const showSplit = tableMembers.length > 1;

  const amountValid = amountCents !== null && amountCents > 0 && amountCents <= MAX_AMOUNT_CENTS;
  const descriptionValid = description.trim() !== '';
  const problem = showSplit ? splitProblem(split, amountCents) : null;
  const valid = amountValid && descriptionValid && problem === null;
  const activeCategories = selectableCategories(categoryList, categoryId);
  const selectedCategory = activeCategories.find((c) => c.id === categoryId);
  const categoryOption = {
    value: categoryId || OTHER_CATEGORY,
    label: selectedCategory ? categoryLabel(selectedCategory, t) : t('categories.other'),
  };
  // Every category plus "Other", always in alphabetical order.
  const categoryOptions = sortByLabel(
    [
      ...activeCategories.map((c) => ({ value: c.id, label: categoryLabel(c, t), icon: categoryIcon(c) })),
      { value: OTHER_CATEGORY, label: t('categories.other'), icon: categoryIcon(null) },
    ],
    locale,
  );
  const payerOption = { value: payer, label: memberName(group, payer, t) };
  const busy = create.isPending || update.isPending || remove.isPending;

  const onDescriptionChange = (text: string) => {
    setDescription(text);
    if (categoryPicked) return;
    const activeIds = new Set(selectableCategories(categoryList).map((c) => c.id));
    setCategoryId(matchCategoryPreset(text, presets.data, activeIds) ?? '');
  };

  const onCategoryChange = (value: string | undefined) => {
    setCategoryPicked(true);
    setCategoryId(!value || value === OTHER_CATEGORY ? '' : value);
  };

  const onAmountChange = (cents: number | null) => {
    setAmountCents(cents);
    // Typed amounts no longer add up to a new total: start again from equal amounts.
    setSplit((s) => ({
      ...s,
      amounts: equalValues(cents ?? 0, s.included),
      locked: s.mode === 'amount' ? [] : s.locked,
    }));
  };

  const addCategory = () => {
    setKnownCategoryIds(categoryList.map((c) => c.id));
    router.push({ pathname: '/group/[groupId]/category/new', params: { groupId: group.id } });
  };

  const onError = (error: unknown) => {
    const code = apiErrorCode(error);
    if (code === 'member_left') toast.error(t('expenses.memberLeft'));
    else if (code === 'version_conflict') toast.error(t('expenses.conflict'));
    else toast.error(t('expenses.saveFailed'));
  };

  const onSuccess = () => router.back();

  const onSave = () => {
    setSubmitted(true);
    if (!valid || amountCents === null) return;
    if (!editing) {
      create.mutate(
        {
          id: newId,
          amount_cents: amountCents,
          description: description.trim(),
          category_id: categoryId || null,
          payer_member_id: payer,
          expense_date: expenseDate,
          // Untouched table (as the group rule set it up) = let the group/category rule decide.
          split: showSplit && splitSignature(split) !== splitSignature(startSplit) ? toSplitSpec(split) : undefined,
        },
        {
          onSuccess: () => {
            onSuccess();
            // First saved expense: a good moment to ask for the notification permission.
            void askOnceInContext().catch((error: unknown) =>
              console.warn('Failed to ask for the notification permission', error),
            );
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
    if (expenseDate !== expense.expense_date) changes.expense_date = expenseDate;
    const splitChanged = splitSignature(split) !== splitSignature(startSplit);
    // An exact split must be sent again when the amount changes (the API rejects it otherwise).
    const resendExact =
      changes.amount_cents !== undefined && split.enabled && split.mode === 'amount';
    if (showSplit && (splitChanged || resendExact)) changes.split = toSplitSpec(split);
    if (Object.keys(changes).length === 0) {
      router.back();
      return;
    }
    update.mutate({ expense, changes }, { onSuccess, onError });
  };

  const onDelete = () => {
    if (!expense) return;
    Alert.alert(
      t('expenses.deleteTitle'),
      t('expenses.deleteBody', { description: expense.description }),
      [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('common.delete'),
          style: 'destructive',
          onPress: () =>
            remove.mutate(expense, {
              onSuccess: () => router.back(),
              onError,
            }),
        },
      ],
    );
  };

  return (
    <Screen className='gap-5'>
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
          onChangeCents={onAmountChange}
          accessibilityLabel={t('expenses.amount')}
          error={submitted && !amountValid ? t('money.invalid') : undefined}
        />
      </View>

      <View className='gap-1.5'>
        <Label nativeID='expense-description'>{t('expenses.description')}</Label>
        <Input
          aria-labelledby='expense-description'
          value={description}
          onChangeText={onDescriptionChange}
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
        <Label nativeID='expense-category'>{t('expenses.category')}</Label>
        <View className='flex-row items-center gap-2'>
          <View className='flex-1'>
            <Select
              value={categoryOption}
              disabled={readOnly}
              onValueChange={(option) => onCategoryChange(option?.value)}
            >
              <SelectTrigger aria-labelledby='expense-category' disabled={readOnly}>
                <View className='flex-1 flex-row items-center gap-2'>
                  <Icon as={categoryIcon(selectedCategory)} size={18} className='text-primary' />
                  <SelectValue placeholder={t('categories.other')} />
                </View>
              </SelectTrigger>
              <SelectContent>
                <ScrollView className='max-h-80' keyboardShouldPersistTaps='handled'>
                  {categoryOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value} label={o.label}>
                      <Icon as={o.icon} size={18} className='text-primary' />
                    </SelectItem>
                  ))}
                </ScrollView>
              </SelectContent>
            </Select>
          </View>
          <Button
            variant='outline'
            size='icon'
            className='size-12'
            disabled={readOnly}
            onPress={addCategory}
            accessibilityLabel={t('expenses.addCategory')}
          >
            <Icon as={Plus} size={20} />
          </Button>
        </View>
      </View>

      <View className='flex-row gap-3'>
        <View className='flex-1 gap-1.5'>
          <Label nativeID='expense-payer'>{t('expenses.payer')}</Label>
          <Select
            value={payerOption}
            disabled={readOnly}
            onValueChange={(option) => option && setPayer(option.value)}
          >
            <SelectTrigger aria-labelledby='expense-payer' disabled={readOnly}>
              <SelectValue placeholder={t('home.you')} />
            </SelectTrigger>
            <SelectContent>
              {members.map((m) => (
                <SelectItem key={m.id} value={m.id} label={memberName(group, m.id, t)} />
              ))}
            </SelectContent>
          </Select>
        </View>
        <View className='flex-1 gap-1.5'>
          <Label>{t('expenses.when')}</Label>
          <DateInput
            value={expenseDate}
            onChange={setExpenseDate}
            maximumDate={today > expenseDate ? today : expenseDate}
            locale={locale}
            accessibilityLabel={t('expenses.when')}
            disabled={readOnly}
          />
        </View>
      </View>

      {showSplit ? (
        <SplitTable
          group={group}
          memberIds={tableMembers}
          state={split}
          onChange={setSplit}
          amountCents={amountCents}
          readOnly={readOnly}
          submitted={submitted}
        />
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
