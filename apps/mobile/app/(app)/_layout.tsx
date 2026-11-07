import { Stack } from 'expo-router';
import { useTranslation } from 'react-i18next';

export const unstable_settings = { initialRouteName: '(tabs)' };

/** Signed-in area. The guard lives in the root layout (Stack.Protected guard={signedIn}). */
export default function AppLayout() {
  const { t } = useTranslation();
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen
        name="expense/new"
        options={{ headerShown: true, title: t('expenses.add'), presentation: 'modal' }}
      />
      <Stack.Screen name="period/[month]" options={{ headerShown: true, title: '' }} />
    </Stack>
  );
}
