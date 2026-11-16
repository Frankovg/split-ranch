import { Stack } from 'expo-router';
import { useTranslation } from 'react-i18next';

export const unstable_settings = { initialRouteName: '(tabs)' };

/** Signed-in area. The guard lives in the root layout (Stack.Protected guard={signedIn}). */
export default function AppLayout() {
  const { t } = useTranslation();
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name='(tabs)' />
      <Stack.Screen
        name='expense/new'
        options={{ headerShown: true, title: t('expenses.add'), presentation: 'modal' }}
      />
      <Stack.Screen name='expense/[id]' options={{ headerShown: true, title: t('expenses.edit') }} />
      <Stack.Screen name='groups/index' options={{ headerShown: true, title: t('groups.title') }} />
      <Stack.Screen name='group/settings' options={{ headerShown: true, title: t('group.settings') }} />
      <Stack.Screen name='group/settle' options={{ headerShown: true, title: t('settle.title') }} />
    </Stack>
  );
}
