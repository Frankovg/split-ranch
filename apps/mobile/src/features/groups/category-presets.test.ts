import { describe, expect, it } from 'vitest';
import { matchCategoryPreset, normalizeKeyword, presetKeywordTaken } from './category-presets';
import type { CategoryPreset } from './types';

const preset = (keyword: string, categoryId: string): CategoryPreset => ({
  id: `${keyword}-${categoryId}`,
  keyword,
  category_id: categoryId,
  created_at: '2026-11-19T12:00:00Z',
});

const presets = [preset('Supermercado', 'groceries'), preset('Gasolina', 'transport'), preset('Super', 'shopping')];
const active = new Set(['groceries', 'transport', 'shopping']);

describe('matchCategoryPreset', () => {
  it('picks the category whose keyword the description contains', () => {
    expect(matchCategoryPreset('Gasolina del coche', presets, active)).toBe('transport');
  });

  it('ignores case and accents', () => {
    expect(matchCategoryPreset('GASOLÍNA', presets, active)).toBe('transport');
  });

  it('prefers the longest keyword', () => {
    expect(matchCategoryPreset('Compra supermercado', presets, active)).toBe('groceries');
    expect(matchCategoryPreset('Super', presets, active)).toBe('shopping');
  });

  it('returns null without a match, description or presets', () => {
    expect(matchCategoryPreset('Cena', presets, active)).toBeNull();
    expect(matchCategoryPreset('  ', presets, active)).toBeNull();
    expect(matchCategoryPreset('Gasolina', undefined, active)).toBeNull();
  });

  it('skips presets of categories that are not active', () => {
    expect(matchCategoryPreset('Gasolina', presets, new Set(['groceries']))).toBeNull();
  });
});

describe('presetKeywordTaken', () => {
  it('compares normalized keywords', () => {
    expect(normalizeKeyword(' Ñandú ')).toBe('nandu');
    expect(presetKeywordTaken('gasolina ', presets)).toBe(true);
    expect(presetKeywordTaken('Cena', presets)).toBe(false);
  });
});
