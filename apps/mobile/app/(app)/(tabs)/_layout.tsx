import { Tabs } from 'expo-router/js-tabs';
import { Calculator, House, ReceiptText, Settings } from 'lucide-react-native';
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
      <Tabs.Screen
        name="index"
        options={{ title: t('tabs.home'), tabBarIcon: ({ color, size }) => <House color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="expenses"
        options={{
          title: t('tabs.expenses'),
          tabBarIcon: ({ color, size }) => <ReceiptText color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="quick/index"
        options={{
          title: t('tabs.quick'),
          tabBarIcon: ({ color, size }) => <Calculator color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: t('tabs.settings'),
          tabBarIcon: ({ color, size }) => <Settings color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
