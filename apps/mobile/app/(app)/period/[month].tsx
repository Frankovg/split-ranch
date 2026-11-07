import { useLocalSearchParams } from 'expo-router';
import { PeriodScreen } from '@/features/household/PeriodScreen';
import { currentMonth } from '@/features/household/dates';

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

export default function PeriodRoute() {
  const { month } = useLocalSearchParams<{ month: string }>();
  // Malformed deep links fall back to the current month instead of a 422 from the API.
  return <PeriodScreen month={month && MONTH.test(month) ? month : currentMonth()} />;
}
