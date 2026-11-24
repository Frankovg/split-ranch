import { BASIS_POINTS_TOTAL } from '@split-ranch/domain';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { Checkbox } from '@/components/Checkbox';
import { MoneyInput } from '@/components/MoneyInput';
import { MoneyText } from '@/components/MoneyText';
import { PercentInput } from '@/components/PercentInput';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { cn } from '@/lib/utils';
import { memberName } from './components';
import {
  previewShares,
  rebalance,
  resetValues,
  splitProblem,
  sumOf,
  type SplitFormState,
  type SplitMode,
} from './split-form';
import type { Group } from './types';

type SplitTableProps = {
  group: Group;
  /** Member ids shown as rows, in group order. */
  memberIds: string[];
  state: SplitFormState;
  onChange: (state: SplitFormState) => void;
  amountCents: number | null;
  readOnly: boolean;
  submitted: boolean;
};

const MODE_LABEL_KEYS = {
  equal: 'expenses.splitEqually',
  parts: 'expenses.splitParts',
  amount: 'expenses.splitAmount',
} as const satisfies Record<SplitMode, string>;

/**
 * Two-column split table. Column 1: "split" on/off and who takes part. Column 2: the
 * split mode and, per member, the share (equal), an editable percentage (parts) or an
 * editable amount (amount); editing one value rebalances the others.
 */
export function SplitTable({ group, memberIds, state, onChange, amountCents, readOnly, submitted }: SplitTableProps) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const total = amountCents ?? 0;
  const shares = previewShares(state, total);
  const problem = splitProblem(state, amountCents);
  const modeOption = { value: state.mode, label: t(MODE_LABEL_KEYS[state.mode]) };

  const toggleMember = (id: string, on: boolean) => {
    const included = memberIds.filter((m) => (m === id ? on : state.included.includes(m)));
    onChange(resetValues({ ...state, included }, total));
  };

  const setPercent = (id: string, bps: number) => {
    const r = rebalance(state.percents, state.included, state.locked, id, bps, BASIS_POINTS_TOTAL);
    onChange({ ...state, percents: r.values, locked: r.locked });
  };

  const setAmount = (id: string, cents: number) => {
    const r = rebalance(state.amounts, state.included, state.locked, id, cents, total);
    onChange({ ...state, amounts: r.values, locked: r.locked });
  };

  return (
    <View className='gap-2'>
      <View className='overflow-hidden rounded-md border border-border'>
        {/* Header row: split on/off | split mode */}
        <View className='min-h-14 flex-row items-center gap-2 border-b border-border bg-muted/40 px-2 py-1'>
          <View className='flex-1 flex-row items-center gap-1'>
            <Checkbox
              checked={state.enabled}
              onCheckedChange={(enabled) => onChange({ ...state, enabled })}
              accessibilityLabel={t('expenses.split')}
              disabled={readOnly}
            />
            <Text className='font-semibold'>{t('expenses.split')}</Text>
          </View>
          <View className='flex-1'>
            <Select
              value={modeOption}
              disabled={readOnly || !state.enabled}
              onValueChange={(option) => option && onChange({ ...state, mode: option.value as SplitMode })}>
              <SelectTrigger aria-label={t('expenses.splitMode')} disabled={readOnly || !state.enabled}>
                <SelectValue placeholder={t('expenses.splitEqually')} />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(MODE_LABEL_KEYS) as SplitMode[]).map((mode) => (
                  <SelectItem key={mode} value={mode} label={t(MODE_LABEL_KEYS[mode])} />
                ))}
              </SelectContent>
            </Select>
          </View>
        </View>

        {state.enabled ? (
          memberIds.map((id, index) => {
            const name = memberName(group, id, t);
            const included = state.included.includes(id);
            return (
              <View
                key={id}
                className={cn(
                  // No vertical padding: min-h-14 (56) already fits the 48dp inputs plus the
                  // 1px row border, so rows keep the same height in every split mode.
                  'min-h-14 flex-row items-center gap-2 px-2',
                  index < memberIds.length - 1 && 'border-b border-border',
                )}>
                <View className='flex-1 flex-row items-center gap-1'>
                  <Checkbox
                    checked={included}
                    onCheckedChange={(on) => toggleMember(id, on)}
                    accessibilityLabel={t('expenses.includeMember', { name })}
                    disabled={readOnly}
                  />
                  <Text className={cn('flex-1', !included && 'text-muted-foreground line-through')} numberOfLines={1}>
                    {name}
                  </Text>
                </View>
                <View className='flex-1 items-end'>
                  {!included ? (
                    <Text className='text-muted-foreground'>—</Text>
                  ) : state.mode === 'equal' ? (
                    <MoneyText cents={shares[id] ?? 0} />
                  ) : state.mode === 'parts' ? (
                    <View className='w-full flex-row items-center gap-2'>
                      <PercentInput
                        className='flex-1'
                        valueBasisPoints={state.percents[id] ?? 0}
                        onChangeBasisPoints={(bps) => setPercent(id, bps)}
                        locale={locale}
                        accessibilityLabel={t('expenses.percentOf', { name })}
                        editable={!readOnly}
                        invalid={submitted && problem === 'percent_sum'}
                      />
                      {/* Fixed width: if the share's text width changed while typing, the
                          input would be resized mid-edit, and Android then restores the
                          previous text (typing "20" ends up as "2"). */}
                      <View className='w-20 items-end'>
                        <MoneyText cents={shares[id] ?? 0} size='sm' tone='muted' />
                      </View>
                    </View>
                  ) : (
                    <MoneyInput
                      className='w-full'
                      valueCents={state.amounts[id] ?? 0}
                      onChangeCents={(cents) => setAmount(id, cents ?? 0)}
                      accessibilityLabel={t('expenses.amountOf', { name })}
                      invalid={submitted && problem === 'amount_sum'}
                    />
                  )}
                </View>
              </View>
            );
          })
        ) : (
          <Text className='px-3 py-3 text-sm text-muted-foreground'>{t('expenses.notSplit')}</Text>
        )}
      </View>

      {problem === 'no_members' && submitted ? (
        <Text className='text-sm text-destructive'>{t('quick.selectAtLeastOne')}</Text>
      ) : null}
      {problem === 'percent_sum' ? (
        <Text className={cn('text-sm', submitted ? 'text-destructive' : 'text-muted-foreground')}>
          {t('expenses.percentSum', {
            current: new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(
              sumOf(state.percents, state.included) / 100,
            ),
          })}
        </Text>
      ) : null}
      {problem === 'amount_sum' ? (
        <Text className={cn('text-sm', submitted ? 'text-destructive' : 'text-muted-foreground')}>
          {t('expenses.amountSum', {
            current: displayMoney(sumOf(state.amounts, state.included), locale),
            total: displayMoney(total, locale),
          })}
        </Text>
      ) : null}
    </View>
  );
}
