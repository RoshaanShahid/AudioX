// templates/pwafiles/service_worker.js

const CACHE_NAME_PREFIX = 'audiox-cache-';
// IMPORTANT: Increment this version number when you update the service worker file
const APP_SHELL_CACHE_NAME = `${CACHE_NAME_PREFIX}app-shell-v5`;
const STATIC_ASSETS_CACHE_NAME = `${CACHE_NAME_PREFIX}static-assets-v2`; // Version this too if strategy changes
const AUDIO_STREAM_CACHE_NAME = `${CACHE_NAME_PREFIX}audio-stream-v2`; // Version this too if strategy changes
const DYNAMIC_CONTENT_CACHE_NAME = `${CACHE_NAME_PREFIX}dynamic-content-v1`; // For dynamic HTML fallbacks

// URLs for pre-caching the app shell (mostly static assets now)
// Remove '/' and other HTML pages if they are handled by 'navigate' and you don't want them pre-cached for offline first.
// Or keep them if you want them available offline via cache after a first successful network fetch.
const APP_SHELL_URLS = [
    // '/', // Example: Homepage - consider if you want this pre-cached or only cached after first visit
    // '/my-downloads/', // Example: Another HTML page
    '/static/css/output.css',
    '/static/img/audiox-favicon.png',
    '/static/img/microphone-icon.png',
    '/static/img/default_avatar.png',
    '/static/js/offline_manager.js',
    '/static/js/audiobook_detail.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap',
    // Add your offline.html page here if you create one
    // '/offline.html',
];

// Other static assets you might want to pre-cache (images, fonts, etc.)
const STATIC_ASSETS_URLS = [
    // Add other frequently used static assets here
];

self.addEventListener('install', event => {
    console.log(`Service Worker: Installing (${APP_SHELL_CACHE_NAME}, ${STATIC_ASSETS_CACHE_NAME})...`);
    event.waitUntil(
        Promise.all([
            caches.open(APP_SHELL_CACHE_NAME).then(cache => {
                console.log('Service Worker: Caching App Shell URLs:', APP_SHELL_URLS);
                const requestsToCache = APP_SHELL_URLS.map(url => {
                    if (url.startsWith('http')) {
                        return new Request(url, { mode: 'cors' });
                    }
                    return url;
                });
                return cache.addAll(requestsToCache).catch(error => {
                    console.error('Service Worker: Failed to cache some App Shell URLs:', error, requestsToCache);
                });
            }),
            caches.open(STATIC_ASSETS_CACHE_NAME).then(cache => {
                console.log('Service Worker: Caching Static Assets:', STATIC_ASSETS_URLS);
                return cache.addAll(STATIC_ASSETS_URLS).catch(error => {
                    console.error('Service Worker: Failed to cache some Static Assets:', error, STATIC_ASSETS_URLS);
                });
            })
        ]).then(() => {
            console.log('Service Worker: All core assets pre-cached during install.');
            return self.skipWaiting();
        })
    );
});

