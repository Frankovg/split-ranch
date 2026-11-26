import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedProps,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Line, Path, Polygon, Polyline, Rect } from 'react-native-svg';
import { Text } from '@/components/ui/text';

/**
 * The app icon drawn as in the native splash (assets/splash-icon.png: the house of
 * assets/icon-source.svg in brand green on the page background), animated:
 * - the house breathes,
 * - the "$" under the roof flips like a coin,
 * - the six windows light up one after another, like keys being tapped,
 * - coins rise from the chimney like smoke.
 *
 * Shapes use the 1024-unit grid of icon-source.svg and are drawn at `size`, so with
 * `size` = the splash `imageWidth` (app.config.ts) the hand-off from the native splash
 * is seamless. With reduced motion the mark is static.
 */

/** Native splash colour of the house (app.config.ts adaptive icon / splash-icon.png). */
const BRAND = '#178264';
const SPLASH_SIZE = 160;

const AnimatedRect = Animated.createAnimatedComponent(Rect);

const WINDOW_W = 91.3;
const WINDOW_H = 71.5;
const WINDOWS = [
  { x: 308.5, y: 617.9 },
  { x: 465.8, y: 617.9 },
  { x: 624.2, y: 617.9 },
  { x: 308.5, y: 716.9 },
  { x: 465.8, y: 716.9 },
  { x: 624.2, y: 716.9 },
];
/** Tap order across the keypad: a short "calculating" rhythm rather than a plain sweep. */
const WINDOW_ORDER = [0, 4, 2, 3, 1, 5];
const WINDOW_STEP_MS = 160;
const WINDOW_CYCLE_MS = WINDOW_STEP_MS * WINDOWS.length + 900;

const DOLLAR =
  'M589.658 344.465 L538.708 352.545 C536.151 346.062 533.846 341.566 531.791 339.055 C529.737 336.544 526.335 334.01 521.587 331.453 L521.587 371.035 C549.345 378.431 567.881 386.238 577.194 394.456 C589.521 405.504 595.684 419.52 595.684 436.504 C595.684 446.456 593.47 455.587 589.042 463.896 C584.613 472.205 578.952 479.145 572.058 484.715 C565.164 490.284 557.837 494.325 550.076 496.836 C542.314 499.347 532.818 500.831 521.587 501.287 L521.587 527.173 L501.591 527.173 L501.591 501.287 C488.168 500.1 477.28 497.932 468.925 494.781 C460.57 491.631 453.357 487.271 447.285 481.701 C441.213 476.132 436.533 470.128 433.246 463.691 C429.959 457.254 427.494 449.469 425.85 440.339 L481.183 433.901 C482.827 442.941 485.041 449.469 487.826 453.487 C490.611 457.505 495.199 461.066 501.591 464.17 L501.591 415.822 C483.146 410.709 470.067 406.281 462.351 402.537 C454.635 398.793 447.947 392.79 442.286 384.526 C436.625 376.263 433.794 366.196 433.794 354.326 C433.794 338.073 439.478 324.491 450.846 313.579 C462.214 302.668 479.129 296.619 501.591 295.432 L501.591 281.873 L521.587 281.873 L521.587 295.432 C542.041 296.71 557.677 301.55 568.497 309.95 C579.317 318.35 586.371 329.855 589.658 344.465 Z M501.591 330.768 C495.747 332.686 491.684 335.06 489.401 337.89 C487.118 340.721 485.977 344.054 485.977 347.889 C485.977 351.906 487.141 355.399 489.47 358.366 C491.798 361.334 495.838 363.822 501.591 365.831 Z M521.587 465.54 C529.349 463.805 535.033 460.952 538.639 456.98 C542.246 453.008 544.049 448.556 544.049 443.626 C544.049 439.334 542.52 435.385 539.461 431.778 C536.402 428.172 530.444 424.816 521.587 421.712 Z';

/** Chimney top centre in the 1024 grid: where the coins start. */
const CHIMNEY = { x: 732, y: 200 };
const COIN_SIZE = 18;
const COIN_RISE_MS = 1_800;
const COINS = [
  { delay: 0, drift: -10 },
  { delay: 600, drift: 8 },
  { delay: 1_200, drift: -4 },
];

function Window({ index, reduceMotion }: { index: number; reduceMotion: boolean }) {
  const lit = useSharedValue(0);
  useEffect(() => {
    if (reduceMotion) return;
    const step = WINDOW_ORDER.indexOf(index);
    lit.value = withDelay(
      step * WINDOW_STEP_MS,
      withRepeat(
        withSequence(
          withTiming(1, { duration: 120 }),
          withTiming(0, { duration: 260 }),
          withTiming(0, { duration: WINDOW_CYCLE_MS - 380 }),
        ),
        -1,
      ),
    );
  }, [index, lit, reduceMotion]);
  const animatedProps = useAnimatedProps(() => ({ opacity: 1 - lit.value * 0.65 }));
  const window = WINDOWS[index] ?? { x: 0, y: 0 };
  return (
    <AnimatedRect
      x={window.x}
      y={window.y}
      width={WINDOW_W}
      height={WINDOW_H}
      rx={14}
      fill={BRAND}
      animatedProps={animatedProps}
    />
  );
}

