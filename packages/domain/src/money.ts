import { DomainError } from './errors';

/** Upper bound for a single amount: 1,000,000.00 EUR in cents. */
export const MAX_AMOUNT_CENTS = 100_000_000;

function assertSafeInt(value: number, what: string): void {
  if (!Number.isSafeInteger(value)) {
    throw new DomainError('invalid_amount', `${what} must be a safe integer, got ${value}`);
  }
}

/**
 * Split `total` cents proportionally to integer `ratios` without losing cents.
 *
 * Largest remainder (Hamilton) method: every share is floored, then the leftover
 * cents go to the shares with the largest fractional remainder; ties are broken by
 * input position (earlier wins). Negative totals are allocated symmetrically.
 * Must stay byte-for-byte equivalent to `split_ranch.domain.money.allocate` (Python).
 */
export function allocate(total: number, ratios: readonly number[]): number[] {
  assertSafeInt(total, 'total');
  if (ratios.length === 0 || ratios.some((r) => !Number.isSafeInteger(r) || r < 0)) {
    throw new DomainError('invalid_ratios', 'ratios must be non-negative integers');
  }
  if (ratios.every((r) => r === 0)) {
    throw new DomainError('invalid_ratios', 'at least one ratio must be positive');
  }
  if (total < 0) {
    return allocate(-total, ratios).map((x) => (x === 0 ? 0 : -x));
  }

  const t = BigInt(total);
  const rSum = ratios.reduce((acc, r) => acc + BigInt(r), 0n);
  const base = ratios.map((r) => (t * BigInt(r)) / rSum);
  const frac = ratios.map((r) => (t * BigInt(r)) % rSum);
  const leftover = Number(t - base.reduce((acc, b) => acc + b, 0n));

  const order = ratios
    .map((_, i) => i)
    .sort((a, b) => {
      const fa = frac[a]!;
      const fb = frac[b]!;
      if (fa !== fb) return fb > fa ? 1 : -1;
      return a - b;
    });
  for (const i of order.slice(0, leftover)) {
    base[i] = base[i]! + 1n;
  }
  return base.map((x) => Number(x));
}

/**
 * Parse a user-typed euro amount into cents. Accepts "12", "12,5", "12.50",
 * "1.234,56" and "1,234.56". Returns null for anything ambiguous or invalid.
 */
export function parseMoney(input: string): number | null {
  const s = input.trim().replace(/\s|€/g, '');
  if (s === '' || !/^\d[\d.,]*$/.test(s)) return null;

  const lastComma = s.lastIndexOf(',');
  const lastDot = s.lastIndexOf('.');
  const sepIndex = Math.max(lastComma, lastDot);

  let intPart = s;
  let decPart = '';
  if (sepIndex !== -1) {
    const tail = s.slice(sepIndex + 1);
    const otherSep = s[sepIndex] === ',' ? '.' : ',';
    const sepCount = s.split(s[sepIndex]!).length - 1;
    // A single separator followed by 1-2 digits is the decimal separator.
    if (sepCount === 1 && tail.length >= 1 && tail.length <= 2) {
      intPart = s.slice(0, sepIndex);
      decPart = tail;
      // Thousands separators in the integer part must be the other symbol, in groups of 3.
      if (intPart.includes(otherSep)) {
        if (!/^\d{1,3}([.,]\d{3})+$/.test(intPart)) return null;
        intPart = intPart.split(otherSep).join('');
      }
    } else if (tail.length === 3) {
      // Only thousands separators, e.g. "1.234" or "1,234,567".
      if (!/^\d{1,3}([.,]\d{3})+$/.test(s) || s.includes(otherSep)) return null;
      intPart = s.split(s[sepIndex]!).join('');
    } else {
      return null;
    }
  }
  if (!/^\d+$/.test(intPart) || (decPart !== '' && !/^\d{1,2}$/.test(decPart))) return null;

  const cents = Number(intPart) * 100 + Number(decPart.padEnd(2, '0') || '0');
  if (!Number.isSafeInteger(cents) || cents > MAX_AMOUNT_CENTS) return null;
  return cents;
}

// Intl constructors are expensive (notably on Hermes): build each formatter once.
const currencyFormatters = new Map<string, Intl.NumberFormat>();
const amountFormatters = new Map<string, Intl.NumberFormat>();

/** Format cents as a localized currency string (default es-ES, EUR). */
export function formatMoney(cents: number, locale = 'es-ES', currency = 'EUR'): string {
  const key = `${locale}|${currency}`;
  let fmt = currencyFormatters.get(key);
  if (!fmt) {
    fmt = new Intl.NumberFormat(locale, { style: 'currency', currency });
    currencyFormatters.set(key, fmt);
  }
  return fmt.format(cents / 100);
}

/** Format cents as a plain decimal string without currency symbol, e.g. 2188 -> "21,88". */
export function formatAmount(cents: number, locale = 'es-ES'): string {
  let fmt = amountFormatters.get(locale);
  if (!fmt) {
    fmt = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    amountFormatters.set(locale, fmt);
  }
  return fmt.format(cents / 100);
}
