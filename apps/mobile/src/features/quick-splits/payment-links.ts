import { formatAmount, plainSpaces } from '@/lib/money';

/**
 * Payment helper links (docs/03 §7). These only open the provider or copy the
 * amount; the app never claims a payment happened (confirmation is the creditor's).
 */

/** Strip URL prefixes, "@" and whitespace from a typed handle. Returns null when empty/invalid. */
export function normaliseHandle(raw: string | undefined | null): string | null {
  if (!raw) return null;
  const h = raw
    .trim()
    .replace(/^https?:\/\//i, '')
    .replace(/^(www\.)?(paypal\.me|revolut\.me)\//i, '')
    .replace(/^@/, '')
    .replace(/\/+$/, '');
  return /^[A-Za-z0-9._-]{1,64}$/.test(h) ? h : null;
}

/** Amount as typed into a banking app (e.g. Bizum): "21,88" for es-ES. */
export function clipboardAmount(cents: number, locale = 'es-ES'): string {
  return plainSpaces(formatAmount(cents, locale));
}

/** PayPal.me link with the amount pre-filled: https://paypal.me/<user>/21.88EUR (dot decimal). */
export function paypalMeUrl(handle: string, cents: number): string | null {
  const user = normaliseHandle(handle);
  if (!user || !Number.isSafeInteger(cents) || cents <= 0) return null;
  const amount = `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
  return `https://paypal.me/${encodeURIComponent(user)}/${amount}EUR`;
}

/** Revolut.me profile link; there is no documented amount parameter, so the amount is copied instead. */
export function revolutUrl(handle: string): string | null {
  const user = normaliseHandle(handle);
  return user ? `https://revolut.me/${encodeURIComponent(user)}` : null;
}
