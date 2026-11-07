import { CloudOff } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/components/EmptyState';
import { Screen } from '@/components/Screen';

/**
 * Honest placeholder for household screens: they need the FastAPI backend,
 * which this build does not talk to yet. Never shows fake data.
 */
export function BackendPlaceholder() {
  const { t } = useTranslation();
  return (
    <Screen>
      <EmptyState icon={CloudOff} title={t('backend.title')} body={t('backend.body')} />
    </Screen>
  );
}
