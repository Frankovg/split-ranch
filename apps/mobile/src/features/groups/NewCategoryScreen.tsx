import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Tag } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Pressable, View } from 'react-native';
import { toast } from 'sonner-native';
import { EmptyState } from '@/components/EmptyState';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { apiErrorCode } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useCategories, useCreateCategory, useUpdateCategory } from './api';
import { CATEGORY_ICONS } from './categories';
import { ErrorScreen, LoadingScreen } from './components';
import { useGroupId } from './route';
import type { Category } from './types';

const ICON_KEYS = Object.keys(CATEGORY_ICONS);

/** New custom category for the open group: a name and an icon. It stays in the group. */
export function NewCategoryScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const create = useCreateCategory(groupId ?? '');
  return (
    <CategoryForm
      initialName=''
      initialIcon='tag'
      pending={create.isPending}
      onSave={(input) =>
        create.mutate(input, {
          onSuccess: () => router.back(),
          onError: (error) =>
            toast.error(apiErrorCode(error) === 'category_exists' ? t('categories.exists') : t('categories.saveFailed')),
        })
      }
    />
  );
}

/** Rename a custom category of the open group or change its icon. */
export function EditCategoryScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const { categoryId } = useLocalSearchParams<{ categoryId: string }>();
  const categories = useCategories(groupId);
  if (categories.isPending) return <LoadingScreen />;
  if (categories.isError) return <ErrorScreen t={t} onRetry={() => void categories.refetch()} />;
  const category = categories.data.find((c) => c.id === categoryId && !c.archived_at && !c.is_default);
  // Archived meanwhile, or a default category (named by the app, not editable here).
  if (!category)
    return (
      <Screen>
        <EmptyState
          icon={Tag}
          title={t('categories.notFound')}
          action={{ label: t('common.back'), onPress: () => router.back() }}
        />
      </Screen>
    );
  return <EditCategory groupId={groupId} category={category} />;
}

function EditCategory({ groupId, category }: { groupId: string; category: Category }) {
  const { t } = useTranslation();
  const update = useUpdateCategory(groupId);
  return (
    <CategoryForm
      initialName={category.name}
      initialIcon={category.icon && CATEGORY_ICONS[category.icon] ? category.icon : 'tag'}
      pending={update.isPending}
      onSave={(input) =>
        update.mutate(
          { categoryId: category.id, input },
          {
            onSuccess: () => router.back(),
            onError: (error) =>
              toast.error(
                apiErrorCode(error) === 'category_exists' ? t('categories.exists') : t('categories.updateFailed'),
              ),
          },
        )
      }
    />
  );
}

function CategoryForm({
  initialName,
  initialIcon,
  pending,
  onSave,
}: {
  initialName: string;
  initialIcon: string;
  pending: boolean;
  onSave: (input: { name: string; icon: string }) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialName);
  const [icon, setIcon] = useState(initialIcon);
  const [submitted, setSubmitted] = useState(false);
  const nameValid = name.trim() !== '';

  const submit = () => {
    setSubmitted(true);
    if (!nameValid || pending) return;
    onSave({ name: name.trim(), icon });
  };

  return (
    <Screen>
      <View className='gap-1.5'>
        <Label nativeID='category-name'>{t('categories.name')}</Label>
        <Input
          aria-labelledby='category-name'
          value={name}
          onChangeText={setName}
          placeholder={t('categories.namePlaceholder')}
          maxLength={40}
          autoFocus={initialName === ''}
          returnKeyType='done'
          onSubmitEditing={submit}
          className={submitted && !nameValid ? 'border-destructive' : undefined}
        />
        {submitted && !nameValid ? (
          <Text className='text-sm text-destructive'>{t('categories.nameRequired')}</Text>
        ) : null}
      </View>

      <View className='gap-1.5'>
        <Label>{t('categories.icon')}</Label>
        <View className='flex-row flex-wrap gap-2'>
          {ICON_KEYS.map((key) => {
            const selected = key === icon;
            const IconComponent = CATEGORY_ICONS[key];
            if (!IconComponent) return null;
            return (
              <Pressable
                key={key}
                role='radio'
                aria-checked={selected}
                accessibilityLabel={t('categories.iconLabel', { icon: key })}
                onPress={() => setIcon(key)}
                className={cn(
                  'size-12 items-center justify-center rounded-md border',
                  selected ? 'border-primary bg-primary/15' : 'border-input active:bg-accent',
                )}>
                <Icon as={IconComponent} size={22} className={selected ? 'text-primary' : 'text-foreground'} />
              </Pressable>
            );
          })}
        </View>
      </View>

      <Button size='lg' disabled={pending} onPress={submit}>
        <Text>{t('common.save')}</Text>
      </Button>
    </Screen>
  );
}
