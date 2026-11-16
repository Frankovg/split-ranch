import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import { getQueryCacheStorage } from '@/lib/storage';
import { createAsyncStringStorage } from './persister-storage';

/** Saves the React Query cache to encrypted MMKV, at most once per second. */
export const queryPersister = createAsyncStoragePersister({
  storage: createAsyncStringStorage(getQueryCacheStorage),
  throttleTime: 1000,
});
