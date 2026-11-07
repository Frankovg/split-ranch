import { describe, expect, it, vi } from 'vitest';

const getSession = vi.fn();
const refreshSession = vi.fn();

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession, refreshSession } } }));
vi.mock('@/lib/env', () => ({ env: { apiUrl: 'https://api.test' }, isApiConfigured: true }));

const { apiErrorCode, ApiError, apiRequest } = await import('./client');

describe('apiErrorCode', () => {
  it('reads the problem+json code and ignores anything else', () => {
    expect(apiErrorCode(new ApiError(409, { code: 'period_locked' }))).toBe('period_locked');
    expect(apiErrorCode(new ApiError(500, 'oops'))).toBeUndefined();
    expect(apiErrorCode(new Error('network'))).toBeUndefined();
  });
});

function authHeader(init: RequestInit | undefined): string | null {
  return new Headers(init?.headers).get('Authorization');
}

describe('apiRequest', () => {
  it('attaches the access token and retries once after refreshing on 401', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'old' } } });
    refreshSession.mockResolvedValue({ data: { session: { access_token: 'new' } }, error: null });
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));

    const res = await apiRequest('/me', {}, fetchImpl);

    expect(res.status).toBe(200);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe('https://api.test/v1/me');
    expect(authHeader(fetchImpl.mock.calls[0]?.[1])).toBe('Bearer old');
    expect(authHeader(fetchImpl.mock.calls[1]?.[1])).toBe('Bearer new');
  });

  it('does not retry when the refresh fails', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'old' } } });
    refreshSession.mockResolvedValue({ data: { session: null }, error: new Error('expired') });
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));

    const res = await apiRequest('me', {}, fetchImpl);

    expect(res.status).toBe(401);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
