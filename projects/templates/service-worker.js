// service-worker.js

// Install event - no caching
self.addEventListener('install', (event) => {
  self.skipWaiting();  // Activate the service worker immediately
});

// Activate event
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());  // Take control of all open pages
});

// Fetch event - no caching, just fetch everything from the network
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));  // Always fetch from network, no cache
});
