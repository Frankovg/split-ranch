// Source: react-native-reusables native-only-animated-view (CLI 0.7.1, nativewind) @ 2026-11-07. Local changes: none.
import { type ComponentProps, type ReactNode, type RefAttributes } from 'react';
import { Platform, Pressable } from 'react-native';
import Animated from 'react-native-reanimated';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

/**
 * This component is used to wrap animated views that should only be animated on native.
 * @param props - The props for the animated view.
 * @returns The animated view if the platform is native, otherwise the children.
 * @example
 * <NativeOnlyAnimatedView entering={FadeIn} exiting={FadeOut}>
 *   <Text>I am only animated on native</Text>
 * </NativeOnlyAnimatedView>
 */
function NativeOnlyAnimatedView(
  props: (ComponentProps<typeof Animated.View> & RefAttributes<typeof Animated.View> 
    & { as?: 'View' }) | (ComponentProps<typeof AnimatedPressable> & RefAttributes<typeof AnimatedPressable> & { as: 'Pressable' })
) {
  if (Platform.OS === 'web') {
    return <>{props.children as ReactNode}</>;
  } else {
    if (props.as === 'Pressable'){
      return <AnimatedPressable {...props} />;
    }
    return <Animated.View {...props} />;
  }
}

export { NativeOnlyAnimatedView };
