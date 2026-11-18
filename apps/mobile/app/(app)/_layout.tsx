import { Stack } from 'expo-router';
import { useTranslation } from 'react-i18next';

export const unstable_settings = { initialRouteName: '(tabs)' };

/**
 * Signed-in area. The guard lives in the root layout (Stack.Protected guard={signedIn}).
 * Group screens sit on this stack, above the tabs, so the tab bar is hidden inside a
 * group and back always returns to the group list.
 */
export default function AppLayout() {
  const { t } = useTranslation();
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name='(tabs)' />
      <Stack.Screen name='groups/new' options={{ headerShown: true, title: t('groups.createTitle') }} />
      <Stack.Screen name='groups/join' options={{ headerShown: true, title: t('groups.joinTitle') }} />
      {/* The group home sets its own title (the group's name) and header actions. */}
      <Stack.Screen name='group/[groupId]' options={{ headerShown: true, title: '' }} />
      <Stack.Screen name='group/[groupId]/search' options={{ headerShown: true, title: t('search.title') }} />
      <Stack.Screen name='group/[groupId]/insights' options={{ headerShown: true, title: t('insights.title') }} />
      <Stack.Screen name='group/[groupId]/settle' options={{ headerShown: true, title: t('settle.title') }} />
      <Stack.Screen name='group/[groupId]/settings' options={{ headerShown: true, title: t('group.settings') }} />
      <Stack.Screen
        name='group/[groupId]/expense/new'
        options={{ headerShown: true, title: t('expenses.add'), presentation: 'modal' }}
      />
      <Stack.Screen name='group/[groupId]/expense/[id]' options={{ headerShown: true, title: t('expenses.edit') }} />
      <Stack.Screen
        name='group/[groupId]/category/new'
        options={{ headerShown: true, title: t('categories.newTitle'), presentation: 'modal' }}
      />
    </Stack>
  );
}
