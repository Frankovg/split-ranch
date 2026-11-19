/**
 * Where a push notification leads. The API puts `{ type, group_id, url }` in the
 * notification data (apps/api use_cases/notifications.py); only the group screens it
 * links to are accepted, so a malformed payload never navigates anywhere unexpected.
 */

const UUID = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';

const ALLOWED = [
  new RegExp(`^/group/(${UUID})$`),
  new RegExp(`^/group/(${UUID})/settle$`),
  new RegExp(`^/group/(${UUID})/expense/${UUID}$`),
];

export type NotificationTarget = { url: string; groupId: string; type: string | null };

export function notificationTarget(data: unknown): NotificationTarget | null {
  if (typeof data !== 'object' || data === null) return null;
  const { url, type } = data as { url?: unknown; type?: unknown };
  if (typeof url !== 'string') return null;
  for (const pattern of ALLOWED) {
    const groupId = pattern.exec(url)?.[1];
    if (groupId) return { url, groupId, type: typeof type === 'string' ? type : null };
  }
  return null;
}
