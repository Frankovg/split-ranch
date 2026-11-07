import { env, isApiConfigured } from '@/lib/env';
import { supabase } from '@/lib/supabase';

/**
 * Minimal fetch client for the FastAPI backend. Attaches the Supabase access token
 * and, on 401, refreshes the session once and retries.
 * TODO: replace the untyped surface with packages/api-client (openapi-fetch +
 * generated types) once the API publishes its OpenAPI document.
 */

const API_PREFIX = '/v1';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API request failed with status ${status}`);
    this.name = 'ApiError';
  }
}

/** Machine-readable `code` of an API problem+json error (e.g. "period_locked"), if any. */
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

function withAuth(init: RequestInit, token: string | null): RequestInit {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body !== undefined && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');
  return { ...init, headers };
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (text === '') return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/** Low-level request: returns the Response after the one-time 401 refresh+retry. */
export async function apiRequest(
  path: string,
  init: RequestInit = {},
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  if (!isApiConfigured) throw new ApiNotConfiguredError();
  // EXPO_PUBLIC_API_URL is the host only; the API version prefix belongs to the client.
  const url = `${env.apiUrl}${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`;
  const res = await fetchImpl(url, withAuth(init, await currentAccessToken()));
  if (res.status !== 401) return res;

  const token = await refreshedAccessToken();
  if (!token) return res;
  return fetchImpl(url, withAuth(init, token));
}

/** JSON request helper: throws ApiError for non-2xx responses. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiRequest(path, init);
  const body = await parseBody(res);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}
