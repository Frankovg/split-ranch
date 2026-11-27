import { useState } from 'react';
import { router } from 'expo-router';
import { Calculator, LogIn, Palette, ShieldCheck } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { toast } from 'sonner-native';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { ScreenBackground } from '@/components/ScreenBackground';
import { isGoogleSignInAvailable, signInWithGoogle, SignInCancelledError } from './google';

export function SignInScreen() {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const available = isGoogleSignInAvailable();

  const onGoogle = async () => {
    if (!available) {
      toast.error(t('auth.notConfigured'));
      return;
    }
    setBusy(true);
    try {
      await signInWithGoogle();
      // The root Stack.Protected guard switches to the app once the session arrives.
    } catch (error) {
      if (!(error instanceof SignInCancelledError)) {
        console.warn('Google sign-in failed', error);
        toast.error(t('auth.failed'));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView className='flex-1 bg-background'>
      <ScreenBackground />
      <View className='flex-1 justify-center gap-10 px-6'>
        <View className='gap-3'>
          <Text className='text-center text-4xl font-extrabold text-primary' role='heading'>
            {t('common.appName')}
          </Text>
          <Text className='text-center text-lg text-muted-foreground'>{t('auth.tagline')}</Text>
        </View>

        <View className='gap-3'>
          <Button size='lg' onPress={onGoogle} disabled={busy}>
            <Icon as={LogIn} size={20} />
            <Text>{t('auth.google')}</Text>
          </Button>
          {!available ? (
            <Text className='text-center text-sm text-muted-foreground'>{t('auth.notConfigured')}</Text>
          ) : null}
          <Button size='lg' variant='outline' onPress={() => router.navigate('/quick-splits')}>
            <Icon as={Calculator} size={20} />
            <Text>{t('auth.quickSplits')}</Text>
          </Button>
        </View>

        <View className='items-center gap-1'>
          <Button variant='ghost' size='sm' onPress={() => router.navigate('/privacy')}>
            <Icon as={ShieldCheck} size={16} className='text-muted-foreground' />
            <Text className='text-muted-foreground'>{t('auth.privacy')}</Text>
          </Button>
          {__DEV__ ? (
            <Button variant='ghost' onPress={() => router.navigate('/dev/gallery')}>
              <Icon as={Palette} size={18} />
              <Text>{t('settings.gallery')}</Text>
            </Button>
          ) : null}
        </View>
      </View>
    </SafeAreaView>
  );
}
