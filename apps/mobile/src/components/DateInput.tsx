import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { CalendarDays } from 'lucide-react-native';
import { Platform, Pressable, View } from 'react-native';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { cn } from '@/lib/utils';

type DateInputProps = {
  /** Calendar day as "YYYY-MM-DD". */
  value: string;
  onChange: (value: string) => void;
  /** Latest selectable day ("YYYY-MM-DD"). */
  maximumDate?: string;
  locale: string;
  accessibilityLabel: string;
  disabled?: boolean;
  className?: string;
};

/** "YYYY-MM-DD" as a local Date at midnight (no time zone shift). */
function toDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

function toIso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Field showing a calendar day; tapping it opens the native date picker. */
export function DateInput({
  value,
  onChange,
  maximumDate,
  locale,
  accessibilityLabel,
  disabled,
  className,
}: DateInputProps) {
  const date = toDate(value);
  const max = maximumDate ? toDate(maximumDate) : undefined;

  if (Platform.OS === 'ios') {
    return (
      <View className={cn('h-12 justify-center', className)}>
        <DateTimePicker
          value={date}
          mode='date'
          display='compact'
          maximumDate={max}
          locale={locale}
          disabled={disabled}
          accessibilityLabel={accessibilityLabel}
          onValueChange={(_event, selected) => onChange(toIso(selected))}
        />
      </View>
    );
  }

  const open = () =>
    DateTimePickerAndroid.open({
      value: date,
      mode: 'date',
      maximumDate: max,
      firstDayOfWeek: 1,
      onValueChange: (_event, selected) => onChange(toIso(selected)),
      onError: (error) => console.warn('Date picker failed', error),
    });

  const label = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
  return (
    <Pressable
      accessibilityRole='button'
      accessibilityLabel={`${accessibilityLabel}: ${label}`}
      disabled={disabled}
      onPress={open}
      className={cn(
        'h-12 flex-row items-center gap-2 rounded-md border border-input px-3 active:bg-accent',
        disabled && 'opacity-50',
        className,
      )}>
      <Icon as={CalendarDays} size={18} className='text-muted-foreground' />
      <Text className='flex-1' numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}
