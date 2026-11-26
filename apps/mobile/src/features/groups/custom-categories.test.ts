import { describe, expect, it } from 'vitest';
import { customCategories } from './custom-categories';
import type { Category } from './types';

const category = (overrides: Partial<Category>): Category => ({
  id: 'id',
  name: 'Name',
  icon: 'tag',
  color: null,
  is_default: false,
  sort_key: 0,
  archived_at: null,
  ...overrides,
});

describe('customCategories', () => {
  it('keeps only active custom categories, sorted by name ignoring case and accents', () => {
    const result = customCategories(
      [
        category({ id: 'gym', name: 'gimnasio' }),
        category({ id: 'default', name: 'Ocio', icon: 'ticket', is_default: true }),
        category({ id: 'archived', name: 'Antiguo', archived_at: '2026-01-01T00:00:00Z' }),
        category({ id: 'pets', name: 'Ánimales' }),
      ],
      'es',
    );
    expect(result.map((c) => c.id)).toEqual(['pets', 'gym']);
  });
});
