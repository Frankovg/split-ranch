import { describe, expect, it, vi } from 'vitest';

const getSession = vi.fn();
const refreshSession = vi.fn();
const apiConfig = vi.hoisted(() => ({ isApiConfigured: true }));

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession, refreshSession } } }));
vi.mock('@/lib/env', () => ({
  env: { apiUrl: 'https://api.test' },
  get isApiConfigured() {
    return apiConfig.isApiConfigured;
  },
}));

const { api, apiErrorCode, ApiError, ApiNotConfiguredError, authFetch, unwrap } = await import('./client');

describe('apiErrorCode', () => {
  it('reads the problem+json code and ignores anything else', () => {
    expect(apiErrorCode(new ApiError(409, { code: 'member_has_open_balance' }))).toBe('member_has_open_balance');
    expect(apiErrorCode(new ApiError(500, 'oops'))).toBeUndefined();
    expect(apiErrorCode(new Error('network'))).toBeUndefined();
  });
});

describe('authFetch', () => {
  it('attaches the access token and retries once, with the same body, after refreshing on 401', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'old' } } });
    refreshSession.mockResolvedValue({ data: { session: { access_token: 'new' } }, error: null });
    const fetchImpl = vi
      .fn<(request: Request) => Promise<Response>>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
    const request = new Request('https://api.test/v1/groups', { method: 'POST', body: '{"name":"Piso"}' });

    const res = await authFetch(request, fetchImpl as typeof fetch);

    expect(res.status).toBe(200);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    const [first, second] = fetchImpl.mock.calls.map(([r]) => r);
    expect(first?.url).toBe('https://api.test/v1/groups');
    expect(first?.headers.get('Authorization')).toBe('Bearer old');
    expect(second?.headers.get('Authorization')).toBe('Bearer new');
    expect(await second?.text()).toBe('{"name":"Piso"}');
  });

  it('does not retry when the refresh fails', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'old' } } });
    refreshSession.mockResolvedValue({ data: { session: null }, error: new Error('expired') });
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));

    const res = await authFetch(new Request('https://api.test/v1/me'), fetchImpl);

    expect(res.status).toBe(401);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('fails without a request when the API URL is not configured', async () => {
    apiConfig.isApiConfigured = false;
    const fetchImpl = vi.fn<typeof fetch>();
    try {
      await expect(authFetch(new Request('https://api.test/v1/me'), fetchImpl)).rejects.toBeInstanceOf(
        ApiNotConfiguredError,
      );
      expect(fetchImpl).not.toHaveBeenCalled();
    } finally {
      apiConfig.isApiConfigured = true;
    }
  });
});

describe('api (openapi-fetch + authFetch)', () => {
  it('builds the URL, sends headers and body, and retries a PATCH after a 401', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'old' } } });
    refreshSession.mockResolvedValue({ data: { session: { access_token: 'new' } }, error: null });
    const fetchMock = vi
      .fn<(request: Request) => Promise<Response>>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(Response.json({ id: 'e1' }, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    try {
      const { data, response } = await api.PATCH('/v1/groups/{group_id}/expenses/{expense_id}', {
        params: { path: { group_id: 'g1', expense_id: 'e1' }, header: { 'if-match': '"3"' } },
        body: { description: 'Cena' },
      });

      expect(response.status).toBe(200);
      expect(data).toEqual({ id: 'e1' });
      const retried = fetchMock.mock.calls[1]?.[0];
      expect(retried?.url).toBe('https://api.test/v1/groups/g1/expenses/e1');
      expect(retried?.method).toBe('PATCH');
      expect(retried?.headers.get('If-Match')).toBe('"3"');
      expect(retried?.headers.get('Authorization')).toBe('Bearer new');
      expect(await retried?.json()).toEqual({ description: 'Cena' });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe('unwrap', () => {
  it('returns the data of a 2xx response', async () => {
    const response = new Response('{"id":"g1"}', { status: 200 });
    await expect(unwrap(Promise.resolve({ data: { id: 'g1' }, response }))).resolves.toEqual({ id: 'g1' });
  });

  it('returns undefined for 204', async () => {
    const response = new Response(null, { status: 204 });
    await expect(unwrap(Promise.resolve({ data: undefined, response }))).resolves.toBeUndefined();
  });

  it('throws ApiError with the problem+json body for non-2xx responses', async () => {
    const response = new Response(null, { status: 409 });
    const error = await unwrap(Promise.resolve({ error: { code: 'member_has_open_balance' }, response })).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as InstanceType<typeof ApiError>).status).toBe(409);
    expect(apiErrorCode(error)).toBe('member_has_open_balance');
  });
});
