import '../global.css';
import '@/i18n';

import { PortalHost } from '@rn-primitives/portal';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { SplashScreen, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Toaster } from 'sonner-native';
import { useApiWarmUpOnForeground, warmUpApi } from '@/lib/api/warm-up';
import { AuthListener } from '@/features/auth/AuthListener';
import { NotificationObserver } from '@/features/notifications/NotificationObserver';
import { LanguageSync } from '@/i18n/LanguageSync';
import { CACHE_BUSTER, CACHE_MAX_AGE, queryClient } from '@/lib/query/client';
import { queryPersister } from '@/lib/query/persister';
import { useAppStateFocus } from '@/lib/query/refresh';
import { useSessionStore } from '@/stores/session';
import { FONT_FAMILY, NAV_THEME } from '@/theme/navigation';
import { ThemeSync, useAppColorScheme } from '@/theme/ThemeSync';
import { tokenColor } from '@/theme/tokens';

export { ErrorBoundary } from 'expo-router';

void SplashScreen.preventAutoHideAsync();
// Start waking the API (Render free plan sleeps when idle) while the splash is still up.
warmUpApi();

export default function RootLayout() {
  const scheme = useAppColorScheme();
  const status = useSessionStore((s) => s.status);
  const { t } = useTranslation();
  useAppStateFocus();
  useApiWarmUpOnForeground();

  useEffect(() => {
    if (status !== 'loading') SplashScreen.hide();
  }, [status]);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <PersistQueryClientProvider
          client={queryClient}
          persistOptions={{
            persister: queryPersister,
            maxAge: CACHE_MAX_AGE,
            buster: CACHE_BUSTER,
          }}
        >
          <ThemeProvider value={NAV_THEME[scheme]}>
            <ThemeSync />
            <LanguageSync />
            <AuthListener />
            <NotificationObserver />
            <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
            {status === 'loading' ? null : (
              <Stack screenOptions={{ headerShown: false }}>
                <Stack.Protected
                  guard={status === 'signedIn'}
                  redirectTo='/sign-in'
                >
                  <Stack.Screen name='(app)' />
                </Stack.Protected>
                <Stack.Protected guard={status === 'signedOut'} redirectTo='/'>
                  <Stack.Screen name='(auth)' />
                </Stack.Protected>
                {/* Quick split editor: reachable signed in and signed out. */}
                <Stack.Screen
                  name='quick/[id]'
                  options={{ headerShown: true, title: t('quick.title') }}
                />
                <Stack.Protected guard={__DEV__}>
                  <Stack.Screen
                    name='dev/gallery'
                    options={{ headerShown: true, title: t('gallery.title') }}
                  />
                </Stack.Protected>
              </Stack>
            )}
            <Toaster
              position='bottom-center'
              theme={scheme}
              toastOptions={{
                // Portfolio toasts: page surface, the variant shown by a brand-coloured border.
                style: {
                  backgroundColor: tokenColor(scheme, 'card'),
                  borderColor: tokenColor(scheme, 'border'),
                  borderWidth: 1,
                  borderRadius: 12,
                },
                titleStyle: { fontFamily: FONT_FAMILY, color: tokenColor(scheme, 'foreground') },
                descriptionStyle: { fontFamily: FONT_FAMILY, color: tokenColor(scheme, 'muted-foreground') },
                success: { borderColor: tokenColor(scheme, 'positive') },
                error: { borderColor: tokenColor(scheme, 'negative') },
                warning: { borderColor: tokenColor(scheme, 'warning') },
              }}
            />
            <PortalHost />
          </ThemeProvider>
        </PersistQueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
