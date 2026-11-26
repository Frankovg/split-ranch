/** Pure helpers for the custom categories screen (kept free of React Native imports for tests). */
import type { Category } from './types';

/** Active categories the members created (not the defaults), sorted by name. */
export function customCategories(categories: Category[], locale: string): Category[] {
  return [...categories]
    .filter((c) => !c.is_default && !c.archived_at)
    .sort((a, b) => a.name.localeCompare(b.name, locale, { sensitivity: 'base' }));
}