self.addEventListener('activate', event => {
    console.log(`Service Worker: Activating (${APP_SHELL_CACHE_NAME}, ${STATIC_ASSETS_CACHE_NAME}, ${AUDIO_STREAM_CACHE_NAME}, ${DYNAMIC_CONTENT_CACHE_NAME})...`);
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName.startsWith(CACHE_NAME_PREFIX) &&
                        ![APP_SHELL_CACHE_NAME, STATIC_ASSETS_CACHE_NAME, AUDIO_STREAM_CACHE_NAME, DYNAMIC_CONTENT_CACHE_NAME].includes(cacheName)) {
                        console.log('Service Worker: Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            console.log('Service Worker: Old caches cleaned.');
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', event => {
    const request = event.request;
    const requestUrl = new URL(request.url);

    // Ignore non-GET requests, requests to chrome extensions, Django admin, app admin, and Stripe
    if (request.method !== 'GET' ||
        requestUrl.protocol === 'chrome-extension:' ||
        requestUrl.pathname.startsWith('/django-admin/') || // Django's default admin
        requestUrl.pathname.startsWith('/admin/') || // Your app's admin section if different
        requestUrl.hostname === 'js.stripe.com' ||
        requestUrl.hostname === 'api.stripe.com') {
        // Let the network handle these requests without SW interference
        event.respondWith(fetch(request));
        return;
    }

    // Strategy for HTML Navigation: Network First, then Cache (for offline fallback)
    if (request.mode === 'navigate') {
        console.log('SW: Handling navigate request (Network First):', requestUrl.pathname);
        event.respondWith(
            fetch(request)
                .then(networkResponse => {
                    // If successful and a 200 OK, clone and cache it in DYNAMIC_CONTENT_CACHE
                    if (networkResponse.ok) {
                        const responseToCache = networkResponse.clone();
                        caches.open(DYNAMIC_CONTENT_CACHE_NAME).then(cache => {
                            console.log('SW: Caching network response for navigate in DYNAMIC_CONTENT_CACHE:', requestUrl.pathname);
                            cache.put(request, responseToCache);
                        });
                    }
                    return networkResponse;
                })
                .catch(() => {
                    // Network failed, try to serve from DYNAMIC_CONTENT_CACHE as a fallback
                    console.warn('SW: Network request failed for navigate, trying DYNAMIC_CONTENT_CACHE:', requestUrl.pathname);
                    return caches.match(request, { cacheName: DYNAMIC_CONTENT_CACHE_NAME })
                        .then(cachedResponse => {
                            if (cachedResponse) {
                                return cachedResponse;
                            }
                            // Optional: return a generic offline.html page if nothing is cached for this path
                            // return caches.match('/offline.html', { cacheName: APP_SHELL_CACHE_NAME });
                            // Fallback to a simple offline message if no specific offline page or cached page found
                            return new Response("You are offline and this page hasn't been cached.", {
                                status: 503,
                                statusText: "Service Unavailable",
                                headers: { 'Content-Type': 'text/html' }
                            });
                        });
                })
        );
        return;
    }

    // Strategy for specific App Shell static assets (CSS, JS, local images) & external fonts: Cache First
    const isAppShellStaticAsset = APP_SHELL_URLS.includes(requestUrl.pathname) ||
                                  STATIC_ASSETS_URLS.includes(requestUrl.pathname) ||
                                  ['https://cdnjs.cloudflare.com', 'https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(requestUrl.origin);

    // Ensure this is not a document request being mistakenly handled here if it's also in APP_SHELL_URLS
    if (isAppShellStaticAsset && request.destination !== 'document') {
        console.log('SW: Handling App Shell static asset (Cache First):', requestUrl.pathname);
        event.respondWith(
            caches.match(request, { ignoreSearch: true }).then(cachedResponse => { // ignoreSearch can be useful for fonts etc.
                if (cachedResponse) return cachedResponse;

                return fetch(request).then(networkResponse => {
                    if (networkResponse.ok) {
                        const responseToCache = networkResponse.clone();
                        let targetCacheName = STATIC_ASSETS_CACHE_NAME; // Default for other static assets
                        if (APP_SHELL_URLS.includes(requestUrl.pathname) || requestUrl.origin.match(/cloudflare|googleapis|gstatic/)) {
                            targetCacheName = APP_SHELL_CACHE_NAME;
                        }
                        caches.open(targetCacheName).then(cache => cache.put(request, responseToCache));
                    }
                    return networkResponse;
                }).catch(error => {
                    console.warn('SW: Network request failed for app/static asset:', requestUrl.pathname, error);
                    // Optional: Provide a fallback for specific failed assets if needed (e.g., a placeholder image)
                    // if (request.destination === 'image') return caches.match('/static/img/placeholder.png');
                });
            })
        );
        return;
    }

    // Strategy for Audio Streams (/stream-audio/): Network First, then Cache
    // This is suitable for content that might be large or frequently updated,
    // but can benefit from caching for offline or repeat plays.
    if (requestUrl.pathname.includes('/stream-audio/')) {
        console.log('SW: Handling audio stream (Network First):', requestUrl.pathname);
        event.respondWith(
            fetch(request)
                .then(networkResponse => {
                    // Only cache full, successful (200 OK) responses for audio streams
                    // Partial content (206) should not be cached as a whole resource typically.
                    if (networkResponse.ok && networkResponse.status === 200) {
                        const responseToCache = networkResponse.clone();
                        caches.open(AUDIO_STREAM_CACHE_NAME).then(cache => {
                            cache.put(request, responseToCache);
                        });
                    }
                    // Return the original network response (could be 200 for full or 206 for partial)
                    return networkResponse;
                })
                .catch(() => {
                    console.warn('SW: Network failed for audio stream, trying cache:', requestUrl.pathname);
                    return caches.match(request, { cacheName: AUDIO_STREAM_CACHE_NAME }).then(cachedResponse => {
                        return cachedResponse || new Response(JSON.stringify({ error: "Offline and audio not in cache" }), {
                            status: 503, headers: { 'Content-Type': 'application/json' }
                        });
                    });
                })
        );
        return;
    }

    // Default strategy for other GET requests (e.g., API calls, images not in app shell): Network Only or Stale-While-Revalidate
    // For API calls (like /api/), usually Network Only is preferred to ensure fresh data.
    // For other static assets not covered, Stale-While-Revalidate can be good.
    // Current setup from user was Stale-While-Revalidate like for 'else'
    // Let's keep it that way for general uncategorized GETs for now but log them.
    console.log('SW: Handling other GET request (Stale-While-Revalidate like):', requestUrl.pathname, 'Destination:', request.destination);
    event.respondWith(
        caches.open(STATIC_ASSETS_CACHE_NAME).then(cache => { // A general cache for these
            return cache.match(request).then(cachedResponse => {
                const fetchPromise = fetch(request).then(networkResponse => {
                    if (networkResponse.ok && networkResponse.status === 200) { // Only cache 200 OK
                        const responseToCache = networkResponse.clone();
                        cache.put(request, responseToCache);
                    }
                    return networkResponse;
                }).catch(err => {
                    console.warn('SW: Network request failed for other asset:', requestUrl.pathname, err.message);
                    if (!cachedResponse) {
                        // If not in cache and network fails, then it's an error.
                        return new Response("Network error: Resource not available offline.", {
                            status: 408, headers: { 'Content-Type': 'text/plain' }
                        });
                    }
                    // If in cache, the error is caught, but cachedResponse will be returned below.
                });
                return cachedResponse || fetchPromise; // Serve from cache if available, update in background
            });
        })
    );
});

self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        console.log('SW: Received SKIP_WAITING message. Calling self.skipWaiting().');
        self.skipWaiting();
    }
    // You can add more message handlers here, e.g., for clearing specific caches
    // else if (event.data && event.data.type === 'CLEAR_DYNAMIC_CACHE') {
    //     console.log('SW: Received CLEAR_DYNAMIC_CACHE message.');
    //     caches.delete(DYNAMIC_CONTENT_CACHE_NAME).then(() => {
    //         console.log('SW: Dynamic content cache cleared.');
    //     });
    // }
});