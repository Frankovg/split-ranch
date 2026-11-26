import { useEffect } from 'react';
import { AppState } from 'react-native';
import { create } from 'zustand';
import { env, isApiConfigured } from '@/lib/env';

/**
 * Cold-start warm-up for the API.
 *
 * The API runs on Render's free plan (infra/render.yaml): the instance spins down after
 * 15 min without traffic and takes ~1 min to boot again. To hide most of that delay, the
 * app fires an unauthenticated, fire-and-forget `GET /healthz` as early as possible (module
 * load of the root layout, i.e. while the splash screen is still up) and again whenever it
 * returns to the foreground. The boot then overlaps with the splash, session restore and
 * sign-in instead of the first data request.
 *
 * The outcome of the ping is published in `useApiStatusStore`, so the boot screen
 * (src/features/boot) can keep showing while the API wakes up instead of bare skeletons.
 *
 * This does not keep the instance awake; it only starts waking it sooner. Pings are
 * throttled because an awake instance answers in milliseconds and needs no extra traffic.
 * Remove this when the API moves to a plan that does not sleep.
 */

/** Below Render's 15 min idle window: a ping more recent than this means the API is awake. */
const WARM_UP_INTERVAL_MS = 5 * 60 * 1000;

/**
 * - `idle`: no ping sent (API not configured, or before the first ping).
 * - `waking`: a ping is in flight; on a cold instance this lasts up to ~1 min.
 * - `awake`: the last ping got a successful response.
 * - `unreachable`: the last ping failed (offline, or the API answered with an error).
 */
export type ApiStatus = 'idle' | 'waking' | 'awake' | 'unreachable';

export const useApiStatusStore = create<{ status: ApiStatus }>()(() => ({ status: 'idle' }));

let lastWarmUpAt: number | null = null;

interface WarmUpOptions {
  fetchImpl?: typeof fetch;
  now?: number;
  /** Ignore the throttle (manual retry from the boot screen). */
  force?: boolean;
}

/** Pings `/healthz` unless a ping went out recently. Never throws. */
export function warmUpApi({ fetchImpl = fetch, now = Date.now(), force = false }: WarmUpOptions = {}): void {
  if (!isApiConfigured) return;
  if (!force && lastWarmUpAt !== null && now - lastWarmUpAt < WARM_UP_INTERVAL_MS) return;
  lastWarmUpAt = now;
  // A foreground re-ping of an awake API must not bring the boot screen back.
  if (useApiStatusStore.getState().status !== 'awake') useApiStatusStore.setState({ status: 'waking' });
  fetchImpl(`${env.apiUrl}/healthz`, { method: 'GET' })
    .then((response) => {
      useApiStatusStore.setState({ status: response.ok ? 'awake' : 'unreachable' });
      if (!response.ok) lastWarmUpAt = null;
    })
    .catch(() => {
      // Offline or still booting: allow the next foreground to try again.
      lastWarmUpAt = null;
      useApiStatusStore.setState({ status: 'unreachable' });
    });
}

/** Re-sends the warm-up ping each time the app comes back to the foreground. */
export function useApiWarmUpOnForeground() {
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (status) => {
      if (status === 'active') warmUpApi();
    });
    return () => subscription.remove();
  }, []);
}

/** Test-only: forget the last ping and the published status. */
export function resetWarmUpForTests() {
  lastWarmUpAt = null;
  useApiStatusStore.setState({ status: 'idle' });
}
