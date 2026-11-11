import {Battle} from './battle.js';
import {fixedView, mobileView} from './layout.js';
import {campaignContent, homeContent} from './campaign-menu.js';
import {characters, controlLayout, weapons} from './touch-layout.js';
import {OceanScene, weaponImage} from './scene.js';

const $ = selector => document.querySelector(selector);
const screen = $('#screen');
const hud = $('#hud');
const controls = $('#controls');
const joystick = $('#joystick');
const stickArea = $('#stick-area');
const media = matchMedia('(pointer: coarse)');
const held = new Set();
const axes = {x: 0, y: 0};
let stickOrigin;
let stickId = null, fireId = null, skill = null, auto = false;
let scene, world, menuLoadout, data, manifest, selected = 1, tier = 0, page = 'loading', muted = false;
const customFields = [
    ['spawnStart', '初始刷怪间隔（毫秒）', 200, 4000, 100, 2400],
    ['minSpawn', '最小刷怪间隔（毫秒）', 100, 2000, 50, 1800],
    ['spawnDecrease', '每次击杀缩短（毫秒）', 0, 30, 1, 0],
    ['speed', '小怪移速倍率', .5, 3, .05, 1],
    ['weaponPrice', '武器价格倍率', .2, 3, .05, 1],
    ['characterPrice', '角色价格倍率', .2, 3, .05, 1],
    ['cooldown', '技能冷却倍率', .2, 3, .05, 1],
    ['rifle', '步枪每发金币', 0, 5, 1, 0],
    ['shotgun', '散弹每次金币', 0, 8, 1, 0],
    ['sniper', '狙击每发金币', 0, 8, 1, 0],
    ['hp', 'Boss 生命倍率', .3, 4, .05, 1],
    ['enemyMin', '小怪最短开火间隔（毫秒）', 1000, 10000, 250, 8000],
    ['enemyMax', '小怪最长开火间隔（毫秒）', 1500, 14000, 250, 12000],
    ['attack', 'Boss 出招间隔倍率', .5, 2.5, .05, 1],
    ['homing', 'Boss 追踪强度倍率', .5, 3, .05, 1],
];
const custom = Object.fromEntries(customFields.map(([key, , , , , value]) => [key, value]));
let shopTab = 'weapon', shopPreview = 'pistol';
let hudKey = '', notice = '', noticeUntil = 0, offline = '', download = false;
const touch = () => media.matches || navigator.maxTouchPoints > 0;
const currentView = () => touch() ? mobileView($('#app').clientWidth, $('#app').clientHeight)
    : fixedView(innerWidth < innerHeight);
const base = './';

function json(name) {
    return fetch(base + name).then(response => {
        if (!response.ok) throw new Error('无法读取 ' + name);
        return response.json();
    });
}

function panel(html, state, small = false) {
    page = state;
    screen.hidden = false;
    screen.classList.toggle('menu', ['menu', 'select', 'custom'].includes(state));
    screen.innerHTML = '<section class="panel' + (small ? ' narrow' : '')
        + (state === 'clear' ? ' stage-clear' : '') + '">' + html + '</section>';
    controls.hidden = true;
    clearInput();
    screen.querySelector('.primary, button')?.focus({preventScroll: true});
}

function button(action, label, primary = false) {
    return '<button type="button" data-action="' + action + '"' + (primary ? ' class="primary"' : '') + '>' + label + '</button>';
}

function menu() {
    scene?.clearWorld();
    scene?.playMusic('music-0');
    world = null;
    $('#app').style.removeProperty('--battle-art');
    hud.hidden = true;
    panel(homeContent(data, button, offline, download), 'menu');
}

function selectLevel() {
    panel(campaignContent(data, selected, tier, button), 'select');
}

function customPanel() {
    panel('<div class="bar"><h2>自定义难度</h2>' + button('select', '返回选关') + '</div>'
        + '<div class="options">' + customFields.map(([key, label, min, max, step]) =>
            '<label>' + label + '<input data-custom="' + key + '" type="number" required min="' + min
            + '" max="' + max + '" step="' + step + '" value="' + custom[key] + '"></label>').join('') + '</div>'
        + '<div class="row">' + button('start-custom', '按自定义设置出击', true) + '</div>', 'custom');
}

function skillNames() {
    if (world.character === 'player1') return ['渔夫手雷'];
    const names = data.characters[world.character].skills.map(s => s.name);
    if (world.character === 'radiation') names.push('辐射激光', '飞镖护盾');
    return names;
}

