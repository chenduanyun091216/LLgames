const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const progress = {value: 0};
const status = {};
const percent = {};
const nativeProgress = {value: 0, max: 100, hasAttribute: () => true};
const loading = {querySelector: selector => ({progress, '.loading-status': status, '.loading-percent': percent})[selector]};
const box = {textContent: '', dataset: {}, addEventListener() {}, setAttribute() {}};
const button = {addEventListener() {}, toggleAttribute() {}};
const choices = [{value: '1.5', checked: true}, {value: '2'}];
const qualityHandlers = {};
const qualityAttributes = new Set();
const quality = {
    style: {setProperty(name, value) { this[name] = value; }},
    querySelectorAll: () => choices,
    querySelector: () => ({focus() {}}),
    addEventListener: (event, handler) => { qualityHandlers[event] = handler; },
    toggleAttribute(name, enabled) {
        if (enabled) qualityAttributes.add(name);
        else qualityAttributes.delete(name);
    },
};
const storage = new Map([['ttgames-render-density', '1']]);
const cleared = [];
const context2d = {
    setTransform() {},
    clearRect(...rect) { cleared.push(rect); },
    fillText() {},
};
const canvas = {clientWidth: 480, clientHeight: 850, style: {}, getContext: () => context2d};
const gameCanvas = {width: 971, height: 448, setAttribute(name, value) { this[name] = value; }};
const offlineStatus = {};
const version = {hidden: true, textContent: 'Web test-build'};
const workerEvents = {};
const worker = {state: 'installing', addEventListener: (event, callback) => { workerEvents[event] = callback; }};
const elements = {infobox: box, 'ttgames-loading': loading, progress: nativeProgress, canvas: gameCanvas,
    'ttgames-fullscreen': button, 'ttgames-ui': canvas, 'ttgames-quality': quality,
    'ttgames-offline': offlineStatus, 'ttgames-version': version};
const observers = [];
const windowEvents = {};
const documentEvents = {};
const refreshCallbacks = [];
let cacheRegistrations = 0;
const viewportEvents = {};
const viewport = {offsetLeft: 0, offsetTop: 0, width: 390, height: 780,
    addEventListener: (event, handler) => { viewportEvents[event] = handler; }};
const viewportStyle = {setProperty(name, value) { this[name] = value; }};

const context = {window: {visualViewport: viewport, isSecureContext: true, localStorage: {getItem: key => storage.get(key),
    setItem: (key, value) => storage.set(key, value)},
    addEventListener: (event, handler) => { windowEvents[event] = handler; }},
    navigator: {serviceWorker: {register: async () => {
        cacheRegistrations++;
        return {installing: worker};
    }}}, console,
    getComputedStyle: () => ({getPropertyValue: name => ({
        '--quality-menu-width': '216px', '--quality-safe-right': '0px',
    })[name]}),
    requestAnimationFrame: fn => refreshCallbacks.push(fn),
    document: {getElementById: id => elements[id], documentElement: {style: viewportStyle},
        addEventListener: (event, handler) => { documentEvents[event] = handler; }},
    MutationObserver: class { constructor(fn) { this.callback = fn; observers.push(this); } observe() {} }};
