const skills = [
    ['化岩冲锋'], ['裂颚骨刺', 480, 1260, 820], ['怒吼地裂', 620, 1280, 920]
];
const limit = (x, min, max) => Math.min(max, Math.max(min, x));
const radians = degrees => degrees * Math.PI / 180;

export function cannonMuzzle(world, side) {
    const {canvasWidth, height, offset} = world.view;
    const layout = canvasWidth >= height ? 'wide' : 'portrait';
    const [x, y] = world.data.TRENCH_CANNON.muzzles[layout][side];
    return {x: x * canvasWidth - offset, y: y * height};
}

export function fireTrenchCannon(world) {
    if (world.phase !== 'boss' || world.boss?.def.key !== 'boss_shieldfish' || world.time < world.cannonAt) return;
    const side = world.cannonSide;
    const {x, y} = cannonMuzzle(world, side);
    const direction = side === 0 ? 1 : -1;
    const kind = side === 0 ? 'fire' : 'ice';
    const layout = world.view.canvasWidth >= world.view.height ? 'wide' : 'portrait';
    for (const angle of world.data.TRENCH_CANNON.angles[layout]) {
        world.shot(x, y, Math.PI / 2 - direction * radians(angle), 5.4, null,
            {r: world.data.TRENCH_BOLT_RADIUS[kind], damage: side === 0 ? 2 : 1, fossil: kind});
    }
    world.cannonAt = world.time + world.data.TRENCH_CANNON.interval;
    world.cannonSide ^= 1;
}

export function trenchAttack(world, boss, pattern) {
    if (!boss.trenchOrder?.length) {
        const remaining = [0, 1, 2];
        const first = pattern === 0 ? 0 : remaining.filter(i => i !== boss.lastTrenchSkill)[Math.floor(world.random() * 2)];
        remaining.splice(remaining.indexOf(first), 1);
        boss.trenchOrder = [first];
        while (remaining.length) boss.trenchOrder.push(remaining.splice(Math.floor(world.random() * remaining.length), 1)[0]);
    }
    const index = boss.lastTrenchSkill = boss.trenchOrder.shift();
    const [label, ...timing] = skills[index];
    const [warning, active, recovery] = index === 0 ? world.data.TRENCH_ROLL_TIMING : timing;
    const {width, bottom} = world;
    const motion = {index, warning, active, start: world.time, recoveryAt: world.time + warning + active,
        x0: boss.x, y0: boss.y, x1: boss.x, y1: boss.y};
    boss.trench = motion;
    if (index === 0) {
        motion.y1 = world.view.height + boss.h * 1.15;
    } else if (index === 1) {
        for (let wave = 0; wave < 4; wave++) {
            world.later(warning + wave * 420, () => {
                const x = boss.x, y = boss.y + boss.h * .28;
                const angle = Math.atan2(world.player.y - y, world.player.x - x);
                for (const offset of [-7, 7]) world.shot(x, y, angle + radians(offset), 4.7, null,
                    {r: world.data.TRENCH_BOLT_RADIUS.bone * world.view.bossScale, fossil: 'bone'});
            });
        }
    } else {
        world.event('roar');
        const lanes = [0, 1, 2, 3, 4, 5, 6];
        for (let i = 0; i < 5; i++) {
            const lane = lanes.splice(Math.floor(world.random() * lanes.length), 1)[0];
            const x = width * (lane + .28 + world.random() * .44) / 7;
            const y = bottom * (1 - world.random() * .055);
            const w = Math.min(width / 8, 74 * world.view.bossScale);
            const h = bottom * (.24 + world.random() * .12);
            world.zone(x, y, w, h, world.tier === 0 ? 1 : 2, warning + i * 170, 540, null, {trenchSpire: true});
        }
    }
    return [label, warning + active + recovery];
}

