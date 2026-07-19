// service-worker.js
//
// Minimal service worker kept for PWA installability. It intentionally has
// NO fetch handler.
//
// Why the fetch handler was removed (2026-07-19):
//   The previous version intercepted every request on the site with
//       event.respondWith(fetch(event.request));
//   and no error handling. That re-issues each request from the service
//   worker context, so any network-level rejection along the
//   Cloudflare ↔ Heroku path (stream reset, connection reuse hiccup,
//   transient edge error) surfaced as a hard failure for the page:
//       "The FetchEvent for <url> resulted in a network error response"
//       "Uncaught (in promise) TypeError: Failed to fetch"
//   instead of the browser's native handling. This is what killed the
//   Job Fit Analyzer's POST in production while staging on localhost
//   (loopback HTTP/1.1, where that fetch essentially cannot fail) was
//   unaffected.
//
//   Because this worker caches nothing, the handler provided zero benefit
//   while adding service-worker startup latency to every request — Chrome
//   explicitly flags and skips "no-op" fetch handlers. Since Chrome 117
//   (2023), a fetch handler is no longer required for PWA installability,
//   so removing it costs nothing. With no fetch handler, the browser
//   handles all requests natively, exactly as if no service worker were in
//   the request path.
//
//   If offline caching is ever added later, the handler must (a) only
//   intercept GET requests, and (b) always attach a .catch() fallback to
//   any fetch passed to event.respondWith().

// Install event
self.addEventListener('install', (event) => {
  self.skipWaiting();  // Activate the updated service worker immediately
});

// Activate event
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());  // Take control of all open pages
});