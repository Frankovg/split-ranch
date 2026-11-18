import { Modal, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { type LucideIcon } from 'lucide-react-native';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { cn } from '@/lib/utils';

export type SheetOption = {
  key: string;
  icon: LucideIcon;
  label: string;
  description?: string;
  destructive?: boolean;
  onPress: () => void;
};

type SheetModalProps = {
  open: boolean;
  onClose: () => void;
  options: SheetOption[];
  /** `sheet`: slides up from the bottom (FAB actions). `menu`: drops from the top right (header ⋮). */
  variant: 'sheet' | 'menu';
  title?: string;
};

/**
 * A short list of actions over a dimmed backdrop. Picking an option closes it first, then
 * runs the action, so a navigation never lands under a still-open modal.
 */
export function SheetModal({ open, onClose, options, variant, title }: SheetModalProps) {
  const insets = useSafeAreaInsets();
  const sheet = variant === 'sheet';
  return (
    <Modal
      visible={open}
      transparent
      animationType={sheet ? 'slide' : 'fade'}
      statusBarTranslucent
      navigationBarTranslucent
      onRequestClose={onClose}>
      <Pressable
        accessibilityRole='button'
        accessibilityLabel={title}
        onPress={onClose}
        className={cn('flex-1 bg-black/50', sheet ? 'justify-end' : 'items-end')}>
        {/* Swallow taps inside the panel so only the backdrop closes it. */}
        <Pressable
          onPress={() => {}}
          style={sheet ? { paddingBottom: insets.bottom + 16 } : { marginTop: insets.top + 8 }}
          className={cn(
            'border-border bg-card gap-1 border',
            sheet ? 'rounded-t-xl px-4 pt-4' : 'mr-2 min-w-56 rounded-xl py-2',
          )}>
          {sheet ? <View className='mb-2 h-1 w-10 self-center rounded-full bg-muted-foreground/40' /> : null}
          {title ? <Text className='px-2 pb-2 text-sm text-muted-foreground'>{title}</Text> : null}
          {options.map((o) => (
            <Pressable
              key={o.key}
              accessibilityRole='button'
              onPress={() => {
                onClose();
                o.onPress();
              }}
              className={cn('flex-row items-center gap-3 rounded-sm active:bg-accent', sheet ? 'min-h-16 px-2 py-3' : 'min-h-12 px-4 py-2')}>
              <Icon as={o.icon} size={22} className={o.destructive ? 'text-destructive' : 'text-primary'} />
              <View className='flex-1'>
                <Text className={cn('font-medium', o.destructive && 'text-destructive')}>{o.label}</Text>
                {o.description ? <Text className='text-sm text-muted-foreground'>{o.description}</Text> : null}
              </View>
            </Pressable>
          ))}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
