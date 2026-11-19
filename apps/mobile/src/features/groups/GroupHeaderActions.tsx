import { useState } from 'react';
import { router } from 'expo-router';
import { ArrowLeftRight, ChartPie, EllipsisVertical, Search, Settings } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { SheetModal } from '@/components/SheetModal';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';

/** Group header, top right: search, insights and a ⋮ menu (settle up, group settings). */
export function GroupHeaderActions({ groupId }: { groupId: string }) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const params = { groupId };
  return (
    <View className='flex-row items-center'>
      <Button
        variant='ghost'
        size='icon'
        accessibilityLabel={t('search.title')}
        onPress={() => router.navigate({ pathname: '/group/[groupId]/search', params })}>
        <Icon as={Search} size={22} />
      </Button>
      <Button
        variant='ghost'
        size='icon'
        accessibilityLabel={t('insights.title')}
        onPress={() => router.navigate({ pathname: '/group/[groupId]/insights', params })}>
        <Icon as={ChartPie} size={22} />
      </Button>
      <Button variant='ghost' size='icon' accessibilityLabel={t('group.menu')} onPress={() => setMenuOpen(true)}>
        <Icon as={EllipsisVertical} size={22} />
      </Button>
      <SheetModal
        variant='menu'
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        title={t('group.menu')}
        options={[
          {
            key: 'settle',
            icon: ArrowLeftRight,
            label: t('settle.open'),
            onPress: () => router.navigate({ pathname: '/group/[groupId]/settle', params }),
          },
          {
            key: 'settings',
            icon: Settings,
            label: t('group.settings'),
            onPress: () => router.navigate({ pathname: '/group/[groupId]/settings', params }),
          },
        ]}
      />
    </View>
  );
}