vm.runInNewContext(fs.readFileSync('web/shell.js', 'utf8'), context);
assert.strictEqual(viewportStyle['--loading-center-x'], '195px');
Object.assign(viewport, {width: 600, height: 270, offsetLeft: 32, offsetTop: 18});
viewportEvents.resize();
assert.strictEqual(viewportStyle['--loading-center-x'], '332px');
assert.strictEqual(viewportStyle['--loading-center-y'], '153px');
assert.strictEqual(viewportStyle['--loading-visible-width'], '600px');
assert.strictEqual(viewportStyle['--game-viewport-left'], '32px');
assert.strictEqual(viewportStyle['--game-viewport-top'], '18px');
assert.strictEqual(viewportStyle['--game-viewport-right'], '632px');
assert.strictEqual(viewportStyle['--game-viewport-bottom'], '288px');
viewport.offsetLeft = 0;
viewportEvents.scroll();
assert.strictEqual(viewportStyle['--loading-center-x'], '300px');
const touch = identifier => ({identifier});
windowEvents.touchstart({touches: [touch(7), touch(8)]});
assert(context.window.ttgamesTouchActive(7));
windowEvents.touchend({touches: [touch(8)]});
assert(!context.window.ttgamesTouchActive(7));
assert(context.window.ttgamesTouchActive(8));
windowEvents.touchcancel({touches: []});
assert(!context.window.ttgamesTouchActive(8));
windowEvents.touchstart({touches: [touch(9)]});
windowEvents.blur();
assert(!context.window.ttgamesTouchActive(9));
windowEvents.touchstart({touches: [touch(10)]});
context.document.hidden = true;
documentEvents.visibilitychange();
assert(!context.window.ttgamesTouchActive(10));
assert.strictEqual(context.window.ttgamesRenderDensity, 1.5);
quality.open = true;
qualityHandlers.change({target: choices[1]});
assert.strictEqual(context.window.ttgamesRenderDensity, 2);
assert.strictEqual(storage.get('ttgames-render-density'), '2');
assert.strictEqual(quality.open, false);
function tick(time) {
    for (const fn of refreshCallbacks.splice(0)) fn(time);
}
nativeProgress.value = 50;
observers[0].callback();
tick(0); tick(100);
assert(progress.value > 0 && progress.value < 15);
assert.strictEqual(percent.textContent, `约 ${Math.floor(progress.value)}%`);
const before = progress.value;
context.window.ttgamesLoadStage(1);
tick(200);
assert(progress.value > before && progress.value < 35);
context.window.ttgamesLoadStage(3);
for (let time = 300; time <= 60000; time += 100) tick(time);
assert(progress.value < 100);
box.textContent = 'Ready to start ! Please click/touch page';
observers[1].callback();
tick(60100);
assert.strictEqual(refreshCallbacks.length, 0);
assert.strictEqual(progress.value, 100);
assert.strictEqual(percent.textContent, '100%');
assert.strictEqual(box.dataset.ready, '');
assert.notStrictEqual(loading.hidden, true);
assert.strictEqual(gameCanvas['data-game-ready'], undefined);
const label = JSON.stringify([['FPS 30', 10, false, [255, 255, 255], 17, 97, 65, 13, 'left']]);
assert.strictEqual(version.hidden, true);
context.window.ttgamesDrawUI('[]', 480, 850, false, false, '', true);
assert.strictEqual(gameCanvas['data-game-ready'], '');
assert.strictEqual(version.hidden, false);
context.window.ttgamesDrawUI(label, 480, 850, true, false);
assert.strictEqual(version.hidden, true);
assert.strictEqual(quality.hidden, true);
context.window.ttgamesDrawUI(label, 480, 850, false, true);
assert.strictEqual(quality.hidden, false);
assert.strictEqual(loading.hidden, true);
viewport.offsetTop = 22;
viewportEvents.scroll();
assert.strictEqual(viewportStyle['--game-viewport-top'], '22px');
context.window.ttgamesDrawUI('[]', 480, 850, false, false);
assert.strictEqual(quality.hidden, true);
assert.deepStrictEqual(cleared, [[0, 0, 480, 850], [13, 93, 73, 21]]);
assert.strictEqual(quality.style['--quality-top'], '286px');
assert.strictEqual(quality.style['--pause-bottom'], '500px');
assert(!qualityAttributes.has('data-side'));
canvas.clientWidth = 844;
canvas.clientHeight = 390;
context.window.ttgamesDrawUI('[]', 960, 444, false, true);
assert.strictEqual(quality.style['--pause-right'], `${844 / 2 + 160 * 844 / 960}px`);
assert(qualityAttributes.has('data-side'));
context.window.ttgamesDrawUI('[]', 960, 444, false, false, 'opening');
assert.strictEqual(canvas.style.opacity, '0');
assert.strictEqual(canvas.style.transition, '');
context.window.ttgamesDrawUI('[]', 960, 444, false, false, 'ending');
assert.strictEqual(canvas.style.transition, 'opacity 460ms ease-out');
context.window.ttgamesDrawUI('[]', 960, 444, false, false);
assert.strictEqual(canvas.style.opacity, '1');

assert.match(offlineStatus.textContent, /正在自动保存/);
setImmediate(() => {
    worker.state = 'redundant';
    workerEvents.statechange();
    assert.match(offlineStatus.textContent, /保存失败/);
});

