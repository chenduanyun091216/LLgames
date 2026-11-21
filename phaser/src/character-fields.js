import {controlLayout} from './touch-layout.js';

const tau = Math.PI * 2;
const fieldColors = {ice: 0xade7ff, water: 0x58ffe2, fire: 0xffab58, radiation: 0xd496ff};

export function drawCharacterFields(scene, world) {
    const {player, time, view} = world;
    const g = scene.effects;
    if (world.enemyFreezeUntil > time + .001) drawSnow(g, view, time);
    if (world.airWave) drawAirWave(g, view, world.airWave, time, world.data.characterFields.radiation.wave_ms);

    const {x, y, w, h} = player;
    const hits = world.fireShieldUntil > time + .001 ? world.fireShieldHits : 0;
    const active = Object.entries({
        ice: world.enemyFreezeUntil,
        water: world.swiftFieldUntil,
        fire: hits ? world.fireShieldUntil : 0,
        radiation: world.radiationFieldUntil,
    }).filter(([, until]) => until > time + .001);
    if (!active.length) return;

    const radius = Math.max(28, Math.round(Math.max(w, h) * .82));
    if (hits) {
        const size = Math.round(radius * 2.65);
        scene.sprite('field-fire', 'effects/fire_armor', x, y, size, size, 5);
    }
    const swift = world.swiftFieldUntil > time + .001;
    const waterRadius = radius + (hits ? Math.round(radius * .26) : 0);
    if (world.radiationFieldUntil > time + .001) {
        drawAura(g, x, y, waterRadius + (swift ? 14 : 0), time, 'radiation');
    }
    if (swift) drawAura(g, x, y, waterRadius, time, 'water');
    drawBadges(scene, view, x, y, radius, active, hits, time);
}

function drawSnow(g, {canvasWidth: width, height, offset}, time) {
    for (let i = 0; i < 96; i++) {
        const x = (i * 137 + time * .023 * (1 + i % 3)) % width - offset;
        const y = (i * 83 + time * .055 * (1 + i % 4)) % height;
        const radius = 2 + i % 4;
        g.fillStyle(0xe1faff, .71).fillCircle(x, y, radius);
        if (i % 5 === 0) {
            g.lineStyle(2, 0xebffff, .75);
            flakeArms(g, x, y, 8);
        }
    }
    g.fillStyle(0xaae6ff, .37).fillRect(-offset, 0, width, 5).fillRect(-offset, height - 5, width, 5);
    g.fillRect(-offset, 5, 5, height - 10).fillRect(width - offset - 5, 5, 5, height - 10);
}

function flakeArms(g, x, y, radius) {
    for (const [dx, dy] of [[radius, 0], [radius * .5, radius * .87], [-radius * .5, radius * .87]]) {
        g.lineBetween(x - dx, y - dy, x + dx, y + dy);
    }
}

function drawAura(g, x, y, radius, time, field) {
    const water = field === 'water';
    const color = fieldColors[field];
    const glow = water ? 0x16c4db : 0x812fff;
    const core = water ? 0xd1fff9 : 0xfcdeff;
    g.lineStyle(18, glow, .19).strokeCircle(x, y, radius);
    g.lineStyle(10, glow, .47).strokeCircle(x, y, radius);
    g.lineStyle(3, color, .88).strokeCircle(x, y, radius);
    g.lineStyle(1, color, .38).strokeCircle(x, y, radius - 7);
    const count = water ? 2 : 3;
    for (let i = 0; i < count; i++) {
        const angle = time * (water ? -.007 : .005) + i * tau / count;
        g.lineStyle(3, core, 1).beginPath();
        g.arc(x, y, radius - 1, angle - 1.15, angle).strokePath();
        const px = x + (radius - 1) * Math.cos(angle);
        const py = y + (radius - 1) * Math.sin(angle);
        if (water) {
            g.fillStyle(color, .61).fillCircle(px, py, 6);
            g.fillStyle(core, 1).fillCircle(px, py, 3);
        } else {
            g.fillStyle(core, .98).fillPoints([{x: px, y: py - 6}, {x: px + 4, y: py},
                {x: px, y: py + 6}, {x: px - 4, y: py}], true);
        }
    }
}

