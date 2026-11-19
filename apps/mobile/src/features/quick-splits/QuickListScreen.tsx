import { useMemo } from 'react';
import { router } from 'expo-router';
import { Calculator, ChevronRight, Plus } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, View } from 'react-native';
import { EmptyState } from '@/components/EmptyState';
import { MoneyText } from '@/components/MoneyText';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { sortEvents, useQuickSplitsStore } from '@/stores/quick-splits';
import { computeQuickResult } from './compute';
import type { QuickEvent } from './types';

function EventRow({ event }: { event: QuickEvent }) {
  const { t } = useTranslation();
  const result = useMemo(() => computeQuickResult(event), [event]);
  return (
    <Pressable
      onPress={() => router.navigate({ pathname: '/quick/[id]', params: { id: event.id } })}
      role='button'
      className='min-h-14 flex-row items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 active:bg-accent'>
      <View className='flex-1 gap-0.5'>
        <Text className='font-semibold'>{event.title.trim() || t('quick.defaultTitle')}</Text>
        <Text className='text-sm text-muted-foreground'>
          {event.participants.map((p) => p.name).join(', ')}
        </Text>
      </View>
      {result.status === 'ok' ? <MoneyText cents={result.totalCents} /> : null}
      <Icon as={ChevronRight} size={20} className='text-muted-foreground' />
    </Pressable>
  );
}

/** List of local Quick splits; shared by the signed-in tab and the signed-out route. */
export function QuickListScreen() {
  const { t } = useTranslation();
  const eventsById = useQuickSplitsStore((s) => s.events);
  const createEvent = useQuickSplitsStore((s) => s.createEvent);
  const events = useMemo(() => sortEvents(eventsById), [eventsById]);

  const onNew = () => {
    const id = createEvent(t('quick.defaultTitle'));
    router.navigate({ pathname: '/quick/[id]', params: { id } });
  };

  if (events.length === 0) {
    return (
      <Screen>
        <EmptyState
          icon={Calculator}
          title={t('quick.emptyTitle')}
          body={t('quick.emptyBody')}
          action={{ label: t('quick.new'), onPress: onNew }}
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <Button onPress={onNew}>
        <Icon as={Plus} size={18} />
        <Text>{t('quick.new')}</Text>
      </Button>
      <View className='gap-2'>
        {events.map((e) => (
          <EventRow key={e.id} event={e} />
        ))}
      </View>
      <Text className='text-center text-sm text-muted-foreground'>{t('quick.offlineNote')}</Text>
    </Screen>
  );
}
