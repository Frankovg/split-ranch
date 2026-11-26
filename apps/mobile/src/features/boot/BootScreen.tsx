import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  FadeIn,
  FadeInDown,
  FadeOut,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/button';
import { Text } from '@/components/ui/text';
import { type ApiStatus } from '@/lib/api/warm-up';
import { useAppColorScheme } from '@/theme/ThemeSync';
import { tokenColor } from '@/theme/tokens';
import { BootMark } from './BootMark';
import { bootStage, WAKING_AFTER_MS } from './stage';

/** The progress bar creeps towards this share over a typical cold start, never to the end. */
const PROGRESS_CEILING = 0.92;
const PROGRESS_MS = 60_000;
const BAR_WIDTH = 176;

interface BootScreenProps {
  apiStatus: ApiStatus;
  onRetry: () => void;
  onQuickSplits: () => void;
}

/**
 * Full-screen launch screen shown over the app while the API wakes up (see BootGate).
 * It starts identical to the native splash (same background, the house centred at the same
 * size) and then comes alive; after a few seconds it explains the wait.
 */
export function BootScreen({ apiStatus, onRetry, onQuickSplits }: BootScreenProps) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const scheme = useAppColorScheme();
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setElapsed(Date.now() - startedAt), 500);
    return () => clearInterval(timer);
  }, [startedAt]);

  const stage = bootStage(elapsed, apiStatus);
  const showProgress = stage === 'waking' || stage === 'slow';
  const showActions = stage === 'slow' || stage === 'unreachable';

  const progress = useSharedValue(0);
  useEffect(() => {
    if (apiStatus === 'awake') {
      progress.value = withTiming(1, { duration: 250 });
    } else if (showProgress) {
      // Pick up where a cold start usually is once the bar appears, then ease out.
      const remaining = Math.max(PROGRESS_MS - WAKING_AFTER_MS, 1_000);
      progress.value = withTiming(PROGRESS_CEILING, {
        duration: remaining,
        easing: Easing.out(Easing.cubic),
      });
    }
  }, [apiStatus, progress, showProgress]);
  const barStyle = useAnimatedStyle(() => ({ width: progress.value * BAR_WIDTH }));

  const message =
    stage === 'preparing'
      ? t('boot.preparing')
      : stage === 'waking'
        ? t('boot.waking')
        : stage === 'slow'
          ? t('boot.slow')
          : stage === 'unreachable'
            ? t('boot.unreachable')
            : null;
  const hint =
    stage === 'waking' ? t('boot.wakingHint') : stage === 'unreachable' ? t('boot.unreachableHint') : null;

  return (
    <Animated.View
      exiting={FadeOut.duration(320)}
      style={[StyleSheet.absoluteFill, { backgroundColor: tokenColor(scheme, 'background') }]}
    >
      {/* Centred exactly like the native splash image, so the hand-off does not jump. */}
      <View style={styles.center} pointerEvents='none'>
        <BootMark />
      </View>

      <View style={styles.below} className='items-center gap-5 px-8'>
        <Animated.View entering={FadeInDown.delay(150).duration(500)}>
          <Logo height={26} />
        </Animated.View>

        <View className='min-h-24 items-center gap-3' accessibilityLiveRegion='polite'>
          {message ? (
            <Animated.View key={stage} entering={FadeIn.duration(400)}>
              <View className='items-center gap-1'>
                <Text className='text-center text-base font-medium text-foreground'>{message}</Text>
                {hint ? <Text className='text-center text-sm text-muted-foreground'>{hint}</Text> : null}
              </View>
            </Animated.View>
          ) : null}

          {showProgress ? (
            <Animated.View entering={FadeIn.duration(400)} accessibilityRole='progressbar'>
              <View className='h-1 overflow-hidden rounded-full bg-muted' style={{ width: BAR_WIDTH }}>
                <Animated.View
                  style={[styles.bar, { backgroundColor: tokenColor(scheme, 'primary') }, barStyle]}
                />
              </View>
            </Animated.View>
          ) : null}
        </View>
      </View>

      {showActions ? (
        <Animated.View
          entering={FadeInDown.duration(400)}
          style={[styles.actions, { paddingBottom: insets.bottom + 24 }]}
        >
          <View className='gap-3 px-6'>
            <Button onPress={onRetry}>
              <Text>{t('common.retry')}</Text>
            </Button>
            <Button variant='outline' onPress={onQuickSplits}>
              <Text>{t('boot.quickSplits')}</Text>
            </Button>
          </View>
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  center: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Starts just under the 160dp mark centred on screen.
  below: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: '50%',
    marginTop: 104,
  },
  bar: {
    height: '100%',
    borderRadius: 999,
  },
  actions: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
  },
});
