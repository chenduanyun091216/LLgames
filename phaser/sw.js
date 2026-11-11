const prefix = 'ttgames-phaser:' + self.registration.scope + ':';

self.addEventListener('install', event => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('message', event => {
    if (event.data !== 'download' || !event.ports[0]) return;
    const port = event.ports[0];
    event.waitUntil((async () => {
        let name;
        try {
            const response = await fetch('./offline.json', {cache: 'no-store'});
            if (!response.ok) throw new Error('无法读取资源清单');
            const {version, files} = await response.json();
            name = prefix + version;
            const complete = new URL('__complete__', self.registration.scope);
            const cache = await caches.open(name);
            if (!await cache.match(complete)) {
                for (let i = 0; i < files.length; i += 8) {
                    await cache.addAll(files.slice(i, i + 8).map(file =>
                        new Request(new URL(file, self.registration.scope), {cache: 'reload'})));
                    port.postMessage({progress: Math.min(files.length, i + 8) / files.length});
                }
                await cache.put(complete, new Response(version));
            }
            for (const key of await caches.keys()) if (key.startsWith(prefix) && key !== name) await caches.delete(key);
            port.postMessage({done: true});
        } catch {
            if (name) await caches.delete(name);
            port.postMessage({error: '离线资源保存失败，请联网重试'});
        }
    })());
});

self.addEventListener('fetch', event => {
    const {request} = event;
    if (request.method !== 'GET' || !request.url.startsWith(self.registration.scope)) return;
    event.respondWith(fetch(request).catch(async () => {
        for (const key of (await caches.keys()).reverse()) {
            if (!key.startsWith(prefix)) continue;
            const cache = await caches.open(key);
            if (!await cache.match(new URL('__complete__', self.registration.scope))) continue;
            const found = await cache.match(request, {ignoreSearch: request.mode === 'navigate'});
            if (found) return found;
        }
        return Response.error();
    }));
});
