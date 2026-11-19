import { useState } from 'react';
import { Trash2 } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { ScrollView, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { apiErrorCode } from '@/lib/api';
import { useCategories, useCategoryPresets, useCreateCategoryPreset, useDeleteCategoryPreset } from './api';
import { categoriesById, categoryIcon, categoryLabel, selectableCategories, sortByLabel } from './categories';
import { presetKeywordTaken } from './category-presets';
import { ErrorScreen, LoadingScreen } from './components';
import { useGroupId } from './route';
import type { Category, CategoryPreset } from './types';

/** The group's category presets: the saved keywords and a form to add one. Any member. */
export function CategoryPresetsScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const categories = useCategories(groupId);
  const presets = useCategoryPresets(groupId);
  if (!groupId || categories.isPending || presets.isPending) return <LoadingScreen />;
  if (categories.isError || presets.isError)
    return (
      <ErrorScreen
        t={t}
        onRetry={() => {
          void categories.refetch();
          void presets.refetch();
        }}
      />
    );
  return <Presets groupId={groupId} categories={categories.data} presets={presets.data} />;
}

function Presets({
  groupId,
  categories,
  presets,
}: {
  groupId: string;
  categories: Category[];
  presets: CategoryPreset[];
}) {
  const { t } = useTranslation();
  const locale = currentMoneyLocale();
  const create = useCreateCategoryPreset(groupId);
  const remove = useDeleteCategoryPreset(groupId);
  const [keyword, setKeyword] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const byId = categoriesById(categories);
  const options = sortByLabel(
    selectableCategories(categories).map((c) => ({ value: c.id, label: categoryLabel(c, t), icon: categoryIcon(c) })),
    locale,
  );
  const selected = options.find((o) => o.value === categoryId);
  const keywordValid = keyword.trim() !== '';
  const categoryValid = selected !== undefined;

  const submit = () => {
    setSubmitted(true);
    if (!keywordValid || !categoryValid || create.isPending) return;
    if (presetKeywordTaken(keyword, presets)) {
      toast.error(t('presets.exists'));
      return;
    }
    create.mutate(
      { keyword: keyword.trim(), category_id: categoryId },
      {
        onSuccess: () => {
          // Ready for the next one; the category often repeats, so it stays selected.
          setKeyword('');
          setSubmitted(false);
        },
        onError: (error) =>
          toast.error(apiErrorCode(error) === 'preset_exists' ? t('presets.exists') : t('presets.saveFailed')),
      },
    );
  };

  return (
    <Screen>
      <Text className='text-sm text-muted-foreground'>{t('presets.intro')}</Text>

      <Card>
        <CardHeader>
          <CardTitle>{t('presets.addTitle')}</CardTitle>
        </CardHeader>
        <CardContent className='gap-3'>
          <View className='gap-1.5'>
            <Label nativeID='preset-keyword'>{t('presets.keyword')}</Label>
            <Input
              aria-labelledby='preset-keyword'
              value={keyword}
              onChangeText={setKeyword}
              placeholder={t('presets.keywordPlaceholder')}
              maxLength={40}
              returnKeyType='done'
              onSubmitEditing={submit}
              className={submitted && !keywordValid ? 'border-destructive' : undefined}
            />
            {submitted && !keywordValid ? (
              <Text className='text-sm text-destructive'>{t('presets.keywordRequired')}</Text>
            ) : null}
          </View>

          <View className='gap-1.5'>
            <Label nativeID='preset-category'>{t('presets.category')}</Label>
            <Select
              value={selected ? { value: selected.value, label: selected.label } : undefined}
              onValueChange={(option) => setCategoryId(option?.value ?? '')}>
              <SelectTrigger
                aria-labelledby='preset-category'
                className={submitted && !categoryValid ? 'border-destructive' : undefined}>
                <View className='flex-1 flex-row items-center gap-2'>
                  {selected ? <Icon as={selected.icon} size={18} className='text-primary' /> : null}
                  <SelectValue placeholder={t('presets.category')} />
                </View>
              </SelectTrigger>
              <SelectContent>
                <ScrollView className='max-h-80' keyboardShouldPersistTaps='handled'>
                  {options.map((o) => (
                    <SelectItem key={o.value} value={o.value} label={o.label}>
                      <Icon as={o.icon} size={18} className='text-primary' />
                    </SelectItem>
                  ))}
                </ScrollView>
              </SelectContent>
            </Select>
            {submitted && !categoryValid ? (
              <Text className='text-sm text-destructive'>{t('presets.categoryRequired')}</Text>
            ) : null}
          </View>

          <Button disabled={create.isPending} onPress={submit}>
            <Text>{t('presets.add')}</Text>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('presets.listTitle')}</CardTitle>
          {presets.length === 0 ? <CardDescription>{t('presets.empty')}</CardDescription> : null}
        </CardHeader>
        {presets.length > 0 ? (
          <CardContent>
            {presets.map((preset) => {
              const category = byId.get(preset.category_id);
              return (
                <View key={preset.id} className='flex-row items-center justify-between gap-3 py-1'>
                  <View className='flex-1'>
                    <Text className='font-medium'>{preset.keyword}</Text>
                    <View className='flex-row items-center gap-1.5'>
                      <Icon as={categoryIcon(category)} size={14} className='text-muted-foreground' />
                      <Text className='text-sm text-muted-foreground'>
                        {category ? categoryLabel(category, t) : t('categories.other')}
                      </Text>
                    </View>
                  </View>
                  <Button
                    variant='ghost'
                    size='icon'
                    disabled={remove.isPending}
                    accessibilityLabel={t('presets.deleteLabel', { keyword: preset.keyword })}
                    onPress={() => remove.mutate(preset.id, { onError: () => toast.error(t('presets.deleteFailed')) })}>
                    <Icon as={Trash2} size={18} />
                  </Button>
                </View>
              );
            })}
          </CardContent>
        ) : null}
      </Card>
    </Screen>
  );
}
