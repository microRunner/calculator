// Cloud Calculator service worker.
// Served from the site root (/sw.js) so its scope covers the whole app.
// Strategy: network-first for the app shell, with a cached fallback so the app
// still opens when offline. API calls and cross-origin requests (Google
// Sign-In, fonts) are never intercepted, keeping history sync with Firestore
// and OAuth behaviour exactly the same as in the browser.
const CACHE = 'cloud-calculator-v1';
const SHELL = [
  '/',
  '/static/style.css?v=3',
  '/static/app.js?v=6',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(req).then((hit) => hit || (req.mode === 'navigate' ? caches.match('/') : undefined))
      )
  );
});
