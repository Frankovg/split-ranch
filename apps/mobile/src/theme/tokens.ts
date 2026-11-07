/**
 * JS mirror of the CSS variables in global.css, for places that cannot use
 * className (React Navigation theme, status bar, icon colours passed as props).
 * Values are raw HSL components exactly as in global.css; tokens.test.ts keeps them in sync.
 */
export const TOKENS = {
  light: {
    background: '30 33% 99%',
    foreground: '20 14% 10%',
    card: '0 0% 100%',
    'card-foreground': '20 14% 10%',
    popover: '0 0% 100%',
    'popover-foreground': '20 14% 10%',
    primary: '14 63% 42%',
    'primary-foreground': '30 40% 98%',
    secondary: '30 20% 93%',
    'secondary-foreground': '20 14% 15%',
    muted: '30 15% 94%',
    'muted-foreground': '20 8% 38%',
    accent: '25 40% 91%',
    'accent-foreground': '20 14% 15%',
    destructive: '0 72% 45%',
    'destructive-foreground': '0 0% 98%',
    border: '30 12% 86%',
    input: '30 12% 78%',
    ring: '14 63% 42%',
    positive: '142 64% 28%',
    'positive-foreground': '0 0% 98%',
    negative: '16 85% 40%',
    'negative-foreground': '0 0% 98%',
    warning: '38 92% 33%',
    'warning-foreground': '0 0% 98%',
    'chart-1': '202 100% 35%',
    'chart-2': '41 100% 45%',
    'chart-3': '164 100% 31%',
    'chart-4': '26 100% 42%',
    'chart-5': '202 77% 63%',
    'chart-6': '327 45% 64%',
  },
  dark: {
    background: '20 14% 7%',
    foreground: '30 20% 95%',
    card: '20 12% 10%',
    'card-foreground': '30 20% 95%',
    popover: '20 12% 10%',
    'popover-foreground': '30 20% 95%',
    primary: '16 70% 62%',
    'primary-foreground': '20 14% 8%',
    secondary: '20 10% 18%',
    'secondary-foreground': '30 20% 95%',
    muted: '20 10% 16%',
    'muted-foreground': '30 8% 66%',
    accent: '20 12% 20%',
    'accent-foreground': '30 20% 95%',
    destructive: '0 75% 62%',
    'destructive-foreground': '20 14% 8%',
    border: '20 10% 22%',
    input: '20 10% 28%',
    ring: '16 70% 62%',
    positive: '142 55% 55%',
    'positive-foreground': '20 14% 8%',
    negative: '16 90% 63%',
    'negative-foreground': '20 14% 8%',
    warning: '40 95% 58%',
    'warning-foreground': '20 14% 8%',
    'chart-1': '202 80% 60%',
    'chart-2': '41 100% 55%',
    'chart-3': '164 70% 45%',
    'chart-4': '26 100% 58%',
    'chart-5': '202 77% 72%',
    'chart-6': '327 50% 72%',
  },
} as const;

export type ColorScheme = keyof typeof TOKENS;
export type TokenName = keyof (typeof TOKENS)['light'];

/** Resolve a token to a CSS colour string usable in style props, e.g. "hsl(14 63% 42%)". */
export function tokenColor(scheme: ColorScheme, name: TokenName): string {
  const [h, s, l] = TOKENS[scheme][name].split(' ');
  return `hsl(${h}, ${s}, ${l})`;
}
