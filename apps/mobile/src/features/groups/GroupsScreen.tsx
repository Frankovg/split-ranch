import { useState } from 'react';
import { router } from 'expo-router';
import { Check, ChevronRight } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { apiErrorCode } from '@/lib/api';
import { usePreferencesStore } from '@/stores/preferences';
import { useAcceptInvitation, useActiveMembership, useCreateGroup, useMe } from './api';
import { invitationCode } from './invitation';

/**
 * My groups (tap to switch), create a group, or join one with a code. Also the first
 * screen for a user who has no group yet.
 */
export function GroupsScreen({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  const me = useMe();
  const active = useActiveMembership();
  const setActiveGroupId = usePreferencesStore((s) => s.setActiveGroupId);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const create = useCreateGroup();
  const accept = useAcceptInvitation();
  const busy = create.isPending || accept.isPending;
  const groups = me.data?.memberships ?? [];

  // After creating or joining, the new group is the active one: go to its home.
  const done = () => {
    if (!embedded && router.canGoBack()) router.back();
  };

  return (
    <Screen>
      {groups.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>{t('groups.mine')}</CardTitle>
          </CardHeader>
          <CardContent>
            {groups.map((g, i) => {
              const selected = g.group_id === active.data?.group_id;
              return (
                <View key={g.group_id}>
                  {i > 0 ? <Separator /> : null}
                  <Pressable
                    accessibilityRole='button'
                    accessibilityState={{ selected }}
                    onPress={() => {
                      setActiveGroupId(g.group_id);
                      done();
                    }}
                    className='flex-row items-center gap-3 py-3 active:opacity-70'>
                    <View className='flex-1'>
                      <Text className='font-medium'>{g.group_name}</Text>
                      {g.role === 'admin' ? (
                        <Text className='text-sm text-muted-foreground'>{t('group.admin')}</Text>
                      ) : null}
                    </View>
                    <Icon
                      as={selected ? Check : ChevronRight}
                      size={18}
                      className={selected ? 'text-primary' : 'text-muted-foreground'}
                    />
                  </Pressable>
                </View>
              );
            })}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{t('groups.createTitle')}</CardTitle>
          <CardDescription>{t('groups.createBody')}</CardDescription>
        </CardHeader>
        <CardContent className='gap-3'>
          <View className='gap-1.5'>
            <Label nativeID='group-name'>{t('groups.name')}</Label>
            <Input
              aria-labelledby='group-name'
              value={name}
              onChangeText={setName}
              placeholder={t('groups.namePlaceholder')}
              maxLength={80}
            />
          </View>
          <Button
            disabled={busy || name.trim() === ''}
            onPress={() =>
              create.mutate(name.trim(), {
                onSuccess: () => {
                  setName('');
                  done();
                },
                onError: () => toast.error(t('groups.createFailed')),
              })
            }>
            <Text>{t('groups.create')}</Text>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('groups.joinTitle')}</CardTitle>
          <CardDescription>{t('groups.joinBody')}</CardDescription>
        </CardHeader>
        <CardContent className='gap-3'>
          <View className='gap-1.5'>
            <Label nativeID='invite-code'>{t('groups.code')}</Label>
            <Input
              aria-labelledby='invite-code'
              value={code}
              onChangeText={setCode}
              autoCapitalize='characters'
              autoCorrect={false}
              maxLength={80}
            />
          </View>
          <Button
            variant='outline'
            disabled={busy || invitationCode(code) === ''}
            onPress={() =>
              accept.mutate(invitationCode(code), {
                onSuccess: () => {
                  setCode('');
                  done();
                },
                onError: (error) =>
                  toast.error(
                    apiErrorCode(error) === 'already_member' ? t('groups.alreadyMember') : t('groups.joinFailed'),
                  ),
              })
            }>
            <Text>{t('groups.join')}</Text>
          </Button>
        </CardContent>
      </Card>
    </Screen>
  );
}
