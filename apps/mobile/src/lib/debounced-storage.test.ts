import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createDebouncedStorage, type StringBackend } from './debounced-storage';

function memoryBackend() {
  const data = new Map<string, string>();
  const writes: string[] = [];
  const backend: StringBackend = {
    getString: (key) => data.get(key),
    set: (key, value) => {
      writes.push(value);
      data.set(key, value);
    },
    remove: (key) => {
      data.delete(key);
    },
  };
  return { backend, data, writes };
}

const value = (n: number) => ({ state: { n }, version: 1 });

describe('createDebouncedStorage', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('writes only the latest value once the delay passes', () => {
    const { backend, writes } = memoryBackend();
    const storage = createDebouncedStorage<{ n: number }>(backend, 300);
    storage.setItem('k', value(1));
    storage.setItem('k', value(2));
    storage.setItem('k', value(3));
    expect(writes).toHaveLength(0);
    vi.advanceTimersByTime(300);
    expect(writes).toEqual([JSON.stringify(value(3))]);
  });

  it('reads a pending value before it is flushed', () => {
    const { backend } = memoryBackend();
    const storage = createDebouncedStorage<{ n: number }>(backend, 300);
    storage.setItem('k', value(7));
    expect(storage.getItem('k')).toEqual(value(7));
  });

  it('flush() writes immediately and cancels the timer', () => {
    const { backend, writes } = memoryBackend();
    const storage = createDebouncedStorage<{ n: number }>(backend, 300);
    storage.setItem('k', value(1));
    storage.flush();
    expect(writes).toEqual([JSON.stringify(value(1))]);
    vi.advanceTimersByTime(1000);
    expect(writes).toHaveLength(1);
  });

  it('removeItem drops pending writes and the stored value', () => {
    const { backend, data } = memoryBackend();
    data.set('k', JSON.stringify(value(1)));
    const storage = createDebouncedStorage<{ n: number }>(backend, 300);
    storage.setItem('k', value(2));
    storage.removeItem('k');
    vi.advanceTimersByTime(300);
    expect(data.has('k')).toBe(false);
    expect(storage.getItem('k')).toBeNull();
  });

  it('returns null for unreadable stored JSON', () => {
    const { backend, data } = memoryBackend();
    data.set('k', '{not json');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const storage = createDebouncedStorage<{ n: number }>(backend, 300);
    expect(storage.getItem('k')).toBeNull();
    warn.mockRestore();
  });
});
