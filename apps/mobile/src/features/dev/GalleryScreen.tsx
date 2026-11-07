import { zodResolver } from '@hookform/resolvers/zod';
import { Inbox, Moon, Plus, Sun } from 'lucide-react-native';
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { z } from 'zod';
import { EmptyState } from '@/components/EmptyState';
import { FormField } from '@/components/FormField';
import { MoneyInput } from '@/components/MoneyInput';
import { MoneyText } from '@/components/MoneyText';
import { Screen } from '@/components/Screen';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Text } from '@/components/ui/text';
import { Textarea } from '@/components/ui/textarea';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { usePreferencesStore } from '@/stores/preferences';
import { useAppColorScheme } from '@/theme/ThemeSync';

/*
 * Dev-only component gallery (docs/13 §7). Sample content below ("Ana", "Lorem"...)
 * is illustrative fixture text for visual checks, not user-facing copy.
 */

const BUTTON_VARIANTS = ['default', 'secondary', 'outline', 'ghost', 'destructive', 'link'] as const;

const sampleSchema = z.object({ name: z.string().min(1, 'Required') });

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="gap-3">{children}</CardContent>
    </Card>
  );
}

export function GalleryScreen() {
  const { t } = useTranslation();
  const scheme = useAppColorScheme();
  const setTheme = usePreferencesStore((s) => s.setTheme);
  const [cents, setCents] = React.useState<number | null>(8750);
  const [checked, setChecked] = React.useState(true);
  const [tab, setTab] = React.useState('a');
  const [toggle, setToggle] = React.useState('equal');
  const { control } = useForm<{ name: string }>({
    resolver: zodResolver(sampleSchema),
    defaultValues: { name: '' },
    mode: 'onTouched',
  });

  return (
    <Screen>
      <Button
        variant="outline"
        onPress={() => setTheme(scheme === 'dark' ? 'light' : 'dark')}
        accessibilityLabel={t('gallery.toggleTheme')}>
        <Icon as={scheme === 'dark' ? Sun : Moon} size={18} />
        <Text>{t('gallery.toggleTheme')}</Text>
      </Button>
      <Text className="text-sm text-muted-foreground">{t('gallery.fontScale')}</Text>

      <Section title={t('gallery.buttons')}>
        {BUTTON_VARIANTS.map((v) => (
          <Button key={v} variant={v} onPress={() => toast(v)}>
            <Text>{v}</Text>
          </Button>
        ))}
        <View className="flex-row flex-wrap gap-2">
          <Button size="sm">
            <Text>sm</Text>
          </Button>
          <Button size="lg">
            <Text>lg</Text>
          </Button>
          <Button size="icon" accessibilityLabel={t('common.add')}>
            <Icon as={Plus} size={20} />
          </Button>
          <Button disabled>
            <Text>disabled</Text>
          </Button>
        </View>
      </Section>

      <Section title={t('gallery.inputs')}>
        <View className="gap-1.5">
          <Label nativeID="g-input">Input</Label>
          <Input placeholder="Lorem" aria-labelledby="g-input" />
        </View>
        <Textarea placeholder="Textarea" accessibilityLabel="Textarea" />
        <MoneyInput size="lg" valueCents={cents} onChangeCents={setCents} accessibilityLabel="MoneyInput" />
        <MoneyInput valueCents={null} onChangeCents={() => {}} accessibilityLabel="MoneyInput" />
        <FormField
          control={control}
          name="name"
          label="FormField"
          description="React Hook Form + Zod"
          render={({ field, inputId }) => (
            <Input
              nativeID={inputId}
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              aria-labelledby={`${inputId}-label`}
            />
          )}
        />
        <Select defaultValue={{ value: 'ana', label: 'Ana' }}>
          <SelectTrigger accessibilityLabel="Select">
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ana" label="Ana" />
            <SelectItem value="bea" label="Bea" />
            <SelectItem value="carlos" label="Carlos" />
          </SelectContent>
        </Select>
        <View className="min-h-12 flex-row items-center gap-3">
          <Switch checked={checked} onCheckedChange={setChecked} accessibilityLabel="Switch" />
          <Text>Switch</Text>
        </View>
        <ToggleGroup type="single" variant="outline" value={toggle} onValueChange={(v) => v && setToggle(v)}>
          {['equal', 'weights', 'percentages'].map((v, i, all) => (
            <ToggleGroupItem key={v} value={v} isFirst={i === 0} isLast={i === all.length - 1} className="flex-1">
              <Text>{v}</Text>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="a">
              <Text>Tab A</Text>
            </TabsTrigger>
            <TabsTrigger value="b">
              <Text>Tab B</Text>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="a">
            <Text>A</Text>
          </TabsContent>
          <TabsContent value="b">
            <Text>B</Text>
          </TabsContent>
        </Tabs>
      </Section>

      <Section title={t('gallery.feedback')}>
        <View className="flex-row flex-wrap gap-2">
          <Badge>
            <Text>default</Text>
          </Badge>
          <Badge variant="secondary">
            <Text>secondary</Text>
          </Badge>
          <Badge variant="outline">
            <Text>outline</Text>
          </Badge>
          <Badge variant="destructive">
            <Text>destructive</Text>
          </Badge>
        </View>
        <View className="flex-row items-center gap-2">
          {['AN', 'BE', 'CA'].map((i) => (
            <Avatar key={i} alt={i}>
              <AvatarFallback>
                <Text>{i}</Text>
              </AvatarFallback>
            </Avatar>
          ))}
        </View>
        <Separator />
        <MoneyText cents={8750} size="3xl" />
        <MoneyText cents={6563} tone="positive" accessibilityPrefix={t('money.youAreOwed', { amount: '' })} />
        <MoneyText cents={-2188} tone="negative" accessibilityPrefix={t('money.youOwe', { amount: '' })} />
        <MoneyText cents={123456789} size="xl" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-14 w-full" />
        <Card>
          <CardHeader>
            <CardTitle>Card</CardTitle>
            <CardDescription>{t('gallery.sample')}</CardDescription>
          </CardHeader>
        </Card>
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline">
              <Text>Dialog</Text>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Dialog</DialogTitle>
              <DialogDescription>{t('gallery.sample')}</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
        <Button variant="secondary" onPress={() => toast.success(t('common.copied'))}>
          <Text>Toast</Text>
        </Button>
        <EmptyState icon={Inbox} title={t('quick.emptyTitle')} body={t('quick.emptyBody')} />
      </Section>
    </Screen>
  );
}
