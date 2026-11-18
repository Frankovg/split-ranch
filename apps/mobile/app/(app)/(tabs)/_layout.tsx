import { Tabs } from 'expo-router/js-tabs';
import { Calculator, Fence, Settings } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { tokenColor } from '@/theme/tokens';
import { useAppColorScheme } from '@/theme/ThemeSync';

export default function TabsLayout() {
  const { t } = useTranslation();
  const scheme = useAppColorScheme();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: tokenColor(scheme, 'primary'),
        tabBarInactiveTintColor: tokenColor(scheme, 'muted-foreground'),
      }}>
      {/* Home: the user's groups ("ranchs"). Room for an AI chat tab later. */}
      <Tabs.Screen
        name='index'
        options={{
          title: t('tabs.ranchs'),
          // The screen draws its own top bar with the wordmark.
          headerShown: false,
          tabBarIcon: ({ color, size }) => <Fence color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name='quick/index'
        options={{
          title: t('tabs.quick'),
          tabBarIcon: ({ color, size }) => <Calculator color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name='settings'
        options={{
          title: t('tabs.settings'),
          tabBarIcon: ({ color, size }) => <Settings color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
