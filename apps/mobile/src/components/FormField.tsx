import { type ReactElement, useId } from 'react';
import {
  Controller,
  type Control,
  type ControllerFieldState,
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
} from 'react-hook-form';
import { View } from 'react-native';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { cn } from '@/lib/utils';

type FormFieldProps<TValues extends FieldValues, TName extends FieldPath<TValues>> = {
  control: Control<TValues>;
  name: TName;
  label: string;
  description?: string;
  className?: string;
  render: (args: {
    field: ControllerRenderProps<TValues, TName>;
    fieldState: ControllerFieldState;
    /** Pass to the input as `nativeID` so the label is associated with it. */
    inputId: string;
  }) => ReactElement;
};

/**
 * React Hook Form `Controller` wrapper: label, description, error message and a11y wiring.
 * Error messages are i18n keys or plain strings produced by the Zod schema.
 */
export function FormField<TValues extends FieldValues, TName extends FieldPath<TValues>>({
  control,
  name,
  label,
  description,
  className,
  render,
}: FormFieldProps<TValues, TName>) {
  const inputId = useId();
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <View className={cn('gap-1.5', className)}>
          <Label nativeID={`${inputId}-label`} className={cn(fieldState.error && 'text-destructive')}>
            {label}
          </Label>
          {render({ field, fieldState, inputId })}
          {description && !fieldState.error ? (
            <Text className='text-sm text-muted-foreground'>{description}</Text>
          ) : null}
          {fieldState.error?.message ? (
            <Text className='text-sm text-destructive' accessibilityLiveRegion='polite'>
              {fieldState.error.message}
            </Text>
          ) : null}
        </View>
      )}
    />
  );
}
