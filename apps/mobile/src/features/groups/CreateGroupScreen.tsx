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
import { useCreateGroup } from './api';

/** New group: a name, then straight into the group (the form leaves the back stack). */
export function CreateGroupScreen() {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const create = useCreateGroup();
  const submit = () =>
    create.mutate(name.trim(), {
      onSuccess: (group) => router.replace({ pathname: '/group/[groupId]', params: { groupId: group.id } }),
      onError: () => toast.error(t('groups.createFailed')),
    });

  return (
    <Screen>
      <Text className='text-muted-foreground'>{t('groups.createBody')}</Text>
      <View className='gap-1.5'>
        <Label nativeID='group-name'>{t('groups.name')}</Label>
        <Input
          aria-labelledby='group-name'
          value={name}
          onChangeText={setName}
          placeholder={t('groups.namePlaceholder')}
          maxLength={80}
          autoFocus
          returnKeyType='done'
          onSubmitEditing={() => name.trim() !== '' && !create.isPending && submit()}
        />
      </View>
      <Button size='lg' disabled={create.isPending || name.trim() === ''} onPress={submit}>
        <Text>{t('groups.create')}</Text>
      </Button>
    </Screen>
  );
}
