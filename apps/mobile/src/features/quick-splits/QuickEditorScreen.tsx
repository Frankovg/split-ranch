import { useMemo, useState } from 'react';
import { router, Stack } from 'expo-router';
import { SearchX, Trash2 } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { EmptyState } from '@/components/EmptyState';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useQuickSplitsStore } from '@/stores/quick-splits';
import { computeQuickResult } from './compute';
import { ItemisedSection } from './components/ItemisedSection';
import { ParticipantsSection } from './components/ParticipantsSection';
import { ResultCard } from './components/ResultCard';
import { TotalModeSection } from './components/TotalModeSection';
import type { QuickMode } from './types';

export function QuickEditorScreen({ id }: { id: string }) {
  const { t } = useTranslation();
  const event = useQuickSplitsStore((s) => s.events[id]);
  const setTitle = useQuickSplitsStore((s) => s.setTitle);
  const setMode = useQuickSplitsStore((s) => s.setMode);
  const deleteEvent = useQuickSplitsStore((s) => s.deleteEvent);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // Set right before deleting: the screen stays mounted during the exit animation.
  const [deleting, setDeleting] = useState(false);
  const result = useMemo(() => (event ? computeQuickResult(event) : null), [event]);

  if (!event || !result) {
    if (deleting) return null;
    return (
      <Screen>
        <EmptyState
          icon={SearchX}
          title={t('quick.notFound')}
          action={{ label: t('common.back'), onPress: () => router.back() }}
        />
      </Screen>
    );
  }

  const displayTitle = event.title.trim() || t('quick.defaultTitle');

  return (
    <>
      <Stack.Screen
        options={{
          title: displayTitle,
          headerRight: () => (
            <Button
              variant='ghost'
              size='icon'
              onPress={() => setConfirmDelete(true)}
              accessibilityLabel={t('quick.deleteEvent')}>
              <Icon as={Trash2} size={20} />
            </Button>
          ),
        }}
      />
      <Screen>
        <View className='gap-1.5'>
          <Label nativeID='quick-title'>{t('quick.eventTitle')}</Label>
          <Input
            value={event.title}
            onChangeText={(v) => setTitle(event.id, v)}
            placeholder={t('quick.eventTitlePlaceholder')}
            aria-labelledby='quick-title'
          />
        </View>

        <ParticipantsSection event={event} />

        <View className='gap-1.5'>
          <Label nativeID='quick-mode'>{t('quick.mode')}</Label>
          <ToggleGroup
            type='single'
            variant='outline'
            value={event.mode}
            onValueChange={(v) => v && setMode(event.id, v as QuickMode)}
            aria-labelledby='quick-mode'>
            <ToggleGroupItem value='total' isFirst className='flex-1'>
              <Text>{t('quick.modeTotal')}</Text>
            </ToggleGroupItem>
            <ToggleGroupItem value='itemised' isLast className='flex-1'>
              <Text>{t('quick.modeItemised')}</Text>
            </ToggleGroupItem>
          </ToggleGroup>
        </View>

        {event.mode === 'total' ? <TotalModeSection event={event} /> : <ItemisedSection event={event} />}

        <ResultCard event={event} result={result} />
      </Screen>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('quick.deleteConfirmTitle', { title: displayTitle })}</DialogTitle>
            <DialogDescription>{t('quick.deleteConfirmBody')}</DialogDescription>
          </DialogHeader>
          <DialogFooter className='flex-row justify-end gap-2'>
            <Button variant='outline' onPress={() => setConfirmDelete(false)}>
              <Text>{t('common.cancel')}</Text>
            </Button>
            <Button
              variant='destructive'
              onPress={() => {
                setConfirmDelete(false);
                setDeleting(true);
                // Opened from a deep link there is no screen to go back to.
                if (router.canGoBack()) router.back();
                else router.replace('/');
                deleteEvent(event.id);
              }}>
              <Text>{t('common.delete')}</Text>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
