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
const choices = [{value: '1'}, {value: '1.5', checked: true}, {value: '2'}];
const qualityHandlers = {};
const quality = {
    style: {},
    querySelectorAll: () => choices,
    querySelector: () => ({focus() {}}),
    addEventListener: (event, handler) => { qualityHandlers[event] = handler; },
    toggleAttribute() {},
};
const storage = new Map();
const cleared = [];
const context2d = {
    setTransform() {},
    clearRect(...rect) { cleared.push(rect); },
    fillText() {},
};
const canvas = {clientWidth: 480, clientHeight: 850, getContext: () => context2d};
const offlineStatus = {};
const workerEvents = {};
const worker = {state: 'installing', addEventListener: (event, callback) => { workerEvents[event] = callback; }};
const elements = {infobox: box, 'ttgames-loading': loading, progress: nativeProgress,
    'ttgames-fullscreen': button, 'ttgames-ui': canvas, 'ttgames-quality': quality,
    'ttgames-offline': offlineStatus};
const observers = [];
let callback;
const context = {window: {isSecureContext: true, localStorage: {getItem: key => storage.get(key),
    setItem: (key, value) => storage.set(key, value)}},
    navigator: {serviceWorker: {register: async () => ({installing: worker})}}, console,
    requestAnimationFrame: fn => { callback = fn; },
    document: {getElementById: id => elements[id], documentElement: {}, addEventListener() {}},
    MutationObserver: class { constructor(fn) { this.callback = fn; observers.push(this); } observe() {} }};
vm.runInNewContext(fs.readFileSync('web/shell.js', 'utf8'), context);
assert.strictEqual(context.window.ttgamesRenderDensity, 1.5);
quality.open = true;
qualityHandlers.change({target: choices[2]});
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
context.window.ttgamesDrawUI(label, 480, 850, true, false);
assert.strictEqual(quality.hidden, true);
context.window.ttgamesDrawUI(label, 480, 850, false, true);
assert.strictEqual(quality.hidden, false);
assert.strictEqual(loading.hidden, true);
context.window.ttgamesDrawUI('[]', 480, 850, false, false);
assert.strictEqual(quality.hidden, true);
assert.deepStrictEqual(cleared, [[0, 0, 480, 850], [13, 93, 73, 21]]);

assert.match(offlineStatus.textContent, /正在自动保存/);
setImmediate(() => {
    worker.state = 'redundant';
    workerEvents.statechange();
    assert.match(offlineStatus.textContent, /保存失败/);
});
