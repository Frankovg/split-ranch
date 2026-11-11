import { type ReactNode } from 'react';
import { ScrollView, View } from 'react-native';
import { SafeAreaView, type Edge } from 'react-native-safe-area-context';
import { cn } from '@/lib/utils';

type ScreenProps = {
  children: ReactNode;
  scroll?: boolean;
  edges?: Edge[];
  className?: string;
};

/** Screen container: themed background, safe area, standard gutter (px-4). */
export function Screen({ children, scroll = true, edges = ['bottom'], className }: ScreenProps) {
  return (
    <SafeAreaView edges={edges} className='flex-1 bg-background'>
      {scroll ? (
        <ScrollView
          keyboardShouldPersistTaps='handled'
          contentContainerClassName={cn('gap-4 px-4 py-4', className)}>
          {children}
        </ScrollView>
      ) : (
        <View className={cn('flex-1 gap-4 px-4 py-4', className)}>{children}</View>
      )}
    </SafeAreaView>
  );
}
