import { useState } from 'react';
import { Search } from 'lucide-react-native';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EmptyState } from '@/components/EmptyState';
import { ScreenBackground } from '@/components/ScreenBackground';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { useDebouncedValue } from '@/lib/use-debounced-value';
import { useCategories, useExpensesInfinite, useGroup } from './api';
import { categoriesById } from './categories';
import { ErrorScreen, ExpenseRow, LoadingScreen } from './components';
import { useGroupId } from './route';

/** Wait this long after the last keystroke before querying the API. */
const SEARCH_DEBOUNCE_MS = 300;
/** The API caps `q` at 100 characters. */
const MAX_QUERY_LENGTH = 100;

/** Search the group's expenses by description, across all dates. */
export function SearchScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const group = useGroup(groupId);
  const categories = useCategories(groupId);
  const [text, setText] = useState('');
  const q = useDebouncedValue(text.trim(), SEARCH_DEBOUNCE_MS);
  // No query, no request: the list stays empty until something is typed.
  const results = useExpensesInfinite(q ? groupId : undefined, { q });

  if (group.isPending) return <LoadingScreen />;
  if (group.isError) return <ErrorScreen t={t} onRetry={() => void group.refetch()} />;

  const g = group.data;
  const categoryById = categoriesById(categories.data);
  const items = results.data?.pages.flatMap((page) => page.items) ?? [];
  const loadMore = () => {
    if (results.hasNextPage && !results.isFetching) void results.fetchNextPage();
  };

  return (
    <SafeAreaView edges={['bottom']} className='flex-1 bg-background'>
      <ScreenBackground />
      <View className='px-4 pt-4'>
        <Input
          value={text}
          onChangeText={setText}
          placeholder={t('search.placeholder')}
          accessibilityLabel={t('search.title')}
          maxLength={MAX_QUERY_LENGTH}
          autoFocus
          returnKeyType='search'
          clearButtonMode='while-editing'
        />
      </View>
      <FlatList
        data={items}
        keyExtractor={(e) => e.id}
        keyboardShouldPersistTaps='handled'
        contentContainerClassName='px-4 py-2'
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        ItemSeparatorComponent={Separator}
        ListEmptyComponent={
          results.isFetching ? (
            <View className='py-8'>
              <ActivityIndicator />
            </View>
          ) : q ? (
            <EmptyState icon={Search} title={t('search.empty', { query: q })} />
          ) : (
            <EmptyState icon={Search} title={t('search.hint')} />
          )
        }
        ListFooterComponent={
          results.isFetchingNextPage ? (
            <View className='py-4'>
              <ActivityIndicator />
            </View>
          ) : undefined
        }
        renderItem={({ item }) => (
          <ExpenseRow
            expense={item}
            group={g}
            category={item.category_id ? categoryById.get(item.category_id) : undefined}
            t={t}
          />
        )}
      />
    </SafeAreaView>
  );
}
