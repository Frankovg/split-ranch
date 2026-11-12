import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { createMMKV, type MMKV } from 'react-native-mmkv';
import { AppState } from 'react-native';
import type { PersistStorage, StateStorage } from 'zustand/middleware';
import { createDebouncedStorage } from './debounced-storage';

/** Plain (unencrypted) MMKV for non-sensitive preferences and Quick-split drafts. */
export const storage: MMKV = createMMKV({ id: 'split-ranch' });

/** Zustand `persist` adapter backed by MMKV (synchronous). */
export const zustandStorage: StateStorage = {
  getItem: (key) => storage.getString(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: (key) => {
    storage.remove(key);
  },
};

/**
 * Debounced MMKV `persist` storage for stores updated on every keystroke (Quick splits):
 * serializes and writes at most once per `delayMs`. Pending writes are flushed when
 * the app leaves the foreground, so a kill from the background loses nothing.
 */
export function createDebouncedMMKVStorage<S>(delayMs = 300): PersistStorage<S> {
  const debounced = createDebouncedStorage<S>(storage, delayMs);
  AppState.addEventListener('change', (state) => {
    if (state !== 'active') debounced.flush();
  });
  return debounced;
}

const SESSION_KEY_NAME = 'split-ranch.session-mmkv-key';
let secureInstance: Promise<MMKV> | null = null;

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Encrypted MMKV used for the Supabase session. The AES-256 key lives in
 * expo-secure-store (Android Keystore); SecureStore alone is too small for a session.
 */
export function getSecureStorage(): Promise<MMKV> {
  secureInstance ??= (async () => {
    let key = await SecureStore.getItemAsync(SESSION_KEY_NAME);
    if (!key) {
      key = toHex(await Crypto.getRandomBytesAsync(16)); // 32 hex chars = AES-256 key length
      await SecureStore.setItemAsync(SESSION_KEY_NAME, key);
    }
    return createMMKV({ id: 'split-ranch.session', encryptionKey: key, encryptionType: 'AES-256' });
  })();
  return secureInstance;
}
