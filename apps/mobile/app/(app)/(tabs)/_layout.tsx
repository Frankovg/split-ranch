import { Tabs } from 'expo-router/js-tabs';
import { Calculator, Fence, Settings } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { tokenColor } from '@/theme/tokens';
import { useAppColorScheme } from '@/theme/ThemeSync';

/** Tab bar content height (icon + label) and the gap kept above the system navigation bar. */
const TAB_BAR_CONTENT_HEIGHT = 60;
const TAB_BAR_BOTTOM_GAP = 8;

export default function TabsLayout() {
  const { t } = useTranslation();
  const scheme = useAppColorScheme();
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        // The default bar (49dp + inset, padding = inset) leaves the labels touching the
        // Android navigation buttons; add a gap on top of the system inset.
        tabBarStyle: {
          height: TAB_BAR_CONTENT_HEIGHT + TAB_BAR_BOTTOM_GAP + insets.bottom,
          paddingBottom: TAB_BAR_BOTTOM_GAP + insets.bottom,
        },
        tabBarActiveTintColor: tokenColor(scheme, 'primary'),
        tabBarInactiveTintColor: tokenColor(scheme, 'muted-foreground'),
        // Custom button so the pressed ripple uses a theme token instead of the library default.
        tabBarButton: ({ children, style, onPress, onLongPress, testID, role, ...rest }) => (
          <Pressable
            onPress={onPress}
            onLongPress={onLongPress}
            testID={testID}
            role={role}
            aria-label={rest['aria-label']}
            aria-selected={rest['aria-selected']}
            android_ripple={{ color: tokenColor(scheme, 'accent'), borderless: false }}
            style={style}
          >
            {children}
          </Pressable>
        ),
      }}
    >
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
