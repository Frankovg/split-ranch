// Source: react-native-reusables button (CLI 0.7.1, nativewind) @ 2026-11-07. Local changes: touch targets raised to >= 48dp (h-12), removed sm: shrink; portfolio style: rounded-sm, the default variant is a high-contrast surface (white on dark, near-black on light) that fills with the primary colour from the left while pressed, outline uses a muted border that turns primary on press.
import { type ComponentProps, type RefAttributes } from 'react';
import { TextClassContext } from '@/components/ui/text';
import { cn } from '@/lib/utils';
import { cva, type VariantProps } from 'class-variance-authority';
import { type GestureResponderEvent, Platform, Pressable, StyleSheet, View } from 'react-native';
import Animated, { type SharedValue, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

/** Duration of the press fill, as in the portfolio's hover fill (300ms ease). */
const FILL_MS = 300;

const buttonVariants = cva(
  cn(
    'group shrink-0 flex-row items-center justify-center gap-2 overflow-hidden rounded-sm shadow-none',
    Platform.select({
      web: "focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive whitespace-nowrap outline-none transition-all focus-visible:ring-[3px] disabled:pointer-events-none [&_svg:not([class*='size-'])]:size-4 [&_svg]:pointer-events-none [&_svg]:shrink-0",
    })
  ),
  {
    variants: {
      variant: {
        default: cn('bg-foreground', Platform.select({ web: 'hover:bg-foreground/90' })),
        destructive: cn(
          'bg-destructive active:bg-destructive/90',
          Platform.select({
            web: 'hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40',
          })
        ),
        outline: cn(
          'border-muted-foreground bg-transparent active:border-primary active:bg-accent border',
          Platform.select({
            web: 'hover:border-primary hover:bg-accent',
          })
        ),
        secondary: cn(
          'bg-secondary active:bg-secondary/80',
          Platform.select({ web: 'hover:bg-secondary/80' })
        ),
        ghost: cn(
          'active:bg-accent dark:active:bg-accent/50',
          Platform.select({ web: 'hover:bg-accent dark:hover:bg-accent/50' })
        ),
        link: '',
      },
      size: {
        default: cn('h-12 px-4 py-2', Platform.select({ web: 'has-[>svg]:px-3' })),
        sm: cn('h-12 gap-1.5 rounded-sm px-3', Platform.select({ web: 'has-[>svg]:px-2.5' })),
        lg: cn('h-14 rounded-sm px-8', Platform.select({ web: 'has-[>svg]:px-4' })),
        icon: 'h-12 w-12',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

const buttonTextVariants = cva(
  cn(
    'text-foreground font-sans text-sm font-medium',
    Platform.select({ web: 'pointer-events-none transition-colors' })
  ),
  {
    variants: {
      variant: {
        default: 'text-background font-semibold',
        destructive: 'text-destructive-foreground',
        outline: cn(
          'group-active:text-accent-foreground',
          Platform.select({ web: 'group-hover:text-accent-foreground' })
        ),
        secondary: 'text-secondary-foreground',
        ghost: 'group-active:text-accent-foreground',
        link: cn(
          'text-primary group-active:underline',
          Platform.select({ web: 'underline-offset-4 hover:underline group-hover:underline' })
        ),
      },
      size: {
        default: '',
        sm: '',
        lg: 'text-base',
        icon: '',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

type ButtonProps = ComponentProps<typeof Pressable> & RefAttributes<typeof Pressable> & VariantProps<typeof buttonVariants>;

/**
 * Primary-colour layer that grows from the left edge while the button is held,
 * the touch equivalent of the portfolio's hover fill.
 */
function PressFill({ progress }: { progress: SharedValue<number> }) {
  const style = useAnimatedStyle(() => ({
    transform: [{ scaleX: progress.value }],
  }));
  return (
    // The colour lives on a plain View: className is applied to NativeWind-wrapped core components.
    <Animated.View pointerEvents='none' style={[StyleSheet.absoluteFill, { transformOrigin: 'left' }, style]}>
      <View className='flex-1 bg-primary' />
    </Animated.View>
  );
}

function Button({ className, variant, size, children, onPressIn, onPressOut, ...props }: ButtonProps) {
  const progress = useSharedValue(0);
  // Function children (render props) cannot be layered over the fill; they keep the plain look.
  const fills = (variant ?? 'default') === 'default' && typeof children !== 'function' && !props.disabled;

  const handlePressIn = (event: GestureResponderEvent) => {
    if (fills) progress.value = withTiming(1, { duration: FILL_MS });
    onPressIn?.(event);
  };
  const handlePressOut = (event: GestureResponderEvent) => {
    if (fills) progress.value = withTiming(0, { duration: FILL_MS });
    onPressOut?.(event);
  };

  return (
    <TextClassContext.Provider value={buttonTextVariants({ variant, size })}>
      <Pressable
        className={cn(props.disabled && 'opacity-50', buttonVariants({ variant, size }), className)}
        role='button'
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        {...props}>
        {fills ? (
          <>
            <PressFill progress={progress} />
            {children}
          </>
        ) : (
          children
        )}
      </Pressable>
    </TextClassContext.Provider>
  );
}

export { Button, buttonTextVariants, buttonVariants };
export type { ButtonProps };
