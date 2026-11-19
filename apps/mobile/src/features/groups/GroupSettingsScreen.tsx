import { useState } from 'react';
import { router } from 'expo-router';
import { ChevronRight, Percent, Share2, UserMinus, Wand2 } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Alert, Share, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { apiErrorCode } from '@/lib/api';
import {
  useCreateInvitation,
  useDeleteGroup,
  useGroup,
  useLeaveGroup,
  useRemoveMember,
  useRenameGroup,
  useSplitRules,
} from './api';
import { activeMembers, ErrorScreen, LoadingScreen, memberName } from './components';
import { useGroupId } from './route';
import type { Group, SplitRule } from './types';

/** Name, members and invite code (any member); remove members and delete (admin only). */
export function GroupSettingsScreen() {
  const { t } = useTranslation();
  const group = useGroup(useGroupId());
  if (group.isPending) return <LoadingScreen />;
  if (group.isError) return <ErrorScreen t={t} onRetry={() => void group.refetch()} />;
  return <Settings group={group.data} />;
}

function Settings({ group }: { group: Group }) {
  const { t } = useTranslation();
  const isAdmin = group.my_role === 'admin';
  const [name, setName] = useState(group.name);
  const [confirmName, setConfirmName] = useState('');
  const rename = useRenameGroup(group.id);
  const invite = useCreateInvitation(group.id);
  const leave = useLeaveGroup(group.id);
  const removeMember = useRemoveMember(group.id);
  const deleteGroup = useDeleteGroup(group.id);
  const rules = useSplitRules(group.id);

  const balanceError = (error: unknown) =>
    toast.error(
      apiErrorCode(error) === 'member_has_open_balance' || apiErrorCode(error) === 'group_has_open_balances'
        ? t('group.settleFirst')
        : t('common.error'),
    );

  const onInvite = () =>
    invite.mutate(undefined, {
      onSuccess: async (inv) => {
        try {
          await Share.share({ message: t('group.inviteMessage', { name: group.name, code: inv.code }) });
        } catch (error) {
          console.warn('Share failed', error);
        }
      },
      onError: () => toast.error(t('group.inviteFailed')),
    });

  const onLeave = () =>
    Alert.alert(t('group.leaveTitle', { name: group.name }), t('group.leaveBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('group.leave'),
        style: 'destructive',
        // The group screens behind this one are gone for this user: back to the group list.
        onPress: () => leave.mutate(undefined, { onSuccess: () => router.dismissTo('/'), onError: balanceError }),
      },
    ]);

  const onRemove = (memberId: string) =>
    Alert.alert(t('group.removeTitle', { name: memberName(group, memberId, t) }), t('group.removeBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('group.remove'),
        style: 'destructive',
        onPress: () => removeMember.mutate(memberId, { onError: balanceError }),
      },
    ]);

  return (
    <Screen>
      <Card>
        <CardHeader>
          <CardTitle>{t('group.name')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-3'>
          <Input aria-label={t('group.name')} value={name} onChangeText={setName} maxLength={80} />
          <Button
            variant='outline'
            disabled={rename.isPending || name.trim() === '' || name.trim() === group.name}
            onPress={() =>
              rename.mutate(name.trim(), {
                onError: () => toast.error(t('common.error')),
              })
            }>
            <Text>{t('common.save')}</Text>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className='flex-row items-center justify-between'>
          <CardTitle>{t('home.members')}</CardTitle>
          <Button variant='ghost' size='sm' disabled={invite.isPending} onPress={onInvite}>
            <Icon as={Share2} size={18} />
            <Text>{t('group.invite')}</Text>
          </Button>
        </CardHeader>
        <CardContent>
          {activeMembers(group).map((m) => (
            <View key={m.id} className='flex-row items-center justify-between py-1'>
              <View>
                <Text>{memberName(group, m.id, t)}</Text>
                {m.role === 'admin' ? (
                  <Text className='text-sm text-muted-foreground'>{t('group.admin')}</Text>
                ) : null}
              </View>
              {isAdmin && m.id !== group.my_member_id ? (
                <Button
                  variant='ghost'
                  size='icon'
                  accessibilityLabel={t('group.removeTitle', { name: memberName(group, m.id, t) })}
                  onPress={() => onRemove(m.id)}>
                  <Icon as={UserMinus} size={18} />
                </Button>
              ) : null}
            </View>
          ))}
          <Text className='pt-2 text-sm text-muted-foreground'>{t('group.inviteHint')}</Text>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('rule.title')}</CardTitle>
          <CardDescription>
            {rules.data ? <RuleSummary group={group} rule={rules.data.default} /> : t('rule.settingsHint')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant='outline'
            onPress={() => router.navigate({ pathname: '/group/[groupId]/split-rule', params: { groupId: group.id } })}>
            <Icon as={Percent} size={18} />
            <Text>{t('rule.edit')}</Text>
            <Icon as={ChevronRight} size={18} className='ml-auto' />
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('group.presets')}</CardTitle>
          <CardDescription>{t('group.presetsHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant='outline'
            onPress={() => router.navigate({ pathname: '/group/[groupId]/category-presets', params: { groupId: group.id } })}>
            <Icon as={Wand2} size={18} />
            <Text>{t('group.presets')}</Text>
            <Icon as={ChevronRight} size={18} className='ml-auto' />
          </Button>
        </CardContent>
      </Card>

      <Button variant='outline' disabled={leave.isPending} onPress={onLeave}>
        <Text>{t('group.leave')}</Text>
      </Button>

      {isAdmin ? (
        <Card>
          <CardHeader>
            <CardTitle>{t('group.deleteTitle')}</CardTitle>
            <CardDescription>{t('group.deleteBody', { name: group.name })}</CardDescription>
          </CardHeader>
          <CardContent className='gap-3'>
            <Label nativeID='confirm-name'>{t('group.deleteConfirm')}</Label>
            <Input aria-labelledby='confirm-name' value={confirmName} onChangeText={setConfirmName} />
            <Button
              variant='destructive'
              disabled={deleteGroup.isPending || confirmName.trim() !== group.name}
              onPress={() =>
                deleteGroup.mutate(confirmName.trim(), {
                  onSuccess: () => router.dismissTo('/'),
                  onError: balanceError,
                })
              }>
              <Text>{t('group.delete')}</Text>
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </Screen>
  );
}

/** "Equal parts" or "Custom: You 60 %, Ana 40 %" (members who left are not listed). */
function RuleSummary({ group, rule }: { group: Group; rule: SplitRule }) {
  const { t } = useTranslation();
  if (rule.split_type !== 'percentages') return t('rule.summaryEqual');
  const format = new Intl.NumberFormat(currentMoneyLocale(), { maximumFractionDigits: 2 });
  const active = new Set(activeMembers(group).map((m) => m.id));
  const parts = rule.shares
    .filter((s) => active.has(s.member_id))
    .map((s) => `${memberName(group, s.member_id, t)} ${format.format(s.basis_points / 100)} %`);
  return t('rule.summaryCustom', { parts: parts.join(', ') });
}