function updateHUD() {
    const b = world.boss;
    const labels = skillNames();
    const cooldowns = labels.map((_, index) => Math.max(0, Math.ceil((world.cooldowns[index] - world.time) / 1000)));
    const text = noticeUntil > performance.now() ? notice : world.phase === 'wave'
        ? 'Boss ' + Math.max(0, Math.ceil((40000 - world.time + world.started) / 1000)) + ' 秒后入场'
        : b?.skillUntil > world.time ? b.skill : '';
    const hp = b ? Math.ceil(b.hp) : 0;
    const key = JSON.stringify([world.level, world.hp, world.gold, world.lives, world.kills, world.score, world.weapon,
        world.character, b?.id, hp, text, auto, muted, cooldowns, world.round, world.weaponUpgrades]);
    if (key === hudKey) return;
    hudKey = key;
    const chapter = world.mode === 'endless' ? '无限 ' + (world.round * 11 + world.level) : '第 ' + world.level + ' 关';
    const difficulty = world.custom.ammo ? '自定义' : data.difficulty[world.tier].name;
    const boss = b ? '<div class="boss-card"><strong>' + b.def.name + ' · ' + hp + '/' + b.maxHp
        + '</strong><progress aria-label="Boss 生命" value="' + hp + '" max="' + b.maxHp + '"></progress><small>' + text + '</small></div>' : '';
    if (!hud.firstElementChild) {
        hud.innerHTML = '<div class="hud-card"></div><div class="hud-actions">'
            + button('auto', '自动') + button('shop', '商店') + button('pause', '暂停')
            + '</div><div class="hud-boss"></div>';
    }
    hud.querySelector('.hud-card').innerHTML = '<strong>' + chapter + ' · ' + world.stage.title + '</strong>难度 ' + difficulty + '<br><span class="hp">生命 '
        + world.hp + '/' + world.maxHp + '</span> · 金币 ' + world.gold + ' · 续关 ' + world.lives + '<br>'
        + data.weapons[world.weapon].name + ' · 击败 ' + world.kills + ' · ' + (b ? '得分 ' + world.score : text);
    hud.querySelector('[data-action="auto"]').textContent = '自动' + (auto ? '开' : '关');
    hud.querySelector('.hud-boss').innerHTML = boss;
    controls.querySelectorAll('[data-skill]').forEach(node => {
        const i = Number(node.dataset.skill);
        node.hidden = i >= 2 && !labels[i];
        node.disabled = !labels[i] || cooldowns[i] > 0;
        node.textContent = cooldowns[i] ? labels[i] + ' ' + cooldowns[i] : labels[i] ?? '技能二';
    });
    controls.querySelector('[data-control="auto"]').setAttribute('aria-pressed', String(auto));
    controls.querySelectorAll('[data-equip]').forEach(node => {
        const type = node.dataset.equip;
        const key = node.dataset.control;
        node.disabled = !world[type === 'weapon' ? 'weapons' : 'characters'].has(key)
            || (world.mode === 'endless' && key === 'pistol');
        node.setAttribute('aria-pressed', String(world[type] === key));
        if (type === 'weapon') {
            const level = world.weaponUpgrades[key];
            if (level) node.dataset.upgradeLevel = level;
            else delete node.dataset.upgradeLevel;
        }
    });
}

function resume() {
    page = 'playing';
    screen.hidden = true;
    controls.hidden = !touch();
    $('#app').classList.toggle('touch', touch());
    layoutControls();
    hud.hidden = false;
    hudKey = '';
    updateHUD();
}

async function loadWorld(next) {
    hud.hidden = true;
    panel('<p role="status">正在加载第 ' + next.level + ' 关 · ' + next.stage.title + '…</p>', 'loading', true);
    try {
        await scene.loadLevel(next, manifest);
        world = next;
        world.resize(currentView());
        $('#app').style.setProperty('--battle-art', 'url("./art/backgrounds/bg' + world.level + '.webp")');
        scene.showWorld(world);
        resume();
    } catch (error) {
        panel('<p role="alert">' + escapeText(error.message) + '</p><div class="row">' + button('menu', '返回首页') + '</div>', 'error', true);
    }
}

