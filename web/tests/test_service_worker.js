const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const scope = 'https://ttgames.test/';
const source = fs.readFileSync('web/sw.js', 'utf8')
    .replace('__BUILD_VERSION__', 'new')
    .replace('__PRECACHE__', JSON.stringify(['./', 'shell-new.js']));

function worker(fetch, addAll = async () => {}) {
    const listeners = new Map(), events = [];
    const cachedPage = {status: 200, body: 'cached page'};
    const cachedScript = {status: 200, body: 'cached script'};
    const cached = new Map([[scope, cachedPage], [scope + 'shell-new.js', cachedScript]]);
    vm.runInNewContext(source, {
        URL, fetch,
        self: {
            registration: {scope}, location: {origin: new URL(scope).origin},
            addEventListener(type, handle) { listeners.set(type, handle); },
            skipWaiting() { events.push('skipWaiting'); },
        },
        caches: {
            async open() {
                return {addAll, async match(url) { return cached.get(url); }};
            },
        },
    });
    return {
        cachedPage, cachedScript, events,
        install() {
            let result;
            listeners.get('install')({waitUntil(value) { result = value; }});
            return result;
        },
        request(path, mode = 'navigate') {
            let result;
            listeners.get('fetch')({
                request: {url: new URL(path, scope).href, mode, method: 'GET', headers: new Map()},
                respondWith(value) { result = value; },
            });
            return result;
        },
    };
}

test('online navigation gets the current HTML even with an older cached page', async () => {
    const paths = [], networkPage = {status: 200, body: 'server page'};
    const instance = worker(async (request, init) => {
        assert.equal(init.cache, 'no-cache');
        paths.push(new URL(request.url).pathname);
        return networkPage;
    });
    for (const path of ['/?perf=1', '/index.html', '/play.html?room=1234']) {
        assert.equal(await instance.request(path), networkPage);
    }
    assert.deepEqual(paths, ['/', '/index.html', '/play.html']);
    assert.equal(await instance.request('/shell-new.js', 'same-origin'), instance.cachedScript);
});

test('offline navigation and temporary server failure use the complete cached page', async () => {
    for (const fetch of [async () => { throw Error('offline'); }, async () => ({status: 503})]) {
        const instance = worker(fetch);
        assert.equal(await instance.request('/'), instance.cachedPage);
        assert.equal(await instance.request('/play.html'), instance.cachedPage);
    }
});

test('the replacement worker activates only after the offline package is cached', async () => {
    let completed;
    const pending = new Promise(resolve => { completed = resolve; });
    const instance = worker(null, () => pending);
    const installing = instance.install();
    assert.deepEqual(instance.events, []);
    completed();
    await installing;
    assert.deepEqual(instance.events, ['skipWaiting']);

    const failed = worker(null, async () => { throw Error('cache failed'); });
    await assert.rejects(failed.install(), /cache failed/);
    assert.deepEqual(failed.events, []);
});
