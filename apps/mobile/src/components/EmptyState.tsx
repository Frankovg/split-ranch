import type { LucideIcon } from 'lucide-react-native';
import { View } from 'react-native';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { cn } from '@/lib/utils';

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  body?: string;
  action?: { label: string; onPress: () => void };
  className?: string;
};

/** Icon + text + optional primary action, for empty lists and not-yet-available screens. */
export function EmptyState({ icon, title, body, action, className }: EmptyStateProps) {
  return (
    <View className={cn('items-center justify-center gap-3 px-6 py-12', className)}>
      <View className="rounded-full bg-muted p-4" importantForAccessibility="no-hide-descendants">
        <Icon as={icon} size={32} className="text-muted-foreground" />
      </View>
      <Text className="text-center text-lg font-semibold" role="heading">
        {title}
      </Text>
      {body ? <Text className="text-center text-muted-foreground">{body}</Text> : null}
      {action ? (
        <Button onPress={action.onPress} className="mt-2">
          <Text>{action.label}</Text>
        </Button>
      ) : null}
    </View>
  );
}
