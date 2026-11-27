import { router, type Href } from 'expo-router';
import {
  addNotificationReceivedListener,
  addNotificationResponseReceivedListener,
  addPushTokenListener,
  clearLastNotificationResponse,
  getLastNotificationResponse,
  setNotificationHandler,
  type NotificationResponse,
} from 'expo-notifications';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform } from 'react-native';
import { queryClient, queryKeys } from '@/lib/query/client';
import { reportError } from '@/lib/sentry';
import { useSessionStore } from '@/stores/session';
import { registerChangedToken, registerIfGranted } from './register';
import { notificationTarget, type NotificationTarget } from './routing';

const isSupported = Platform.OS === 'android' || Platform.OS === 'ios';

if (isSupported) {
  // Pushes that arrive with the app open are shown as a banner too.
  setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

function refresh(target: NotificationTarget) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.group(target.groupId) });
  if (target.type === 'member_joined') void queryClient.invalidateQueries({ queryKey: queryKeys.groups() });
}

// Registration runs in the background, so a failure is otherwise invisible: the device
// just stops getting pushes.
function warn(message: string) {
  return (error: unknown) => {
    console.warn(message, error);
    reportError(error, 'notifications.register');
  };
}

/**
 * Push notifications while signed in: keeps this device registered (also when the token or
 * the app language changes), refreshes the group's data when a push arrives and opens the
 * linked screen when one is tapped, including the tap that launched the app.
 */
export function NotificationObserver() {
  const status = useSessionStore((s) => s.status);
  const { i18n } = useTranslation();
  const language = i18n.language;
  const signedIn = status === 'signedIn';

  useEffect(() => {
    if (!isSupported || !signedIn) return;
    void registerIfGranted().catch(warn('Failed to register for push notifications'));
  }, [signedIn, language]);

  useEffect(() => {
    if (!isSupported || !signedIn) return;
    const subscription = addPushTokenListener((token) => {
      void registerChangedToken(token).catch(warn('Failed to refresh the push token'));
    });
    return () => subscription.remove();
  }, [signedIn]);

  useEffect(() => {
    if (!isSupported || !signedIn) return;
    const subscription = addNotificationReceivedListener((notification) => {
      const target = notificationTarget(notification.request.content.data);
      if (target) refresh(target);
    });
    return () => subscription.remove();
  }, [signedIn]);

  useEffect(() => {
    if (!isSupported || !signedIn) return;
    function open(response: NotificationResponse) {
      clearLastNotificationResponse();
      const target = notificationTarget(response.notification.request.content.data);
      if (!target) return;
      refresh(target);
      router.push(target.url as Href);
    }
    // The tap that opened the app from a cold start.
    const last = getLastNotificationResponse();
    if (last) open(last);
    const subscription = addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, [signedIn]);

  return null;
}
