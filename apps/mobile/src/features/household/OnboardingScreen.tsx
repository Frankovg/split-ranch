import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { useAcceptInvitation, useCreateHousehold } from './api';

/** Accepts a bare code or a full invitation link and returns the code (last path segment). */
export function invitationCode(input: string): string {
  const trimmed = input.trim().replace(/\/+$/, '');
  return trimmed.split('/').pop() ?? '';
}

/** Shown when the user has no household yet: create one or join with an invitation. */
export function OnboardingScreen() {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const create = useCreateHousehold();
  const accept = useAcceptInvitation();
  const busy = create.isPending || accept.isPending;

  return (
    <Screen>
      <Card>
        <CardHeader>
          <CardTitle>{t('onboarding.title')}</CardTitle>
          <CardDescription>{t('onboarding.body')}</CardDescription>
        </CardHeader>
        <CardContent className='gap-3'>
          <View className='gap-1.5'>
            <Label nativeID='household-name'>{t('onboarding.name')}</Label>
            <Input
              aria-labelledby='household-name'
              value={name}
              onChangeText={setName}
              placeholder={t('onboarding.namePlaceholder')}
              maxLength={80}
            />
          </View>
          <Button
            disabled={busy || name.trim() === ''}
            onPress={() =>
              create.mutate(name.trim(), { onError: () => toast.error(t('onboarding.createFailed')) })
            }>
            <Text>{t('onboarding.create')}</Text>
          </Button>
        </CardContent>
      </Card>

      <Text className='text-center text-muted-foreground'>{t('onboarding.or')}</Text>

      <Card>
        <CardHeader>
          <CardTitle>{t('onboarding.joinTitle')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-3'>
          <View className='gap-1.5'>
            <Label nativeID='invite-code'>{t('onboarding.code')}</Label>
            <Input
              aria-labelledby='invite-code'
              value={code}
              onChangeText={setCode}
              autoCapitalize='none'
              autoCorrect={false}
            />
          </View>
          <Button
            variant='outline'
            disabled={busy || invitationCode(code) === ''}
            onPress={() =>
              accept.mutate(invitationCode(code), {
                onError: () => toast.error(t('onboarding.joinFailed')),
              })
            }>
            <Text>{t('onboarding.join')}</Text>
          </Button>
        </CardContent>
      </Card>
    </Screen>
  );
}
