import Constants from 'expo-constants';
import {
  getExpoPushTokenAsync,
  getPermissionsAsync,
  requestPermissionsAsync,
  type DevicePushToken,
  type PermissionStatus,
} from 'expo-notifications';
import { Platform } from 'react-native';
import i18n from '@/i18n';
import { api, unwrap } from '@/lib/api';
import { isApiConfigured } from '@/lib/env';
import { ensureChannels } from './channels';

/**
 * This device's push registration. The Expo push token is sent to the API together with
 * the app language, which the server uses for the notification text. Nothing here throws
 * for "not supported" cases (web, no projectId, no API): they just register nothing.
 */

const isSupported = Platform.OS === 'android' || Platform.OS === 'ios';

/** Last token sent to the API, so sign-out can remove it without asking Expo again. */
let registeredToken: string | null = null;

/** Last native device token handled by registerChangedToken, to drop repeated events. */
let lastDeviceToken: string | null = null;

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? Constants.easConfig?.projectId;
}

/** Without devicePushToken, Expo fetches the native token itself (see registerChangedToken). */
async function expoToken(devicePushToken?: DevicePushToken): Promise<string | null> {
  const id = projectId();
  if (!id) {
    console.warn('Push notifications disabled: the EAS projectId is missing from the app config');
    return null;
  }
  return (await getExpoPushTokenAsync({ projectId: id, devicePushToken })).data;
}

async function sendToken(token: string): Promise<void> {
  await unwrap(
    api.PUT('/v1/me/push-tokens', {
      body: {
        token,
        platform: Platform.OS === 'ios' ? 'ios' : 'android',
        locale: i18n.language === 'en' ? 'en' : 'es',
      },
    }),
  );
  registeredToken = token;
}

export async function pushPermission(): Promise<PermissionStatus | null> {
  if (!isSupported) return null;
  return (await getPermissionsAsync()).status;
}

/** Registers the device when permission is already granted (never prompts). */
export async function registerIfGranted(): Promise<boolean> {
  if (!isSupported || !isApiConfigured) return false;
  await ensureChannels();
  if ((await getPermissionsAsync()).status !== 'granted') return false;
  const token = await expoToken();
  if (!token) return false;
  await sendToken(token);
  return true;
}

/**
 * Registers the token delivered by the push token listener. On Android every native token
 * fetch (including the one inside getExpoPushTokenAsync) also fires that listener, so this
 * reuses the delivered token instead of fetching again (which would loop) and skips tokens
 * it already handled.
 */
export async function registerChangedToken(devicePushToken: DevicePushToken): Promise<void> {
  if (!isSupported || !isApiConfigured) return;
  const key =
    typeof devicePushToken.data === 'string' ? devicePushToken.data : JSON.stringify(devicePushToken.data);
  if (key === lastDeviceToken) return;
  lastDeviceToken = key;
  try {
    const token = await expoToken(devicePushToken);
    if (token) await sendToken(token);
  } catch (error) {
    // Let a later event for the same token try again.
    lastDeviceToken = null;
    throw error;
  }
}

/**
 * Asks for permission when the system still allows it, then registers. Returns the
 * resulting permission status ('denied' means only the system settings can change it).
 */
export async function requestAndRegister(): Promise<PermissionStatus | null> {
  if (!isSupported) return null;
  await ensureChannels();
  const current = await getPermissionsAsync();
  let status = current.status;
  if (status !== 'granted' && current.canAskAgain) {
    status = (await requestPermissionsAsync()).status;
  }
  if (status === 'granted' && isApiConfigured) {
    const token = await expoToken();
    if (token) await sendToken(token);
  }
  return status;
}

/** Asks once, in context (e.g. after the first expense), if the user was never asked. */
export async function askOnceInContext(): Promise<void> {
  if (!isSupported) return;
  const current = await getPermissionsAsync();
  if (current.status === 'undetermined' && current.canAskAgain) await requestAndRegister();
}

/** Stops pushes to this device for the signed-in user. Call it before signing out. */
export async function unregisterDevice(): Promise<void> {
  if (!isSupported || !isApiConfigured) return;
  let token = registeredToken;
  if (!token && (await getPermissionsAsync()).status === 'granted') token = await expoToken();
  if (!token) return;
  await unwrap(api.DELETE('/v1/me/push-tokens', { body: { token } }));
  registeredToken = null;
}
