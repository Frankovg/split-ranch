import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { Input } from '@/components/ui/input';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { formatAmount, parseMoney, plainSpaces } from '@/lib/money';
import { cn } from '@/lib/utils';

type MoneyInputProps = {
  /** Value in integer cents; null when empty or invalid. */
  valueCents: number | null;
  onChangeCents: (cents: number | null) => void;
  /** Big numeric entry for the primary amount of a screen. */
  size?: 'default' | 'lg';
  accessibilityLabel: string;
  /** External error message (e.g. from a form); shown instead of the parse error. */
  error?: string;
  /** Marks the field invalid (red border) when the message is rendered elsewhere, e.g. by FormField. */
  invalid?: boolean;
  onBlur?: () => void;
  nativeID?: string;
  className?: string;
};

function toText(cents: number | null): string {
  return cents === null ? '' : plainSpaces(formatAmount(cents, currentMoneyLocale()), '');
}

/**
 * Euro amount input. Parsing is delegated to `parseMoney` from @split-ranch/domain
 * (accepts "12", "12,5", "1.234,56"...); cents are the only value that leaves this component.
 */
export function MoneyInput({
  valueCents,
  onChangeCents,
  size = 'default',
  accessibilityLabel,
  error,
  invalid,
  onBlur,
  nativeID,
  className,
}: MoneyInputProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(() => toText(valueCents));
  const [touched, setTouched] = useState(false);

  // Sync when the value is changed from outside (e.g. form reset). Adjusted during render
  // (react.dev "adjusting state when a prop changes") instead of in an effect, which
  // would cost an extra render with stale text.
  const [prevValueCents, setPrevValueCents] = useState(valueCents);
  if (valueCents !== prevValueCents) {
    setPrevValueCents(valueCents);
    if (parseMoney(text) !== valueCents) setText(toText(valueCents));
  }

  const parsed = text.trim() === '' ? null : parseMoney(text);
  const parseError = touched && text.trim() !== '' && parsed === null ? t('money.invalid') : undefined;
  const message = error ?? parseError;

  return (
    <View className='gap-1'>
      <View className='flex-row items-center'>
        <Input
          nativeID={nativeID}
          value={text}
          onChangeText={(value) => {
            setText(value);
            onChangeCents(value.trim() === '' ? null : parseMoney(value));
          }}
          onBlur={() => {
            setTouched(true);
            if (parsed !== null) setText(toText(parsed));
            onBlur?.();
          }}
          keyboardType='decimal-pad'
          inputMode='decimal'
          placeholder={t('money.placeholder')}
          accessibilityLabel={accessibilityLabel}
          aria-invalid={invalid || message !== undefined}
          className={cn(
            'tabular-nums flex-1 pr-10 text-right',
            size === 'lg' && 'h-16 text-3xl font-semibold',
            (invalid || message !== undefined) && 'border-destructive',
            className,
          )}
        />
        <Text
          className={cn('absolute right-3 text-muted-foreground', size === 'lg' && 'text-2xl')}
          importantForAccessibility='no'>
          €
        </Text>
      </View>
      {message ? (
        <Text className='text-sm text-destructive' accessibilityLiveRegion='polite'>
          {message}
        </Text>
      ) : null}
    </View>
  );
}
