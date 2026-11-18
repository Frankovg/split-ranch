import { Check } from 'lucide-react-native';
import { Pressable, View } from 'react-native';
import { Icon } from '@/components/ui/icon';
import { cn } from '@/lib/utils';

type CheckboxProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  accessibilityLabel: string;
  disabled?: boolean;
};

/** Square checkbox with a 48dp touch target. */
export function Checkbox({ checked, onCheckedChange, accessibilityLabel, disabled }: CheckboxProps) {
  return (
    <Pressable
      role='checkbox'
      aria-checked={checked}
      accessibilityLabel={accessibilityLabel}
      disabled={disabled}
      onPress={() => onCheckedChange(!checked)}
      hitSlop={8}
      className={cn('size-10 items-center justify-center', disabled && 'opacity-50')}>
      <View
        className={cn(
          'size-6 items-center justify-center rounded-md border-2',
          checked ? 'border-primary bg-primary' : 'border-input bg-transparent',
        )}>
        {checked ? <Icon as={Check} size={16} strokeWidth={3} className='text-primary-foreground' /> : null}
      </View>
    </Pressable>
  );
}
