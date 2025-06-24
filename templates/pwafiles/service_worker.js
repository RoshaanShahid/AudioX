// templates/pwafiles/service_worker.js

const CACHE_NAME_PREFIX = "audiox-cache-"
// IMPORTANT: Increment this version number to ensure the new service worker installs
const APP_SHELL_CACHE_NAME = `${CACHE_NAME_PREFIX}app-shell-v7`
const STATIC_ASSETS_CACHE_NAME = `${CACHE_NAME_PREFIX}static-assets-v3`
const AUDIO_STREAM_CACHE_NAME = `${CACHE_NAME_PREFIX}audio-stream-v3`
const DYNAMIC_CONTENT_CACHE_NAME = `${CACHE_NAME_PREFIX}dynamic-content-v2`

// URLs for pre-caching the app shell
const APP_SHELL_URLS = [
  "/static/css/output.css",
  "/static/img/audiox-favicon.png",
  "/static/img/microphone-icon.png",
  "/static/img/default_avatar.png",
  "/static/img/placeholders/placeholder.svg",
  "/static/js/offline_manager.js",
  "/static/js/audiobook_detail.js",
  "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
]

// Other static assets you might want to pre-cache
const STATIC_ASSETS_URLS = [
  // Add other frequently used static assets here
]

self.addEventListener("install", (event) => {
  console.log(`Service Worker: Installing (${APP_SHELL_CACHE_NAME}, ${STATIC_ASSETS_CACHE_NAME})...`)
  event.waitUntil(
    Promise.all([
      caches.open(APP_SHELL_CACHE_NAME).then((cache) => {
        console.log("Service Worker: Caching App Shell URLs:", APP_SHELL_URLS)
        // CORRECTED: Pass the array of URL strings directly to addAll.
        // This fixes the TypeError and allows the service worker to install correctly.
        return cache.addAll(APP_SHELL_URLS).catch((error) => {
          console.error("Service Worker: Failed to cache App Shell URLs:", error)
        })
      }),
      caches.open(STATIC_ASSETS_CACHE_NAME).then((cache) => {
        console.log("Service Worker: Caching Static Assets:", STATIC_ASSETS_URLS)
        return cache.addAll(STATIC_ASSETS_URLS).catch((error) => {
          console.error("Service Worker: Failed to cache Static Assets:", error)
        })
      }),
    ]).then(() => {
      console.log("Service Worker: All core assets pre-cached during install.")
      return self.skipWaiting()
    }),
  )
})

self.addEventListener("activate", (event) => {
  console.log(
    `Service Worker: Activating (${APP_SHELL_CACHE_NAME}, ${STATIC_ASSETS_CACHE_NAME}, ${AUDIO_STREAM_CACHE_NAME}, ${DYNAMIC_CONTENT_CACHE_NAME})...`,
  )
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            if (
              cacheName.startsWith(CACHE_NAME_PREFIX) &&
              ![
                APP_SHELL_CACHE_NAME,
                STATIC_ASSETS_CACHE_NAME,
                AUDIO_STREAM_CACHE_NAME,
                DYNAMIC_CONTENT_CACHE_NAME,
              ].includes(cacheName)
            ) {
              console.log("Service Worker: Deleting old cache:", cacheName)
              return caches.delete(cacheName)
            }
          }),
        )
      })
      .then(() => {
        console.log("Service Worker: Old caches cleaned.")
        return self.clients.claim()
      }),
  )
})

