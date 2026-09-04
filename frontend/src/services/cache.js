// Tiny in-memory cache shared across the app's lifetime (module-level state
// survives view switches and re-renders, only resets on a full page reload).
// Two tiers:
//  - TTL entries for data that changes over time (network summary, hotspots,
//    alerts, grid lists) — short-lived so tab switching doesn't feel like a
//    full reload, but stays fresh.
//  - Permanent entries for static reference data (grid geometry) that never
//    changes for a given grid_id, so it's fetched at most once per session.

const store = new Map(); // key -> { value, expires: number | null }

export function getCached(key) {
  const entry = store.get(key);
  if (!entry) return undefined;
  if (entry.expires !== null && Date.now() > entry.expires) {
    store.delete(key);
    return undefined;
  }
  return entry.value;
}

export function setCached(key, value, ttlMs = null) {
  store.set(key, { value, expires: ttlMs ? Date.now() + ttlMs : null });
}

// Dedupes concurrent requests for the same key and caches the result.
// `fetcher` is only called on a cache miss (or after TTL expiry).
export async function withCache(key, ttlMs, fetcher) {
  const cached = getCached(key);
  if (cached !== undefined) return cached;

  const inflightKey = `__inflight__${key}`;
  const inflight = store.get(inflightKey);
  if (inflight) return inflight.value;

  const promise = fetcher();
  store.set(inflightKey, { value: promise, expires: null });
  try {
    const result = await promise;
    setCached(key, result, ttlMs);
    return result;
  } finally {
    store.delete(inflightKey);
  }
}

export function clearCache(prefix) {
  if (!prefix) {
    store.clear();
    return;
  }
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key);
  }
}
