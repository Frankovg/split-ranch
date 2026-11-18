import { useState } from 'react';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, View } from 'react-native';
import { toast } from 'sonner-native';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/ui/icon';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Text } from '@/components/ui/text';
import { apiErrorCode } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useCreateCategory } from './api';
import { CATEGORY_ICONS } from './categories';
import { useGroupId } from './route';

const ICON_KEYS = Object.keys(CATEGORY_ICONS);

/** New custom category for the open group: a name and an icon. It stays in the group. */
export function NewCategoryScreen() {
  const { t } = useTranslation();
  const groupId = useGroupId();
  const create = useCreateCategory(groupId ?? '');
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('tag');
  const [submitted, setSubmitted] = useState(false);
  const nameValid = name.trim() !== '';

  const submit = () => {
    setSubmitted(true);
    if (!nameValid || !groupId || create.isPending) return;
    create.mutate(
      { name: name.trim(), icon },
      {
        onSuccess: () => router.back(),
        onError: (error) =>
          toast.error(apiErrorCode(error) === 'category_exists' ? t('categories.exists') : t('categories.saveFailed')),
      },
    );
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
          autoFocus
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

      <Button size='lg' disabled={create.isPending} onPress={submit}>
        <Text>{t('common.save')}</Text>
      </Button>
    </Screen>
  );
}
