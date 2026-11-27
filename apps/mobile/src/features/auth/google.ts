import type * as NitroGoogleSignInModule from 'react-native-nitro-google-signin';
import * as Crypto from 'expo-crypto';
import { env } from '@/lib/env';
import { supabase } from '@/lib/supabase';

/**
 * Google sign-in behind a swappable abstraction (docs/05 "Google sign-in").
 *
 * Flow: random raw nonce -> its SHA-256 (hex) goes to Credential Manager, which embeds it
 * in the ID token's `nonce` claim -> supabase.auth.signInWithIdToken({ token, nonce: raw }).
 * Supabase hashes the raw nonce and rejects the token unless it matches the claim, so a
 * leaked ID token cannot be replayed without the raw nonce, which never leaves this flow.
 *
 * The nonce is mandatory: a token without the expected claim is rejected here before it
 * reaches Supabase (Supabase itself still accepts nonce-less tokens when no nonce is sent).
 *
 * Provider: react-native-nitro-google-signin (MIT, Credential Manager on Android).
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

interface GoogleIdTokenProvider {
  /** Returns a Google ID token whose `nonce` claim is `hashedNonce`. */
  getIdToken(hashedNonce: string): Promise<string>;
  signOut(): Promise<void>;
}

type NitroGoogleSignIn = typeof NitroGoogleSignInModule;

let nitroModule: Promise<NitroGoogleSignIn> | null = null;

/**
 * Loads the library on first use. Importing it creates the native HybridObject right away,
 * so a static import would crash the whole app on a dev client built without the module;
 * loading it lazily only disables Google sign-in in that case.
 */
function loadNitroGoogleSignIn(): Promise<NitroGoogleSignIn> {
  nitroModule ??= import('react-native-nitro-google-signin').catch((error: unknown) => {
    nitroModule = null;
    throw new Error('Google sign-in native module is not available (rebuild the dev client)', {
      cause: error,
    });
  });
  return nitroModule;
}

const credentialManagerProvider: GoogleIdTokenProvider = {
  async getIdToken(hashedNonce) {
    const {
      GoogleOneTapSignIn,
      isErrorWithCode,
      isNoSavedCredentialFoundResponse,
      isSuccessResponse,
      statusCodes,
    } = await loadNitroGoogleSignIn();
    // The library only accepts the nonce through configure() (sign-in methods take no
    // arguments) and falls back to an internal random nonce it never returns. Configure on
    // every attempt so each ID token carries this attempt's nonce.
    GoogleOneTapSignIn.configure({ webClientId: env.googleWebClientId, nonce: hashedNonce });
    try {
      await GoogleOneTapSignIn.checkPlayServices();
      // Authorized accounts first, then every account on the device, then the explicit
      // "Sign in with Google" dialog (also covers a device with no Google account yet).
      let response = await GoogleOneTapSignIn.signIn();
      if (isNoSavedCredentialFoundResponse(response))
        response = await GoogleOneTapSignIn.createAccount();
      if (isNoSavedCredentialFoundResponse(response))
        response = await GoogleOneTapSignIn.presentExplicitSignIn();
      if (!isSuccessResponse(response)) throw new SignInCancelledError();
      const idToken = response.data.idToken;
      if (!idToken) throw new Error('Google did not return an ID token (check the web client id)');
      return idToken;
    } catch (error) {
      if (isErrorWithCode(error) && error.code === statusCodes.SIGN_IN_CANCELLED) {
        throw new SignInCancelledError();
      }
      if (isErrorWithCode(error) && error.code === statusCodes.DEVELOPER_ERROR) {
        throw new Error(
          `Google sign-in is misconfigured (check the web client id and the Android SHA-1 fingerprints): ${error.message}`,
          { cause: error },
        );
      }
      throw error;
    }
  },
  async signOut() {
    // Also clears the Credential Manager state so the account picker shows again.
    const { GoogleOneTapSignIn } = await loadNitroGoogleSignIn();
    await GoogleOneTapSignIn.signOut();
  },
};

const provider: GoogleIdTokenProvider = credentialManagerProvider;

async function createNonce(): Promise<{ raw: string; hashed: string }> {
  const bytes = await Crypto.getRandomBytesAsync(32);
  const raw = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  // Hex-encoded SHA-256: the format Supabase compares against the token's `nonce` claim.
  const hashed = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, raw);
  return { raw, hashed };
}

/**
 * Reads the `nonce` claim from a JWT payload without verifying the signature (Supabase
 * verifies the token). Returns undefined when the token is malformed or has no nonce.
 */
export function readIdTokenNonce(idToken: string): string | undefined {
  const payload = idToken.split('.')[1];
  if (!payload) return undefined;
  try {
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const claims: unknown = JSON.parse(atob(padded));
    if (typeof claims !== 'object' || claims === null || !('nonce' in claims)) return undefined;
    return typeof claims.nonce === 'string' ? claims.nonce : undefined;
  } catch {
    return undefined;
  }
}

export function isGoogleSignInAvailable(): boolean {
  return supabase !== null && env.googleWebClientId !== '';
}

// One sign-in at a time: configure() is global native state, so a concurrent attempt
// (e.g. a double tap) would overwrite the nonce of the one already in progress.
let inFlight: Promise<void> | null = null;

/** Sign in with Google and create the Supabase session. Throws SignInCancelledError on cancel. */
export function signInWithGoogle(): Promise<void> {
  if (!inFlight) {
    inFlight = runSignIn().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

async function runSignIn(): Promise<void> {
  const client = supabase;
  if (!client || env.googleWebClientId === '') throw new AuthNotConfiguredError();

  const nonce = await createNonce();
  const idToken = await provider.getIdToken(nonce.hashed);
  if (readIdTokenNonce(idToken) !== nonce.hashed) {
    // Fail closed: never send a token that is not bound to this attempt's nonce.
    throw new Error('Google ID token does not carry the expected nonce');
  }
  const { error } = await client.auth.signInWithIdToken({
    provider: 'google',
    token: idToken,
    nonce: nonce.raw,
  });
  if (error) throw error;
}

/**
 * Sign out of Supabase and of the Google library so the account picker shows again.
 * `local` clears only this device without depending on the server (e.g. a deleted account).
 */
export async function signOut(scope: 'global' | 'local' = 'global'): Promise<void> {
  await supabase?.auth.signOut({ scope });
  try {
    await provider.signOut();
  } catch (error) {
    console.warn('Google sign-out failed', error);
  }
}
