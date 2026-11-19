import { useState } from 'react';
import { router } from 'expo-router';
import { ChevronRight, Fence, KeyRound, Plus } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { FlatList, Pressable, RefreshControl, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EmptyState } from '@/components/EmptyState';
import { Fab, FAB_CLEARANCE } from '@/components/Fab';
import { Logo } from '@/components/Logo';
import { ScreenBackground } from '@/components/ScreenBackground';
import { SheetModal } from '@/components/SheetModal';
import { Card } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { useRefreshByUser } from '@/lib/query/refresh';
import { useGroups } from './api';
import { activeMembers, ErrorScreen, LoadingScreen } from './components';
import type { Group } from './types';

/** Home ("Ranchs"): one card per group; the "+" creates a group or joins one with a code. */
export function GroupsScreen() {
  const { t } = useTranslation();
  const groups = useGroups();
  const [sheetOpen, setSheetOpen] = useState(false);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(groups.refetch);

  if (groups.isPending) return <LoadingScreen />;
  if (groups.isError) return <ErrorScreen t={t} onRetry={() => void groups.refetch()} />;

  return (
    <SafeAreaView edges={['top', 'bottom']} className='flex-1 bg-background'>
      <ScreenBackground />
      {/* No navigation header on this tab: the wordmark is the top bar. */}
      <View className='items-center px-4 pt-4 pb-4' accessibilityRole='header'>
        <Logo height={26} />
      </View>
      <FlatList
        data={groups.data}
        keyExtractor={(g) => g.id}
        contentContainerClassName='gap-3 px-4 pt-4'
        contentContainerStyle={{ paddingBottom: FAB_CLEARANCE }}
        refreshControl={
          <RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />
        }
        ListEmptyComponent={
          <EmptyState icon={Fence} title={t('groups.empty')} body={t('groups.emptyBody')} />
        }
        renderItem={({ item }) => <GroupCard group={item} />}
      />
      <Fab label={t('groups.fab')} onPress={() => setSheetOpen(true)} />
      <SheetModal
        variant='sheet'
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title={t('groups.fab')}
        options={[
          {
            key: 'create',
            icon: Plus,
            label: t('groups.createTitle'),
            description: t('groups.createBody'),
            onPress: () => router.navigate('/groups/new'),
          },
          {
            key: 'join',
            icon: KeyRound,
            label: t('groups.joinTitle'),
            description: t('groups.joinBody'),
            onPress: () => router.navigate('/groups/join'),
          },
        ]}
      />
    </SafeAreaView>
  );
}

function GroupCard({ group }: { group: Group }) {
  const { t } = useTranslation();
  const meta = [
    t('groups.memberCount', { count: activeMembers(group).length }),
    group.my_role === 'admin' ? t('group.admin') : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Pressable
      accessibilityRole='button'
      onPress={() => router.navigate({ pathname: '/group/[groupId]', params: { groupId: group.id } })}
      className='active:opacity-80'
    >
      <Card className='flex-row items-center gap-3 px-4 py-4'>
        <View className='h-12 w-12 items-center justify-center rounded-full bg-accent'>
          <Text className='text-lg font-semibold text-primary'>
            {group.name.trim().charAt(0).toUpperCase()}
          </Text>
        </View>
        <View className='flex-1 gap-0.5'>
          <Text className='text-lg font-semibold' numberOfLines={1}>
            {group.name}
          </Text>
          <Text className='text-sm text-muted-foreground'>{meta}</Text>
        </View>
        <Icon as={ChevronRight} size={20} className='text-muted-foreground' />
      </Card>
    </Pressable>
  );
}
