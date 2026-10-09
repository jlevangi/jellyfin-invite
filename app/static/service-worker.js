const CACHE = 'pierces-media-shell-v2';
const SHELL = ['/static/css/base.css', '/static/img/favicon.png', '/static/offline.html'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('pierces-media-shell-') && key !== CACHE).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname === '/service-worker.js' || url.pathname === '/manifest.webmanifest' || url.pathname.startsWith('/api/') || url.pathname.startsWith('/invite') || url.pathname.startsWith('/oidc/') || url.pathname.startsWith('/j/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/static/offline.html')));
    return;
  }
  if (SHELL.includes(url.pathname)) event.respondWith(fetch(request).then(response => { if (response.ok) caches.open(CACHE).then(cache => cache.put(request, response.clone())); return response; }).catch(() => caches.match(request)));
});