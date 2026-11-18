import { useState } from 'react';
import { View } from 'react-native';
import { Input } from '@/components/ui/input';
import { Text } from '@/components/ui/text';
import { cn } from '@/lib/utils';

type PercentInputProps = {
  /** Basis points (100 % = 10000). */
  valueBasisPoints: number;
  onChangeBasisPoints: (basisPoints: number) => void;
  locale: string;
  accessibilityLabel: string;
  editable?: boolean;
  invalid?: boolean;
  className?: string;
};

function toText(bps: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2, useGrouping: false }).format(bps / 100);
}

/** "70", "33,33" or "33.33" as basis points; null when not a percentage between 0 and 100. */
export function parsePercent(text: string): number | null {
  const normalized = text.trim().replace(',', '.');
  if (!/^\d{1,3}(\.\d{0,2})?$/.test(normalized)) return null;
  const bps = Math.round(Number(normalized) * 100);
  return bps <= 10_000 ? bps : null;
}

/** Percentage entry with up to two decimals; only basis points leave this component. */
export function PercentInput({
  valueBasisPoints,
  onChangeBasisPoints,
  locale,
  accessibilityLabel,
  editable = true,
  invalid,
  className,
}: PercentInputProps) {
  const [text, setText] = useState(() => toText(valueBasisPoints, locale));

  // Follow outside changes (rebalancing) unless the text already means that value.
  const [prevValue, setPrevValue] = useState(valueBasisPoints);
  if (valueBasisPoints !== prevValue) {
    setPrevValue(valueBasisPoints);
    if (parsePercent(text) !== valueBasisPoints) setText(toText(valueBasisPoints, locale));
  }

  return (
    <View className={cn('flex-row items-center', className)}>
      <Input
        value={text}
        onChangeText={(next) => {
          setText(next);
          const bps = next.trim() === '' ? 0 : parsePercent(next);
          if (bps !== null) onChangeBasisPoints(bps);
        }}
        onBlur={() => setText(toText(valueBasisPoints, locale))}
        keyboardType='decimal-pad'
        inputMode='decimal'
        selectTextOnFocus
        editable={editable}
        accessibilityLabel={accessibilityLabel}
        aria-invalid={invalid}
        className={cn('tabular-nums flex-1 pr-8 text-right', invalid && 'border-destructive')}
      />
      <Text className='absolute right-3 text-muted-foreground' importantForAccessibility='no'>
        %
      </Text>
    </View>
  );
}
