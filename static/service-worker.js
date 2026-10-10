// Cache the app shell only. Private pages, feedback, books and PDFs stay online.
const CACHE_NAME = 'library-app-shell-v1';
const APP_SHELL = ['/static/style.css', '/static/profiles/default.svg', '/static/icons/library-192.png', '/static/icons/library-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
  }
});
