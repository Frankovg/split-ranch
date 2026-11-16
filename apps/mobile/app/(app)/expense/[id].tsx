import { useLocalSearchParams } from 'expo-router';
import { NewExpenseScreen } from '@/features/groups/NewExpenseScreen';

export default function EditExpenseRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <NewExpenseScreen expenseId={id} />;
}
