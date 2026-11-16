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
const offlineStatus = {};
const version = {hidden: true};
const workerEvents = {};
const worker = {state: 'installing', addEventListener: (event, callback) => { workerEvents[event] = callback; }};
const elements = {infobox: box, 'ttgames-loading': loading, progress: nativeProgress,
    'ttgames-fullscreen': button, 'ttgames-ui': canvas, 'ttgames-quality': quality,
    'ttgames-offline': offlineStatus, 'ttgames-version': version};
const observers = [];
const windowEvents = {};
const documentEvents = {};
let callback;
const viewportEvents = {};
const viewport = {offsetLeft: 0, offsetTop: 0, width: 390, height: 780,
    addEventListener: (event, handler) => { viewportEvents[event] = handler; }};
const viewportStyle = {setProperty(name, value) { this[name] = value; }};

const context = {window: {visualViewport: viewport, isSecureContext: true, localStorage: {getItem: key => storage.get(key),
    setItem: (key, value) => storage.set(key, value)},
    addEventListener: (event, handler) => { windowEvents[event] = handler; }},
    navigator: {serviceWorker: {register: async () => ({installing: worker})}}, console,
    getComputedStyle: () => ({getPropertyValue: name => ({
        '--quality-menu-width': '216px', '--quality-safe-right': '0px',
    })[name]}),
    requestAnimationFrame: fn => { callback = fn; },
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
function tick(time) { const fn = callback; fn(time); }
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
assert.strictEqual(progress.value, 100);
assert.strictEqual(percent.textContent, '100%');
assert.strictEqual(box.dataset.ready, '');
assert.notStrictEqual(loading.hidden, true);
const label = JSON.stringify([['FPS 30', 10, false, [255, 255, 255], 17, 97, 65, 13, 'left']]);
assert.strictEqual(version.hidden, true);
context.window.ttgamesDrawUI('[]', 480, 850, false, false, '', true);
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

// The opt-in meter measures both branches, including time between Python frames.
let frameTime = 0;
const frameStats = {style: {}};
context.window.location = {search: '?perf=1'};
context.performance = {now: () => frameTime};
context.document.createElement = () => frameStats;
context.document.body = {append() {}};
context.document.hidden = false;
vm.runInNewContext(fs.readFileSync('web/shell.js', 'utf8'), context);
for (let i = 0; i <= 60; i++) {
    frameTime = i * 1000 / 60;
    context.window.ttgamesRecordFrame('single');
}
assert.match(frameStats.textContent, /单人 · 60 FPS/);
assert.match(frameStats.textContent, /P95 16.7 \/ 最大 16.7 ms · >50ms 0/);
frameTime = 1100;
context.window.ttgamesRecordFrame('single');
for (let i = 1; i <= 54; i++) {
    frameTime = 1100 + i * 1000 / 60;
    context.window.ttgamesRecordFrame('single');
}
assert.match(frameStats.textContent, /最大 100.0 ms · >50ms 1/);
context.document.hidden = true;
documentEvents.visibilitychange();
frameTime = 10000;
context.window.ttgamesRecordFrame('lan');
context.document.hidden = false;
documentEvents.visibilitychange();
for (let i = 0; i <= 60; i++) {
    frameTime = 10000 + i * 1000 / 60;
    context.window.ttgamesRecordFrame('lan');
}
assert.match(frameStats.textContent, /联机 · 60 FPS/);
assert.match(frameStats.textContent, />50ms 0/);
