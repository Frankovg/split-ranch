import { useEffect } from 'react';
import { AppState } from 'react-native';
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
 * This does not keep the instance awake; it only starts waking it sooner. Pings are
 * throttled because an awake instance answers in milliseconds and needs no extra traffic.
 * Remove this when the API moves to a plan that does not sleep.
 */

/** Below Render's 15 min idle window: a ping more recent than this means the API is awake. */
const WARM_UP_INTERVAL_MS = 5 * 60 * 1000;

let lastWarmUpAt: number | null = null;

/** Pings `/healthz` unless a ping went out recently. Never throws; the result is ignored. */
export function warmUpApi(fetchImpl: typeof fetch = fetch, now: number = Date.now()): void {
  if (!isApiConfigured) return;
  if (lastWarmUpAt !== null && now - lastWarmUpAt < WARM_UP_INTERVAL_MS) return;
  lastWarmUpAt = now;
  fetchImpl(`${env.apiUrl}/healthz`, { method: 'GET' }).catch(() => {
    // Offline or still booting: allow the next foreground to try again.
    lastWarmUpAt = null;
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

/** Test-only: forget the last ping. */
export function resetWarmUpForTests() {
  lastWarmUpAt = null;
}
