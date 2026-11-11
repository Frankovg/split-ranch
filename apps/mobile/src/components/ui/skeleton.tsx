// Source: react-native-reusables skeleton (CLI 0.7.1, nativewind) @ 2026-11-07. Local changes: none.
import { type ComponentProps, type RefAttributes } from 'react';
import { cn } from '@/lib/utils';
import { View } from 'react-native';

function Skeleton({
  className,
  ...props
}: ComponentProps<typeof View> & RefAttributes<View>) {
  return <View className={cn('bg-accent animate-pulse rounded-md', className)} {...props} />;
}

export { Skeleton };
