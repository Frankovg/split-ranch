import type { Session } from '@supabase/supabase-js';
import { create } from 'zustand';

export type AuthStatus = 'loading' | 'signedIn' | 'signedOut';

interface SessionState {
  status: AuthStatus;
  session: Session | null;
  setSession: (session: Session | null) => void;
}

/** Auth status mirrored from supabase.auth.onAuthStateChange (see src/features/auth/AuthListener). */
export const useSessionStore = create<SessionState>()((set) => ({
  status: 'loading',
  session: null,
  setSession: (session) => set({ session, status: session ? 'signedIn' : 'signedOut' }),
}));
