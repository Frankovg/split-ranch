import { useState } from 'react';
import {
  ChevronDown,
  Database,
  Globe,
  Mail,
  ShieldCheck,
  Smartphone,
  Target,
  UserCheck,
  type LucideIcon,
} from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Linking, Pressable, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { cn } from '@/lib/utils';

/** Where every privacy request (access, copy, deletion...) goes. */
export const CONTACT_EMAIL = 'contact@franamoroso.com';

const SUMMARY = [
  { id: 'data', icon: Database },
  { id: 'local', icon: Smartphone },
  { id: 'purpose', icon: Target },
  { id: 'where', icon: Globe },
  { id: 'rights', icon: UserCheck },
] as const satisfies readonly { id: string; icon: LucideIcon }[];

const SECTIONS = [
  'controller',
  'processing',
  'sharing',
  'retention',
  'deletion',
  'yourRights',
  'minors',
] as const;

/**
 * Privacy policy (GDPR art. 13 + Spanish LOPDGDD): a one-glance summary, then the legal
 * detail folded by section. Reachable signed in and signed out.
 * TODO: publish this same text at a public URL (and a web page to request account
 * deletion without the app) before the Google Play release; the store listing needs both.
 */
export function PrivacyScreen() {
  const { t } = useTranslation();
  const email = CONTACT_EMAIL;

  const writeToUs = () =>
    Linking.openURL(`mailto:${email}`).catch(() => toast(t('privacy.contactFailed', { email })));

  return (
    <Screen>
      <View className='items-center gap-2 pt-2'>
        <View className='mb-1 size-16 items-center justify-center rounded-full bg-primary/15'>
          <Icon as={ShieldCheck} size={32} className='text-primary' />
        </View>
        <Text role='heading' className='text-center text-2xl font-extrabold'>
          {t('privacy.heroTitle')}
        </Text>
        <Text className='text-center text-muted-foreground'>{t('privacy.heroBody')}</Text>
        <Text className='text-xs text-muted-foreground'>{t('privacy.updated')}</Text>
      </View>

      <Card>
        <CardHeader>
          <CardTitle>{t('privacy.summary')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-4'>
          {SUMMARY.map(({ id, icon }) => (
            <View key={id} className='flex-row items-start gap-3'>
              <View className='size-10 items-center justify-center rounded-xl bg-primary/10'>
                <Icon as={icon} size={20} className='text-primary' />
              </View>
              <View className='flex-1 gap-0.5'>
                <Text className='font-semibold'>{t(`privacy.${id}Title`)}</Text>
                <Text className='text-sm text-muted-foreground'>{t(`privacy.${id}Body`)}</Text>
              </View>
            </View>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('privacy.detail')}</CardTitle>
        </CardHeader>
        <CardContent>
          {SECTIONS.map((id, index) => (
            <View key={id}>
              {index > 0 ? <Separator /> : null}
              <Section title={t(`privacy.${id}Title`)} body={t(`privacy.${id}Body`, { email })} />
            </View>
          ))}
        </CardContent>
      </Card>

      <Button variant='outline' onPress={() => void writeToUs()}>
        <Icon as={Mail} size={18} />
        <Text>{t('privacy.contact', { email })}</Text>
      </Button>
    </Screen>
  );
}

/** One folded section of the legal detail; tap the title to open it. */
function Section({ title, body }: { title: string; body: string }) {
  const [open, setOpen] = useState(false);
  return (
    <View>
      <Pressable
        role='button'
        aria-expanded={open}
        onPress={() => setOpen((v) => !v)}
        className='flex-row items-center gap-3 py-3.5 active:opacity-70'>
        <Text className='flex-1 font-medium'>{title}</Text>
        <Icon as={ChevronDown} size={18} className={cn('text-muted-foreground', open && 'rotate-180')} />
      </Pressable>
      {open ? <Text className='pb-4 text-sm leading-6 text-muted-foreground'>{body}</Text> : null}
    </View>
  );
}
