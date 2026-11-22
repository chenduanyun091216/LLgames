// This file is filled with the exact URLs of the generated build.
const prefix = `ttgames:${self.registration.scope}:`;
const version = prefix + '__BUILD_VERSION__';
const assets = __PRECACHE__.map(path => new URL(path, self.registration.scope).href);
const shell = assets[0];
const known = new Set(assets);
const navigationPaths = new Set(['./', 'index.html', 'play.html'].map(path => new URL(path, shell).pathname));

self.addEventListener('install', event => {
    event.waitUntil((async () => {
        const cache = await caches.open(version);
        await cache.addAll(assets);
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        for (const key of await caches.keys()) {
            if (key.startsWith(prefix) && key !== version) await caches.delete(key);
        }
        await self.clients.claim();
    })());
});

async function loadShell(request) {
    let response, failure;
    try {
        response = await fetch(request, {cache: 'no-cache'});
        if (response.status < 500) return response;
    } catch (error) {
        failure = error;
    }
    const cache = await caches.open(version);
    const cached = await cache.match(shell);
    if (cached || response) return cached || response;
    throw failure;
}

self.addEventListener('fetch', event => {
    const {request} = event;
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin) return;
    if (request.mode === 'navigate') {
        if (navigationPaths.has(url.pathname)) event.respondWith(loadShell(request));
        return;
    }
    url.hash = '';
    // The runtime's tiny audio probe also works with a complete response to a range request.
    if (known.has(url.href) && (!request.headers.has('Range') || url.pathname.endsWith('/empty.ogg'))) {
        event.respondWith(caches.open(version).then(async cache => (await cache.match(url.href)) || fetch(request)));
    }
});
