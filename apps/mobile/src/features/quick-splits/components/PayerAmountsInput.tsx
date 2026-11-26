import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { MoneyInput } from '@/components/MoneyInput';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { payersGap } from '../model';
import type { QuickParticipant } from '../types';

type PayerAmountsInputProps = {
  participants: readonly QuickParticipant[];
  amounts: Readonly<Record<string, number>>;
  /** What the amounts must add up to; null hides the hint (no total yet). */
  totalCents: number | null;
  onChange: (participantId: string, cents: number | null) => void;
};

/** "Several payers": how much each participant put in, and how far that is from the total. */
export function PayerAmountsInput({ participants, amounts, totalCents, onChange }: PayerAmountsInputProps) {
  const { t } = useTranslation();
  const gap = totalCents === null ? null : payersGap(participants, amounts, totalCents);
  const money = (cents: number) => displayMoney(cents, currentMoneyLocale());

  return (
    <View className='gap-2'>
      {participants.map((p) => (
        <View key={p.id} className='min-h-14 flex-row items-center gap-3'>
          <Text className='flex-1'>{p.name}</Text>
          <MoneyInput
            className='w-36'
            valueCents={amounts[p.id] ?? null}
            onChangeCents={(cents) => onChange(p.id, cents)}
            accessibilityLabel={t('quick.payerAmountOf', { name: p.name })}
          />
        </View>
      ))}
      {gap === null ? null : gap === 0 ? (
        <Text className='text-sm text-positive'>{t('quick.payersMatch')}</Text>
      ) : (
        <Text className='text-sm text-warning'>
          {gap > 0
            ? t('quick.payersMissing', { amount: money(gap) })
            : t('quick.payersExcess', { amount: money(-gap) })}
        </Text>
      )}
    </View>
  );
}
