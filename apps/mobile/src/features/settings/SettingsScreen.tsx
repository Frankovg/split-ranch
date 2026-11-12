import Constants from 'expo-constants';
import { router } from 'expo-router';
import { LogOut, Palette } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { signOut } from '@/features/auth/google';
import {
  usePreferencesStore,
  type LanguagePreference,
  type ThemePreference,
} from '@/stores/preferences';
import { useSessionStore } from '@/stores/session';

const THEMES: ThemePreference[] = ['system', 'light', 'dark'];
const LANGUAGES: LanguagePreference[] = ['system', 'es', 'en'];

export function SettingsScreen() {
  const { t } = useTranslation();
  const { theme, language, setTheme, setLanguage } = usePreferencesStore(
    useShallow((s) => ({
      theme: s.theme,
      language: s.language,
      setTheme: s.setTheme,
      setLanguage: s.setLanguage,
    })),
  );
  // Only the email: the session object changes on every token refresh.
  const email = useSessionStore((s) => s.session?.user.email);

  const themeLabel: Record<ThemePreference, string> = {
    system: t('settings.themeSystem'),
    light: t('settings.themeLight'),
    dark: t('settings.themeDark'),
  };
  const languageLabel: Record<LanguagePreference, string> = {
    system: t('settings.languageSystem'),
    es: t('settings.languageEs'),
    en: t('settings.languageEn'),
  };

  return (
    <Screen>
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.appearance')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-4'>
          <View className='gap-2'>
            <Label>{t('settings.theme')}</Label>
            <ToggleGroup
              type='single'
              variant='outline'
              value={theme}
              onValueChange={(v) => v && setTheme(v as ThemePreference)}>
              {THEMES.map((v) => (
                <ToggleGroupItem key={v} value={v} isFirst={v === 'system'} isLast={v === 'dark'} className='flex-1'>
                  <Text>{themeLabel[v]}</Text>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </View>
          <View className='gap-2'>
            <Label>{t('settings.language')}</Label>
            <ToggleGroup
              type='single'
              variant='outline'
              value={language}
              onValueChange={(v) => v && setLanguage(v as LanguagePreference)}>
              {LANGUAGES.map((v) => (
                <ToggleGroupItem key={v} value={v} isFirst={v === 'system'} isLast={v === 'en'} className='flex-1'>
                  <Text>{languageLabel[v]}</Text>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </View>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.account')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-3'>
          {email ? <Text className='text-muted-foreground'>{t('auth.signedInAs', { email })}</Text> : null}
          <Button variant='outline' onPress={() => void signOut()}>
            <Icon as={LogOut} size={18} />
            <Text>{t('auth.signOut')}</Text>
          </Button>
        </CardContent>
      </Card>

      {__DEV__ ? (
        <Card>
          <CardHeader>
            <CardTitle>{t('settings.developer')}</CardTitle>
          </CardHeader>
          <CardContent>
            <Button variant='secondary' onPress={() => router.push('/dev/gallery')}>
              <Icon as={Palette} size={18} />
              <Text>{t('settings.gallery')}</Text>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Text className='text-center text-sm text-muted-foreground'>
        {t('settings.version', { version: Constants.expoConfig?.version ?? '?' })}
      </Text>
    </Screen>
  );
}
