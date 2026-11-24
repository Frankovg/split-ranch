import { Plus } from 'lucide-react-native';
import { Pressable } from 'react-native';
import { Icon } from '@/components/ui/icon';

/** Height plus bottom margin of the FAB: lists add this as bottom padding so nothing hides under it. */
export const FAB_CLEARANCE = 96;

/**
 * The primary "+" action, centred at the bottom of the screen (mint, as the portfolio's
 * accent). Place it as the last child of a `flex-1` container that has no bottom padding:
 * absolute children ignore the parent's padding, so a SafeAreaView's bottom inset does not
 * lift it above the Android navigation bar. Wrap it in a plain `flex-1` View inside the
 * SafeAreaView instead.
 */
export function Fab({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole='button'
      accessibilityLabel={label}
      onPress={onPress}
      className='absolute bottom-6 h-16 w-16 items-center justify-center self-center rounded-full bg-primary shadow-lg shadow-black/40 active:bg-primary/85'>
      <Icon as={Plus} size={30} className='text-primary-foreground' />
    </Pressable>
  );
}
