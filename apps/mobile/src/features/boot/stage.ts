import type { ApiStatus } from '@/lib/api/warm-up';

/**
 * What the boot screen says while the API wakes up (src/features/boot/BootScreen):
 * - `quiet`: just the animation; a warm API usually answers before anything is said.
 * - `preparing`: a short "getting things ready".
 * - `waking`: the API is clearly cold; explain the wait and show a progress bar.
 * - `slow`: well past a normal cold start; keep waiting but offer retry and Quick splits.
 * - `unreachable`: the ping failed; offer retry and Quick splits.
 */
export type BootStage = 'quiet' | 'preparing' | 'waking' | 'slow' | 'unreachable';

export const PREPARING_AFTER_MS = 2_500;
export const WAKING_AFTER_MS = 8_000;
/** Render's cold start is ~1 min; past this something is off. */
export const SLOW_AFTER_MS = 75_000;
/** Shortest time the boot screen stays up, so a fast answer is not a flash. */
export const MIN_VISIBLE_MS = 900;

export function bootStage(elapsedMs: number, apiStatus: ApiStatus): BootStage {
  if (apiStatus === 'unreachable') return 'unreachable';
  if (elapsedMs >= SLOW_AFTER_MS) return 'slow';
  if (elapsedMs >= WAKING_AFTER_MS) return 'waking';
  if (elapsedMs >= PREPARING_AFTER_MS) return 'preparing';
  return 'quiet';
}

/**
 * Whether a signed-in launch needs the boot screen: only when there is nothing cached to
 * show and the API has not answered yet. With a cache the app shows it right away and
 * refreshes in the background, as before.
 */
export function needsBootScreen(apiStatus: ApiStatus, hasCachedData: boolean): boolean {
  if (hasCachedData) return false;
  return apiStatus === 'waking' || apiStatus === 'unreachable';
}
