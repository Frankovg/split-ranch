import { useState } from 'react';
import { AlertTriangle, ChartPie, ChevronLeft, ChevronRight } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { PieChart } from 'react-native-gifted-charts';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EmptyState } from '@/components/EmptyState';
import { ScreenBackground } from '@/components/ScreenBackground';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { currentMoneyLocale } from '@/i18n';
import { displayMoney } from '@/lib/money';
import { useRefreshByUser, useRefreshOnFocus } from '@/lib/query/refresh';
import { cn } from '@/lib/utils';
import { useAppColorScheme } from '@/theme/ThemeSync';
import { type ColorScheme, tokenColor } from '@/theme/tokens';
import { useCategories, useGroup, useSummary } from './api';
import { categoryLabels } from './categories';
import { ErrorScreen, LoadingScreen } from './components';
import { monthLabel, monthRange, yearRange } from './dates';
import { buildPie, percentOf, type PieModel, type Slice } from './insights';
import { useGroupId } from './route';
import type { DateRange, Summary } from './types';

type Period = 'month' | 'year' | 'all';
type Scope = 'group' | 'me';

const PERIODS = ['month', 'year', 'all'] as const;
/** Legend rows shown before the legend scrolls. */
const LEGEND_VISIBLE_ROWS = 5;
const LEGEND_ROW_HEIGHT = 28;
const PIE_RADIUS = 76;
const PIE_INNER_RADIUS = 54;

function capitalize(text: string): string {
  return text.charAt(0).toLocaleUpperCase() + text.slice(1);
}

/**
 * Insights: spending per category as a donut for one month, one year or all time, for the
 * whole group or only the caller's share. Read-only; nothing is added from here.
 */
