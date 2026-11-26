import { zodResolver } from '@hookform/resolvers/zod';
import { Trash2 } from 'lucide-react-native';
import { useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { ScrollView } from 'react-native';
import { z } from 'zod';
import { FormField } from '@/components/FormField';
import { MoneyInput } from '@/components/MoneyInput';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { MAX_AMOUNT_CENTS } from '@/lib/money';
import { useQuickSplitsStore } from '@/stores/quick-splits';
import { payersGap } from '../model';
import type { QuickEvent, QuickExpense, QuickParticipant } from '../types';
import { PayerAmountsInput } from './PayerAmountsInput';

/** Payer toggle value for "several payers" (never a participant id). */
const MULTIPLE_PAYERS = '__multiple__';

type SchemaKey = 'money.invalid' | 'quick.selectPayer' | 'quick.selectAtLeastOne' | 'quick.incomplete.payers_mismatch';

function buildSchema(t: (key: SchemaKey) => string, participants: readonly QuickParticipant[]) {
  return z
    .object({
      description: z.string().trim().max(60),
      amountCents: z
        .number({ error: t('money.invalid') })
        .int()
        .positive(t('money.invalid'))
        .max(MAX_AMOUNT_CENTS, t('money.invalid'))
        .nullable()
        .refine((v) => v !== null, t('money.invalid')),
      payerId: z.string().min(1, t('quick.selectPayer')),
      payerAmounts: z.record(z.string(), z.number()),
      participantIds: z.array(z.string()).min(1, t('quick.selectAtLeastOne')),
    })
    .refine(
      (v) =>
        v.payerId !== MULTIPLE_PAYERS ||
        v.amountCents === null ||
        payersGap(participants, v.payerAmounts, v.amountCents) === 0,
      { error: t('quick.incomplete.payers_mismatch'), path: ['payerAmounts'] },
    );
}

type ExpenseForm = z.input<ReturnType<typeof buildSchema>>;

type ExpenseDialogProps = {
  event: QuickEvent;
  /** Existing expense to edit, or null to create one. */
  expense: QuickExpense | null;
  onClose: () => void;
};

/** Create/edit an itemised expense. RHF + Zod via the FormField wrapper. */
export function ExpenseDialog({ event, expense, onClose }: ExpenseDialogProps) {
  const { t } = useTranslation();
  const upsertExpense = useQuickSplitsStore((s) => s.upsertExpense);
  const removeExpense = useQuickSplitsStore((s) => s.removeExpense);
  const everyone = event.participants.map((p) => p.id);

  const { control, handleSubmit, getValues, setValue } = useForm<ExpenseForm>({
    resolver: zodResolver(buildSchema(t, event.participants)),
    defaultValues: {
      description: expense?.description ?? '',
      amountCents: expense?.amountCents ?? null,
      payerId: expense?.payerAmounts ? MULTIPLE_PAYERS : (expense?.payerId ?? event.participants[0]?.id ?? ''),
      payerAmounts: expense?.payerAmounts ?? {},
      participantIds: expense?.participantIds ?? everyone,
    },
  });
  const payerId = useWatch({ control, name: 'payerId' });
  const amountCents = useWatch({ control, name: 'amountCents' });

  /** Pick a payer; switching to "several" starts with the previous payer holding the whole amount. */
  const onPayerChange = (next: string, onChange: (v: string) => void) => {
    const { payerId: previous, payerAmounts, amountCents: amount } = getValues();
    if (next === MULTIPLE_PAYERS && previous !== MULTIPLE_PAYERS && Object.keys(payerAmounts).length === 0) {
      if (amount !== null && amount > 0 && previous !== '') setValue('payerAmounts', { [previous]: amount });
    }
    onChange(next);
  };

  const onSubmit = handleSubmit((values) => {
    if (values.amountCents === null) return;
    upsertExpense(event.id, {
      id: expense?.id,
      description: values.description.trim(),
      amountCents: values.amountCents,
      ...(values.payerId === MULTIPLE_PAYERS
        ? {
            payerId: '',
            // Keep only people who put money in, in canonical order.
            payerAmounts: Object.fromEntries(
              everyone.flatMap((id) => {
                const cents = values.payerAmounts[id] ?? 0;
                return cents > 0 ? [[id, cents]] : [];
              }),
            ),
          }
        : { payerId: values.payerId, payerAmounts: null }),
      // Store in canonical (creation) order.
      participantIds: everyone.filter((id) => values.participantIds.includes(id)),
    });
    onClose();
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='max-h-[90%]'>
        <DialogHeader>
          <DialogTitle>{expense ? t('quick.editExpense') : t('quick.addExpense')}</DialogTitle>
        </DialogHeader>
        <ScrollView keyboardShouldPersistTaps='handled' contentContainerClassName='gap-4'>
          <FormField
            control={control}
            name='description'
            label={t('quick.expenseDescription')}
            render={({ field, inputId }) => (
              <Input
                nativeID={inputId}
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                placeholder={t('quick.expenseDescriptionPlaceholder')}
                aria-labelledby={`${inputId}-label`}
              />
            )}
          />
          <FormField
            control={control}
            name='amountCents'
            label={t('quick.expenseAmount')}
            render={({ field, fieldState, inputId }) => (
              <MoneyInput
                nativeID={inputId}
                valueCents={field.value}
                onChangeCents={field.onChange}
                onBlur={field.onBlur}
                accessibilityLabel={t('quick.expenseAmount')}
                invalid={fieldState.invalid}
              />
            )}
          />
          <FormField
            control={control}
            name='payerId'
            label={t('quick.expensePaidBy')}
            render={({ field }) => (
              <ToggleGroup
                type='single'
                variant='outline'
                value={field.value}
                onValueChange={(v) => v && onPayerChange(v, field.onChange)}
                className='flex-wrap justify-start gap-2'>
                {event.participants.map((p) => (
                  <ToggleGroupItem key={p.id} value={p.id} className='rounded-md border-l'>
                    <Text>{p.name}</Text>
                  </ToggleGroupItem>
                ))}
                {event.participants.length > 1 ? (
                  <ToggleGroupItem value={MULTIPLE_PAYERS} className='rounded-md border-l'>
                    <Text>{t('quick.multiplePayers')}</Text>
                  </ToggleGroupItem>
                ) : null}
              </ToggleGroup>
            )}
          />
          {payerId === MULTIPLE_PAYERS ? (
            <FormField
              control={control}
              name='payerAmounts'
              label={t('quick.payerAmounts')}
              render={({ field }) => (
                <PayerAmountsInput
                  participants={event.participants}
                  amounts={field.value}
                  totalCents={amountCents}
                  onChange={(participantId, cents) => {
                    const { [participantId]: _old, ...rest } = field.value;
                    field.onChange(cents !== null && cents > 0 ? { ...rest, [participantId]: cents } : rest);
                  }}
                />
              )}
            />
          ) : null}
          <FormField
            control={control}
            name='participantIds'
            label={t('quick.expenseFor')}
            render={({ field }) => (
              <ToggleGroup
                type='multiple'
                variant='outline'
                value={field.value}
                onValueChange={field.onChange}
                className='flex-wrap justify-start gap-2'>
                {event.participants.map((p) => (
                  <ToggleGroupItem key={p.id} value={p.id} className='rounded-md border-l'>
                    <Text>{p.name}</Text>
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          />
        </ScrollView>
        <DialogFooter className='flex-row flex-wrap justify-between gap-2'>
          {expense ? (
            <Button
              variant='ghost'
              size='icon'
              onPress={() => {
                removeExpense(event.id, expense.id);
                onClose();
              }}
              accessibilityLabel={t('quick.deleteExpense')}>
              <Icon as={Trash2} size={20} className='text-destructive' />
            </Button>
          ) : null}
          <Button onPress={() => void onSubmit()} className='flex-1'>
            <Text>{t('common.save')}</Text>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
