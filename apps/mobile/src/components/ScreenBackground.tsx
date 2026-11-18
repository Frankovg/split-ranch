import { useId } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { tokenColor } from '@/theme/tokens';
import { useAppColorScheme } from '@/theme/ThemeSync';

/**
 * Brand backdrop: a diagonal gradient (surface → background → accent), the static
 * version of the portfolio's animated page background. Render it first inside a
 * container whose own background is the page background.
 */
export function ScreenBackground() {
  const scheme = useAppColorScheme();
  // Unique per instance so gradients of stacked screens never resolve to each other.
  const id = `screen-bg-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  return (
    <View pointerEvents='none' style={StyleSheet.absoluteFill}>
      <Svg width='100%' height='100%'>
        <Defs>
          <LinearGradient id={id} x1='0' y1='0' x2='1' y2='1'>
            <Stop offset='0' stopColor={tokenColor(scheme, 'card')} stopOpacity={scheme === 'dark' ? 1 : 0} />
            <Stop offset='0.5' stopColor={tokenColor(scheme, 'background')} />
            <Stop offset='1' stopColor={tokenColor(scheme, 'accent')} />
          </LinearGradient>
        </Defs>
        <Rect width='100%' height='100%' fill={`url(#${id})`} />
      </Svg>
    </View>
  );
}
