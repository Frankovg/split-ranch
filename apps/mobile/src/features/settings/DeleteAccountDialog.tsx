import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { signOut } from '@/features/auth/google';
import { api, apiErrorCode, ApiError, unwrap } from '@/lib/api';

/** Groups the API lists in `409 account_has_open_balances`. */
function unsettledGroups(error: unknown): string[] {
  if (apiErrorCode(error) !== 'account_has_open_balances' || !(error instanceof ApiError)) return [];
  const groups = (error.body as { groups?: { group_name?: unknown }[] }).groups ?? [];
  return groups.map((g) => (typeof g.group_name === 'string' ? g.group_name : '')).filter(Boolean);
}

/**
 * Confirms account deletion by typing a word. The API refuses while any group has an open
 * balance; on success this device signs out (the server already dropped its push token).
 */
export function DeleteAccountDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const word = t('settings.deleteWord');
  const [typed, setTyped] = useState('');
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE('/v1/me', { body: { confirm: 'DELETE' } })),
    onSuccess: async () => {
      toast.success(t('settings.deleted'));
      await signOut('local');
    },
    onError: (error) => {
      if (unsettledGroups(error).length === 0) toast.error(t('settings.deleteFailed'));
    },
  });
  const blocking = unsettledGroups(remove.error);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settings.deleteTitle')}</DialogTitle>
          <DialogDescription>{t('settings.deleteBody')}</DialogDescription>
        </DialogHeader>
        {blocking.length > 0 ? (
          <View className='gap-1 rounded-lg border border-warning p-3'>
            <Text className='font-medium'>{t('settings.deleteSettleFirst')}</Text>
            {blocking.map((name) => (
              <Text key={name} className='text-muted-foreground'>
                • {name}
              </Text>
            ))}
          </View>
        ) : null}
        <View className='gap-2'>
          <Label nativeID='delete-account-word'>{t('settings.deleteConfirmLabel', { word })}</Label>
          <Input
            aria-labelledby='delete-account-word'
            autoCapitalize='characters'
            autoCorrect={false}
            value={typed}
            onChangeText={setTyped}
          />
        </View>
        <DialogFooter>
          <Button variant='outline' onPress={onClose}>
            <Text>{t('common.cancel')}</Text>
          </Button>
          <Button
            variant='destructive'
            disabled={remove.isPending || typed.trim().toUpperCase() !== word}
            onPress={() => remove.mutate()}>
            <Text>{t('settings.deleteConfirm')}</Text>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
