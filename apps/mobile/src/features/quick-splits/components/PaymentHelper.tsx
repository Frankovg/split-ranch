import * as Clipboard from 'expo-clipboard';
import { Copy, ExternalLink, Wallet } from 'lucide-react-native';
import * as React from 'react';
import { useTranslation } from 'react-i18next';
import { Linking, View } from 'react-native';
import { toast } from 'sonner-native';
import { MoneyText } from '@/components/MoneyText';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Icon } from '@/components/ui/icon';
import { Separator } from '@/components/ui/separator';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { clipboardAmount, paypalMeUrl, revolutUrl } from '../payment-links';

type PaymentHelperProps = {
  amountCents: number;
  creditorName: string;
  /** Creditor's handles, typed ad hoc in Quick splits (docs/03 §7.4). */
  paypalMe?: string;
  revolut?: string;
};

/**
 * "Pagar" helper for one transfer (docs/03 §7): copy the amount (Bizum: then pay from
 * the bank app; launching the bank app is post-MVP), PayPal.me with the amount
 * pre-filled, Revolut profile + copied amount. It never marks anything as paid.
 */
export function PaymentHelper({ amountCents, creditorName, paypalMe, revolut }: PaymentHelperProps) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const amountText = clipboardAmount(amountCents, locale);
  const paypal = paypalMe ? paypalMeUrl(paypalMe, amountCents) : null;
  const revolutLink = revolut ? revolutUrl(revolut) : null;

  const copyAmount = async () => {
    await Clipboard.setStringAsync(amountText);
    toast.success(t('pay.amountCopied', { amount: amountText }));
  };

  const open = async (url: string) => {
    try {
      await Linking.openURL(url);
    } catch (error) {
      console.warn('Failed to open payment link', error);
      toast.error(t('pay.openFailed'));
    }
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          size="sm"
          variant="secondary"
          accessibilityLabel={t('pay.buttonLabel', {
            amount: displayMoney(amountCents, locale),
            name: creditorName,
          })}>
          <Icon as={Wallet} size={16} />
          <Text>{t('pay.button')}</Text>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('pay.title', { name: creditorName })}</DialogTitle>
          <DialogDescription>{t('pay.disclaimer', { name: creditorName })}</DialogDescription>
        </DialogHeader>
        <MoneyText cents={amountCents} size="3xl" className="text-center" />

        <View className="gap-2">
          <Text className="font-semibold">{t('pay.bizum')}</Text>
          <Text className="text-sm text-muted-foreground">{t('pay.bizumHint')}</Text>
          <Button variant="outline" onPress={copyAmount}>
            <Icon as={Copy} size={18} />
            <Text>{t('pay.copyAmount')}</Text>
          </Button>
        </View>

        <Separator />

        <View className="gap-2">
          {paypal ? (
            <Button variant="outline" onPress={() => void open(paypal)}>
              <Icon as={ExternalLink} size={18} />
              <Text>{t('pay.paypal')}</Text>
            </Button>
          ) : (
            <Text className="text-sm text-muted-foreground">
              {t('pay.handleMissing', { provider: 'PayPal.me', name: creditorName })}
            </Text>
          )}
          {revolutLink ? (
            <>
              <Button
                variant="outline"
                onPress={async () => {
                  await copyAmount();
                  await open(revolutLink);
                }}>
                <Icon as={ExternalLink} size={18} />
                <Text>{t('pay.revolut')}</Text>
              </Button>
              <Text className="text-sm text-muted-foreground">{t('pay.revolutHint')}</Text>
            </>
          ) : (
            <Text className="text-sm text-muted-foreground">
              {t('pay.handleMissing', { provider: 'Revolut', name: creditorName })}
            </Text>
          )}
        </View>
      </DialogContent>
    </Dialog>
  );
}
