import { useState } from 'react';
import { BASIS_POINTS_TOTAL } from '@split-ranch/domain';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';
import { toast } from 'sonner-native';
import { PercentInput } from '@/components/PercentInput';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Text } from '@/components/ui/text';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { currentMoneyLocale } from '@/i18n';
import { cn } from '@/lib/utils';
import { useGroup, useSetDefaultRule, useSplitRules } from './api';
import { activeMembers, ErrorScreen, LoadingScreen, memberName } from './components';
import { useGroupId } from './route';
import { equalValues, rebalance, sumOf } from './split-form';
import {
  ruleFormFromRule,
  ruleMembersChanged,
  ruleProblem,
  ruleSignature,
  toRule,
  type RuleFormState,
  type RuleMode,
} from './split-rule';
import type { Group, SplitRule } from './types';

const RULE_MODES = ['equal', 'custom'] as const satisfies readonly RuleMode[];

/** The group's default split rule: equal parts or a percentage per member. Any member. */
export function SplitRuleScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const group = useGroup(groupId);
  const rules = useSplitRules(groupId);
  if (group.isPending || rules.isPending) return <LoadingScreen />;
  if (group.isError || rules.isError)
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void group.refetch();
          void rules.refetch();
        }}
      />
    );
  return <RuleEditor group={group.data} rule={rules.data.default} />;
}

function RuleEditor({ group, rule }: { group: Group; rule: SplitRule }) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const everyone = activeMembers(group).map((m) => m.id);
  const save = useSetDefaultRule(group.id);
  const [state, setState] = useState<RuleFormState>(() => ruleFormFromRule(rule, everyone));
  const [submitted, setSubmitted] = useState(false);
  const membersChanged = ruleMembersChanged(rule, everyone);
  const problem = ruleProblem(state, everyone);
  const unchanged = ruleSignature(toRule(state, everyone)) === ruleSignature(rule) && !membersChanged;

  const setMode = (mode: RuleMode) =>
    // A fresh custom rule starts from equal percentages.
    setState((s) =>
      mode === s.mode
        ? s
        : mode === 'custom' && s.mode === 'equal'
          ? { mode, percents: equalValues(BASIS_POINTS_TOTAL, everyone), locked: [] }
          : { ...s, mode },
    );

  const setPercent = (id: string, bps: number) =>
    setState((s) => {
      const r = rebalance(s.percents, everyone, s.locked, id, bps, BASIS_POINTS_TOTAL);
      return { ...s, percents: r.values, locked: r.locked };
    });

  const onSave = () => {
    setSubmitted(true);
    if (problem !== null || save.isPending) return;
    save.mutate(toRule(state, everyone), {
      onSuccess: () => router.back(),
      onError: () => toast.error(t('rule.saveFailed')),
    });
  };

  return (
    <Screen>
      <Text className='text-sm text-muted-foreground'>{t('rule.intro')}</Text>

      <ToggleGroup
        type='single'
        variant='outline'
        value={state.mode}
        onValueChange={(v) => v && setMode(v as RuleMode)}
        className='w-full'>
        {RULE_MODES.map((mode, i) => (
          <ToggleGroupItem
            key={mode}
            value={mode}
            isFirst={i === 0}
            isLast={i === RULE_MODES.length - 1}
            className='flex-1'>
            <Text>{t(`rule.mode.${mode}`)}</Text>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <Card>
        <CardHeader>
          <CardTitle>{t(`rule.mode.${state.mode}`)}</CardTitle>
          <CardDescription>{t(`rule.hint.${state.mode}`)}</CardDescription>
        </CardHeader>
        <CardContent className='gap-1'>
          {everyone.map((id) => {
            const name = memberName(group, id, t);
            return (
              <View key={id} className='min-h-14 flex-row items-center gap-3'>
                <Text className='flex-1' numberOfLines={1}>
                  {name}
                </Text>
                {state.mode === 'custom' ? (
                  <PercentInput
                    className='w-28'
                    valueBasisPoints={state.percents[id] ?? 0}
                    onChangeBasisPoints={(bps) => setPercent(id, bps)}
                    locale={locale}
                    accessibilityLabel={t('expenses.percentOf', { name })}
                    invalid={submitted && problem === 'percent_sum'}
                  />
                ) : (
                  <Text className='tabular-nums text-muted-foreground'>
                    {new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(
                      (state.percents[id] ?? 0) / 100,
                    )}{' '}
                    %
                  </Text>
                )}
              </View>
            );
          })}
          {problem === 'percent_sum' ? (
            <Text className={cn('pt-2 text-sm', submitted ? 'text-destructive' : 'text-muted-foreground')}>
              {t('expenses.percentSum', {
                current: new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(
                  sumOf(state.percents, everyone) / 100,
                ),
              })}
            </Text>
          ) : null}
          {membersChanged ? (
            <Text className='pt-2 text-sm text-muted-foreground'>{t('rule.membersChanged')}</Text>
          ) : null}
        </CardContent>
      </Card>

      <Text className='text-sm text-muted-foreground'>{t('rule.onlyNew')}</Text>

      <Button size='lg' disabled={save.isPending || unchanged} onPress={onSave}>
        <Text>{t('common.save')}</Text>
      </Button>
    </Screen>
  );
}
