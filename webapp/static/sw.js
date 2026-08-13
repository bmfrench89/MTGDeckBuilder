/* Service worker — the piece that makes "Add to Home Screen" feel like an app rather
   than a bookmark.

   Deliberately conservative, because this app's whole point is showing you the CURRENT
   state of your collection and decks:
     * Pages and API responses are ALWAYS fetched from the network first. Serving a
       cached deck list would be worse than useless — you'd optimise a deck and see the
       old cards.
     * Only the static shell (CSS, JS, icons) is cached, and only as a fallback.
     * If the PC running the server is off, you get an honest "server unreachable" page
       instead of a browser error nobody can act on.
   Scryfall card images are left entirely alone: the browser's own HTTP cache already
   handles them, and they're on a CDN. */
/* Substituted at serve time by app.py's `_asset_version()` (git HEAD, else the
   newest asset mtime). Hand-pinning this was a standing known-deferred bug: a
   forgotten bump leaves an installed phone serving stale assets silently. The
   literal below is only the fallback for opening this file directly. */
const VERSION = 'mtgdb-__ASSET_VERSION__';
const SHELL = [
  '/static/app.css',
  '/static/tokens.css',
  '/static/cardpanel.css',
  '/static/cardpanel.js',
  '/static/cardgrid.js',
  '/static/collection.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;

  // Static shell: cache-first, it never changes between deploys of the same version.
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(e.request, copy));
        return res;
      }))
    );
    return;
  }

  // Everything else (deck pages, the collection, APIs): network only. Stale data here
  // would actively mislead, so we'd rather say the server is unreachable.
  e.respondWith(
    fetch(e.request).catch(() => new Response(
      `<!doctype html><meta charset="utf-8">
       <meta name="viewport" content="width=device-width,initial-scale=1">
       <title>Server unreachable</title>
       <style>body{background:#0b0d13;color:#e8ecf5;font-family:system-ui,sans-serif;
         display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px}
         .b{max-width:32ch;text-align:center}h1{color:#5BE0D4;font-size:1.4rem;margin:0 0 12px}
         p{color:#8a93a8;line-height:1.5;margin:0 0 8px}code{color:#E8B84B}</style>
       <div class="b"><h1>Can't reach the deckbuilder</h1>
       <p>This app reads your collection live from the machine running the server.</p>
       <p>Check that PC is awake, <code>run.bat</code> is running, and your phone is on the
       same Wi-Fi.</p></div>`,
      { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 503 }
    ))
  );
});
