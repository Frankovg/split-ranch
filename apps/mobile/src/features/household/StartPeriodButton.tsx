import { Play } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Alert } from 'react-native';
import { toast } from 'sonner-native';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { useStartPeriod } from './api';
import type { Period } from './types';

/** Starts the next period after `latest` closed. Any member can do it. */
export function StartPeriodButton({
  householdId,
  latest,
  onStarted,
}: {
  householdId: string;
  latest: Period;
  onStarted?: (period: Period) => void;
}) {
  const { t } = useTranslation();
  const start = useStartPeriod(householdId);
  const next = latest.seq + 1;
  const onPress = () =>
    Alert.alert(t('period.startTitle', { seq: next }), t('period.startBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('period.start'),
        onPress: () =>
          start.mutate(undefined, {
            onSuccess: (period) => {
              toast.success(t('period.started', { seq: period.seq }));
              onStarted?.(period);
            },
            onError: () => toast.error(t('period.startFailed')),
          }),
      },
    ]);
  return (
    <Button size='lg' disabled={start.isPending} onPress={onPress}>
      <Icon as={Play} size={20} />
      <Text>{t('period.start')}</Text>
    </Button>
  );
}
