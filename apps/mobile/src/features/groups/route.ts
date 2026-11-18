import { useLocalSearchParams } from 'expo-router';

/**
 * The group a screen under `app/(app)/group/[groupId]/` belongs to. The group comes from
 * the route, so the back stack always matches what is on screen (group list → group → …).
 */
export function useGroupId(): string {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  return groupId;
}
