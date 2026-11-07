import { cva, type VariantProps } from 'class-variance-authority';
import { useTranslation } from 'react-i18next';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { spokenMoney } from '@/lib/money/spoken';
import { cn } from '@/lib/utils';

const moneyTextVariants = cva('tabular-nums font-semibold', {
  variants: {
    tone: {
      default: 'text-foreground',
      muted: 'text-muted-foreground',
      positive: 'text-positive',
      negative: 'text-negative',
    },
    size: {
      sm: 'text-sm',
      base: 'text-base',
      lg: 'text-lg',
      xl: 'text-xl',
      '3xl': 'text-3xl',
    },
  },
  defaultVariants: { tone: 'default', size: 'base' },
});

type MoneyTextProps = VariantProps<typeof moneyTextVariants> & {
  cents: number;
  /** Optional spoken prefix, e.g. "Ana" or "Debes", announced before the amount. */
  accessibilityPrefix?: string;
  className?: string;
};

/**
 * Euro amount with tabular figures. Never truncates (no numberOfLines): it wraps
 * at large font scales instead. Screen readers hear the amount spelled out.
 */
export function MoneyText({ cents, tone, size, accessibilityPrefix, className }: MoneyTextProps) {
  const { t } = useTranslation();
  const spoken = spokenMoney(cents, t);
  return (
    <Text
      className={cn(moneyTextVariants({ tone, size }), className)}
      accessible
      accessibilityLabel={accessibilityPrefix ? `${accessibilityPrefix}: ${spoken}` : spoken}>
      {displayMoney(cents, currentMoneyLocale())}
    </Text>
  );
}
