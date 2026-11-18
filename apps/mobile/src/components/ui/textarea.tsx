// Source: react-native-reusables textarea (CLI 0.7.1, nativewind) @ 2026-11-07. Local changes: portfolio style (brand font, transparent background, mint border on focus).
import { type ComponentProps, type RefAttributes } from 'react';
import { cn } from '@/lib/utils';
import { Platform, TextInput } from 'react-native';

function Textarea({
  className,
  multiline = true,
  numberOfLines = Platform.select({ web: 2, native: 8 }), // On web, numberOfLines also determines initial height. On native, it determines the maximum height.
  placeholderClassName,
  ...props
}: ComponentProps<typeof TextInput> & RefAttributes<TextInput>) {
  return (
    <TextInput
      className={cn(
        'text-foreground font-sans border-input flex min-h-16 w-full flex-row rounded-md border bg-transparent px-3 py-2 text-base shadow-sm shadow-black/5 md:text-sm',
        Platform.select({
          web: 'placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive field-sizing-content resize-y outline-none transition-[color,box-shadow] focus-visible:ring-[3px] disabled:cursor-not-allowed',
        }),
        Platform.select({ native: 'focus:border-primary' }),
        props.editable === false && 'opacity-50',
        className
      )}
      placeholderClassName={cn('text-muted-foreground', placeholderClassName)}
      multiline={multiline}
      numberOfLines={numberOfLines}
      textAlignVertical='top'
      {...props}
    />
  );
}

export { Textarea };
