const CACHE_NAME = 'infinity-agent-cache-v1'
const urlsToCache = [
  '/Infinity-agent/',
  '/Infinity-agent/index.html',
  '/Infinity-agent/manifest.webmanifest'
]

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((resp) => resp || fetch(event.request))
  )
})
