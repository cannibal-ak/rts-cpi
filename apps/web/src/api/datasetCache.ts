/**
 * In-memory session cache for the CPI data grids.
 *
 * The three grids (pricing, velocity, cruise) each load an entire capture date
 * into memory via fetchAllPages and filter client-side. The rows lived only in
 * component state, so every tab switch or route return re-downloaded the whole
 * dataset — 164 requests for the largest date. This module keeps completed
 * datasets in a module-level store for the lifetime of the page, keyed by
 * (endpoint, tenant, server-side query), and revalidates them with a cheap
 * 50-row probe instead of a full walk.
 *
 * Why a probe rather than a freshness timestamp: rows are never UPDATEd —
 * ingestion inserts fresh UUIDs with a new loaded_at, and manual delete removes
 * rows (changing the total). Ordering is deterministic (cap_date, cap_time,
 * id DESC), so the first 50 rows' (id, loaded_at) plus the total form a
 * reliable fingerprint of the whole dataset. A manual delete can be masked for
 * up to 60s by the server's count(*) memo — the same staleness the live grid
 * has always had.
 *
 * Deliberately memory-only: closing the browser drops the cache (user's
 * chosen scope). The store/lookup seam here is where a persistent (IndexedDB)
 * layer would slot in later.
 */

import { fetchAllPages, PagedResult } from './fetchAllPages';

/** Rows must expose these for fingerprinting; every grid row type does. */
interface CacheableRow {
  id: string;
  loaded_at?: string | null;
}

export interface DatasetKeyParts {
  /** API path, e.g. '/api/v1/airline/snapshots' — any stable per-grid string works. */
  endpoint: string;
  /** Tenant code the tab passes. MUST be in the key: two tenants' parameter-less
   *  requests are identical on the wire but return different data. */
  tenant: string;
  /** The tab's server-side query (file_date, airline, …). Pagination keys are ignored. */
  query: Record<string, string | undefined>;
}

const IGNORED_QUERY_KEYS = new Set(['page', 'page_size', 'with_total', 'tenant']);

export function datasetKey({ endpoint, tenant, query }: DatasetKeyParts): string {
  const q = Object.entries(query)
    .filter(([k, v]) => !IGNORED_QUERY_KEYS.has(k) && v !== undefined && v !== '')
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${k}=${v}`)
    .join('&');
  return `${endpoint}|${tenant}|${q}`;
}

interface DatasetEntry {
  rows: CacheableRow[];
  total: number;
  fingerprint: string;
  appliedFileDate: string | null;
  savedAt: number;
  lastUsedAt: number;
  validatedAt: number;
}

/** Rows hashed into the fingerprint; also the probe request's page size. */
const PROBE_SIZE = 50;
/** Within this window a dataset is served with zero requests (tab flips,
 *  StrictMode double-mounts). Past it, one probe request revalidates. */
const TRUST_MS = 30_000;
/** Heap guards: one WM-sized date (~164k rows) plus a few normal ones. */
const MAX_ENTRIES = 4;
const MAX_TOTAL_ROWS = 250_000;

const store = new Map<string, DatasetEntry>();

/** FNV-1a 32-bit — tiny, stable, plenty for change detection. */
function fnv1a(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16);
}

function fingerprintOf(total: number, appliedFileDate: string | null | undefined, rows: CacheableRow[]): string {
  const head = rows
    .slice(0, PROBE_SIZE)
    .map(r => `${r.id},${r.loaded_at ?? ''}`)
    .join(';');
  return fnv1a(`${total}|${appliedFileDate ?? ''}|${head}`);
}

function evictToBudget(protectedKey: string): void {
  const totalRows = () => [...store.values()].reduce((n, e) => n + e.rows.length, 0);
  while (store.size > MAX_ENTRIES || (store.size > 1 && totalRows() > MAX_TOTAL_ROWS)) {
    let lruKey: string | null = null;
    let lruAt = Infinity;
    for (const [k, e] of store) {
      if (k === protectedKey) continue;
      if (e.lastUsedAt < lruAt) {
        lruAt = e.lastUsedAt;
        lruKey = k;
      }
    }
    if (!lruKey) break; // only the just-stored entry remains
    store.delete(lruKey);
  }
}

/** Drop everything — called on logout so datasets never outlive the session
 *  that loaded them (shared-machine hygiene). */
export function clearDatasetCache(): void {
  store.clear();
}

export interface FetchAllPagesCachedArgs<T> {
  key: DatasetKeyParts;
  /** Same contract as fetchAllPages: forward signal and withTotal to the endpoint. */
  fetchPage: (
    page: number,
    pageSize: number,
    signal?: AbortSignal,
    withTotal?: boolean,
  ) => Promise<PagedResult<T>>;
  onProgress?: (loaded: number, total: number) => void;
  signal?: AbortSignal;
}

/**
 * Drop-in replacement for fetchAllPages that serves repeat views from the
 * session cache. Returns the cached array BY REFERENCE — callers must treat it
 * as immutable (the grids only .filter/.map/.slice, verified at call sites).
 * Aborted loads are never cached and AbortErrors propagate unchanged.
 */
export async function fetchAllPagesCached<T extends CacheableRow>({
  key,
  fetchPage,
  onProgress,
  signal,
}: FetchAllPagesCachedArgs<T>): Promise<T[]> {
  const k = datasetKey(key);
  const now = Date.now();
  const direct = store.get(k);

  // Fresh enough to trust without a round trip.
  if (direct && now - direct.validatedAt < TRUST_MS) {
    direct.lastUsedAt = now;
    onProgress?.(direct.rows.length, direct.rows.length);
    return direct.rows as T[];
  }

  // A dated entry may exist under the server-pinned date when the caller sent
  // no file_date; the probe's applied_file_date resolves which one to check.
  const dateless = !key.query.file_date;
  const haveCandidate =
    direct !== undefined ||
    (dateless && [...store.keys()].some(sk => sk.startsWith(`${key.endpoint}|${key.tenant}|`)));

  if (haveCandidate) {
    const probe = await fetchPage(1, PROBE_SIZE, signal, true);
    const probeDate = probe.page_info.applied_file_date ?? null;
    const candidate =
      direct ??
      (probeDate
        ? store.get(datasetKey({ ...key, query: { ...key.query, file_date: probeDate } }))
        : undefined);
    if (candidate) {
      const probeFp = fingerprintOf(probe.page_info.total, probeDate, probe.items);
      if (probeFp === candidate.fingerprint) {
        candidate.validatedAt = Date.now();
        candidate.lastUsedAt = candidate.validatedAt;
        onProgress?.(candidate.rows.length, candidate.rows.length);
        return candidate.rows as T[];
      }
    }
  }

  // Cache miss (or stale): full walk. On abort this throws and nothing is stored.
  const { rows, total, appliedFileDate } = await fetchAllPages<T>({ fetchPage, onProgress, signal });
  if (signal?.aborted) return rows; // superseded load — don't poison the cache

  // Store under an explicit-date key so a later dateless lookup can resolve it.
  const storageKey = dateless && appliedFileDate
    ? datasetKey({ ...key, query: { ...key.query, file_date: appliedFileDate } })
    : k;
  const t = Date.now();
  store.set(storageKey, {
    rows,
    total,
    fingerprint: fingerprintOf(total, appliedFileDate, rows),
    appliedFileDate,
    savedAt: t,
    lastUsedAt: t,
    validatedAt: t,
  });
  evictToBudget(storageKey);
  return rows;
}
