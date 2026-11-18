// Source: react-native-reusables toggle (CLI 0.7.1, nativewind) @ 2026-11-07. Local changes: touch targets raised to >= 48dp (h-12), removed sm: shrink; portfolio style: rounded-sm, the pressed state is a card surface with a primary border and semibold text.
import { type ComponentProps, useContext } from 'react';
import { Icon } from '@/components/ui/icon';
import { TextClassContext } from '@/components/ui/text';
import { cn } from '@/lib/utils';
import * as TogglePrimitive from '@rn-primitives/toggle';
import { cva, type VariantProps } from 'class-variance-authority';
import { Platform } from 'react-native';

const toggleVariants = cva(
  cn(
    'active:bg-muted group flex flex-row items-center justify-center gap-2 rounded-sm',
    Platform.select({
      web: 'hover:bg-muted hover:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive inline-flex cursor-default whitespace-nowrap outline-none transition-[color,box-shadow] focus-visible:ring-[3px] disabled:pointer-events-none [&_svg]:pointer-events-none',
    })
  ),
  {
    variants: {
      variant: {
        default: 'bg-transparent',
        outline: cn(
          'border-input active:bg-accent border bg-transparent',
          Platform.select({
            web: 'hover:bg-accent hover:text-accent-foreground',
          })
        ),
      },
      size: {
        default: 'h-12 min-w-12 px-3',
        sm: 'h-12 min-w-12 px-2',
        lg: 'h-14 min-w-14 px-3',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

function Toggle({
  className,
  variant,
  size,
  ...props
}: ComponentProps<typeof TogglePrimitive.Root> & VariantProps<typeof toggleVariants>) {
  return (
    <TextClassContext.Provider
      value={cn(
        'text-sm text-foreground font-sans font-medium',
        props.pressed
          ? 'text-foreground font-semibold'
          : Platform.select({ web: 'group-hover:text-muted-foreground' }),
        className
      )}>
      <TogglePrimitive.Root
        className={cn(
          toggleVariants({ variant, size }),
          props.disabled && 'opacity-50',
          props.pressed && 'bg-card border-primary',
          className
        )}
        {...props}
      />
    </TextClassContext.Provider>
  );
}

function ToggleIcon({ className, ...props }: ComponentProps<typeof Icon>) {
  const textClass = useContext(TextClassContext);
  return <Icon className={cn('size-4 shrink-0', textClass, className)} {...props} />;
}

export { Toggle, ToggleIcon, toggleVariants };
