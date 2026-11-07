/**
 * Public build-time configuration. EXPO_PUBLIC_* values are inlined into the bundle,
 * so they must never contain secrets. Missing values leave the related feature disabled.
 */
export const env = {
  supabaseUrl: process.env.EXPO_PUBLIC_SUPABASE_URL ?? '',
  supabasePublishableKey: process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '',
  googleWebClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ?? '',
  apiUrl: (process.env.EXPO_PUBLIC_API_URL ?? '').replace(/\/+$/, ''),
} as const;

export const isSupabaseConfigured = env.supabaseUrl !== '' && env.supabasePublishableKey !== '';
export const isApiConfigured = env.apiUrl !== '';
