import { createHash } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type Response = { type: 'success' | 'noSavedCredentialFound' | 'cancelled'; data: { idToken: string } | null };

const configure = vi.fn();
const checkPlayServices = vi.fn<() => Promise<void>>();
const nativeSignIn = vi.fn<() => Promise<Response>>();
const createAccount = vi.fn<() => Promise<Response>>();
const presentExplicitSignIn = vi.fn<() => Promise<Response>>();
const nativeSignOut = vi.fn<() => Promise<void>>();
const signInWithIdToken = vi.fn();
const env = { googleWebClientId: 'web-client-id' };

vi.mock('react-native-nitro-google-signin', () => ({
  GoogleOneTapSignIn: {
    configure,
    checkPlayServices,
    signIn: nativeSignIn,
    createAccount,
    presentExplicitSignIn,
    signOut: nativeSignOut,
  },
  isSuccessResponse: (r: Response) => r.type === 'success' && r.data !== null,
  isNoSavedCredentialFoundResponse: (r: Response) => r.type === 'noSavedCredentialFound',
  isErrorWithCode: (e: unknown) => typeof e === 'object' && e !== null && 'code' in e,
  statusCodes: { SIGN_IN_CANCELLED: 'SIGN_IN_CANCELLED', DEVELOPER_ERROR: 'DEVELOPER_ERROR' },
}));
vi.mock('expo-crypto', () => ({
  CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
  getRandomBytesAsync: async (n: number) => new Uint8Array(n).fill(7),
  digestStringAsync: async (_alg: string, data: string) => createHash('sha256').update(data).digest('hex'),
}));
vi.mock('@/lib/env', () => ({ env }));
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { signInWithIdToken, signOut: vi.fn() } } }));

const { readIdTokenNonce, signInWithGoogle, SignInCancelledError, AuthNotConfiguredError } = await import('./google');

const RAW_NONCE = '07'.repeat(32);
const HASHED_NONCE = createHash('sha256').update(RAW_NONCE).digest('hex');

function fakeIdToken(claims: Record<string, unknown>): string {
  const part = (value: object) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${part({ alg: 'RS256' })}.${part(claims)}.signature`;
}

const success = (claims: Record<string, unknown> = { nonce: HASHED_NONCE }): Response => ({
  type: 'success',
  data: { idToken: fakeIdToken(claims) },
});
const noCredential: Response = { type: 'noSavedCredentialFound', data: null };

beforeEach(() => {
  vi.clearAllMocks();
  env.googleWebClientId = 'web-client-id';
  checkPlayServices.mockResolvedValue();
  signInWithIdToken.mockResolvedValue({ error: null });
});

describe('readIdTokenNonce', () => {
  it('reads the nonce claim and ignores malformed tokens', () => {
    expect(readIdTokenNonce(fakeIdToken({ nonce: 'abc' }))).toBe('abc');
    expect(readIdTokenNonce(fakeIdToken({ sub: '1' }))).toBeUndefined();
    expect(readIdTokenNonce('not-a-jwt')).toBeUndefined();
    expect(readIdTokenNonce('a.%%%.c')).toBeUndefined();
  });
});

describe('signInWithGoogle', () => {
  it('puts the hashed nonce in the ID token request and sends the raw nonce to Supabase', async () => {
    const response = success();
    nativeSignIn.mockResolvedValue(response);

    await signInWithGoogle();

    expect(configure).toHaveBeenCalledWith({ webClientId: 'web-client-id', nonce: HASHED_NONCE });
    expect(signInWithIdToken).toHaveBeenCalledWith({
      provider: 'google',
      token: response.data?.idToken,
      nonce: RAW_NONCE,
    });
  });

  it('falls back to createAccount and then the explicit sign-in dialog', async () => {
    nativeSignIn.mockResolvedValue(noCredential);
    createAccount.mockResolvedValue(noCredential);
    presentExplicitSignIn.mockResolvedValue(success());

    await signInWithGoogle();

    expect(createAccount).toHaveBeenCalledOnce();
    expect(presentExplicitSignIn).toHaveBeenCalledOnce();
    expect(signInWithIdToken).toHaveBeenCalledOnce();
  });

  it('maps a cancelled picker to SignInCancelledError without calling Supabase', async () => {
    nativeSignIn.mockResolvedValue({ type: 'cancelled', data: null });

    await expect(signInWithGoogle()).rejects.toBeInstanceOf(SignInCancelledError);
    expect(signInWithIdToken).not.toHaveBeenCalled();
  });

  it.each([
    ['a different nonce', { nonce: 'other' }],
    ['no nonce', { sub: '1' }],
  ])('rejects an ID token with %s before it reaches Supabase', async (_label, claims) => {
    nativeSignIn.mockResolvedValue(success(claims));

    await expect(signInWithGoogle()).rejects.toThrow('expected nonce');
    expect(signInWithIdToken).not.toHaveBeenCalled();
  });

  it('runs a single flow for concurrent calls so the nonce is not overwritten', async () => {
    nativeSignIn.mockResolvedValue(success());

    const first = signInWithGoogle();
    const second = signInWithGoogle();
    expect(second).toBe(first);
    await Promise.all([first, second]);

    expect(configure).toHaveBeenCalledOnce();
    expect(signInWithIdToken).toHaveBeenCalledOnce();

    // A later attempt starts a new flow with its own nonce.
    await signInWithGoogle();
    expect(configure).toHaveBeenCalledTimes(2);
  });

  it('throws AuthNotConfiguredError without a web client id', async () => {
    env.googleWebClientId = '';

    await expect(signInWithGoogle()).rejects.toBeInstanceOf(AuthNotConfiguredError);
    expect(configure).not.toHaveBeenCalled();
  });
});
