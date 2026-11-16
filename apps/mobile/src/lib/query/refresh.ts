import { focusManager, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus, Platform } from 'react-native';
import { queryKeys } from './client';

/**
 * Pull-to-refresh state driven only by the user's gesture. `isRefetching` from
 * useQuery is also true for background refetches (e.g. after an invalidation),
 * which would show the RefreshControl spinner without a pull.
 * Pattern from the TanStack Query React Native example (useRefreshByUser).
 */
export function useRefreshByUser(...refetchers: (() => Promise<unknown>)[]) {
  const [isRefetchingByUser, setIsRefetchingByUser] = useState(false);
  const refetchByUser = async () => {
    setIsRefetchingByUser(true);
    try {
      await Promise.all(refetchers.map((refetch) => refetch()));
    } finally {
      setIsRefetchingByUser(false);
    }
  };
  return { isRefetchingByUser, refetchByUser };
}

function onAppStateChange(status: AppStateStatus) {
  if (Platform.OS !== 'web') focusManager.setFocused(status === 'active');
}

/** Tells TanStack Query when the app returns to the foreground so stale queries refetch. */
export function useAppStateFocus() {
  useEffect(() => {
    const subscription = AppState.addEventListener('change', onAppStateChange);
    return () => subscription.remove();
  }, []);
}

/**
 * Refetches the group's stale, active queries when the screen regains focus
 * (tabs stay mounted, so switching tabs alone never refetches). Skips the first focus,
 * which coincides with mount.
 */
export function useRefreshOnFocus(groupId: string | undefined) {
  const queryClient = useQueryClient();
  const firstTimeRef = useRef(true);

  useFocusEffect(
    useCallback(() => {
      if (firstTimeRef.current) {
        firstTimeRef.current = false;
        return;
      }
      if (!groupId) return;
      void queryClient.refetchQueries({
        queryKey: queryKeys.group(groupId),
        stale: true,
        type: 'active',
      });
    }, [queryClient, groupId]),
  );
}
