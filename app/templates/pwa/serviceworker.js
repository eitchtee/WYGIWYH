// Base Service Worker implementation.  To use your own Service Worker, set the PWA_SERVICE_WORKER_PATH variable in settings.py

var staticCacheName = "django-pwa-v" + new Date().getTime();
var filesToCache = [
    '/offline/',
    '/static/css/django-pwa-app.css',
    '/static/img/favicon/android-icon-192x192.png',
    '/static/img/favicon/apple-icon-180x180.png',
    '/static/img/pwa/splash-640x1136.png',
    '/static/img/pwa/splash-750x1334.png',
];

// Cache on install
self.addEventListener("install", event => {
    this.skipWaiting();
    event.waitUntil(
        caches.open(staticCacheName)
            .then(cache => {
                return cache.addAll(filesToCache);
            })
    );
});

// Clear cache on activate
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames
                    .filter(cacheName => (cacheName.startsWith("django-pwa-")))
                    .filter(cacheName => (cacheName !== staticCacheName))
                    .map(cacheName => caches.delete(cacheName))
            );
        })
    );
});

// Serve from Cache
self.addEventListener("fetch", event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                if (response) {
                    return response;
                }
                return fetch(event.request).catch(() => {
                    const isHtmxRequest = event.request.headers.get('HX-Request') === 'true';
                    const isHtmxBoosted = event.request.headers.get('HX-Boosted') === 'true';

                    if (!isHtmxRequest || isHtmxBoosted) {
                        // Serve offline content without changing URL
                        return caches.match('/offline/').then(offlineResponse => {
                            if (offlineResponse) {
                                return offlineResponse.text().then(offlineText => {
                                    return new Response(offlineText, {
                                        status: 200,
                                        headers: {'Content-Type': 'text/html'}
                                    });
                                });
                            }
                            // If offline page is not in cache, return a simple offline message
                            return new Response('<h1>Offline</h1><p>The page is not available offline.</p>', {
                                status: 200,
                                headers: {'Content-Type': 'text/html'}
                            });
                        });
                    } else {
                        // For non-boosted HTMX requests, let it fail normally
                        throw new Error('Network request failed');
                    }
                });
            })
    );
});