self.addEventListener("fetch", (event) => {
  const request = event.request
  const requestUrl = new URL(request.url)

  if (
    request.method !== "GET" ||
    requestUrl.protocol === "chrome-extension:" ||
    requestUrl.pathname.startsWith("/django-admin/") ||
    requestUrl.pathname.startsWith("/admin/") ||
    requestUrl.hostname === "js.stripe.com" ||
    requestUrl.hostname === "api.stripe.com"
  ) {
    event.respondWith(fetch(request))
    return
  }

  if (request.mode === "navigate") {
    console.log("SW: Handling navigate request (Network First):", requestUrl.pathname)
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse.ok) {
            const responseToCache = networkResponse.clone()
            caches.open(DYNAMIC_CONTENT_CACHE_NAME).then((cache) => {
              console.log("SW: Caching network response for navigate in DYNAMIC_CONTENT_CACHE:", requestUrl.pathname)
              cache.put(request, responseToCache)
            })
          }
          return networkResponse
        })
        .catch(() => {
          console.warn("SW: Network request failed for navigate, trying DYNAMIC_CONTENT_CACHE:", requestUrl.pathname)
          return caches.match(request, { cacheName: DYNAMIC_CONTENT_CACHE_NAME }).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse
            }
            return new Response("You are offline and this page hasn't been cached.", {
              status: 503,
              statusText: "Service Unavailable",
              headers: { "Content-Type": "text/html" },
            })
          })
        }),
    )
    return
  }

  const isAppShellStaticAsset =
    APP_SHELL_URLS.includes(requestUrl.pathname) ||
    STATIC_ASSETS_URLS.includes(requestUrl.pathname) ||
    ["https://cdnjs.cloudflare.com", "https://fonts.googleapis.com", "https://fonts.gstatic.com"].includes(
      requestUrl.origin,
    )

  if (isAppShellStaticAsset && request.destination !== "document") {
    console.log("SW: Handling App Shell static asset (Cache First):", requestUrl.pathname)
    event.respondWith(
      caches.match(request, { ignoreSearch: true }).then((cachedResponse) => {
        if (cachedResponse) return cachedResponse

        return fetch(request)
          .then((networkResponse) => {
            if (networkResponse.ok) {
              const responseToCache = networkResponse.clone()
              let targetCacheName = STATIC_ASSETS_CACHE_NAME
              if (
                APP_SHELL_URLS.includes(requestUrl.pathname) ||
                requestUrl.origin.match(/cloudflare|googleapis|gstatic/)
              ) {
                targetCacheName = APP_SHELL_CACHE_NAME
              }
              caches.open(targetCacheName).then((cache) => cache.put(request, responseToCache))
            }
            return networkResponse
          })
          .catch((error) => {
            console.warn("SW: Network request failed for app/static asset:", requestUrl.pathname, error)
          })
      }),
    )
    return
  }

  if (requestUrl.pathname.includes("/stream_audio/")) {
    console.log("SW: Handling audio stream (Network First):", requestUrl.pathname)
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse.ok && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone()
            caches.open(AUDIO_STREAM_CACHE_NAME).then((cache) => {
              cache.put(request, responseToCache)
            })
          }
          return networkResponse
        })
        .catch(() => {
          console.warn("SW: Network failed for audio stream, trying cache:", requestUrl.pathname)
          return caches.match(request, { cacheName: AUDIO_STREAM_CACHE_NAME }).then((cachedResponse) => {
            return (
              cachedResponse ||
              new Response(JSON.stringify({ error: "Offline and audio not in cache" }), {
                status: 503,
                headers: { "Content-Type": "application/json" },
              })
            )
          })
        }),
    )
    return
  }

  console.log(
    "SW: Handling other GET request (Stale-While-Revalidate like):",
    requestUrl.pathname,
    "Destination:",
    request.destination,
  )
  event.respondWith(
    caches.open(STATIC_ASSETS_CACHE_NAME).then((cache) => {
      return cache.match(request).then((cachedResponse) => {
        const fetchPromise = fetch(request)
          .then((networkResponse) => {
            if (networkResponse.ok && networkResponse.status === 200) {
              const responseToCache = networkResponse.clone()
              cache.put(request, responseToCache)
            }
            return networkResponse
          })
          .catch((err) => {
            console.warn("SW: Network request failed for other asset:", requestUrl.pathname, err.message)
            if (!cachedResponse) {
              return new Response("Network error: Resource not available offline.", {
                status: 408,
                headers: { "Content-Type": "text/plain" },
              })
            }
          })
        return cachedResponse || fetchPromise
      })
    }),
  )
})

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    console.log("SW: Received SKIP_WAITING message. Calling self.skipWaiting().")
    self.skipWaiting()
  }
})