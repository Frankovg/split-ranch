import { router } from 'expo-router';
import { ChevronRight, Plus, Trash2 } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { Alert, Pressable, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Icon } from '@/components/ui/icon';
import { Text } from '@/components/ui/text';
import { currentMoneyLocale } from '@/i18n';
import { useArchiveCategory, useCategories } from './api';
import { categoryIcon } from './categories';
import { ErrorScreen, LoadingScreen } from './components';
import { customCategories } from './custom-categories';
import { useGroupId } from './route';
import type { Category } from './types';

/** The group's custom categories (not the defaults): edit, delete or add one. Any member. */
export function CategoriesScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const categories = useCategories(groupId);
  if (categories.isPending) return <LoadingScreen />;
  if (categories.isError) return <ErrorScreen t={t} onRetry={() => void categories.refetch()} />;
  return <Categories groupId={groupId} categories={categories.data} />;
}

function Categories({ groupId, categories }: { groupId: string; categories: Category[] }) {
  const { t } = useTranslation();
  const archive = useArchiveCategory(groupId);
  const custom = customCategories(categories, currentMoneyLocale());

  const onDelete = (category: Category) =>
    Alert.alert(t('categories.deleteTitle', { name: category.name }), t('categories.deleteBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: () => archive.mutate(category.id, { onError: () => toast.error(t('categories.deleteFailed')) }),
      },
    ]);

  return (
    <Screen>
      <Button
        onPress={() => router.navigate({ pathname: '/group/[groupId]/category/new', params: { groupId } })}>
        <Icon as={Plus} size={18} className='text-primary-foreground' />
        <Text>{t('categories.newTitle')}</Text>
      </Button>

      <Card>
        <CardHeader>
          <CardTitle>{t('categories.listTitle')}</CardTitle>
          {custom.length === 0 ? <CardDescription>{t('categories.empty')}</CardDescription> : null}
        </CardHeader>
        {custom.length > 0 ? (
          <CardContent>
            {custom.map((category) => (
              <View key={category.id} className='flex-row items-center gap-2'>
                <Pressable
                  role='button'
                  accessibilityLabel={t('categories.editLabel', { name: category.name })}
                  onPress={() =>
                    router.navigate({
                      pathname: '/group/[groupId]/category/[categoryId]',
                      params: { groupId, categoryId: category.id },
                    })
                  }
                  className='flex-1 flex-row items-center gap-3 rounded-md py-2 active:bg-accent'>
                  <Icon as={categoryIcon(category)} size={20} className='text-primary' />
                  <Text className='flex-1'>{category.name}</Text>
                  <Icon as={ChevronRight} size={18} className='text-muted-foreground' />
                </Pressable>
                <Button
                  variant='ghost'
                  size='icon'
                  disabled={archive.isPending}
                  accessibilityLabel={t('categories.deleteTitle', { name: category.name })}
                  onPress={() => onDelete(category)}>
                  <Icon as={Trash2} size={18} />
                </Button>
              </View>
            ))}
          </CardContent>
        ) : null}
      </Card>
    </Screen>
  );
}