function Coin({ delay, drift, scale }: { delay: number; drift: number; scale: number }) {
  const progress = useSharedValue(0);
  useEffect(() => {
    progress.value = withDelay(
      delay,
      withRepeat(withTiming(1, { duration: COIN_RISE_MS, easing: Easing.out(Easing.quad) }), -1),
    );
  }, [delay, progress]);
  const style = useAnimatedStyle(() => {
    const p = progress.value;
    return {
      opacity: p < 0.15 ? p / 0.15 : 1 - (p - 0.15) / 0.85,
      transform: [
        { translateY: -p * 70 * scale },
        { translateX: Math.sin(p * Math.PI) * drift * scale },
        { scale: 0.6 + p * 0.5 },
      ],
    };
  });
  const size = COIN_SIZE * scale;
  return (
    <Animated.View
      style={[
        styles.coin,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          left: (CHIMNEY.x / 1024) * SPLASH_SIZE * scale - size / 2,
          top: (CHIMNEY.y / 1024) * SPLASH_SIZE * scale - size / 2,
        },
        style,
      ]}
    >
      <Text style={[styles.coinText, { fontSize: size * 0.62, lineHeight: size * 0.9 }]}>$</Text>
    </Animated.View>
  );
}

export function BootMark({ size = SPLASH_SIZE }: { size?: number }) {
  const reduceMotion = useReducedMotion();
  const breath = useSharedValue(1);
  const flip = useSharedValue(0);

  useEffect(() => {
    if (reduceMotion) return;
    breath.value = withRepeat(
      withTiming(1.035, { duration: 1_400, easing: Easing.inOut(Easing.sin) }),
      -1,
      true,
    );
    flip.value = withDelay(
      500,
      withRepeat(
        withSequence(
          withTiming(360, { duration: 700, easing: Easing.inOut(Easing.cubic) }),
          withDelay(1_700, withTiming(0, { duration: 0 })),
        ),
        -1,
      ),
    );
  }, [breath, flip, reduceMotion]);

  const houseStyle = useAnimatedStyle(() => ({ transform: [{ scale: breath.value }] }));
  // The "$" is centred horizontally in the grid, so flipping the full-size layer around
  // its own centre turns the glyph in place.
  const dollarStyle = useAnimatedStyle(() => ({
    transform: [{ perspective: 600 }, { rotateY: `${flip.value}deg` }],
  }));
  const scale = size / SPLASH_SIZE;

  return (
    <View
      style={{ width: size, height: size }}
      accessibilityRole='image'
      accessibilityLabel='Splitranch'
    >
      {reduceMotion
        ? null
        : COINS.map((coin) => <Coin key={coin.delay} {...coin} scale={scale} />)}
      <Animated.View style={[StyleSheet.absoluteFill, houseStyle]}>
        <Svg width={size} height={size} viewBox='0 0 1024 1024'>
          <Polygon
            points='677,209.8 787,209.8 787,381.4 677,308.8'
            fill={BRAND}
            stroke={BRAND}
            strokeWidth={22}
            strokeLinejoin='round'
          />
          <Path
            d='M205.1 383.6 L205.1 757.6 C205.1 814.067 233.333 842.3 289.8 842.3 L734.2 842.3 C790.667 842.3 818.9 814.067 818.9 757.6 L818.9 383.6'
            fill='none'
            stroke={BRAND}
            strokeWidth={46}
          />
          <Polyline
            points='157.8,433.1 512,196.6 866.2,433.1'
            fill='none'
            stroke={BRAND}
            strokeWidth={68}
            strokeLinecap='round'
            strokeLinejoin='round'
          />
          <Line x1={205.1} y1={562.9} x2={818.9} y2={562.9} stroke={BRAND} strokeWidth={36} />
          {WINDOWS.map((_, index) => (
            <Window key={index} index={index} reduceMotion={reduceMotion} />
          ))}
        </Svg>
        <Animated.View style={[StyleSheet.absoluteFill, dollarStyle]}>
          <Svg width={size} height={size} viewBox='0 0 1024 1024'>
            <Path d={DOLLAR} fill={BRAND} />
          </Svg>
        </Animated.View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  coin: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: BRAND,
    backgroundColor: '#E3F2EC',
  },
  coinText: {
    color: BRAND,
    fontWeight: '700',
    textAlign: 'center',
    includeFontPadding: false,
  },
});
