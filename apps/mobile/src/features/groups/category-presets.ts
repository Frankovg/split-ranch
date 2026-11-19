/**
 * Category presets: keywords that pick a category for a new expense whose description
 * contains them ("Supermercado" → Groceries). Each group keeps its own list on the API;
 * the matching happens here, while the description is typed.
 */
import type { CategoryPreset } from './types';

/** Lower case without accents, so "Gasolína" and "gasolina" are the same keyword. */
export function normalizeKeyword(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
}

/**
 * The category of the preset whose keyword the description contains, or null. When
 * several match, the longest keyword wins (the most specific one). Presets of categories
 * not in `activeCategoryIds` are ignored.
 */
export function matchCategoryPreset(
  description: string,
  presets: readonly CategoryPreset[] | undefined,
  activeCategoryIds: ReadonlySet<string>,
): string | null {
  const text = normalizeKeyword(description);
  if (text === '' || !presets) return null;
  let best: { categoryId: string; length: number } | null = null;
  for (const preset of presets) {
    const keyword = normalizeKeyword(preset.keyword);
    if (keyword === '' || !activeCategoryIds.has(preset.category_id) || !text.includes(keyword)) continue;
    if (!best || keyword.length > best.length) best = { categoryId: preset.category_id, length: keyword.length };
  }
  return best?.categoryId ?? null;
}

/** True when the group already has a preset with this keyword (case and accents ignored). */
export function presetKeywordTaken(keyword: string, presets: readonly CategoryPreset[] | undefined): boolean {
  const normalized = normalizeKeyword(keyword);
  return (presets ?? []).some((p) => normalizeKeyword(p.keyword) === normalized);
}
