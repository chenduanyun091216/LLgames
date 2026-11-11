// Boss timelines use milliseconds. Collision uses the same geometry as each warning.
const mix = (a, b, n) => a + (b - a) * n;
const between = (world, left, right) => mix(left, right, world.random());

function target(world, offset = 0) {
    return Math.max(28, Math.min(world.width - 28, world.player.x + offset));
}

function aimed(world, x, y) {
    return Math.atan2(world.player.y - y, world.player.x - x);
}

export const bubbleColors = ['sky-blue', 'lavender', 'amber', 'rose', 'mint', 'gold', 'indigo', 'orchid'];

export function attack(world, boss, pattern) {
    const {width, bottom, tier} = world;
    const {x, y, level} = boss;
    const mouth = y + boss.h * .30;
    const warning = [1050, 900, 750][tier];
    const lane = (at, w, damage, wait = warning, active = 420, art = null, extra = {}) =>
        world.zone(at, (bottom + 32) / 2, w, bottom + 32, damage, wait, active, art, extra);
    const ring = (cx, cy, r, damage, wait = warning, active = 300, art = null) =>
        world.zone(cx, cy, r * 2, r * 2, damage, wait, active, art, {circle: true});
    const fan = (count, spread, speed, art, extra = {}, wait = 0, fromX = x, fromY = mouth, angle = Math.PI / 2) => {
        world.later(wait, () => {
            for (let i = 0; i < count; i++) {
                const theta = angle + (count === 1 ? 0 : mix(-spread, spread, i / (count - 1)));
                world.shot(fromX, fromY, theta, speed, art, extra);
            }
        });
    };

    // Standard shots are interleaved with each early boss's signature attack.
    if (level >= 2 && level <= 6 && pattern % 4 === 3) {
        lane(target(world), level === 6 ? 72 : 38, level === 6 ? 2 : 1, warning, 1100, null, {sway: level * 4});
        return ['深海激光', warning + 1100];
    }
    if (level <= 6 && pattern % 2 === 1) {
        const art = level === 4 ? 'boss_trident_gold' : level === 5 ? 'boss_dragon_fireball' : 'bubble_crab';
        fan(Math.min(boss.def.projectile_count, [2, 3, 5][tier]), .37, 2.7, art,
            {homing: level >= 4 ? .011 * world.custom.homing : 0}, 300, x, mouth, aimed(world, x, mouth));
        return ['散射', 800];
    }
    switch (level) {
    case 1: {
        const launch = Math.max(32, Math.min(world.player.y - 48, mouth));
        for (const side of [-1, 1]) {
            const x = target(world, 46 * side);
            world.zone(x, launch, 78, 78, 1, side === 1 ? 240 : 0, 990, 'boss_claw', {
                circle: true, safeFor: 110, claw: side,
                trajectory: age => ({y: launch + (bottom + 150 - launch) * (age / 990) ** 1.25}),
            });
        }
        return ['赤钳合击', 1280];
    }
    case 2:
        for (const side of [-1, 1]) {
            const cx = x + side * Math.min(48, boss.w * .3);
            const cy = bottom * .5;
            world.zone(cx, mouth, 90, 90, 0, 0, 860, side < 0 ? 'bubble_crab' : 'bubble_crab_red', {
                circle: true, artOnly: true, trajectory: age => ({y: mix(mouth, cy, age / 860)}),
            });
            world.later(860, () => world.spawnEnemy('crab', {
                x: cx, y: cy, hp: boss.maxHp * [.15, .20, .25][tier], speed: 1.9,
                chases: true, contactAt: world.time + 450, tint: side < 0 ? 0xff738f : 0xffdf79,
            }));
        }
        return ['潮汐横扫', 1260];
    case 3:
        world.zone(x, y, 0, 0, 1, 0, 2040, null, {
            tentacles: true, targetX: world.player.x, targetY: world.player.y,
        });
        return ['墨涌陷阱', 2040];
    case 4:
        for (let i = 0; i < 3; i++) {
            world.later(220 * i, () => {
                const start = Math.max(32, Math.min(mouth, world.player.y - 48));
                const speed = Math.max(.70, (world.view.height - start + 100) / 780);
                world.zone(world.player.x, start, 12, 82, 2, 0, 1320 - 220 * i,
                    i % 2 ? 'boss_trident_red' : 'boss_trident_gold',
                    {artOnly: true, trajectory: age => ({y: start + age * speed})});
            });
        }
        return ['猎潮突进', 1320];
    case 5:
        for (let i = 0; i < 10; i++) world.later(i * 400, () => world.shot(boss.x,
            boss.y + boss.h * .15, Math.PI / 2, 5.5, 'boss_dragon_fireball', {r: 18, blast: 55, dragon: true}));
        return ['火龙突击', 4000];
    case 6:
        boss.rush = {start: world.time, x, y, targetX: world.player.x};
        return ['深渊封潮', 5244];
    case 7:
        switch (pattern % 4) {
        case 0:
            fan(2, .22, 5, 'boss_niu_slam_axe', {r: 25, returns: 1, spin: true, damage: 2},
                250, x, mouth, aimed(world, x, mouth));
            return ['回旋战斧', 1800];
        case 1:
            lane(target(world), 100, 2, warning, 650, 'boss_niu_slam_axe');
            return ['巨斧震地', warning + 750];
        case 2:
            for (const offset of [-150, 0, 150]) lane(target(world, offset), 65, 2, warning, 1250);
            return ['三重雷击', warning + 1250];
        default:
            fan(6, .71, 3.7, 'boss_trident_red', {}, 300);
            return ['六向弹幕', 850];
        }
    case 8:
        switch (pattern % 4) {
        case 0:
            fan(3, .39, 3.8, 'fisher_grenade', {r: 25, homing: .019, blast: 55, damage: 2}, 300);
            return ['追踪炸弹', 1300];
        case 1:
            for (let i = 0; i < 4; i++) fan(1, 0, 5, 'whale_tidal_crescent', {r: 27}, 300 + i * 210, x, mouth, aimed(world, x, mouth));
            return ['月牙连斩', 1400];
        case 2:
            world.slowUntil = world.time + 3000;
            for (let i = 0; i < 3; i++) fan(5, 1.1, 2.8, 'bubble_crab', {}, i * 500);
            return ['暴雪', 3000];
        default:
            boss.fusionUntil = world.time + [2000, 2500, 3000][tier];
            if (boss.hp > boss.maxHp * .55) boss.shieldUntil = boss.fusionUntil;
            else fan(8, 1.05, 4.5, 'orochi_fireball', {r: 22, damage: 2}, 600);
            return ['合体强化', 2900];
        }
    case 9:
        switch (pattern % 4) {
        case 0:
            world.zone(x, mouth, Math.max(4, 24 * world.view.bossScale), 0, 2, 150, 4510, null,
                {rail: true, directions: Math.floor(world.random() * 8)});
            return ['等离子轨道炮', 4660];
        case 1:
            for (let i = 0; i < 3; i++) fan(1, 0, 4.3, 'mecha_guided_missile',
                {r: 15, homing: .035, returns: 1, pierce: true}, 540 + i * 850, x + (i - 1) * 32 * world.view.bossScale, mouth,
                Math.PI / 2 + (1 - i) * Math.PI * 32 / 180);
            return ['制导导弹', 2240];
        case 2:
            boss.destination = {x: width / 2, y: bottom * .48};
            for (let i = 0; i < 8; i++) {
                const theta = i * Math.PI / 4;
                const cx = width / 2 + Math.cos(theta) * 117, cy = bottom * .48 + Math.sin(theta) * 117;
                ring(cx, cy, 20, 1, 640 + i * 150, 1450 - i * 150, 'mecha_emp_iron_ball');
                fan(1, 0, 4, 'mecha_emp_iron_ball', {r: 16}, 2140, cx, cy, theta);
            }
            world.zone(width / 2, bottom * .48, 235, 235, 2, 2050, 320, 'mecha_emp_ring', {circle: true, silent: true, ring: true});
            return ['电磁脉冲', 2700];
        default:
            for (let i = 0; i < 2; i++) fan(7, 1.08, 3.7, 'mecha_molten_burst', {r: 21, damage: 2}, i * 650);
            return ['熔芯喷发', 1300];
        }
    case 10:
        switch (pattern % 4) {
        case 0:
            boss.resistUntil = world.time + 5000;
            for (let i = 0; i < 13; i++) {
                const safe = width * (.5 + Math.sin(i * .47) * .28);
                for (let cx = 42; cx < width; cx += 79) {
                    if (Math.abs(cx - safe) > 71) fan(1, 0, 4.6, 'whale_tidal_crescent', {r: 25}, i * 400, cx, -30);
                }
            }
            return ['潮汐月刃', 5000];
        case 1:
            for (let i = 0; i < 3; i++) {
                const side = target(world, (i - 1) * 60);
                for (const cx of [side, (side + width * .48) % width]) {
                    world.zone(cx, bottom / 2, 56, bottom, 2, 650 + i * 1000, 440, 'whale_rune_geyser', {lift: true});
                }
            }
            return ['符文涌泉', 3200];
        case 2:
            fan(3, .85, 2, 'whale_ancient_pearl', {r: 25, bounces: 6, damage: 2}, 350);
            return ['圣珠齐射', 2700];
        default:
            boss.destination = {x: width / 2, y: 115};
            boss.pull = {until: world.time + 5000, hp: boss.hp - boss.maxHp * .20};
            return ['巨鲸吸附 · 集火打断', 5000];
        }
    case 11:
        switch (pattern % 4) {
        case 0:
            for (let i = 0; i < 8; i++) fan(2, .16, 4.1, 'orochi_fireball', {r: 17}, 190 * i,
                x + (i - 3.5) * boss.w / 9, mouth, aimed(world, x, mouth));
            return ['八首火弹', 2100];
        case 1:
            for (let i = 0; i < 3; i++) {
                for (const side of [-1, 1]) lane(target(world, side * (57 + i * 23)), 52,
                    2, 900 + i * 1350, 300, 'boss_bite');
            }
            return ['双首砸击', 4050];
        case 2:
            for (let i = 0; i < 8; i++) {
                world.spawnEnemy('orochi_head', {x: (i + .5) * width / 8, y: -32, hp: boss.maxHp * .03,
                    speed: 2.6, life: 4150, counts: false, noLeak: true, index: i});
            }
            return ['八首分裂', 4150];
        default:
            for (let i = 0; i < 4; i++) lane(width * (i + .5) / 4, 28, 2, 850, 3000, null, {sway: 30});
            return ['蛇瞳激光', 3850];
        }
    default:
        throw new Error('Unknown boss level: ' + level);
    }
}

