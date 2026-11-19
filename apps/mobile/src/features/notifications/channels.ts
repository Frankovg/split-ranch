import { AndroidImportance, setNotificationChannelAsync } from 'expo-notifications';
import { Platform } from 'react-native';
import i18n from '@/i18n';

/**
 * Android notification channels; the API sends each push to one of them
 * (CHANNEL_FOR_KIND in apps/api use_cases/notifications.py). Users can mute a channel in
 * the system settings. On Android 13+ the permission prompt only appears once a channel
 * exists, so this runs before asking for permission or a token.
 */
export const CHANNELS = ['expenses', 'payments', 'group'] as const;

export async function ensureChannels(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await Promise.all(
    CHANNELS.map((id) =>
      setNotificationChannelAsync(id, {
        name: i18n.t(`notifications.channels.${id}`),
        importance: AndroidImportance.HIGH,
        lightColor: '#178264',
      }),
    ),
  );
}
