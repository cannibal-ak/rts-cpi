/*
 * Altitude AI — minimal network-first service worker.
 *
 * Hard rules (do not relax — they keep users from ever seeing stale data):
 *   1. NETWORK-FIRST: every request goes to the network first. The cache is only
 *      ever consulted when the network fails (offline fallback).
 *   2. NEVER cache the HTML document (navigations) or any /api response. Those
 *      always go straight to the network, untouched, so the app and its data
 *      can never be served stale from a cache.
 *   3. skipWaiting + clients.claim so a new worker takes over immediately and
 *      updates apply cleanly without a manual hard-refresh.
 *
 * Only same-origin static assets (JS, CSS, images, icons, manifest) get a
 * runtime cache entry, purely so the shell can still paint if the network drops.
 */

const RUNTIME = 'altitude-runtime-v1';

self.addEventListener('install', (event) => {
  // Activate this worker as soon as it finishes installing.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // Drop any caches from older worker versions.
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== RUNTIME).map((k) => caches.delete(k)));
      // Take control of all open clients right away.
      await self.clients.claim();
    })()
  );
});

// Allow the page to tell a waiting worker to activate immediately.
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Only GETs are cacheable; everything else passes straight through.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Same-origin only — never touch cross-origin (CDN SDK, fonts, etc.).
  if (url.origin !== self.location.origin) return;

  // RULE 2: never intercept the API or the HTML document — always network.
  if (url.pathname.startsWith('/api')) return;
  if (req.mode === 'navigate') return;

  // RULE 1: network-first for static assets, cache only as offline fallback.
  event.respondWith(networkFirst(req));
});

async function networkFirst(req) {
  const cache = await caches.open(RUNTIME);
  try {
    const res = await fetch(req);
    // Cache only successful, same-origin (basic) responses for offline fallback.
    if (res && res.ok && res.type === 'basic') {
      cache.put(req, res.clone());
    }
    return res;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    throw err;
  }
}
