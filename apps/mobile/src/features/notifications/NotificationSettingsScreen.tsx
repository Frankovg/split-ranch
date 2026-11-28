import { BellOff, Settings as SettingsIcon } from 'lucide-react-native';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AppState, Linking, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Text } from '@/components/ui/text';
import { reportError } from '@/lib/sentry';
import { useNotificationPrefs, useUpdateNotificationPrefs } from './api';
import { EVENT_PREFS, type EventPref } from './prefs';
import { pushPermission, requestAndRegister } from './register';
import type { NotificationPrefsUpdate } from './types';

type Permission = Awaited<ReturnType<typeof pushPermission>>;

/** Re-reads the OS permission on mount and whenever the app returns to the foreground. */
function usePushPermission() {
  const [permission, setPermission] = useState<Permission>(null);
  const refresh = useCallback(() => {
    void pushPermission()
      .then(setPermission)
      .catch((error: unknown) => console.warn('Failed to read the notification permission', error));
  }, []);
  useEffect(() => {
    refresh();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') refresh();
    });
    return () => subscription.remove();
  }, [refresh]);
  return { permission, setPermission };
}

type RowProps = {
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
};

function SwitchRow({ label, description, checked, disabled, onCheckedChange }: RowProps) {
  return (
    <View className='flex-row items-center gap-4 py-1'>
      <View className='flex-1 gap-0.5'>
        <Label disabled={disabled} onPress={() => !disabled && onCheckedChange(!checked)}>
          {label}
        </Label>
        <Text className='text-sm text-muted-foreground'>{description}</Text>
      </View>
      <Switch
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        accessibilityLabel={label}
      />
    </View>
  );
}

export function NotificationSettingsScreen() {
  const { t } = useTranslation();
  const { prefs, isPending, isError, refetch } = useNotificationPrefs();
  const update = useUpdateNotificationPrefs();
  const { permission, setPermission } = usePushPermission();

  const save = (changes: NotificationPrefsUpdate) =>
    update.mutate(changes, { onError: () => toast.error(t('notifications.saveError')) });

  const setEnabled = (enabled: boolean) => {
    save({ enabled });
    if (!enabled) return;
    // Turning notifications on is the moment to ask for the system permission.
    void requestAndRegister()
      .then(setPermission)
      .catch((error: unknown) => {
        console.warn('Failed to register for push notifications', error);
        reportError(error, 'notifications.register');
      });
  };

  if (!prefs) {
    return (
      <Screen>
        {isPending ? (
          <Text className='text-center text-muted-foreground'>{t('common.loading')}</Text>
        ) : isError ? (
          <View className='items-center gap-3'>
            <Text className='text-center text-muted-foreground'>{t('common.error')}</Text>
            <Button variant='outline' onPress={() => void refetch()}>
              <Text>{t('common.retry')}</Text>
            </Button>
          </View>
        ) : null}
      </Screen>
    );
  }

  const eventLabel: Record<EventPref, { label: string; description: string }> = {
    expense_created: {
      label: t('notifications.expenseCreated'),
      description: t('notifications.expenseCreatedHint'),
    },
    expense_changed: {
      label: t('notifications.expenseChanged'),
      description: t('notifications.expenseChangedHint'),
    },
    payments: { label: t('notifications.payments'), description: t('notifications.paymentsHint') },
    member_joined: {
      label: t('notifications.memberJoined'),
      description: t('notifications.memberJoinedHint'),
    },
  };

  return (
    <Screen>
      {prefs.enabled && permission === 'denied' ? (
        <Card className='border-warning'>
          <CardContent className='gap-3 pt-6'>
            <View className='flex-row items-center gap-2'>
              <Icon as={BellOff} size={18} className='text-warning' />
              <Text className='flex-1 font-medium'>{t('notifications.blockedTitle')}</Text>
            </View>
            <Text className='text-sm text-muted-foreground'>{t('notifications.blockedBody')}</Text>
            <Button variant='outline' onPress={() => void Linking.openSettings()}>
              <Icon as={SettingsIcon} size={18} />
              <Text>{t('notifications.openSettings')}</Text>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className='pt-6'>
          <SwitchRow
            label={t('notifications.enabled')}
            description={t('notifications.enabledHint')}
            checked={prefs.enabled}
            onCheckedChange={setEnabled}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('notifications.events')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-2'>
          {EVENT_PREFS.map((key, index) => (
            <View key={key} className='gap-2'>
              {index > 0 ? <Separator /> : null}
              <SwitchRow
                label={eventLabel[key].label}
                description={eventLabel[key].description}
                checked={prefs[key]}
                disabled={!prefs.enabled}
                onCheckedChange={(checked) => save({ [key]: checked })}
              />
            </View>
          ))}
        </CardContent>
      </Card>

      <Text className='text-center text-sm text-muted-foreground'>{t('notifications.footer')}</Text>
    </Screen>
  );
}
