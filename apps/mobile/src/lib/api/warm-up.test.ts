import { afterEach, describe, expect, it, vi } from 'vitest';

const apiConfig = vi.hoisted(() => ({ isApiConfigured: true }));

vi.mock('react-native', () => ({ AppState: { addEventListener: vi.fn() } }));
vi.mock('@/lib/env', () => ({
  env: { apiUrl: 'https://api.test' },
  get isApiConfigured() {
    return apiConfig.isApiConfigured;
  },
}));

const { resetWarmUpForTests, useApiStatusStore, warmUpApi } = await import('./warm-up');

const MINUTE = 60 * 1000;
const status = () => useApiStatusStore.getState().status;

afterEach(() => {
  resetWarmUpForTests();
  apiConfig.isApiConfigured = true;
});

describe('warmUpApi', () => {
  it('pings /healthz and throttles pings within five minutes', () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));

    warmUpApi({ fetchImpl, now: 0 });
    warmUpApi({ fetchImpl, now: 4 * MINUTE });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith('https://api.test/healthz', { method: 'GET' });

    warmUpApi({ fetchImpl, now: 5 * MINUTE });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('ignores the throttle when forced', () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));

    warmUpApi({ fetchImpl, now: 0 });
    warmUpApi({ fetchImpl, now: MINUTE, force: true });

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('publishes waking, then awake on a successful response', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));

    warmUpApi({ fetchImpl, now: 0 });
    expect(status()).toBe('waking');

    await vi.waitFor(() => expect(status()).toBe('awake'));
  });

  it('keeps an awake status while a foreground re-ping is in flight', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));
    warmUpApi({ fetchImpl, now: 0 });
    await vi.waitFor(() => expect(status()).toBe('awake'));

    fetchImpl.mockReturnValue(new Promise<Response>(() => {}));
    warmUpApi({ fetchImpl, now: 10 * MINUTE });

    expect(status()).toBe('awake');
  });

  it('publishes unreachable on an error response', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 503 }));

    warmUpApi({ fetchImpl, now: 0 });

    await vi.waitFor(() => expect(status()).toBe('unreachable'));
  });

  it('allows a new ping right after a failed one', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValueOnce(new Error('offline'));

    warmUpApi({ fetchImpl, now: 0 });
    await vi.waitFor(() => expect(status()).toBe('unreachable'));
    fetchImpl.mockResolvedValue(new Response('{}'));
    warmUpApi({ fetchImpl, now: MINUTE });

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('does nothing when the API URL is not configured', () => {
    apiConfig.isApiConfigured = false;
    const fetchImpl = vi.fn<typeof fetch>();

    warmUpApi({ fetchImpl, now: 0 });

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(status()).toBe('idle');
  });
});
