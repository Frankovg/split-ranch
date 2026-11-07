import { useLocalSearchParams } from 'expo-router';
import { QuickEditorScreen } from '@/features/quick-splits/QuickEditorScreen';

export default function QuickSplitRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <QuickEditorScreen id={id} />;
}
