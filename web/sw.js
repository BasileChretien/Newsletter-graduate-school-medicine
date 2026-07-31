/* MERIDIAN newsletter builder -- offline support.
 *
 * Why: a cold load fetches ~16 MB of Python runtime. Without a service
 * worker that happens again on every visit that misses the HTTP cache,
 * and the page cannot run at all on a machine that is offline or behind
 * a network that blocks the host. An editor covering one issue from a
 * locked-down hospital PC is exactly the case the browser build exists
 * for.
 *
 * The strategy is deliberately split, and the split is the important
 * part of this file.
 *
 *   ./pyodide/*   CACHE FIRST. Immutable for a given Pyodide version:
 *                 every byte is pinned by SHA-256 in
 *                 `pyodide-assets.json` and fetched at deploy time. If
 *                 the version changes, the filenames and the cache
 *                 version change with it.
 *
 *   everything    NETWORK FIRST, falling back to cache when offline.
 *   else          This is the deliberate part. `meridian-bundle.zip` is
 *                 a copy of the real `scripts/` package, and serving a
 *                 stale one means the page silently runs last release's
 *                 parser -- the exact failure the bundle-drift test
 *                 exists to prevent. Caching it cache-first would
 *                 reintroduce that by another route. Online, an editor
 *                 always gets current code; offline, they get the last
 *                 version they successfully loaded.
 *
 * Nothing derived from the editor is ever cached. The DOCX never
 * reaches the network (there is no endpoint), and the `.eml` and the
 * built HTML are blob: URLs, which are not fetch events this worker
 * sees. The rules below only ever match same-origin GETs for the
 * application's own static files.
 */

/* Replaced at deploy time with the commit SHA -- see deploy-web.yml.
 * A new deploy changes these bytes, the browser sees a byte-different
 * worker, installs it, and `activate` drops every previous cache. That
 * is what stops an old bundle outliving a release. */
const VERSION = "__MERIDIAN_VERSION__";
const CACHE = `meridian-${VERSION}`;

/* The app shell. `./pyodide/` is NOT precached: it is ~16 MB, and
 * forcing it down during install would block the worker becoming ready
 * on a slow connection. It populates on first real use instead. */
const SHELL = [
  "./",
  "./index.html",
  "./app.js",
  "./style.css",
  "./meridian-bundle.zip",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // Individually, not `addAll`: that rejects the whole install if any
    // single request fails, which would leave the page with no worker
    // at all because one file 404'd.
    await Promise.all(SHELL.map((url) =>
      cache.add(new Request(url, { cache: "reload" })).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== CACHE && key.startsWith("meridian-")) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

/* The core runtime. These are fetched by `loadPyodide` very early --
 * on a FIRST visit that happens before this worker has taken control,
 * so they miss the cache while the wheels loaded later land in it. The
 * page therefore asks us to warm them once it has booted successfully,
 * which is the point at which we know they are the right files and the
 * editor is not waiting on us.
 *
 * Precaching them during `install` instead would block the worker
 * becoming ready on ~12 MB, on exactly the slow connection where that
 * hurts most. */
const RUNTIME_CORE = [
  "./pyodide/pyodide.js",
  "./pyodide/pyodide.asm.js",
  "./pyodide/pyodide.asm.wasm",
  "./pyodide/python_stdlib.zip",
  "./pyodide/pyodide-lock.json",
];

self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "warm") return;
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(RUNTIME_CORE.map(async (url) => {
      if (await cache.match(url)) return;
      try { await cache.add(url); } catch { /* offline already; fine */ }
    }));
  })());
});

function isRuntimeAsset(url) {
  return url.pathname.includes("/pyodide/");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // Same-origin only. Nothing else should exist -- `connect-src 'self'`
  // would block it -- but a worker that could proxy cross-origin
  // requests is not something to leave to another layer's guarantee.
  if (url.origin !== self.location.origin) return;

  if (isRuntimeAsset(url)) {
    event.respondWith((async () => {
      const hit = await caches.match(request);
      if (hit) return hit;
      const res = await fetch(request);
      if (res.ok) (await caches.open(CACHE)).put(request, res.clone());
      return res;
    })());
    return;
  }

  event.respondWith((async () => {
    try {
      const res = await fetch(request);
      if (res.ok) (await caches.open(CACHE)).put(request, res.clone());
      return res;
    } catch (err) {
      const hit = await caches.match(request);
      if (hit) return hit;
      throw err;
    }
  })());
});
