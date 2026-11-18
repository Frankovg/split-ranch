import { ChevronDown } from 'lucide-react-native';
import { type ReactNode, useEffect } from 'react';
import { type LayoutChangeEvent, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { Icon } from '@/components/ui/icon';

/** Shared by the panel and its chevron so both move together. */
export const COLLAPSE_DURATION_MS = 250;

/** 1 when expanded, 0 when collapsed; animates on change but not on mount. */
function useExpandProgress(expanded: boolean) {
  const progress = useSharedValue(expanded ? 1 : 0);
  useEffect(() => {
    // withTiming follows the system "reduce motion" setting by default.
    progress.value = withTiming(expanded ? 1 : 0, { duration: COLLAPSE_DURATION_MS });
  }, [expanded, progress]);
  return progress;
}

/**
 * Animates its children's height between 0 and their natural height. The content is
 * laid out absolutely so it can be measured while the clipping wrapper is collapsed
 * (pattern from the Reanimated accordion example).
 */
export function Collapsible({ expanded, children }: { expanded: boolean; children: ReactNode }) {
  const progress = useExpandProgress(expanded);
  const contentHeight = useSharedValue(0);
  const style = useAnimatedStyle(() => ({
    height: contentHeight.value * progress.value,
    opacity: progress.value,
  }));

  const onLayout = (e: LayoutChangeEvent) => {
    contentHeight.value = e.nativeEvent.layout.height;
  };

  return (
    <Animated.View
      style={[{ overflow: 'hidden' }, style]}
      pointerEvents={expanded ? 'auto' : 'none'}
      accessibilityElementsHidden={!expanded}
      importantForAccessibility={expanded ? 'auto' : 'no-hide-descendants'}>
      <View className='absolute inset-x-0 top-0' onLayout={onLayout}>
        {children}
      </View>
    </Animated.View>
  );
}

/** Chevron that points down when collapsed and up when expanded. */
export function CollapsibleChevron({ expanded }: { expanded: boolean }) {
  const progress = useExpandProgress(expanded);
  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${progress.value * 180}deg` }] }));
  return (
    <Animated.View style={style}>
      <Icon as={ChevronDown} size={20} className='text-muted-foreground' />
    </Animated.View>
  );
}
