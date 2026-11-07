import { GoogleSignin, isErrorWithCode, statusCodes } from '@react-native-google-signin/google-signin';
import * as Crypto from 'expo-crypto';
import { env } from '@/lib/env';
import { supabase } from '@/lib/supabase';

/**
 * Google sign-in behind a swappable abstraction (docs/05 "Google sign-in").
 *
 * Flow: random nonce -> SHA-256 passed to the Google library -> Google ID token ->
 * supabase.auth.signInWithIdToken({ provider: 'google', token, nonce: rawNonce }).
 *
 * TODO(T-0.4 Credential Manager spike): the current provider uses the FREE
 * `GoogleSignin` API of @react-native-google-signin/google-signin, which still wraps
 * the deprecated legacy Google Sign-In SDK on Android and cannot embed a nonce in
 * the ID token. Replace `legacyProvider` with the Universal Sign-In API (paid) or a
 * free Credential-Manager library; both accept the hashed nonce, and then
 * `nonceApplied` becomes true so Supabase verifies it.
 */

export class AuthNotConfiguredError extends Error {
  constructor() {
    super('Supabase or Google client id is not configured');
    this.name = 'AuthNotConfiguredError';
  }
}

export class SignInCancelledError extends Error {
  constructor() {
    super('Google sign-in was cancelled');
    this.name = 'SignInCancelledError';
  }
}

interface GoogleIdTokenResult {
  idToken: string;
  /** True when the provider embedded the hashed nonce in the ID token. */
  nonceApplied: boolean;
}

interface GoogleIdTokenProvider {
  getIdToken(hashedNonce: string): Promise<GoogleIdTokenResult>;
  signOut(): Promise<void>;
}

let configured = false;

const legacyProvider: GoogleIdTokenProvider = {
  async getIdToken() {
    if (!configured) {
      GoogleSignin.configure({ webClientId: env.googleWebClientId });
      configured = true;
    }
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    try {
      const response = await GoogleSignin.signIn();
      if (response.type !== 'success') throw new SignInCancelledError();
      const idToken = response.data.idToken;
      if (!idToken) throw new Error('Google did not return an ID token (check the web client id)');
      // The legacy API has no nonce parameter.
      return { idToken, nonceApplied: false };
    } catch (error) {
      if (isErrorWithCode(error) && error.code === statusCodes.SIGN_IN_CANCELLED) {
        throw new SignInCancelledError();
      }
      throw error;
    }
  },
  async signOut() {
    if (configured) await GoogleSignin.signOut();
  },
};

const provider: GoogleIdTokenProvider = legacyProvider;

async function createNonce(): Promise<{ raw: string; hashed: string }> {
  const bytes = await Crypto.getRandomBytesAsync(32);
  const raw = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  const hashed = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, raw);
  return { raw, hashed };
}

export function isGoogleSignInAvailable(): boolean {
  return supabase !== null && env.googleWebClientId !== '';
}

/** Sign in with Google and create the Supabase session. Throws SignInCancelledError on cancel. */
export async function signInWithGoogle(): Promise<void> {
  const client = supabase;
  if (!client || env.googleWebClientId === '') throw new AuthNotConfiguredError();

  const nonce = await createNonce();
  const { idToken, nonceApplied } = await provider.getIdToken(nonce.hashed);
  const { error } = await client.auth.signInWithIdToken({
    provider: 'google',
    token: idToken,
    ...(nonceApplied ? { nonce: nonce.raw } : {}),
  });
  if (error) throw error;
}

/** Sign out of Supabase and of the Google library so the account picker shows again. */
export async function signOut(): Promise<void> {
  await supabase?.auth.signOut();
  try {
    await provider.signOut();
  } catch (error) {
    console.warn('Google sign-out failed', error);
  }
}
