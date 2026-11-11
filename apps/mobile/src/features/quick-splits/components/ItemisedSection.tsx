import { useState } from 'react';
import { Plus } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, View } from 'react-native';
import { MoneyText } from '@/components/MoneyText';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import type { QuickEvent, QuickExpense } from '../types';
import { ExpenseDialog } from './ExpenseDialog';

/** Mode 2 inputs: list of expenses, each with payer and participant subset. */
export function ItemisedSection({ event }: { event: QuickEvent }) {
  const { t } = useTranslation();
  // undefined = closed, null = new expense, object = editing
  const [editing, setEditing] = useState<QuickExpense | null | undefined>(undefined);
  const names = new Map(event.participants.map((p) => [p.id, p.name]));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('quick.expenses')}</CardTitle>
      </CardHeader>
      <CardContent className='gap-2'>
        {event.expenses.length === 0 ? (
          <Text className='text-muted-foreground'>{t('quick.noExpenses')}</Text>
        ) : (
          event.expenses.map((e) => (
            <Pressable
              key={e.id}
              role='button'
              onPress={() => setEditing(e)}
              accessibilityHint={t('quick.editExpense')}
              className='min-h-14 flex-row items-center gap-3 rounded-md border border-border px-3 py-2 active:bg-accent'>
              <View className='flex-1'>
                <Text className='font-medium'>{e.description || t('quick.expenses')}</Text>
                <Text className='text-sm text-muted-foreground'>
                  {t('quick.expenseSummary', {
                    payer: names.get(e.payerId) ?? '?',
                    count: e.participantIds.length,
                  })}
                </Text>
              </View>
              <MoneyText cents={e.amountCents} />
            </Pressable>
          ))
        )}
        <Button
          variant='outline'
          onPress={() => setEditing(null)}
          disabled={event.participants.length === 0}>
          <Icon as={Plus} size={18} />
          <Text>{t('quick.addExpense')}</Text>
        </Button>
      </CardContent>
      {editing !== undefined ? (
        <ExpenseDialog event={event} expense={editing} onClose={() => setEditing(undefined)} />
      ) : null}
    </Card>
  );
}
