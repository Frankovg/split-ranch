import '../global.css';
import '@/i18n';

import { PortalHost } from '@rn-primitives/portal';
import { QueryClientProvider } from '@tanstack/react-query';
import { SplashScreen, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Toaster } from 'sonner-native';
import { AuthListener } from '@/features/auth/AuthListener';
import { LanguageSync } from '@/i18n/LanguageSync';
import { queryClient } from '@/lib/query/client';
import { useAppStateFocus } from '@/lib/query/refresh';
import { useSessionStore } from '@/stores/session';
import { NAV_THEME } from '@/theme/navigation';
import { ThemeSync, useAppColorScheme } from '@/theme/ThemeSync';

export { ErrorBoundary } from 'expo-router';

void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useAppColorScheme();
  const status = useSessionStore((s) => s.status);
  const { t } = useTranslation();
  useAppStateFocus();

  useEffect(() => {
    if (status !== 'loading') SplashScreen.hide();
  }, [status]);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider value={NAV_THEME[scheme]}>
            <ThemeSync />
            <LanguageSync />
            <AuthListener />
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
            <Toaster position='bottom-center' />
            <PortalHost />
          </ThemeProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
