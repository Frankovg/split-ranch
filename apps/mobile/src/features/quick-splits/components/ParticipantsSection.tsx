import { Plus, Trash2 } from 'lucide-react-native';
import * as React from 'react';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Text } from '@/components/ui/text';
import { useQuickSplitsStore } from '@/stores/quick-splits';
import { canRemoveParticipant, isDuplicateName, normaliseName } from '../model';
import type { QuickEvent, QuickParticipant } from '../types';

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0] ?? '')
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

function ParticipantDialog({
  event,
  participant,
  onClose,
}: {
  event: QuickEvent;
  participant: QuickParticipant;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const update = useQuickSplitsStore((s) => s.updateParticipant);
  const remove = useQuickSplitsStore((s) => s.removeParticipant);
  const setMe = useQuickSplitsStore((s) => s.setMe);
  const [name, setName] = React.useState(participant.name);
  const [isMe, setIsMe] = React.useState(event.meId === participant.id);
  const duplicate = isDuplicateName(event, name, participant.id);
  const valid = normaliseName(name) !== '' && !duplicate;

  const onSave = () => {
    if (!valid) return;
    update(event.id, participant.id, { name });
    if (isMe !== (event.meId === participant.id)) setMe(event.id, isMe ? participant.id : null);
    onClose();
  };

  const onRemove = () => {
    if (!canRemoveParticipant(event, participant.id)) {
      toast.error(t('quick.cantRemovePayer', { name: participant.name }));
      return;
    }
    remove(event.id, participant.id);
    onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('quick.editParticipant', { name: participant.name })}</DialogTitle>
        </DialogHeader>
        <View className="gap-1.5">
          <Label nativeID="participant-name">{t('quick.participantName')}</Label>
          <Input value={name} onChangeText={setName} aria-labelledby="participant-name" aria-invalid={duplicate} />
          {duplicate ? <Text className="text-sm text-destructive">{t('quick.duplicateName')}</Text> : null}
        </View>
        <View className="min-h-12 flex-row items-center gap-3">
          <Switch checked={isMe} onCheckedChange={setIsMe} accessibilityLabel={t('quick.thisIsMe')} />
          <Text className="flex-1" onPress={() => setIsMe((v) => !v)}>
            {t('quick.thisIsMe')}
          </Text>
        </View>
        <DialogFooter className="flex-row flex-wrap justify-between gap-2">
          <Button variant="ghost" onPress={onRemove}>
            <Icon as={Trash2} size={18} className="text-destructive" />
            <Text className="text-destructive">{t('quick.removeParticipant', { name: participant.name })}</Text>
          </Button>
          <Button onPress={onSave} disabled={!valid}>
            <Text>{t('common.save')}</Text>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ParticipantsSection({ event }: { event: QuickEvent }) {
  const { t } = useTranslation();
  const addParticipant = useQuickSplitsStore((s) => s.addParticipant);
  const [name, setName] = React.useState('');
  const [editing, setEditing] = React.useState<QuickParticipant | null>(null);
  const duplicate = name.trim() !== '' && isDuplicateName(event, name);

  const onAdd = () => {
    if (normaliseName(name) === '' || duplicate) return;
    if (addParticipant(event.id, name)) setName('');
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('quick.participants')}</CardTitle>
      </CardHeader>
      <CardContent className="gap-3">
        <View className="flex-row flex-wrap gap-2">
          {event.participants.map((p) => (
            <Button
              key={p.id}
              variant="outline"
              size="sm"
              className="rounded-full pl-1"
              onPress={() => setEditing(p)}
              accessibilityLabel={t('quick.editParticipant', { name: p.name })}>
              <Avatar alt={p.name} className="size-8">
                <AvatarFallback>
                  <Text className="text-xs">{initials(p.name)}</Text>
                </AvatarFallback>
              </Avatar>
              <Text>{p.id === event.meId ? t('quick.nameYou', { name: p.name }) : p.name}</Text>
            </Button>
          ))}
        </View>
        <View className="flex-row items-start gap-2">
          <View className="flex-1 gap-1">
            <Input
              value={name}
              onChangeText={setName}
              placeholder={t('quick.participantPlaceholder')}
              accessibilityLabel={t('quick.participantName')}
              onSubmitEditing={onAdd}
              submitBehavior="submit"
              returnKeyType="done"
              aria-invalid={duplicate}
            />
            {duplicate ? <Text className="text-sm text-destructive">{t('quick.duplicateName')}</Text> : null}
          </View>
          <Button
            size="icon"
            onPress={onAdd}
            disabled={normaliseName(name) === '' || duplicate}
            accessibilityLabel={t('quick.addParticipant')}>
            <Icon as={Plus} size={22} />
          </Button>
        </View>
      </CardContent>
      {editing ? <ParticipantDialog event={event} participant={editing} onClose={() => setEditing(null)} /> : null}
    </Card>
  );
}