// The meter samples submitted frames using their timestamps.
let frameTime = 0;
const frameStats = {style: {}};
context.window.location = {search: '?perf=1'};
context.performance = {now: () => frameTime};
context.document.createElement = () => frameStats;
context.document.body = {append() {}};
context.document.hidden = false;
vm.runInNewContext(fs.readFileSync('web/shell.js', 'utf8'), context);
context.window.ttgamesDrawUI('[]', 480, 850, true, false);
assert.strictEqual(cacheRegistrations, 1);
function record(time, mode, resized = false) {
    frameTime = time;
    context.window.ttgamesRecordFrame(mode, resized);
}
for (let i = 0; i <= 60; i++) {
    tick(i * 1000 / 60);
    record(i * 1000 / 60, 'single');
}
assert.match(frameStats.textContent, /单人 · 60 FPS · 浏览器 rAF 60 Hz/);
assert.strictEqual(refreshCallbacks.length, 1);
assert.match(frameStats.textContent, /Web test-build/);
assert.match(frameStats.textContent, /P95 16.7 \/ 最大 16.7 ms · >50ms 0/);
record(1100, 'single');
for (let i = 1; i <= 54; i++) {
    record(1100 + i * 1000 / 60, 'single');
}
assert.match(frameStats.textContent, /最大 100.0 ms · >50ms 1/);
context.document.hidden = true;
documentEvents.visibilitychange();
record(10000, 'lan');
context.document.hidden = false;
documentEvents.visibilitychange();
for (let i = 0; i <= 60; i++) {
    tick(10000 + i * 1000 / 60);
    record(10000 + i * 1000 / 60, 'lan');
}
assert.match(frameStats.textContent, /联机 · 60 FPS · 浏览器 rAF 60 Hz/);
assert.match(frameStats.textContent, />50ms 0/);
record(14000, 'lan', true);
assert.strictEqual(frameStats.textContent, '');
for (let i = 1; i <= 60; i++) {
    const time = 14000 + i * 1000 / 60;
    tick(time);
    if (i % 2 === 0) record(time, 'lan');
}
assert.match(frameStats.textContent, /联机 · 30 FPS · 浏览器 rAF 60 Hz/);
assert.match(frameStats.textContent, />50ms 0/);
assert.strictEqual(refreshCallbacks.length, 1);

// The game can fill inset edges immediately after presenting.
let insetCallback;
context.ResizeObserver = class { constructor(fn) { insetCallback = fn; } observe() {} };
const paint = [];
let gameBounds = {left: 20, right: 824, top: 0, bottom: 370, width: 804, height: 370};
Object.assign(canvas, {clientWidth: 804, clientHeight: 370});
canvas.getBoundingClientRect = () => gameBounds;
context.navigator.platform = 'MacIntel';
context.navigator.maxTouchPoints = 5;
gameCanvas.style = {setProperty(key, value) { this[key] = value; }};
gameCanvas.toggleAttribute = (key, enabled) => gameCanvas[key] = enabled;
elements['ttgames-safe-area-fill'] = {
    clientWidth: 844, clientHeight: 390,
    getBoundingClientRect: () => ({left: 0, top: 0, width: 844, height: 390}),
    getContext: () => ({drawImage(...args) { paint.push(args); }}),
};
vm.runInNewContext(fs.readFileSync('web/shell.js', 'utf8'), context);
context.window.ttgamesSetSceneSize(640, 320, 960, 480);
assert.strictEqual(gameCanvas['data-scene-crop'], true);
assert.strictEqual(gameCanvas.style['--scene-scale-x'], 1.5);
assert.strictEqual(context.window.ttgamesViewportWidth, 804);
insetCallback();
context.window.ttgamesFillSafeArea();
assert.strictEqual(paint.length, 5);
assert(paint.some(call => call[1] === 639));
context.window.ttgamesSetSceneSize(960, 480, 960, 480);
assert.strictEqual(gameCanvas['data-scene-crop'], false);
gameBounds = {left: 0, right: 844, top: 0, bottom: 390, width: 844, height: 390};
Object.assign(canvas, {clientWidth: 844, clientHeight: 390});
insetCallback();
context.window.ttgamesFillSafeArea();
assert.strictEqual(paint.length, 5);