function drawBadges(scene, view, cx, cy, radius, active, hits, time) {
    const g = scene.effects;
    const w = 58, h = 23, gap = 3;
    const baseX = Math.max(4 - view.offset, Math.min(view.canvasWidth - view.offset - w - 4,
        Math.round(cx - radius * .42 - w)));
    const stackHeight = h + (active.length - 1) * (h + gap);
    const baseTop = Math.max(6, Math.round(cy - radius - stackHeight));
    let x = baseX, top = baseTop;
    if (view.entityScale < 1) {
        const buttons = Object.values(controlLayout(view));
        const rightLimit = Math.min(cx, view.canvasWidth - view.offset - 4);
        const obstruction = () => buttons.find(([bx, by, r]) =>
            x + view.offset < bx + r && x + w + view.offset > bx - r
                && top < by + r && top + stackHeight > by - r);
        let blocked;
        while (x + w <= rightLimit && (blocked = obstruction())) {
            x = blocked[0] + blocked[2] + gap - view.offset;
        }
        if (x + w > rightLimit) {
            x = baseX;
            while ((blocked = obstruction())) top = blocked[1] - blocked[2] - gap - stackHeight;
        }
    }
    let y = (top >= 6 ? top : baseTop) + stackHeight - h;
    for (const [field, until] of active) {
        const color = fieldColors[field];
        g.fillStyle(0x07101d, .94).fillRoundedRect(x, y, w, h, 6);
        g.lineStyle(1, color, .85).strokeRoundedRect(x, y, w, h, 6);
        drawIcon(g, field, x + 11, y + h / 2, color);
        const id = 'field-timer-' + field;
        let label = scene.objects.get(id);
        if (!label) {
            label = scene.add.text(0, 0, '', {fontFamily: 'Arial, sans-serif', fontSize: '16px',
                fontStyle: 'bold', color: '#f9fbff'}).setOrigin(.5).setDepth(8);
            scene.objects.set(id, label);
        }
        const seconds = (Math.ceil((until - time - .001) / 100) / 10).toFixed(1) + 's';
        label.setPosition(x + 36, y + h / 2 - (field === 'fire' ? 2 : 0));
        if (label.text !== seconds) label.setText(seconds);
        scene.live.add(id);
        if (field === 'fire') {
            g.fillStyle(color, 1);
            for (let i = 0; i < hits; i++) g.fillCircle(x + 36 + (2 * i - hits + 1) * 3, y + h - 4, 2);
        }
        y -= h + gap;
    }
}

function drawIcon(g, field, x, y, color) {
    g.lineStyle(2, color, 1);
    if (field === 'ice') {
        flakeArms(g, x, y, 6);
    } else if (field === 'water') {
        for (const shift of [-3, 2]) {
            g.strokePoints([{x: x + shift - 2, y: y - 5}, {x: x + shift + 2, y},
                {x: x + shift - 2, y: y + 5}]);
        }
    } else if (field === 'fire') {
        g.strokePoints([{x: x - 5, y: y - 5}, {x: x + 5, y: y - 5}, {x: x + 4, y: y + 2},
            {x, y: y + 6}, {x: x - 4, y: y + 2}], true);
    } else {
        g.fillStyle(color, 1).fillPoints([{x: x + 1, y: y - 7}, {x: x - 5, y: y + 1},
            {x, y: y + 1}, {x: x - 1, y: y + 7}, {x: x + 5, y: y - 2}, {x: x + 1, y: y - 2}], true);
    }
}

function drawAirWave(g, {canvasWidth, offset, height}, {x, y, started}, time, duration) {
    const progress = (time - started) / duration;
    if (progress < 0 || progress >= 1) return;
    const reach = Math.hypot(Math.max(x + offset, canvasWidth - x - offset), Math.max(y, height - y));
    const radius = 23 + reach * progress ** .86;
    const fade = (1 - progress) ** .7;
    if (progress < .3) g.fillStyle(0xdeccff, .41 * (1 - progress / .3)).fillCircle(x, y, radius / 3);
    for (const [shift, color, alpha, width] of [[0, 0x763bff, .24, 27], [-2, 0x9466ff, .56, 14],
        [-3, 0xdec8ff, .96, 7], [-3, 0xf6ffff, 1, 3], [-24, 0xa67cff, .72, 3], [-44, 0x83d0ff, .58, 2]]) {
        if (radius + shift > 0) g.lineStyle(width, color, alpha * fade).strokeCircle(x, y, radius + shift);
    }
    for (let i = 0; i < 24; i++) {
        const angle = i * tau / 24 + progress * .32;
        const dx = Math.cos(angle), dy = Math.sin(angle);
        const distance = radius + 9 + i % 4 * 4;
        const trail = distance - 8 - i % 3 * 8;
        const px = x + dx * distance, py = y + dy * distance;
        g.lineStyle(2 + i % 2, 0xc393ff, .63 * fade).lineBetween(x + dx * trail, y + dy * trail, px, py);
        g.fillStyle(0xf1f8ff, .97 * fade).fillCircle(px, py, 2 + i % 2);
    }
}
