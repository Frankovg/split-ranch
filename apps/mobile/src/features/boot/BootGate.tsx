import { useIsRestoring, useQueryClient } from '@tanstack/react-query';
import { SplashScreen, useRouter } from 'expo-router';
import { useEffect } from 'react';
import { create } from 'zustand';
import { useApiStatusStore, warmUpApi } from '@/lib/api/warm-up';
import { queryKeys } from '@/lib/query/client';
import { useSessionStore } from '@/stores/session';
import { BootScreen } from './BootScreen';
import { MIN_VISIBLE_MS, needsBootScreen } from './stage';

type BootPhase = 'undecided' | 'showing' | 'done';

/** Launch state; module-level so it lasts for the whole app process, not one mount. */
const useBootStore = create<{ phase: BootPhase; shownAt: number }>()(() => ({
  phase: 'undecided',
  shownAt: 0,
}));

/**
 * Owns the launch sequence: keeps the native splash up while the session and the persisted
 * query cache are restored, then decides once whether the animated boot screen is needed
 * (signed in, nothing cached, API still waking on Render) and keeps it over the app until the
 * API answers. Without it, a cold API showed bare skeletons for up to a minute.
 *
 * The decision is taken once per launch: after the boot screen is dismissed (or skipped),
 * later foreground re-pings never bring it back. A signed-out launch defers the decision
 * until sign-in, so a first sign-in against a cold API gets the boot screen too.
 * Render it inside PersistQueryClientProvider, after the navigator so it overlays it.
 */
export function BootGate() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const isRestoring = useIsRestoring();
  const sessionStatus = useSessionStore((s) => s.status);
  const apiStatus = useApiStatusStore((s) => s.status);
  const phase = useBootStore((s) => s.phase);
  const shownAt = useBootStore((s) => s.shownAt);

  const ready = sessionStatus !== 'loading' && !isRestoring;
  const signedIn = sessionStatus === 'signedIn';

  // Decide once the session and the cache are known.
  useEffect(() => {
    if (!ready || !signedIn || phase !== 'undecided') return;
    const hasCachedData = queryClient.getQueryData(queryKeys.groups()) !== undefined;
    useBootStore.setState(
      needsBootScreen(apiStatus, hasCachedData) ? { phase: 'showing', shownAt: Date.now() } : { phase: 'done' },
    );
  }, [apiStatus, phase, queryClient, ready, signedIn]);

  // Hide the native splash in the same commit the boot screen (or the app) is rendered.
  const decided = ready && (!signedIn || phase !== 'undecided');
  useEffect(() => {
    if (decided) SplashScreen.hide();
  }, [decided]);

  // Leave once the API answers, but not before the screen had a moment on screen.
  useEffect(() => {
    if (phase !== 'showing' || apiStatus !== 'awake') return;
    const wait = Math.max(0, shownAt + MIN_VISIBLE_MS - Date.now());
    const timer = setTimeout(() => useBootStore.setState({ phase: 'done' }), wait);
    return () => clearTimeout(timer);
  }, [apiStatus, phase, shownAt]);

  // Signed out while it is up (e.g. an expired session): never cover the sign-in screen.
  if (phase !== 'showing' || !signedIn) return null;
  return (
    <BootScreen
      apiStatus={apiStatus}
      onRetry={() => warmUpApi({ force: true })}
      onQuickSplits={() => {
        useBootStore.setState({ phase: 'done' });
        router.navigate('/quick');
      }}
    />
  );
}
