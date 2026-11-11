import { Minus, Plus } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { MoneyInput } from '@/components/MoneyInput';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Text } from '@/components/ui/text';
import { useQuickSplitsStore } from '@/stores/quick-splits';
import { MAX_WEIGHT } from '../model';
import type { QuickEvent } from '../types';

const NO_PAYER = '__none__';

/** Mode 1 inputs: total, payer, include/exclude and optional weights per person. */
export function TotalModeSection({ event }: { event: QuickEvent }) {
  const { t } = useTranslation();
  const setTotalAmount = useQuickSplitsStore((s) => s.setTotalAmount);
  const setTotalPayer = useQuickSplitsStore((s) => s.setTotalPayer);
  const toggleExcluded = useQuickSplitsStore((s) => s.toggleExcluded);
  const setWeight = useQuickSplitsStore((s) => s.setWeight);

  const payer = event.participants.find((p) => p.id === event.total.payerId);
  const payerOption = payer
    ? { value: payer.id, label: payer.name }
    : { value: NO_PAYER, label: t('quick.noPayer') };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('quick.total')}</CardTitle>
      </CardHeader>
      <CardContent className='gap-4'>
        <MoneyInput
          size='lg'
          valueCents={event.total.amountCents}
          onChangeCents={(cents) => setTotalAmount(event.id, cents)}
          accessibilityLabel={t('quick.total')}
        />

        <View className='gap-1.5'>
          <Label nativeID='total-payer'>{t('quick.payer')}</Label>
          <Select
            value={payerOption}
            onValueChange={(option) =>
              setTotalPayer(event.id, !option || option.value === NO_PAYER ? null : option.value)
            }>
            <SelectTrigger aria-labelledby='total-payer'>
              <SelectValue placeholder={t('quick.noPayer')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_PAYER} label={t('quick.noPayer')} />
              {event.participants.map((p) => (
                <SelectItem key={p.id} value={p.id} label={p.name} />
              ))}
            </SelectContent>
          </Select>
        </View>

        <View className='gap-2'>
          <Text className='font-semibold'>{t('quick.split')}</Text>
          {event.participants.map((p) => {
            const included = !event.total.excludedIds.includes(p.id);
            const weight = event.total.weights[p.id] ?? 1;
            return (
              <View key={p.id} className='min-h-14 flex-row flex-wrap items-center gap-3'>
                <Switch
                  checked={included}
                  onCheckedChange={() => toggleExcluded(event.id, p.id)}
                  accessibilityLabel={t('quick.include', { name: p.name })}
                />
                <Text className={included ? 'flex-1' : 'flex-1 text-muted-foreground line-through'}>{p.name}</Text>
                {included ? (
                  <View className='flex-row items-center gap-1'>
                    <Button
                      variant='ghost'
                      size='icon'
                      disabled={weight <= 1}
                      onPress={() => setWeight(event.id, p.id, weight - 1)}
                      accessibilityLabel={t('quick.decreaseWeight', { name: p.name })}>
                      <Icon as={Minus} size={18} />
                    </Button>
                    <Text
                      className='min-w-8 text-center tabular-nums'
                      accessibilityLabel={t('quick.weightOf', { name: p.name, weight })}>
                      ×{weight}
                    </Text>
                    <Button
                      variant='ghost'
                      size='icon'
                      disabled={weight >= MAX_WEIGHT}
                      onPress={() => setWeight(event.id, p.id, weight + 1)}
                      accessibilityLabel={t('quick.increaseWeight', { name: p.name })}>
                      <Icon as={Plus} size={18} />
                    </Button>
                  </View>
                ) : null}
              </View>
            );
          })}
        </View>
      </CardContent>
    </Card>
  );
}
