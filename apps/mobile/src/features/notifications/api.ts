import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMe } from '@/features/groups/api';
import type { Me } from '@/features/groups/types';
import { api, unwrap } from '@/lib/api';
import { queryKeys } from '@/lib/query/client';
import { applyPrefs } from './prefs';
import type { NotificationPrefsUpdate } from './types';

/** The signed-in user's notification switches (part of `/v1/me`). */
export function useNotificationPrefs() {
  const me = useMe();
  return { ...me, prefs: me.data?.notifications };
}

/** Partial update of the switches, applied optimistically and rolled back on error. */
export function useUpdateNotificationPrefs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: NotificationPrefsUpdate) =>
      unwrap(api.PATCH('/v1/me', { body: { notifications: changes } })),
    onMutate: async (changes) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.me() });
      const previous = queryClient.getQueryData<Me>(queryKeys.me());
      if (previous) {
        queryClient.setQueryData<Me>(queryKeys.me(), {
          ...previous,
          notifications: applyPrefs(previous.notifications, changes),
        });
      }
      return { previous };
    },
    onError: (_error, _changes, context) => {
      if (context?.previous) queryClient.setQueryData(queryKeys.me(), context.previous);
    },
    onSuccess: (me) => queryClient.setQueryData(queryKeys.me(), me),
  });
}
