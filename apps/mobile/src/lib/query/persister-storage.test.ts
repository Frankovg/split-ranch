import { describe, expect, it } from 'vitest';
import type { StringBackend } from '@/lib/debounced-storage';
import { createAsyncStringStorage } from './persister-storage';

function memoryBackend(): StringBackend {
  const data = new Map<string, string>();
  return {
    getString: (key) => data.get(key),
    set: (key, value) => {
      data.set(key, value);
    },
    remove: (key) => {
      data.delete(key);
    },
  };
}

describe('createAsyncStringStorage', () => {
  it('returns null for a missing key', async () => {
    const storage = createAsyncStringStorage(async () => memoryBackend());
    await expect(storage.getItem('missing')).resolves.toBeNull();
  });

  it('round-trips a value and removes it', async () => {
    const backend = memoryBackend();
    const storage = createAsyncStringStorage(async () => backend);
    await storage.setItem('k', 'v');
    await expect(storage.getItem('k')).resolves.toBe('v');
    await storage.removeItem('k');
    await expect(storage.getItem('k')).resolves.toBeNull();
  });
});
