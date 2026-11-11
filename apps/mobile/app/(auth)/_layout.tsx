import { Stack } from 'expo-router';
import { useTranslation } from 'react-i18next';

export const unstable_settings = { initialRouteName: 'sign-in' };

/** Signed-out area: sign-in plus the Quick splits list (no account needed). */
export default function AuthLayout() {
  const { t } = useTranslation();
  return (
    <Stack>
      <Stack.Screen name='sign-in' options={{ headerShown: false }} />
      <Stack.Screen name='quick-splits' options={{ title: t('quick.title') }} />
    </Stack>
  );
}
