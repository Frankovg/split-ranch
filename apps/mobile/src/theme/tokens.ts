/**
 * JS mirror of the CSS variables in global.css, for places that cannot use
 * className (React Navigation theme, status bar, icon colours passed as props).
 * Values are raw HSL components exactly as in global.css; tokens.test.ts keeps them in sync.
 */
export const TOKENS = {
  light: {
    background: '150 14% 97%',
    foreground: '0 0% 9%',
    card: '0 0% 100%',
    'card-foreground': '0 0% 9%',
    popover: '0 0% 100%',
    'popover-foreground': '0 0% 9%',
    primary: '163 70% 30%',
    'primary-foreground': '0 0% 100%',
    secondary: '160 10% 92%',
    'secondary-foreground': '0 0% 9%',
    muted: '160 10% 93%',
    'muted-foreground': '0 0% 38%',
    accent: '162 45% 90%',
    'accent-foreground': '163 45% 13%',
    destructive: '8 90% 45%',
    'destructive-foreground': '0 0% 100%',
    border: '160 10% 86%',
    input: '0 0% 70%',
    ring: '163 70% 30%',
    positive: '163 70% 28%',
    'positive-foreground': '0 0% 100%',
    negative: '317 60% 42%',
    'negative-foreground': '0 0% 100%',
    warning: '45 95% 35%',
    'warning-foreground': '0 0% 100%',
    'chart-1': '202 100% 35%',
    'chart-2': '41 100% 45%',
    'chart-3': '163 70% 30%',
    'chart-4': '26 100% 42%',
    'chart-5': '202 77% 63%',
    'chart-6': '317 55% 50%',
  },
  dark: {
    background: '0 0% 7%',
    foreground: '0 0% 95%',
    card: '0 0% 14%',
    'card-foreground': '0 0% 95%',
    popover: '0 0% 14%',
    'popover-foreground': '0 0% 95%',
    primary: '162 80% 65%',
    'primary-foreground': '0 0% 14%',
    secondary: '0 0% 18%',
    'secondary-foreground': '0 0% 95%',
    muted: '0 0% 15%',
    'muted-foreground': '0 0% 72%',
    accent: '163 45% 13%',
    'accent-foreground': '0 0% 95%',
    destructive: '8 100% 50%',
    'destructive-foreground': '0 0% 100%',
    border: '163 45% 13%',
    input: '0 0% 45%',
    ring: '162 80% 65%',
    positive: '162 80% 65%',
    'positive-foreground': '0 0% 14%',
    negative: '317 73% 61%',
    'negative-foreground': '0 0% 7%',
    warning: '57 91% 56%',
    'warning-foreground': '0 0% 7%',
    'chart-1': '202 80% 60%',
    'chart-2': '41 100% 55%',
    'chart-3': '162 80% 65%',
    'chart-4': '26 100% 58%',
    'chart-5': '202 77% 72%',
    'chart-6': '317 73% 61%',
  },
} as const;

export type ColorScheme = keyof typeof TOKENS;
export type TokenName = keyof (typeof TOKENS)['light'];

/** Resolve a token to a CSS colour string usable in style props, e.g. "hsl(14 63% 42%)". */
export function tokenColor(scheme: ColorScheme, name: TokenName, alpha?: number): string {
  const [h, s, l] = TOKENS[scheme][name].split(' ');
  return alpha === undefined ? `hsl(${h}, ${s}, ${l})` : `hsla(${h}, ${s}, ${l}, ${alpha})`;
}
