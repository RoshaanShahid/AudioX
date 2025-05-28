// AudioXApp/static/service-worker.js

const CACHE_VERSION = 1;
const APP_SHELL_CACHE_NAME = `audiox-app-shell-v${CACHE_VERSION}`;
const AUDIO_CACHE_NAME = `audiobook-audio-cache-v1`; // Must match the one in downloadManager.js
const OFFLINE_FALLBACK_PAGE = '/offline-fallback/'; // Create a simple Django view/template for this

// List of URLs for the app shell to cache during installation.
// Be very careful with what you add here. Only essential, static assets.
// Incorrect paths or too many files can break offline functionality or waste storage.
const APP_SHELL_URLS_TO_CACHE = [
    '/', // Your homepage
    "{% static 'css/output.css' %}", // Main stylesheet
    "{% static 'js/downloadManager.js' %}", // Main download script (if global)
    // Add other critical JS files like your main site JS, if any
    // "{% static 'img/audiox-favicon.png' %}", // Example icon
    // OFFLINE_FALLBACK_PAGE, // The page to show when offline and requested page isn't cached
    // You might need to dynamically get these URLs from Django if they change often,
    // or use a build step to generate this list. For now, manually list a few key ones.
    // Be cautious with Font Awesome CDN links here - they are third-party.
    // Better to self-host if you want them fully offline reliable via service worker.
];


// --- Service Worker Lifecycle Events ---

// Install event: Cache the app shell.
self.addEventListener('install', event => {
    console.log('[ServiceWorker] Install event');
    event.waitUntil(
        caches.open(APP_SHELL_CACHE_NAME)
            .then(cache => {
                console.log('[ServiceWorker] Caching App Shell:', APP_SHELL_URLS_TO_CACHE);
                // Use addAll with caution. If any request fails, the whole operation fails.
                // Consider caching essential items individually with cache.add() in a loop.
                return cache.addAll(APP_SHELL_URLS_TO_CACHE).catch(error => {
                    console.error('[ServiceWorker] Failed to cache app shell during install:', error);
                    // Optionally, don't let the SW install if critical assets fail.
                    // For now, we'll let it proceed even if some non-critical assets fail.
                });
            })
            .then(() => {
                console.log('[ServiceWorker] App Shell cached successfully.');
                return self.skipWaiting(); // Activate the new service worker immediately
            })
    );
});

// Activate event: Clean up old caches.
self.addEventListener('activate', event => {
    console.log('[ServiceWorker] Activate event');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    // Delete old versions of our app shell cache
                    if (cacheName.startsWith('audiox-app-shell-') && cacheName !== APP_SHELL_CACHE_NAME) {
                        console.log('[ServiceWorker] Deleting old app shell cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                    // Note: We are NOT deleting the AUDIO_CACHE_NAME here,
                    // as it's managed by downloadManager.js for user-downloaded content.
                    // If you version AUDIO_CACHE_NAME, you'd need a migration strategy.
                })
            );
        }).then(() => {
            console.log('[ServiceWorker] Activated and old caches cleaned.');
            return self.clients.claim(); // Take control of all open clients
        })
    );
});

// --- Fetch Event: Intercept network requests ---
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Strategy 1: For audio files (managed by AUDIO_CACHE_NAME)
    // Try cache first, then network. Audio files are explicitly added by downloadManager.js.
    if (event.request.destination === 'audio' || url.pathname.startsWith('/api/v1/chapters/') && url.pathname.endsWith('/serve-file/')) {
        // The actual caching of audio is done in downloadManager.js.
        // Here, we try to serve from cache if available.
        event.respondWith(
            caches.open(AUDIO_CACHE_NAME).then(cache => {
                return cache.match(event.request).then(cachedResponse => {
                    if (cachedResponse) {
                        // console.log('[ServiceWorker] Serving audio from cache:', event.request.url);
                        return cachedResponse;
                    }
                    // If not in cache, and it's a /serve-file/ URL, it means it wasn't downloaded via downloadManager.
                    // Or, it's a streaming request. Let it go to the network.
                    // console.log('[ServiceWorker] Audio not in cache, fetching from network:', event.request.url);
                    return fetch(event.request).catch(error => {
                        console.warn('[ServiceWorker] Network fetch failed for audio:', event.request.url, error);
                        // Optionally return a placeholder "audio unavailable offline" response
                    });
                });
            })
        );
        return;
    }

    // Strategy 2: For App Shell URLs (Cache First, then Network)
    if (APP_SHELL_URLS_TO_CACHE.includes(url.pathname) || (url.origin === self.location.origin && event.request.destination === 'document')) {
        event.respondWith(
            caches.open(APP_SHELL_CACHE_NAME).then(cache => {
                return cache.match(event.request).then(cachedResponse => {
                    if (cachedResponse) {
                        // console.log('[ServiceWorker] Serving app shell from cache:', event.request.url);
                        return cachedResponse;
                    }
                    // console.log('[ServiceWorker] App shell not in cache, fetching from network:', event.request.url);
                    return fetch(event.request).then(networkResponse => {
                        // Optionally cache new app shell requests on the fly if they are not part of the initial list
                        // but be careful not to cache dynamic HTML or API responses here by mistake.
                        // if (networkResponse.ok && APP_SHELL_URLS_TO_CACHE.includes(url.pathname)) {
                        // cache.put(event.request, networkResponse.clone());
                        // }
                        return networkResponse;
                    }).catch(error => {
                        console.warn('[ServiceWorker] Network fetch failed for app shell:', event.request.url, error);
                        // If it's a navigation request (document) and fails, show offline fallback page.
                        if (event.request.mode === 'navigate' && OFFLINE_FALLBACK_PAGE) {
                            return caches.match(OFFLINE_FALLBACK_PAGE);
                        }
                        // For other asset types, just let the browser handle the error.
                    });
                });
            })
        );
        return;
    }


    // Strategy 3: For other requests (e.g., API calls, external assets not in app shell)
    // Network first, then cache (if you decide to cache API responses, which can be complex)
    // For now, let's just do network first for non-audio, non-app-shell requests.
    // If it's an API call (e.g., to /api/v1/audiobooks/downloadable/), we generally want fresh data.
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(error => {
                console.warn('[ServiceWorker] Network fetch failed for API request:', event.request.url, error);
                // You could return a generic "API unavailable offline" JSON response if appropriate.
                // return new Response(JSON.stringify({ error: "Offline", message: "The API is currently unavailable." }), {
                //     headers: { 'Content-Type': 'application/json' },
                //     status: 503 // Service Unavailable
                // });
            })
        );
        return;
    }

    // Default: Let the browser handle the request if no strategy matches (shouldn't happen often).
    // console.log('[ServiceWorker] No specific strategy, letting browser handle:', event.request.url);
    // event.respondWith(fetch(event.request)); // This is often the default if you don't call event.respondWith
});
