import type { NotificationPrefs, NotificationPrefsUpdate } from './types';

/** The per-event switches, in the order the settings screen shows them. */
export const EVENT_PREFS = ['expense_created', 'expense_changed', 'payments', 'member_joined'] as const;
export type EventPref = (typeof EVENT_PREFS)[number];

/** Merge a partial update into the switches (fields left out keep their value). */
export function applyPrefs(prefs: NotificationPrefs, changes: NotificationPrefsUpdate): NotificationPrefs {
  const next = { ...prefs };
  for (const key of Object.keys(changes) as (keyof NotificationPrefsUpdate)[]) {
    const value = changes[key];
    if (typeof value === 'boolean') next[key] = value;
  }
  return next;
}
