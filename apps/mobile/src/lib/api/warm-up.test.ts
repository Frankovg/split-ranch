import { afterEach, describe, expect, it, vi } from 'vitest';

const apiConfig = vi.hoisted(() => ({ isApiConfigured: true }));

vi.mock('react-native', () => ({ AppState: { addEventListener: vi.fn() } }));
vi.mock('@/lib/env', () => ({
  env: { apiUrl: 'https://api.test' },
  get isApiConfigured() {
    return apiConfig.isApiConfigured;
  },
}));

const { resetWarmUpForTests, warmUpApi } = await import('./warm-up');

const MINUTE = 60 * 1000;

afterEach(() => {
  resetWarmUpForTests();
  apiConfig.isApiConfigured = true;
});

describe('warmUpApi', () => {
  it('pings /healthz and throttles pings within five minutes', () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));

    warmUpApi(fetchImpl, 0);
    warmUpApi(fetchImpl, 4 * MINUTE);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith('https://api.test/healthz', { method: 'GET' });

    warmUpApi(fetchImpl, 5 * MINUTE);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('allows a new ping right after a failed one', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValueOnce(new Error('offline'));

    warmUpApi(fetchImpl, 0);
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    fetchImpl.mockResolvedValue(new Response('{}'));
    warmUpApi(fetchImpl, MINUTE);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('does nothing when the API URL is not configured', () => {
    apiConfig.isApiConfigured = false;
    const fetchImpl = vi.fn<typeof fetch>();

    warmUpApi(fetchImpl, 0);

    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
