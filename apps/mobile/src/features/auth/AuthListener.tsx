import * as React from 'react';
import { queryClient } from '@/lib/query/client';
import { bindAuthAutoRefresh, supabase } from '@/lib/supabase';
import { useSessionStore } from '@/stores/session';

/**
 * Mirrors the Supabase auth state into the session store and binds token
 * auto-refresh to AppState. When auth is not configured the app runs signed out
 * (Quick splits still work).
 */
export function AuthListener() {
  const setSession = useSessionStore((s) => s.setSession);

  React.useEffect(() => {
    const client = supabase;
    if (!client) {
      setSession(null);
      return;
    }
    let active = true;
    client.auth
      .getSession()
      .then(({ data }) => {
        if (active) setSession(data.session);
      })
      .catch((error: unknown) => {
        console.warn('Failed to restore the auth session', error);
        if (active) setSession(null);
      });

    const { data } = client.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT') queryClient.clear();
      setSession(session);
    });
    const unbindRefresh = bindAuthAutoRefresh();
    return () => {
      active = false;
      data.subscription.unsubscribe();
      unbindRefresh();
    };
  }, [setSession]);

  return null;
}
