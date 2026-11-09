// This file is filled with the exact URLs of the generated build.
const prefix = `ttgames:${self.registration.scope}:`;
const version = prefix + '__BUILD_VERSION__';
const assets = __PRECACHE__.map(path => new URL(path, self.registration.scope).href);
const shell = assets[0];
const known = new Set(assets);

self.addEventListener('install', event => {
    event.waitUntil(caches.open(version).then(cache => cache.addAll(assets)));
});

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        for (const key of await caches.keys()) {
            if (key.startsWith(prefix) && key !== version) await caches.delete(key);
        }
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', event => {
    const {request} = event;
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin) return;
    if (request.mode === 'navigate') {
        if (url.pathname !== new URL(shell).pathname &&
            url.pathname !== new URL('index.html', shell).pathname) return;
        // Use the HTML paired with this worker's assets until the next worker activates.
        event.respondWith(caches.open(version).then(async cache => (await cache.match(shell)) || fetch(request)));
        return;
    }
    url.hash = '';
    // The runtime's tiny audio probe also works with a complete response to a range request.
    if (known.has(url.href) && (!request.headers.has('Range') || url.pathname.endsWith('/empty.ogg'))) {
        event.respondWith(caches.open(version).then(async cache => (await cache.match(url.href)) || fetch(request)));
    }
});
