import type { PersistStorage, StorageValue } from 'zustand/middleware';

/** Minimal synchronous string store (MMKV in the app, a Map in tests). */
export interface StringBackend {
  getString(key: string): string | undefined;
  set(key: string, value: string): void;
  remove(key: string): void;
}

export interface DebouncedPersistStorage<S> extends PersistStorage<S> {
  /** Write every pending value now (e.g. when the app goes to the background). */
  flush(): void;
}

/**
 * Zustand `persist` storage that coalesces writes: the persist middleware calls
 * `setItem` on every state change (each keystroke while typing), and this storage
 * serializes and writes only the latest value once `delayMs` passes without changes.
 * It implements PersistStorage directly (not createJSONStorage) so JSON.stringify is
 * debounced too, not just the write. Reads see pending values, so nothing is lost
 * between a change and its flush.
 */
export function createDebouncedStorage<S>(backend: StringBackend, delayMs: number): DebouncedPersistStorage<S> {
  const pending = new Map<string, StorageValue<S>>();
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    for (const [name, value] of pending) backend.set(name, JSON.stringify(value));
    pending.clear();
  };

  return {
    getItem: (name) => {
      const queued = pending.get(name);
      if (queued) return queued;
      const raw = backend.getString(name);
      if (raw === undefined) return null;
      try {
        return JSON.parse(raw) as StorageValue<S>;
      } catch (error) {
        console.warn(`Ignoring unreadable persisted state for "${name}"`, error);
        return null;
      }
    },
    setItem: (name, value) => {
      pending.set(name, value);
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(flush, delayMs);
    },
    removeItem: (name) => {
      pending.delete(name);
      backend.remove(name);
    },
    flush,
  };
}
