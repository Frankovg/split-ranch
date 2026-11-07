import { zodResolver } from '@hookform/resolvers/zod';
import { Trash2 } from 'lucide-react-native';
import { useForm } from 'react-hook-form';
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
import type { QuickEvent, QuickExpense } from '../types';

function buildSchema(t: (key: 'money.invalid' | 'quick.selectPayer' | 'quick.selectAtLeastOne') => string) {
  return z.object({
    description: z.string().trim().max(60),
    amountCents: z
      .number({ error: t('money.invalid') })
      .int()
      .positive(t('money.invalid'))
      .max(MAX_AMOUNT_CENTS, t('money.invalid'))
      .nullable()
      .refine((v) => v !== null, t('money.invalid')),
    payerId: z.string().min(1, t('quick.selectPayer')),
    participantIds: z.array(z.string()).min(1, t('quick.selectAtLeastOne')),
  });
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

  const { control, handleSubmit } = useForm<ExpenseForm>({
    resolver: zodResolver(buildSchema(t)),
    defaultValues: {
      description: expense?.description ?? '',
      amountCents: expense?.amountCents ?? null,
      payerId: expense?.payerId ?? event.participants[0]?.id ?? '',
      participantIds: expense?.participantIds ?? everyone,
    },
  });

  const onSubmit = handleSubmit((values) => {
    if (values.amountCents === null) return;
    upsertExpense(event.id, {
      id: expense?.id,
      description: values.description.trim(),
      amountCents: values.amountCents,
      payerId: values.payerId,
      // Store in canonical (creation) order.
      participantIds: everyone.filter((id) => values.participantIds.includes(id)),
    });
    onClose();
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90%]">
        <DialogHeader>
          <DialogTitle>{expense ? t('quick.editExpense') : t('quick.addExpense')}</DialogTitle>
        </DialogHeader>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerClassName="gap-4">
          <FormField
            control={control}
            name="description"
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
            name="amountCents"
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
            name="payerId"
            label={t('quick.expensePaidBy')}
            render={({ field }) => (
              <ToggleGroup
                type="single"
                variant="outline"
                value={field.value}
                onValueChange={(v) => v && field.onChange(v)}
                className="flex-wrap justify-start gap-2">
                {event.participants.map((p) => (
                  <ToggleGroupItem key={p.id} value={p.id} className="rounded-md border-l">
                    <Text>{p.name}</Text>
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          />
          <FormField
            control={control}
            name="participantIds"
            label={t('quick.expenseFor')}
            render={({ field }) => (
              <ToggleGroup
                type="multiple"
                variant="outline"
                value={field.value}
                onValueChange={field.onChange}
                className="flex-wrap justify-start gap-2">
                {event.participants.map((p) => (
                  <ToggleGroupItem key={p.id} value={p.id} className="rounded-md border-l">
                    <Text>{p.name}</Text>
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          />
        </ScrollView>
        <DialogFooter className="flex-row flex-wrap justify-between gap-2">
          {expense ? (
            <Button
              variant="ghost"
              size="icon"
              onPress={() => {
                removeExpense(event.id, expense.id);
                onClose();
              }}
              accessibilityLabel={t('quick.deleteExpense')}>
              <Icon as={Trash2} size={20} className="text-destructive" />
            </Button>
          ) : null}
          <Button onPress={() => void onSubmit()} className="flex-1">
            <Text>{t('common.save')}</Text>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