function escapeText(value) {
    return String(value).replace(/[&<>"']/g, key => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[key]);
}

function newRun(mode = 'campaign', settings = false) {
    auto = touch();
    showNotice('');
    const settingsData = settings ? {...custom, spawn: custom.spawnStart / 2400,
        enemyMin: Math.min(custom.enemyMin, custom.enemyMax), enemyMax: Math.max(custom.enemyMin, custom.enemyMax),
        ammo: {rifle: custom.rifle, shotgun: custom.shotgun, sniper: custom.sniper}} : {};
    const next = new Battle(data, {level: mode === 'endless' ? 1 : selected,
        tier: settings || mode === 'endless' ? 1 : tier, mode, custom: settingsData, view: currentView()});
    if (mode === 'campaign' && menuLoadout) {
        next.weapon = menuLoadout.weapon;
        next.character = menuLoadout.character;
        next.weapons = new Set(menuLoadout.weapons);
        next.weaponUpgrades = {...menuLoadout.weaponUpgrades};
        next.characters = new Set(menuLoadout.characters);
        next.startLevel(next.level);
    }
    return loadWorld(next);
}

function pause() {
    panel('<h2>游戏暂停</h2><div class="row">' + button('resume', '继续游戏', true)
        + button('mute', muted ? '打开声音' : '关闭声音') + button('menu', '返回首页') + '</div>', 'pause', true);
}

const weaponDescriptions = {pistol: '基础单发', rifle: '连续射击', shotgun: '扇形散射', sniper: '高伤害单发'};
const skillDescriptions = {
    ice: ['拦截敌弹，破碎时减速周围敌人。', '扇形发射冰球，冻结小怪、减速首领。'],
    water: ['恢复生命。', '短时间提高移动速度和射速。'],
    fire: ['挡住敌人与可拦截的子弹。', '发射火球和会爆炸的火箭。'],
    radiation: ['电击附近多个目标。', '吸附弹幕并爆发范围伤害。',
        '发射持续光束，再次触发可横扫。', '飞镖环绕拦截子弹，结束后向外飞出。'],
};

function shop(returnTo = 'playing', message = '') {
    const isWeapon = shopTab === 'weapon';
    const keys = isWeapon ? weapons : characters;
    const definitions = isWeapon ? data.weapons : data.characters;
    const owned = isWeapon ? world.weapons : world.characters;
    if (!keys.includes(shopPreview)) shopPreview = keys[0];
    const status = key => key === world[shopTab] ? '已装备' : owned.has(key) ? '已购' : world.price(shopTab, key) + ' 金币';
    const image = key => isWeapon ? weaponImage(key, 'ui/weapon_showcase') : 'players/player_' + key;
    const selected = definitions[shopPreview];
    const skillLabels = isWeapon ? [] : selected.skills.map(skill => skill.name);
    if (shopPreview === 'radiation') skillLabels.push('辐射激光', '飞镖护盾');
    const description = isWeapon ? '<p>' + weaponDescriptions[shopPreview] + '</p>' : '<ul>'
        + skillLabels.map((name, index) => '<li><strong>' + name + '</strong>'
            + skillDescriptions[shopPreview][index] + '</li>').join('') + '</ul>';
    const shelves = ['weapon', 'character'].map(type => {
        const gear = type === 'weapon';
        const items = (gear ? weapons : characters).map(key => {
            const equipped = key === world[type];
            const purchased = (gear ? world.weapons : world.characters).has(key);
            const label = equipped ? '已装备' : purchased ? '已购' : world.price(type, key) + ' 金币';
            const sprite = gear ? weaponImage(key) : 'players/player_' + key;
            const item = (gear ? data.weapons : data.characters)[key];
            const level = gear ? world.weaponUpgrades[key] ?? 0 : 0;
            const upgrade = gear ? world.upgradePrice(key) : null;
            return '<div><button type="button" data-action="equip-' + type + '-' + key
                + '" data-return="' + returnTo + '" aria-pressed="' + equipped + '"><img alt="" src="./art/'
                + sprite + '.webp"><strong>' + item.name + (level ? ' Lv.' + level : '') + '</strong><small class="'
                + (equipped ? 'equipped' : purchased ? 'owned' : '') + '">' + label + '</small></button>'
                + (upgrade === null ? '' : '<button class="shop-upgrade" type="button" data-action="upgrade-' + key
                    + '" data-return="' + returnTo + '">加强 ' + upgrade + '</button>')
                + (gear ? '' : '<button type="button" data-action="preview-' + key
                    + '" data-return="' + returnTo + '">看技能</button>') + '</div>';
        }).join('');
        return '<section class="shop-shelf"><h3>' + (gear ? '装备' : '角色') + '</h3><div class="shop">' + items + '</div></section>';
    }).join('');
    const back = returnTo === 'clear' ? 'clear' : returnTo === 'select' ? 'shop-menu-close' : 'resume';
    panel('<div class="bar"><h2>商店</h2><span class="shop-gold"><img src="./art/ui/coin.webp" alt="金币">' + world.gold + '</span>'
        + button(back, '×') + '</div>' + shelves
        + '<div class="shop-feature"><div><h3>' + selected.name + '</h3>' + description
        + '<p class="shop-price" role="status">' + (message || status(shopPreview)) + '</p></div>'
        + '<img alt="" src="./art/' + image(shopPreview) + '.webp"></div>', 'shop');
}

function results() {
    const phase = world.phase;
    if (phase === 'defeat') {
        panel('<h2>出击失败</h2><p>' + escapeText(world.reason) + ' · 得分 ' + world.score + '</p><div class="row">'
            + (world.lives ? button('revive', '续关 · 剩余 ' + world.lives, true) : '')
            + button('retry', '重打本关') + button('menu', '返回首页') + '</div>', 'defeat', true);
    } else {
        const completed = world;
        const finished = phase === 'victory';
        if (finished) {
            panel('<h2>战役胜利</h2><p>得分 ' + world.score + ' · 金币 ' + world.gold + '</p><div class="row">'
                + button('menu', '返回首页') + '</div>', phase, true);
        } else {
            const next = world.level % world.data.levels.length;
            const reward = world.data.CAMPAIGN_REWARDS[world.level - 1];
            panel('<div class="clear-readout"><span class="clear-radar" aria-hidden="true">✓</span><div>'
                + '<p>第 ' + world.level + ' 关 · ' + escapeText(world.stage.title) + '</p><h2>关卡通过</h2>'
                + '<p>奖励 <strong>+' + reward + '</strong> 金币</p></div></div>'
                + '<p class="clear-next">' + (world.mode === 'campaign' ? '即将进入' : '下一关') + '第 ' + (next + 1)
                + ' 关 · ' + escapeText(world.data.levels[next].title) + '</p>'
                + '<p>得分 ' + world.score + ' · 金币 ' + world.gold + '</p><div class="row">'
                + button('next', '下一关', true) + button('shop-clear', '装备商店') + '</div>', phase, true);
        }
        if (world.mode === 'campaign') setTimeout(() => {
            if (world !== completed || page !== phase) return;
            if (finished) menu();
            else {
                world.next();
                loadWorld(world);
            }
        }, finished ? 4000 : 2000);
    }
}

function showNotice(message) {
    notice = message;
    noticeUntil = performance.now() + 2200;
}

async function saveOffline() {
    if (download) return;
    if (!navigator.serviceWorker || !isSecureContext) {
        offline = '请通过 HTTPS 或本机 localhost 保存离线资源';
        return menu();
    }
    download = true;
    offline = '准备保存离线资源…';
    menu();
    try {
        await navigator.serviceWorker.register('./sw.js');
        const {active} = await navigator.serviceWorker.ready;
        const channel = new MessageChannel();
        channel.port1.onmessage = ({data: progress}) => {
            if (progress.done || progress.error) {
                download = false;
                offline = progress.error ?? '离线资源已保存，可在同一浏览器重新打开';
                channel.port1.close();
            } else offline = '正在保存 ' + Math.round(progress.progress * 100) + '%';
            if (page === 'menu') menu();
        };
        active.postMessage('download', [channel.port2]);
    } catch {
        download = false;
        offline = '离线资源保存失败';
        if (page === 'menu') menu();
    }
}

$('#app').addEventListener('click', event => {
    const node = event.target.closest('[data-action]');
    const quick = event.target.closest('[data-equip]');
    if (quick && page === 'playing') {
        world.equip(quick.dataset.equip, quick.dataset.control);
        updateHUD();
    }
    if (!node) return;
    const action = node.dataset.action;
    if (action.startsWith('level-')) {
        selected = Number(action.slice(6));
        selectLevel();
        screen.querySelector('[data-action="' + action + '"]')?.focus();
        return;
    }
    if (action.startsWith('tier-')) {
        tier = Number(action.slice(5));
        selectLevel();
        screen.querySelector('[data-action="' + action + '"]')?.focus();
        return;
    }
    if (action.startsWith('preview-')) {
        shopTab = 'character';
        shopPreview = action.slice(8);
        shop(node.dataset.return);
        return;
    }
    if (action.startsWith('upgrade-')) {
        shopTab = 'weapon';
        shopPreview = action.slice(8);
        const success = world.upgradeWeapon(shopPreview);
        shop(node.dataset.return, success ? '已加强至 Lv.' + world.weaponUpgrades[shopPreview] : '金币不足');
        return;
    }
    if (action.startsWith('equip-')) {
        const [, type, id] = action.split('-');
        shopTab = type;
        shopPreview = id;
        shop(node.dataset.return, world.equip(type, id) ? '已装备' : '金币不足');
        if (page === 'shop' && node.dataset.return !== 'select') updateHUD();
        return;
    }
    switch (action) {
    case 'menu': menu(); break;
    case 'select': selectLevel(); break;
    case 'custom': customPanel(); break;
    case 'start': newRun(); break;
    case 'start-custom':
        for (const input of screen.querySelectorAll('[data-custom]')) {
            if (!input.reportValidity()) return;
            custom[input.dataset.custom] = input.valueAsNumber;
        }
        newRun('campaign', true);
        break;
    case 'endless': newRun('endless'); break;
    case 'resume': resume(); break;
    case 'pause': pause(); break;
    case 'shop': shop(); break;
    case 'shop-menu':
        menuLoadout ??= new Battle(data, {tier});
        menuLoadout.tier = tier;
        world = menuLoadout;
        shop('select');
        break;
    case 'shop-menu-close': world = null; selectLevel(); break;
    case 'shop-clear': shop('clear'); break;
    case 'clear': results(); break;
    case 'auto': auto = !auto; updateHUD(); break;
    case 'mute': muted = !muted; scene.sound.mute = muted; pause(); break;
    case 'revive': if (world.revive()) resume(); break;
    case 'retry': world.retry(); loadWorld(world); break;
    case 'next': world.next(); loadWorld(world); break;
    case 'offline': saveOffline(); break;
    }
});

function clearInput() {
    held.clear();
    axes.x = axes.y = 0;
    stickId = fireId = null;
    skill = null;
    joystick.style.removeProperty('left');
    joystick.style.removeProperty('top');
    joystick.firstElementChild.style.transform = '';
}

function controlsInput() {
    const on = (...codes) => codes.some(code => held.has(code));
    const dx = Number(on('ArrowRight', 'KeyD')) - Number(on('ArrowLeft', 'KeyA'));
    const dy = Number(on('ArrowDown', 'KeyS')) - Number(on('ArrowUp', 'KeyW'));
    const input = {x: dx || dy ? dx : axes.x, y: dx || dy ? dy : axes.y,
        fire: auto || fireId !== null || on('KeyJ'), skill};
    skill = null;
    return input;
}

window.addEventListener('keydown', event => {
    if (event.code === 'Escape' && world && (page === 'pause' || page === 'playing')) {
        event.preventDefault();
        if (!event.repeat) page === 'pause' ? resume() : pause();
        return;
    }
    if (page !== 'playing' || event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.code;
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'KeyJ', 'KeyK', 'KeyL', 'KeyW', 'KeyA', 'KeyS', 'KeyD'].includes(key)) {
        event.preventDefault();
        held.add(key);
    }
    if (!event.repeat) {
        if (key === 'KeyT') { auto = !auto; updateHUD(); }
        if (key === 'KeyH') pause();
        if (key === 'KeyK') skill = 0;
        if (key === 'KeyL') skill = 1;
        if (key === 'Space' && world.character === 'radiation') skill = 2;
        if (key === 'KeyR' && world.character === 'radiation') skill = 3;
        if (key === 'KeyB') shop();
        if (key === 'KeyQ' || key === 'KeyE') {
            const owned = weapons.filter(id => world.weapons.has(id) && !(world.mode === 'endless' && id === 'pistol'));
            const step = key === 'KeyQ' ? -1 : 1;
            world.equip('weapon', owned[(owned.indexOf(world.weapon) + step + owned.length) % owned.length]);
        }
        const character = characters[['Digit1', 'Digit2', 'Digit3', 'Digit4'].indexOf(key)];
        if (character && world.characters.has(character)) world.equip('character', character);
    }
});
window.addEventListener('keyup', event => held.delete(event.code));
window.addEventListener('blur', clearInput);
document.addEventListener('visibilitychange', () => {
    clearInput();
    if (document.hidden && page === 'playing') pause();
});
window.addEventListener('resize', () => {
    if (!world || scene.world !== world) return;
    world.resize(currentView());
    scene.resizeWorld();
    scene.renderWorld();
    layoutControls();
});

function layoutControls() {
    if (!world || !touch()) return;
    const view = world.view;
    const positions = controlLayout(view);
    const ratio = controls.clientWidth / view.canvasWidth;
    if (!ratio) return;
    for (const node of controls.querySelectorAll('[data-control]')) {
        const [x, y, radius] = positions[node.dataset.control];
        node.style.left = x * ratio + 'px';
        node.style.top = y * ratio + 'px';
        node.style.setProperty('--control-size', 2 * radius * ratio + 'px');
    }
    stickArea.style.setProperty('--stick-size', (view.height < 500 ? 92 : 128) * ratio + 'px');
}

function moveStick(event) {
    const ratio = controls.clientWidth / world.view.canvasWidth;
    const dx = (event.clientX - stickOrigin.x) / ratio;
    const dy = (event.clientY - stickOrigin.y) / ratio;
    const radius = (world.view.height < 500 ? 46 : 64) - 16;
    const distance = Math.hypot(dx, dy);
    const strength = Math.min(1, Math.max(0, (distance - 2) / (radius * .5 - 2)));
    axes.x = distance ? dx / distance * strength : 0;
    axes.y = distance ? dy / distance * strength : 0;
    joystick.firstElementChild.style.transform = 'translate(' + (axes.x * radius * ratio)
        + 'px,' + (axes.y * radius * ratio) + 'px)';
}

stickArea.addEventListener('pointerdown', event => {
    if (stickId !== null) return;
    stickId = event.pointerId;
    stickOrigin = {x: event.clientX, y: event.clientY};
    const rect = stickArea.getBoundingClientRect();
    joystick.style.left = event.clientX - rect.left + 'px';
    joystick.style.top = event.clientY - rect.top + 'px';
    stickArea.setPointerCapture(event.pointerId);
});
stickArea.addEventListener('pointermove', event => {
    if (stickId === event.pointerId) moveStick(event);
});
for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    stickArea.addEventListener(type, event => {
        if (stickId !== event.pointerId) return;
        stickId = null;
        axes.x = axes.y = 0;
        joystick.style.removeProperty('left');
        joystick.style.removeProperty('top');
        joystick.firstElementChild.style.transform = '';
    });
    $('#fire').addEventListener(type, event => {
        if (fireId === event.pointerId) fireId = null;
    });
}
$('#fire').addEventListener('pointerdown', event => {
    if (fireId !== null) return;
    fireId = event.pointerId;
    event.currentTarget.setPointerCapture(event.pointerId);
});
controls.querySelectorAll('[data-skill]').forEach(node =>
    node.addEventListener('pointerdown', () => { skill = Number(node.dataset.skill); }));

try {
    [data, manifest] = await Promise.all([json('campaign.json'), json('assets.json')]);
    $('#loadout').innerHTML = [
        ...weapons.map(key => [key, 'weapon', data.weapons[key].name, weaponImage(key)]),
        ...characters.map(key => [key, 'character', data.characters[key].name, 'players/player_' + key]),
    ].map(([key, type, label, image]) => '<button type="button" data-control="' + key
        + '" data-equip="' + type + '" aria-label="' + label + '"><img src="./art/' + image + '.webp" alt=""></button>').join('');
    const ocean = new OceanScene();
    ocean.hooks = {ready: created => { scene = created; menu(); },
        paused: () => page !== 'playing', input: controlsInput, notice: showNotice,
        frame: battle => {
            if (['defeat', 'clear', 'victory'].includes(battle.phase)) results();
            updateHUD();
        }};
    new Phaser.Game({type: Phaser.AUTO, parent: 'game', backgroundColor: '#071825', width: 960, height: 720,
        scene: ocean, scale: {mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH}, input: {keyboard: false}});
} catch (error) {
    panel('<p role="alert">' + escapeText(error.message) + '</p><div class="row"><button type="button" onclick="location.reload()">重试</button></div>', 'error', true);
}
