/** Pure helpers for the insights pie chart: slices, colour assignment and the ranked list. */

import type { TokenName } from '@/theme/tokens';

/** Categorical colours available for slices, in fixed order (never cycled). */
export const SLICE_COLORS = [
  'chart-1',
  'chart-2',
  'chart-3',
  'chart-4',
  'chart-5',
  'chart-6',
] as const;
/** Colour of the folded "rest" slice and of the categories inside it. */
export const REST_COLOR: TokenName = 'muted-foreground';
/** Key of the folded slice; category ids are UUIDs, so it can never clash. */
export const REST_KEY = 'rest';

export interface CategoryTotal {
  /** Category id, or 'none' for expenses without a category. */
  key: string;
  label: string;
  cents: number;
}

export interface Slice extends CategoryTotal {
  color: TokenName;
}

export interface RankedRow extends CategoryTotal {
  /** Colour of the slice this category is drawn in (the rest colour when folded). */
  color: TokenName;
}

export interface PieModel {
  /** Slices, largest first; a folded "rest" slice, when present, is always last. */
  slices: Slice[];
  /** Every category with spending, largest first (ties by label), each with its slice colour. */
  rows: RankedRow[];
  totalCents: number;
}

function byCentsDesc(a: CategoryTotal, b: CategoryTotal): number {
  return b.cents - a.cents || a.label.localeCompare(b.label);
}

/**
 * Builds the pie: up to six slices; with more categories the five largest keep their own
 * slice and the rest fold into one. Colours follow the category (its position in
 * `stableOrder`), never its rank, so a category keeps its colour while the rank changes.
 */
export function buildPie(
  totals: CategoryTotal[],
  stableOrder: readonly string[],
  restLabel: string,
): PieModel {
  const ranked = totals.filter((t) => t.cents > 0).sort(byCentsDesc);
  const fold = ranked.length > SLICE_COLORS.length;
  const own = fold ? ranked.slice(0, SLICE_COLORS.length - 1) : ranked;
  const rank = (key: string) => {
    const i = stableOrder.indexOf(key);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const colors = new Map<string, TokenName>(
    [...own]
      .sort((a, b) => rank(a.key) - rank(b.key) || a.label.localeCompare(b.label))
      .map((t, i) => [t.key, SLICE_COLORS[i]!]),
  );
  const rows = ranked.map((t) => ({ ...t, color: colors.get(t.key) ?? REST_COLOR }));
  const slices: Slice[] = own.map((t) => ({ ...t, color: colors.get(t.key)! }));
  if (fold) {
    const rest = ranked.slice(own.length).reduce((sum, t) => sum + t.cents, 0);
    slices.push({ key: REST_KEY, label: restLabel, cents: rest, color: REST_COLOR });
  }
  return { slices, rows, totalCents: ranked.reduce((sum, t) => sum + t.cents, 0) };
}

/** Share of `cents` in `total` as a whole percent (0 when there is no total). */
export function percentOf(cents: number, total: number): number {
  return total > 0 ? Math.round((cents / total) * 100) : 0;
}