export function shedTrenchArmor(world, boss) {
    boss.armorThreshold ??= .75;
    let wave = 0;
    while (boss.armorThreshold > 0 && boss.hp > 0 && boss.hp <= boss.maxHp * boss.armorThreshold) {
        boss.armorThreshold -= .25;
        for (let i = 0; i < 4; i++) world.shot(boss.x, boss.y, 0, 10.5, null, {
            r: world.data.TRENCH_BOLT_RADIUS.armor * world.view.bossScale, fossil: 'armor',
            orbit: {boss, phase: radians(i * 90 + wave * 26), until: world.time + 1000}
        });
        wave++;
    }
}

export function holdTrenchShard(shot, world) {
    const {player, time, width, bottom} = world;
    if (!shot.orbit) return false;
    const {boss, phase, until} = shot.orbit;
    const angle = phase + radians((1000 - until + time) * .18);
    shot.x = limit(boss.x + Math.sin(angle) * boss.w * .62, shot.r, width - shot.r);
    shot.y = limit(boss.y + Math.cos(angle) * boss.h * .47, shot.r, bottom - shot.r);
    if (time < until) return true;
    shot.angle = Math.atan2(player.y - shot.y, player.x - shot.x);
    shot.orbit = null;
    return false;
}

export function trenchSpireHeight(zone, time) {
    return zone.h * limit((time - zone.impact) / 135, 0, 1);
}

export function trenchSpireHits(zone, entity, time) {
    const height = trenchSpireHeight(zone, time);
    const bottom = entity.y + entity.h / 2;
    if (height <= 0 || entity.y - entity.h / 2 >= zone.y || bottom <= zone.y - height) return false;
    const widest = zone.w / 2 * Math.min(1, (bottom - zone.y + height) / height);
    return entity.x + entity.w / 2 > zone.x - widest && entity.x - entity.w / 2 < zone.x + widest;
}

export function trenchRolling(boss, time) {
    const s = boss.trench;
    return s?.index === 0 && time >= s.start + s.warning && time < s.recoveryAt;
}

export function updateTrenchBoss(boss, world) {
    const {time, width, player} = world;
    const s = boss.trench;
    if (s.index !== 0) return;
    if (trenchRolling(boss, time)) {
        if (s.targetX == null) {
            s.targetX = player.x;
            s.targetY = player.y;
            const run = s.targetY - s.y0;
            const exitX = run > 0 ? s.targetX + (s.targetX - s.x0) * (s.y1 - s.targetY) / run : s.targetX;
            s.x1 = limit(exitX, 0, width);
            const first = Math.hypot(s.targetX - s.x0, run);
            const remaining = Math.hypot(s.x1 - s.targetX, s.y1 - s.targetY);
            s.fraction = first / (first + remaining);
        }
        const at = (time - s.start - s.warning) / s.active;
        if (at < s.fraction) {
            const step = at / s.fraction;
            boss.x = s.x0 + (s.targetX - s.x0) * step;
            boss.y = s.y0 + (s.targetY - s.y0) * step;
        } else {
            const step = (at - s.fraction) / (1 - s.fraction);
            boss.x = s.targetX + (s.x1 - s.targetX) * step;
            boss.y = s.targetY + (s.y1 - s.targetY) * step;
        }
    } else if (time >= s.recoveryAt) {
        const at = (time - s.recoveryAt) / (boss.skillUntil - s.recoveryAt);
        const half = Math.min(width / 2, boss.w / 2);
        boss.x = limit(s.x1, half, width - half);
        boss.y = -boss.h / 2 + (boss.h + 48) * at;
    }
}

export function trenchFrame(boss, time) {
    const s = boss.trench;
    if (!s || time >= boss.skillUntil) return Math.floor(time / 132) % 6;
    const age = time - s.start;
    return 6 * [1, 2, 4][s.index] + (age < s.warning
        ? Math.min(5, Math.floor(age * 3 / s.warning))
        : 2 + Math.floor((age - s.warning) / 100) % 3);
}
