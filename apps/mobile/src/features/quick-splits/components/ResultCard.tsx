import { ArrowRight, Check, Share2 } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Share, View } from 'react-native';
import type { TFunction } from 'i18next';
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
import { useQuickSplitsStore } from '@/stores/quick-splits';

type ResultCardProps = { event: QuickEvent; result: QuickResult };

/**
 * Manual "owes" / "has paid" switch for someone who owes money. Only the user changes it;
 * for the phone's owner ("you") it reads "I owe" / "I already paid".
 */
function PaidToggle({ event, id, name, t }: { event: QuickEvent; id: string; name: string; t: TFunction }) {
  const togglePaid = useQuickSplitsStore((s) => s.togglePaid);
  const paid = event.paidIds.includes(id);
  const me = event.meId === id;
  const label = me
    ? t(paid ? 'quick.status.mePaid' : 'quick.status.meOwes')
    : t(paid ? 'quick.status.paid' : 'quick.status.owes');
  return (
    <Button
      size="sm"
      variant={paid ? 'secondary' : 'outline'}
      onPress={() => togglePaid(event.id, id)}
      role="switch"
      accessibilityState={{ checked: paid }}
      accessibilityLabel={t('quick.status.toggle', { name, status: label })}>
      {paid ? <Icon as={Check} size={16} className="text-positive" /> : null}
      <Text className={paid ? 'text-positive' : 'text-negative'}>{label}</Text>
    </Button>
  );
}

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
      event.paidIds,
    );
    try {
      await Share.share({ message });
    } catch (error) {
      console.warn('Share failed', error);
    }
  };

  const displayName = (id: string, name: string) =>
    id === event.meId ? t('quick.nameYou', { name }) : name;

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
              <Text className="flex-shrink">{displayName(p.id, p.name)}</Text>
              <View className="flex-row items-center gap-2">
                {/* Without a payer nobody is owed yet: everyone owes their own share. */}
                {!result.balances && p.amountCents > 0 ? (
                  <PaidToggle event={event} id={p.id} name={p.name} t={t} />
                ) : null}
                <MoneyText cents={p.amountCents} accessibilityPrefix={p.name} />
              </View>
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
                    <Text>{displayName(b.id, b.name)}</Text>
                    <Text className="text-sm text-muted-foreground">
                      {t('quick.paid', { amount: displayMoney(b.paidCents, currentMoneyLocale()) })}
                    </Text>
                  </View>
                  <View className="flex-row items-center gap-2">
                    {b.netCents < 0 ? <PaidToggle event={event} id={b.id} name={b.name} t={t} /> : null}
                    <MoneyText
                      cents={b.netCents}
                      tone={b.netCents > 0 ? 'positive' : b.netCents < 0 ? 'negative' : 'muted'}
                      accessibilityPrefix={b.name}
                    />
                  </View>
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
                  const paid = event.paidIds.includes(tr.fromId);
                  return (
                    <View
                      key={`${tr.fromId}-${tr.toId}`}
                      className="flex-row flex-wrap items-center gap-2 rounded-md bg-muted px-3 py-2">
                      <View
                        className="flex-1 flex-row flex-wrap items-center gap-1"
                        accessible
                        accessibilityLabel={`${tr.fromName} → ${tr.toName}`}>
                        <Text className="font-medium">{displayName(tr.fromId, tr.fromName)}</Text>
                        <Icon as={ArrowRight} size={16} className="text-muted-foreground" />
                        <Text className="font-medium">{displayName(tr.toId, tr.toName)}</Text>
                      </View>
                      {paid ? <Icon as={Check} size={16} className="text-positive" /> : null}
                      <MoneyText
                        cents={tr.amountCents}
                        tone={paid ? 'muted' : 'default'}
                        accessibilityPrefix={`${tr.fromName} → ${tr.toName}`}
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
