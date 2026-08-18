/**
 * Shared page walker for the CPI data grids.
 *
 * The pricing, velocity and cruise grids each had their own copy of this loop.
 * They drifted: a fix scoping "Load All" to the selected date landed in the
 * pricing copy and was missed in the velocity copy, which is what allowed an
 * unfiltered full-table walk to reach production. One implementation, so a fix
 * applies everywhere.
 *
 * The grids still load a whole capture date into memory and filter client-side.
 * That is a deliberate trade — filtering stays instant — and is affordable
 * because the server now scopes every query to a single date. Dates have since
 * grown to ~164k rows (WM), so repeat loads are served from the session cache
 * in datasetCache.ts; this walker is the cache-miss path.
 */

/** Minimal shape this helper needs from a paginated endpoint. */
export interface PagedResult<T> {
  items: T[];
  page_info: { total: number; applied_file_date?: string | null };
}

/** Server maximum. Was 100, which cost ~10x the requests for the same rows. */
export const PAGE_FETCH_SIZE = 1000;

/**
 * In-flight requests per grid. Lowered from 10: several grids and users at ten
 * apiece was enough to saturate the API's database connection pool.
 */
export const FETCH_CONCURRENCY = 4;

export interface FetchAllPagesArgs<T> {
  /**
   * Fetch one page. Must forward `signal` to the underlying request and
   * `withTotal` to the endpoint's `with_total` param — only page 1 needs the
   * count; repeating it on every page cost 163 redundant count(*) calls on
   * the largest date.
   */
  fetchPage: (
    page: number,
    pageSize: number,
    signal?: AbortSignal,
    withTotal?: boolean,
  ) => Promise<PagedResult<T>>;
  onProgress?: (loaded: number, total: number) => void;
  signal?: AbortSignal;
}

export interface FetchAllPagesResult<T> {
  rows: T[];
  total: number;
  /** cap_date the server actually queried (echoes the pin when none was sent). */
  appliedFileDate: string | null;
}

export async function fetchAllPages<T>({
  fetchPage,
  onProgress,
  signal,
}: FetchAllPagesArgs<T>): Promise<FetchAllPagesResult<T>> {
  const first = await fetchPage(1, PAGE_FETCH_SIZE, signal, true);
  const total = first.page_info.total;
  const appliedFileDate = first.page_info.applied_file_date ?? null;
  const numPages = Math.max(1, Math.ceil(total / PAGE_FETCH_SIZE));
  onProgress?.(first.items.length, total);
  if (numPages <= 1) return { rows: first.items, total, appliedFileDate };

  const rest: number[] = [];
  for (let p = 2; p <= numPages; p++) rest.push(p);

  const collected: T[] = [...first.items];
  for (let i = 0; i < rest.length; i += FETCH_CONCURRENCY) {
    // Check between batches so an abandoned load (tab switch, filter change,
    // unmount) stops issuing requests for results nobody will read.
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const batch = rest.slice(i, i + FETCH_CONCURRENCY);
    const results = await Promise.all(
      batch.map(p => fetchPage(p, PAGE_FETCH_SIZE, signal, false).then(r => r.items)),
    );
    for (const items of results) collected.push(...items);
    onProgress?.(collected.length, total);
  }
  return { rows: collected, total, appliedFileDate };
}
