import {
  captureException,
  init,
  setUser,
  wrap,
  wrapExpoRouterErrorBoundary,
} from '@sentry/react-native';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { ApiError } from '@/lib/api';
import { env, isSentryConfigured } from '@/lib/env';

/**
 * Crash and error reporting (Sentry, EU region). Disabled when EXPO_PUBLIC_SENTRY_DSN is
 * empty, so local builds stay quiet unless a DSN is set in .env.local. Errors only: no
 * tracing, no session replay (free plan quota), and no default PII (docs/08).
 *
 * Automatic coverage once initialised: unhandled JS errors and promise rejections, native
 * crashes, and render errors caught by the root ErrorBoundary. `reportError` is only for
 * handled failures that the user would otherwise hit silently.
 */
export function initSentry(): void {
  if (!isSentryConfigured) return;
  init({
    dsn: env.sentryDsn,
    // The EAS channel ('preview', 'production') is added by the SDK as the
    // `expo.updates.channel` tag. Not read here: importing expo-updates throws on a dev
    // client built without its native module and would take the whole app down.
    environment: __DEV__ ? 'development' : 'production',
    sendDefaultPii: false,
    tracesSampleRate: 0,
  });
}

// With Sentry off, the wrappers below return the component untouched (wrapping without
// init only logs warnings).
const passThrough = <C,>(component: C): C => component;

/** Root layout wrapper (touch/error context). */
export const wrapRoot: typeof wrap = isSentryConfigured ? wrap : passThrough;

/** Expo Router error boundary that also reports the render error it catches. */
export const wrapErrorBoundary: typeof wrapExpoRouterErrorBoundary = isSentryConfigured
  ? wrapExpoRouterErrorBoundary
  : passThrough;

/**
 * Whether a handled error is worth an event: not a lost connection (expected on a phone)
 * and not an API 5xx, which the API already reports to Sentry with its full context.
 */
export function isReportable(error: unknown): boolean {
  if (error instanceof TypeError && error.message === 'Network request failed') return false;
  if (error instanceof ApiError && error.status >= 500) return false;
  return true;
}

/** Reports a handled error with a short `area` tag; a no-op when Sentry is off. */
export function reportError(error: unknown, area: string): void {
  if (!isSentryConfigured || !isReportable(error)) return;
  captureException(error, { tags: { area } });
}

/**
 * Attaches the signed-in user to future events as the same pseudonymised id the API logs
 * and reports (sha256 of the user id, first 16 hex chars), never the email.
 */
export function setSentryUser(userId: string | null): void {
  if (!isSentryConfigured) return;
  if (userId === null) {
    setUser(null);
    return;
  }
  digestStringAsync(CryptoDigestAlgorithm.SHA256, userId)
    .then((digest) => setUser({ id: digest.slice(0, 16) }))
    .catch((error: unknown) => console.warn('Failed to set the Sentry user', error));
}
