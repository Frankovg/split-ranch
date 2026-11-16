import type { StringBackend } from '@/lib/debounced-storage';

/** Storage shape expected by `createAsyncStoragePersister`. */
export interface AsyncStringStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

/**
 * Adapts a synchronous string store (MMKV) that is opened asynchronously (the
 * encrypted instance needs its key from SecureStore) to the async storage the
 * TanStack Query persister expects. Missing keys map to `null`.
 */
export function createAsyncStringStorage(getBackend: () => Promise<StringBackend>): AsyncStringStorage {
  return {
    getItem: async (key) => (await getBackend()).getString(key) ?? null,
    setItem: async (key, value) => {
      (await getBackend()).set(key, value);
    },
    removeItem: async (key) => {
      (await getBackend()).remove(key);
    },
  };
}
