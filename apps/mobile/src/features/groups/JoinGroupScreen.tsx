import { useState } from 'react';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { apiErrorCode } from '@/lib/api';
import { useAcceptInvitation } from './api';
import { invitationCode } from './invitation';

/** Join with an invitation code, then straight into the group (the form leaves the back stack). */
export function JoinGroupScreen() {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const accept = useAcceptInvitation();
  const normalized = invitationCode(code);
  const submit = () =>
    accept.mutate(normalized, {
      onSuccess: (group) => router.replace({ pathname: '/group/[groupId]', params: { groupId: group.id } }),
      onError: (error) =>
        toast.error(apiErrorCode(error) === 'already_member' ? t('groups.alreadyMember') : t('groups.joinFailed')),
    });

  return (
    <Screen>
      <Text className='text-muted-foreground'>{t('groups.joinBody')}</Text>
      <View className='gap-1.5'>
        <Label nativeID='invite-code'>{t('groups.code')}</Label>
        <Input
          aria-labelledby='invite-code'
          value={code}
          onChangeText={setCode}
          autoCapitalize='characters'
          autoCorrect={false}
          maxLength={80}
          autoFocus
          returnKeyType='done'
          onSubmitEditing={() => normalized !== '' && !accept.isPending && submit()}
        />
      </View>
      <Button size='lg' disabled={accept.isPending || normalized === ''} onPress={submit}>
        <Text>{t('groups.join')}</Text>
      </Button>
    </Screen>
  );
}
