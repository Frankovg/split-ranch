/**
 * Category display helpers. The API stores an icon key per category; default categories
 * (copied into every new group) are named by the UI from their icon so they follow the
 * app language. "Other" is the expense without a category (`category_id: null`).
 */
import type { TFunction } from 'i18next';
import {
  Baby,
  Bike,
  Book,
  Briefcase,
  Bus,
  Car,
  Coffee,
  Dog,
  Droplet,
  Dumbbell,
  Flame,
  Fuel,
  Gamepad2,
  Gift,
  GraduationCap,
  Heart,
  House,
  type LucideIcon,
  Music,
  Pill,
  Plane,
  ShieldCheck,
  Shirt,
  ShoppingBag,
  ShoppingCart,
  Smartphone,
  Sofa,
  Tag,
  Ticket,
  Train,
  Utensils,
  Wifi,
  Wine,
  Wrench,
  Zap,
} from 'lucide-react-native';
import type { Category } from './types';

/** Icon keys stored in `categories.icon`, in the order the icon picker shows them. */
export const CATEGORY_ICONS: Record<string, LucideIcon> = {
  cart: ShoppingCart,
  home: House,
  bolt: Zap,
  droplet: Droplet,
  flame: Flame,
  wifi: Wifi,
  bus: Bus,
  utensils: Utensils,
  ticket: Ticket,
  heart: Heart,
  sofa: Sofa,
  shield: ShieldCheck,
  bag: ShoppingBag,
  plane: Plane,
  car: Car,
  fuel: Fuel,
  train: Train,
  bike: Bike,
  coffee: Coffee,
  wine: Wine,
  gift: Gift,
  shirt: Shirt,
  baby: Baby,
  pet: Dog,
  book: Book,
  school: GraduationCap,
  gym: Dumbbell,
  music: Music,
  games: Gamepad2,
  pill: Pill,
  work: Briefcase,
  phone: Smartphone,
  tools: Wrench,
  tag: Tag,
};

/** Icon keys of the default categories the API creates (see DEFAULT_CATEGORIES). */
const DEFAULT_ICON_KEYS = ['ticket', 'cart', 'heart', 'sofa', 'shield', 'home', 'utensils', 'bag', 'bus'] as const;
type DefaultIconKey = (typeof DEFAULT_ICON_KEYS)[number];

const isDefaultIconKey = (icon: string | null): icon is DefaultIconKey =>
  icon !== null && (DEFAULT_ICON_KEYS as readonly string[]).includes(icon);

/**
 * The default "Otros" category older groups got (icon `dots`). Migration 0008 archives
 * it: "Other" is the expense without a category. Until then it is shown as "Other" and
 * left out of the pickers.
 */
export function isLegacyOther(category: Pick<Category, 'icon' | 'is_default'>): boolean {
  return category.is_default && category.icon === 'dots';
}

/** Categories a picker offers: not archived (unless `keepId`) and not the legacy "Otros". */
export function selectableCategories(categories: Category[] | undefined, keepId?: string): Category[] {
  return (categories ?? []).filter((c) => !isLegacyOther(c) && (!c.archived_at || c.id === keepId));
}

/** The icon of a category; "Other" (no category) and unknown keys use a tag. */
export function categoryIcon(category: Pick<Category, 'icon'> | null | undefined): LucideIcon {
  return (category?.icon && CATEGORY_ICONS[category.icon]) || Tag;
}

/** Display name: default categories are translated, custom ones keep the name typed. */
export function categoryLabel(category: Pick<Category, 'name' | 'icon' | 'is_default'>, t: TFunction): string {
  if (isLegacyOther(category)) return t('categories.other');
  if (category.is_default && isDefaultIconKey(category.icon)) return t(`categories.default.${category.icon}`);
  return category.name;
}

/** Sorts by display label, alphabetically in the app language (accents and case ignored). */
export function sortByLabel<T extends { label: string }>(items: T[], locale: string): T[] {
  return [...items].sort((a, b) => a.label.localeCompare(b.label, locale, { sensitivity: 'base' }));
}

/** Category id → display name, for lists that show the category of each expense. */
export function categoryLabels(categories: Category[] | undefined, t: TFunction): Map<string, string> {
  return new Map((categories ?? []).map((c) => [c.id, categoryLabel(c, t)]));
}

/** Category id → category, to look up the category of each listed expense. */
export function categoriesById(categories: Category[] | undefined): Map<string, Category> {
  return new Map((categories ?? []).map((c) => [c.id, c]));
}
