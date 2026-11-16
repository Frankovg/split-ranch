import { createApiClient } from '@split-ranch/api-client';
import { env, isApiConfigured } from '@/lib/env';
import { supabase } from '@/lib/supabase';

/**
 * Typed client for the FastAPI backend (openapi-fetch over the types generated in
 * packages/api-client). Auth lives in `authFetch`, passed to the client as its `fetch`:
 * it attaches the Supabase access token and, on 401, refreshes the session once and
 * re-sends a copy of the request (a Request body can only be read once, so the copy is
 * taken before the first send).
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API request failed with status ${status}`);
    this.name = 'ApiError';
  }
}

/** Machine-readable `code` of an API problem+json error (e.g. "member_has_open_balance"), if any. */
export function apiErrorCode(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || typeof error.body !== 'object' || error.body === null) return undefined;
  const code = (error.body as { code?: unknown }).code;
  return typeof code === 'string' ? code : undefined;
}

export class ApiNotConfiguredError extends Error {
  constructor() {
    super('EXPO_PUBLIC_API_URL is not set');
    this.name = 'ApiNotConfiguredError';
  }
}

async function currentAccessToken(): Promise<string | null> {
  // getSession() returns the stored session and refreshes it when close to expiry.
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } };
  return data.session?.access_token ?? null;
}

async function refreshedAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.auth.refreshSession();
  if (error) return null; // failed refresh: onAuthStateChange signs the user out
  return data.session?.access_token ?? null;
}

function withToken(request: Request, token: string | null): Request {
  if (!token) return request;
  const headers = new Headers(request.headers);
  headers.set('Authorization', `Bearer ${token}`);
  return new Request(request, { headers });
}

/** `fetch` for the API client: token on every request, one refresh+retry on 401. */
export async function authFetch(request: Request, fetchImpl: typeof fetch = fetch): Promise<Response> {
  if (!isApiConfigured) throw new ApiNotConfiguredError();
  const retry = request.clone();
  const res = await fetchImpl(withToken(request, await currentAccessToken()));
  if (res.status !== 401) return res;

  const token = await refreshedAccessToken();
  if (!token) return res;
  return fetchImpl(withToken(retry, token));
}

/** Paths already include the `/v1` prefix, so the base URL is the API host only. */
export const api = createApiClient({
  baseUrl: env.apiUrl,
  fetch: (request) => authFetch(request),
  headers: { Accept: 'application/json' },
});

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/**
 * Awaits an `api.GET/POST/...` call and returns its data, throwing ApiError (with the
 * problem+json body) for non-2xx responses so React Query sees a failed query/mutation.
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, error ?? null);
  return data as T;
}
