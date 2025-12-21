const CACHE_VERSION = "solara-pwa-v3";
const CACHE_BUST = `?v=${CACHE_VERSION}`;
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/css/style.css",
  "/css/desktop.css",
  "/css/mobile.css",
  "/js/index.js",
  "/js/mobile.js",
  "/favicon.svg",
  "/favicon.png",
  "/manifest.webmanifest",
  "/offline.html",
  "/icons/icon-192.svg",
  "/icons/icon-512.svg"
].map((asset) => `${asset}${CACHE_BUST}`);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => (key === CACHE_VERSION ? null : caches.delete(key))))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const cloned = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, cloned));
          return response;
        })
        .catch(() =>
          caches.match(request, { ignoreSearch: true })
            .then((cached) => cached || caches.match(`/offline.html${CACHE_BUST}`, { ignoreSearch: true }))
        )
    );
    return;
  }
  event.respondWith(
    caches.match(request, { ignoreSearch: true })
      .then((cached) =>
        cached ||
        fetch(request).then((response) => {
          const cloned = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, cloned));
          return response;
        })
      )
  );
});
