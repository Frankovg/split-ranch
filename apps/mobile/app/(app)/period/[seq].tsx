import { useLocalSearchParams } from 'expo-router';
import { PeriodScreen } from '@/features/household/PeriodScreen';

const SEQ = /^[1-9][0-9]{0,6}$/;

export default function PeriodRoute() {
  const { seq } = useLocalSearchParams<{ seq: string }>();
  // Malformed deep links show the latest period instead of a 422 from the API.
  return <PeriodScreen periodKey={seq && SEQ.test(seq) ? Number(seq) : 'current'} />;
}