export function InsightsScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const group = useGroup(groupId);
  const categories = useCategories(groupId);
  const [period, setPeriod] = useState<Period>('month');
  const [scope, setScope] = useState<Scope>('group');
  // Offsets from the current month / year (0 = now, -1 = the previous one).
  const [monthOffset, setMonthOffset] = useState(0);
  const [yearOffset, setYearOffset] = useState(0);
  const timeZone = group.data?.timezone;
  const range: DateRange = !timeZone
    ? {}
    : period === 'month'
      ? monthRange(timeZone, monthOffset)
      : period === 'year'
        ? yearRange(timeZone, yearOffset)
        : {};
  const summary = useSummary(group.data ? groupId : undefined, { ...range, mine: scope === 'me' });
  useRefreshOnFocus(groupId);
  const { isRefetchingByUser, refetchByUser } = useRefreshByUser(
    summary.refetch,
    categories.refetch,
  );

  if (group.isPending) return <LoadingScreen />;
  if (group.isError) return <ErrorScreen t={t} onRetry={() => void group.refetch()} />;

  const locale = currentMoneyLocale();

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <ScreenBackground />
      <ScrollView
        contentContainerClassName='gap-4 px-4 py-4'
        refreshControl={
          <RefreshControl refreshing={isRefetchingByUser} onRefresh={() => void refetchByUser()} />
        }
      >
        {/* Filters: one block above the chart. */}
        <View className='gap-3'>
          <Tabs value={period} onValueChange={(v) => setPeriod(v as Period)}>
            <TabsList className='mr-0 h-11 w-full'>
              {PERIODS.map((p) => (
                <TabsTrigger key={p} value={p} className='flex-1'>
                  <Text>{t(`insights.period.${p}`)}</Text>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <ToggleGroup
            type='single'
            variant='outline'
            value={scope}
            onValueChange={(v) => v && setScope(v as Scope)}
            className='w-full'
          >
            {(['group', 'me'] as const).map((s, i) => (
              <ToggleGroupItem
                key={s}
                value={s}
                isFirst={i === 0}
                isLast={i === 1}
                className='flex-1'
              >
                <Text>{t(`insights.scope.${s}`)}</Text>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {period === 'month' && range.from ? (
            <PeriodStepper
              label={capitalize(monthLabel(range.from, locale))}
              previousLabel={t('insights.previousMonth')}
              nextLabel={t('insights.nextMonth')}
              canGoNext={monthOffset < 0}
              onStep={(delta) => setMonthOffset((o) => o + delta)}
            />
          ) : null}
          {period === 'year' && range.from ? (
            <PeriodStepper
              label={range.from.slice(0, 4)}
              previousLabel={t('insights.previousYear')}
              nextLabel={t('insights.nextYear')}
              canGoNext={yearOffset < 0}
              onStep={(delta) => setYearOffset((o) => o + delta)}
            />
          ) : null}
        </View>

        {summary.isPending ? (
          <Card className='h-48 opacity-60' />
        ) : summary.isError ? (
          <EmptyState
            icon={AlertTriangle}
            title={t('common.error')}
            action={{ label: t('common.retry'), onPress: () => void summary.refetch() }}
          />
        ) : summary.data.total_cents <= 0 ? (
          <EmptyState
            icon={ChartPie}
            title={t(scope === 'me' ? 'insights.emptyMine' : 'insights.empty')}
          />
        ) : (
          <CategoryBreakdown
            // A new period or scope starts with no slice selected.
            key={`${period}|${range.from ?? ''}|${scope}`}
            summary={summary.data}
            categoryNames={categoryLabels(categories.data, t)}
            stableOrder={[...(categories.data ?? []).map((c) => c.id), 'none']}
            locale={locale}
          />
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

/** "‹ noviembre de 2026 ›": steps one period back or forward (never past the current one). */
function PeriodStepper({
  label,
  previousLabel,
  nextLabel,
  canGoNext,
  onStep,
}: {
  label: string;
  previousLabel: string;
  nextLabel: string;
  canGoNext: boolean;
  onStep: (delta: number) => void;
}) {
  return (
    <View className='flex-row items-center justify-between'>
      <Button
        variant='ghost'
        size='icon'
        accessibilityLabel={previousLabel}
        onPress={() => onStep(-1)}
      >
        <Icon as={ChevronLeft} size={22} />
      </Button>
      <Text className='flex-1 text-center text-base font-semibold' accessibilityLiveRegion='polite'>
        {label}
      </Text>
      <Button
        variant='ghost'
        size='icon'
        accessibilityLabel={nextLabel}
        disabled={!canGoNext}
        onPress={() => onStep(1)}
      >
        <Icon as={ChevronRight} size={22} />
      </Button>
    </View>
  );
}

function CategoryBreakdown({
  summary,
  categoryNames,
  stableOrder,
  locale,
}: {
  summary: Summary;
  categoryNames: Map<string, string>;
  stableOrder: string[];
  locale: string;
}) {
  const { t } = useTranslation();
  const scheme = useAppColorScheme();
  const [selectedKey, setSelectedKey] = useState<string | undefined>();
  const pie = buildPie(
    summary.by_category.map((c) => ({
      key: c.category_id ?? 'none',
      label: c.category_id ? (categoryNames.get(c.category_id) ?? '—') : t('categories.other'),
      cents: c.total_cents,
    })),
    stableOrder,
    t('insights.rest'),
  );
  const toggle = (key: string) => setSelectedKey((current) => (current === key ? undefined : key));

  return (
    <>
      <Card className='py-4'>
        <CardContent className='flex-row items-center gap-4 px-4'>
          <Donut
            pie={pie}
            scheme={scheme}
            selectedKey={selectedKey}
            onToggle={toggle}
            locale={locale}
          />
          <Legend pie={pie} scheme={scheme} selectedKey={selectedKey} onToggle={toggle} />
        </CardContent>
      </Card>
      <Card className='py-4'>
        <CardContent className='gap-3 px-4'>
          <View className='flex-row items-baseline justify-between gap-3'>
            <Text className='font-semibold' role='heading'>
              {t('insights.byCategory')}
            </Text>
            <Text className='text-sm text-muted-foreground'>
              {t('insights.count', { count: summary.count })}
            </Text>
          </View>
          {/* The ranked list doubles as the chart's table view. */}
          <View className='gap-1'>
            {pie.rows.map((row) => {
              const value = displayMoney(row.cents, locale);
              return (
                <View
                  key={row.key}
                  accessible
                  accessibilityLabel={`${row.label}: ${value}`}
                  className='min-h-10 flex-row items-center gap-3'
                >
                  <Swatch color={tokenColor(scheme, row.color)} />
                  <Text className='flex-1' numberOfLines={1}>
                    {row.label}
                  </Text>
                  <Text className='font-medium tabular-nums'>{value}</Text>
                </View>
              );
            })}
          </View>
        </CardContent>
      </Card>
    </>
  );
}

function Donut({
  pie,
  scheme,
  selectedKey,
  onToggle,
  locale,
}: {
  pie: PieModel;
  scheme: ColorScheme;
  selectedKey: string | undefined;
  onToggle: (key: string) => void;
  locale: string;
}) {
  const { t } = useTranslation();
  const surface = tokenColor(scheme, 'card');
  const selected = pie.slices.find((s) => s.key === selectedKey);
  // A single slice needs no gap stroke: it would draw a seam at 12 o'clock.
  const stroke = pie.slices.length > 1 ? 2 : 0;
  return (
    <View
      accessible
      accessibilityLabel={`${t('insights.total')}: ${displayMoney(pie.totalCents, locale)}`}
      importantForAccessibility='yes'
    >
      <PieChart
        donut
        radius={PIE_RADIUS}
        innerRadius={PIE_INNER_RADIUS}
        innerCircleColor={surface}
        strokeColor={surface}
        strokeWidth={stroke}
        extraRadius={6}
        data={pie.slices.map((s) => ({
          value: s.cents,
          color: tokenColor(scheme, s.color),
          focused: s.key === selectedKey,
          onPress: () => onToggle(s.key),
        }))}
        centerLabelComponent={() => (
          <View className='items-center px-1' style={{ maxWidth: PIE_INNER_RADIUS * 2 - 8 }}>
            <Text className='text-xs text-muted-foreground' numberOfLines={1}>
              {selected
                ? `${selected.label} · ${percentOf(selected.cents, pie.totalCents)}%`
                : t('insights.total')}
            </Text>
            <Text
              className='text-sm font-semibold tabular-nums'
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              {displayMoney(selected ? selected.cents : pie.totalCents, locale)}
            </Text>
          </View>
        )}
      />
    </View>
  );
}

/** Category names with their slice colour; scrolls once it has more than five rows. */
function Legend({
  pie,
  scheme,
  selectedKey,
  onToggle,
}: {
  pie: PieModel;
  scheme: ColorScheme;
  selectedKey: string | undefined;
  onToggle: (key: string) => void;
}) {
  const scrolls = pie.slices.length > LEGEND_VISIBLE_ROWS;
  return (
    <ScrollView
      className='flex-1'
      style={{ maxHeight: LEGEND_VISIBLE_ROWS * LEGEND_ROW_HEIGHT }}
      scrollEnabled={scrolls}
      nestedScrollEnabled
      showsVerticalScrollIndicator={false}
    >
      {pie.slices.map((slice: Slice) => {
        const selected = slice.key === selectedKey;
        return (
          <Pressable
            key={slice.key}
            accessibilityRole='button'
            accessibilityState={{ selected }}
            onPress={() => onToggle(slice.key)}
            style={{ height: LEGEND_ROW_HEIGHT }}
            className='flex-row items-center gap-2 rounded-sm px-1 active:bg-accent'
          >
            <Swatch color={tokenColor(scheme, slice.color)} />
            <Text className={cn('flex-1 text-sm', selected && 'font-semibold')} numberOfLines={1}>
              {slice.label}
            </Text>
            <Text className='text-xs tabular-nums text-muted-foreground'>
              {percentOf(slice.cents, pie.totalCents)}%
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function Swatch({ color }: { color: string }) {
  return <View className='h-3 w-3 rounded-sm' style={{ backgroundColor: color }} />;
}
