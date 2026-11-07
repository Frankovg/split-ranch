import { createClient, type SupabaseClient, type SupportedStorage } from '@supabase/supabase-js';
import { AppState, type AppStateStatus } from 'react-native';
import { env, isSupabaseConfigured } from './env';
import { getSecureStorage } from './storage';

/**
 * Supabase client used ONLY for auth (sign-in, session refresh, sign-out).
 * All data goes through the FastAPI backend (src/lib/api); never call
 * `supabase.from(...)` or `supabase.rpc(...)` from features.
 */

const sessionStorage: SupportedStorage = {
  getItem: async (key) => (await getSecureStorage()).getString(key) ?? null,
  setItem: async (key, value) => {
    (await getSecureStorage()).set(key, value);
  },
  removeItem: async (key) => {
    (await getSecureStorage()).remove(key);
  },
};

/** Null when EXPO_PUBLIC_SUPABASE_URL / _PUBLISHABLE_KEY are not set (auth disabled). */
export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(env.supabaseUrl, env.supabasePublishableKey, {
      auth: {
        storage: sessionStorage,
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: false,
      },
    })
  : null;

/**
 * Supabase recommends driving token auto-refresh from AppState on React Native:
 * refresh only while the app is in the foreground. Returns an unsubscribe function.
 */
export function bindAuthAutoRefresh(): () => void {
  const client = supabase;
  if (!client) return () => {};
  const apply = (state: AppStateStatus) => {
    if (state === 'active') void client.auth.startAutoRefresh();
    else void client.auth.stopAutoRefresh();
  };
  apply(AppState.currentState === 'active' ? 'active' : 'background');
  const sub = AppState.addEventListener('change', apply);
  return () => sub.remove();
}
