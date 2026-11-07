import { ArrowRight, Share2 } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Share, View } from 'react-native';
import { MoneyText } from '@/components/MoneyText';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import type { QuickResult } from '../compute';
import { buildShareText } from '../share-text';
import type { QuickEvent } from '../types';
import { PaymentHelper } from './PaymentHelper';

type ResultCardProps = { event: QuickEvent; result: QuickResult };

export function ResultCard({ event, result }: ResultCardProps) {
  const { t } = useTranslation();

  if (result.status === 'incomplete') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('quick.result')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Text className="text-muted-foreground">{t(`quick.incomplete.${result.reason}`)}</Text>
        </CardContent>
      </Card>
    );
  }

  const title = event.title.trim() || t('quick.defaultTitle');
  const onShare = async () => {
    const message = buildShareText(
      title,
      result,
      {
        each: t('share.each'),
        payments: t('share.payments'),
        noPayments: t('share.noPayments'),
        footer: t('share.footer'),
      },
      currentMoneyLocale(),
    );
    try {
      await Share.share({ message });
    } catch (error) {
      console.warn('Share failed', error);
    }
  };

  const handles = new Map(event.participants.map((p) => [p.id, p]));

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t('quick.result')}</CardTitle>
        <MoneyText cents={result.totalCents} size="xl" accessibilityPrefix={t('quick.total')} />
      </CardHeader>
      <CardContent className="gap-4">
        {result.skippedExpenseIds.length > 0 ? (
          <Badge variant="outline" className="self-start border-warning">
            <Text className="text-warning">{t('quick.skipped', { count: result.skippedExpenseIds.length })}</Text>
          </Badge>
        ) : null}

        <View className="gap-2">
          <Text className="font-semibold">{t('quick.each')}</Text>
          {result.perPerson.map((p) => (
            <View key={p.id} className="min-h-10 flex-row flex-wrap items-center justify-between gap-2">
              <Text className="flex-shrink">{p.name}</Text>
              <MoneyText cents={p.amountCents} accessibilityPrefix={p.name} />
            </View>
          ))}
        </View>

        {result.balances ? (
          <>
            <Separator />
            <View className="gap-2">
              <Text className="font-semibold">{t('quick.balances')}</Text>
              {result.balances.map((b) => (
                <View key={b.id} className="min-h-10 flex-row flex-wrap items-center justify-between gap-2">
                  <View className="flex-shrink">
                    <Text>{b.name}</Text>
                    <Text className="text-sm text-muted-foreground">
                      {t('quick.paid', { amount: displayMoney(b.paidCents, currentMoneyLocale()) })}
                    </Text>
                  </View>
                  <MoneyText
                    cents={b.netCents}
                    tone={b.netCents > 0 ? 'positive' : b.netCents < 0 ? 'negative' : 'muted'}
                    accessibilityPrefix={b.name}
                  />
                </View>
              ))}
            </View>

            <Separator />
            <View className="gap-2">
              <Text className="font-semibold">{t('quick.transfers')}</Text>
              {result.transfers.length === 0 ? (
                <Text className="text-muted-foreground">{t('quick.noTransfers')}</Text>
              ) : (
                result.transfers.map((tr) => {
                  const creditor = handles.get(tr.toId);
                  return (
                    <View
                      key={`${tr.fromId}-${tr.toId}`}
                      className="flex-row flex-wrap items-center gap-2 rounded-md bg-muted px-3 py-2">
                      <View
                        className="flex-1 flex-row flex-wrap items-center gap-1"
                        accessible
                        accessibilityLabel={`${tr.fromName} → ${tr.toName}`}>
                        <Text className="font-medium">{tr.fromName}</Text>
                        <Icon as={ArrowRight} size={16} className="text-muted-foreground" />
                        <Text className="font-medium">{tr.toName}</Text>
                      </View>
                      <MoneyText cents={tr.amountCents} accessibilityPrefix={`${tr.fromName} → ${tr.toName}`} />
                      <PaymentHelper
                        amountCents={tr.amountCents}
                        creditorName={tr.toName}
                        paypalMe={creditor?.paypalMe}
                        revolut={creditor?.revolut}
                      />
                    </View>
                  );
                })
              )}
            </View>
          </>
        ) : null}

        <Button onPress={onShare}>
          <Icon as={Share2} size={18} />
          <Text>{t('quick.shareResult')}</Text>
        </Button>
      </CardContent>
    </Card>
  );
}