export function storm(world, boss, final) {
    boss.stormUntil = world.time + 10000;
    boss.attackAt = boss.stormUntil + boss.interval;
    boss.skill = final ? '终焉雷暴 · 击碎气泡' : '八首雷暴 · 击碎气泡';
    boss.skillUntil = boss.stormUntil;
    for (let i = 0; i < 8; i++) {
        world.spawnEnemy('orochi_bubble', {x: world.width / 2 + (i - 3.5) * boss.w * .118,
            y: boss.y - boss.h * .42 + (i % 2) * 39, hp: boss.maxHp * .05, speed: 0,
            life: 10000, counts: false, noLeak: true, index: i});
    }
    for (let i = 0; i < 7; i++) {
        world.later(i * 1400, () => {
            const x = target(world, between(world, -37, 37));
            world.zone(x, world.player.y, 100, 100, 2, 1000, 260, null, {circle: true});
        });
    }
}

export function railShape(zone, boss, bottom, time) {
    const age = Math.max(0, time - zone.impact);
    const x = boss.x + boss.w * .16;
    const y = boss.y + boss.h * .28;
    const height = Math.max(0, bottom - y) * Math.min(1, age / 650);
    const elapsed = Math.max(0, age - 650);
    const lash = Math.floor(elapsed / 1620);
    const phase = elapsed % 1620;
    const striking = age >= 650 && lash < 3 && phase < 620;
    const direction = zone.directions & (1 << lash) ? 1 : -1;
    const progress = phase / 620;
    const swing = direction * Math.min(285, height * .62) * Math.sin(Math.PI * progress);
    const drift = Math.sin(Math.PI * (phase - 620) / 1000);
    const reach = striking ? 1 - .18 * Math.sin(2 * Math.PI * progress) ** 2 : 1 - .07 * drift;
    const points = Array.from({length: 33}, (_, index) => {
        const fraction = index / 32;
        const bend = striking ? swing * fraction ** .75 * Math.sin(Math.PI * (1.75 * fraction - 2 * progress))
            : height * .10 * drift * fraction * Math.sin(age * .004 - fraction * 3);
        return [x + bend, y + height * reach * fraction];
    });
    return {points, striking, lash, width: zone.w};
}

export function tentacleShape(zone, boss, height, time) {
    const age = time - zone.impact;
    const phase = age % 680;
    const progress = phase / 680;
    const waveCycle = 2 * Math.PI;
    return {
        striking: phase >= 150 && phase < 475, lash: Math.floor(age / 680),
        paths: [-1, 1].map(side => {
            let x = boss.x + side * boss.w * .32, y = boss.y + boss.h * .08;
            const reach = Math.max(1, height - y);
            const aim = Math.atan2(zone.targetY - y, zone.targetX - x)
                + side * .28 * Math.sin(progress * waveCycle);
            const target = Math.min(1, Math.hypot(zone.targetX - x, zone.targetY - y) / reach);
            const points = [[x, y, 23]];
            for (let i = 1; i <= 24; i++) {
                const t = i / 24;
                const phase = (t - .5 / 24 - target / 2 - (progress - .5)) * waveCycle;
                const tangent = aim + Math.sin(phase) * (.46 + .10 * (1 - Math.sin(Math.PI * progress)));
                x += Math.cos(tangent) * reach / 24;
                y += Math.sin(tangent) * reach / 24;
                points.push([x, y, Math.max(3, 23 * (1 - t) ** .7)]);
            }
            return points;
        }),
    };
}
