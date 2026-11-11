import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {Battle, bossBoxes, STEP} from '../src/battle.js';

const data = JSON.parse(readFileSync(new URL('../dist/campaign.json', import.meta.url)));
const manifest = JSON.parse(readFileSync(new URL('../dist/assets.json', import.meta.url)));

function stepFor(battle, ms, input = {}) {
    for (let i = 0; i < Math.ceil(ms / STEP); i++) {
        battle.step(typeof input === 'function' ? input(battle) : input);
        battle.events.length = 0;
    }
}

test('campaign weapons use the configured base firing intervals and damage', () => {
    for (const [weapon, interval, damage, count] of [
        ['pistol', 400, 1, 1], ['rifle', 286, 1.5, 1],
        ['shotgun', 400, .85, 3], ['sniper', 666, 2, 1],
    ]) {
        const battle = new Battle(data);
        battle.gold = 100;
        assert.ok(battle.equip('weapon', weapon));
        battle.time = 1000;
        battle.fire();
        assert.deepEqual(battle.bullets.map(b => b.damage), Array(count).fill(damage));
        battle.time += interval - 1;
        battle.fire();
        assert.equal(battle.bullets.length, count);
        battle.time++;
        battle.fire();
        assert.equal(battle.bullets.length, count * 2);
    }
});

test('weapon upgrades cost consecutive multiples and sniper missiles fire every fourth shot', () => {
    const battle = new Battle(data);
    battle.gold = 200;
    assert.equal(battle.upgradeWeapon('pistol'), false);
    assert.equal(battle.upgradeWeapon('shotgun'), false);
    assert.ok(battle.equip('weapon', 'shotgun'));
    for (const cost of [12, 24, 36]) {
        const gold = battle.gold;
        assert.equal(battle.upgradePrice('shotgun'), cost);
        assert.ok(battle.upgradeWeapon('shotgun'));
        assert.equal(battle.gold, gold - cost);
    }
    assert.equal(battle.upgradePrice('shotgun'), null);
    assert.ok(battle.equip('weapon', 'sniper'));
    assert.ok(battle.upgradeWeapon('sniper'));
    for (let i = 0; i < 4; i++) {
        battle.time += 1000;
        battle.fire();
    }
    assert.deepEqual(battle.bullets.map(b => b.blastDamage ?? b.damage), [2, 2, 2, 1]);
    const missile = battle.bullets[3];
    assert.ok(missile.explosive);
    const targets = [0, 45, 200].map((offset, id) => ({
        id, x: missile.x + offset, y: missile.y + missile.dy, w: 24, h: 24, hp: 20, def: {},
    }));
    battle.bullets = [missile];
    battle.enemies = targets;
    battle.updateProjectiles();
    assert.deepEqual(targets.map(enemy => enemy.hp), [19, 19, 20]);
    assert.equal(battle.bullets.length, 1);
    assert.ok(battle.bullets.every(b => b.guided && b.w === missile.w / 2 && b.damage === .5));
    const followup = {id: 4, x: missile.x + 120, y: targets[0].y - 95, w: 38, h: 38, hp: 20, def: {}};
    battle.enemies = [followup];
    for (let i = 0; i < 90 && battle.bullets.length; i++) {
        battle.time += STEP;
        battle.updateProjectiles();
    }
    assert.equal(followup.hp, 19.5);
    assert.equal(battle.bullets.length, 0);
    battle.gold = 0;
    assert.equal(battle.upgradeWeapon('sniper'), false);
    assert.equal(battle.weaponUpgrades.sniper, 1);
});

test('a split missile flies away before returning to its original target', () => {
    const battle = new Battle(data);
    const original = {id: 1, x: 240, y: 260, w: 40, h: 40, hp: 20, def: {}};
    const other = {...original, id: 2, x: 360, y: 300};
    battle.enemies = [original, other];
    battle.detonate({x: 240, y: 280, angle: 0, w: 24, h: 24, explosive: 64,
        blastDamage: 1, missile: true, splitCount: 1, weapon: 'sniper', damage: 1}, original);
    const child = battle.bullets[0];
    battle.time = child.guideAt;
    battle.updateProjectiles();
    assert.ok(child.y > 280);
    assert.equal(original.hp, 19);
    battle.time += STEP;
    battle.updateProjectiles();
    assert.ok(child.leftOriginal);
    assert.equal(child.canHitOriginal, false);
    battle.enemies = [original];
    for (let i = 0; i < 150 && battle.bullets.length; i++) {
        battle.time += STEP;
        battle.updateProjectiles();
    }
    assert.equal(original.hp, 18.5);
});

test('guided sniper rounds prioritize and open the nearest live gift', () => {
    for (const missile of [true, false]) {
        const battle = new Battle(data, {}, () => .7);
        const round = {x: 240, y: 350, angle: 0, w: 12, h: 12, guided: true, missile, hit: new Set()};
        battle.bullets = [round];
        battle.enemies = [{id: 1, x: 220, y: 310, w: 12, h: 12, hp: 10}];
        const near = {kind: 'gift', x: 300, y: 270, w: 44, h: 44, life: 10000};
        const far = {...near, x: 110};
        const expired = {...near, x: 220, y: 325, life: 0};
        battle.drops = [expired, far, near];
        battle.updateProjectiles();
        assert.ok(round.angle > 0);
        round.x = near.x;
        round.y = near.y;
        battle.updateProjectiles();
        assert.equal(near.life, 0);
        assert.equal(far.life, 10000);
        assert.ok(battle.hasteUntil > battle.time);
        assert.equal(battle.bullets.length, 0);
    }
});

test('a campaign goes from the first wave to the last boss and victory using real weapon hits', () => {
    const battle = new Battle(data, {tier: 1}, () => .61);
    for (let n = 1; n <= 11; n++) {
        assert.equal(battle.level, n);
        assert.ok(manifest['backgrounds/bg' + n]);
        assert.ok(manifest['bosses/' + (n === 8 ? 'zongzong' : data.bosses[n - 1].key)]);
        if (![6, 11].includes(n)) {
            assert.equal(battle.phase, 'wave');
            battle.invulnerable = Infinity;
            stepFor(battle, 1500);
            assert.ok(battle.enemies.length > 0);
            stepFor(battle, 38000);
            assert.equal(battle.phase, 'wave');
            stepFor(battle, 510);
        }
        assert.equal(battle.phase, 'boss');
        assert.equal(battle.boss.maxHp, data.CAMPAIGN_BOSS_HP[n - 1][1]);
        battle.invulnerable = Infinity;
        battle.gold = 500;
        battle.equip('weapon', 'rifle');
        // Real movement, shooting and collision. Ignore incoming damage to isolate progression.
        for (let i = 0; battle.phase === 'boss' && i < 26000; i++) {
            const dx = bossBoxes(battle.boss, battle.time)[0].x - battle.player.x;
            battle.step({x: Math.abs(dx) < 3 ? 0 : Math.sign(dx), fire: true});
            if (battle.boss?.pull) battle.boss.pull = battle.boss.destination = null;
            battle.events.length = 0;
        }
        assert.equal(battle.phase, n === 11 ? 'victory' : 'clear', 'level ' + n);
        assert.equal(battle.shots.length + battle.zones.length + battle.tasks.length, 0);
        if (n < 11) battle.next();
    }
});

test('the first six campaign bosses cast one extra signature below half health', () => {
    for (let level = 1; level <= 6; level++) {
        const battle = new Battle(data, {level});
        if (battle.phase === 'wave') battle.beginBoss();
        const boss = battle.boss;
        boss.y = 60 + boss.h / 2;
        battle.time = boss.attackAt;
        battle.updateBoss();
        const openingSkill = boss.skill;
        const openingStart = boss.skillStarted;
        boss.hp = boss.maxHp / 2 - 1;
        battle.time++;
        battle.updateBoss();
        assert.equal(boss.skillStarted, openingStart);
        boss.hp = boss.maxHp / 2;
        battle.time = boss.skillUntil + 1;
        battle.updateBoss();
        assert.equal(boss.skillStarted, openingStart);
        boss.hp--;
        battle.time++;
        battle.updateBoss();
        assert.equal(boss.skill, openingSkill);
        assert.equal(boss.skillStarted, battle.time);
        const extraStart = boss.skillStarted;
        battle.time = boss.skillUntil + 1;
        battle.updateBoss();
        assert.equal(boss.skillStarted, extraStart);
        assert.equal(boss.pattern, 1);
    }
});

test('each boss executes its signature and later attack patterns', () => {
    for (let level = 1; level <= 11; level++) {
        const battle = new Battle(data, {level, tier: 2}, () => .61);
        if (battle.phase === 'wave') battle.beginBoss();
        const names = new Set();
        let hasHazard = false;
        for (let i = 0; i < 3600; i++) {
            battle.invulnerable = Infinity;
            battle.step();
            names.add(battle.boss.skill);
            hasHazard ||= Boolean(battle.shots.length || battle.zones.length);
            if (battle.phase === 'defeat') battle.revive();
        }
        assert.ok(hasHazard, 'level ' + level);
        assert.ok(names.size >= (level >= 7 ? 5 : 3), 'level ' + level + ' ' + [...names]);
    }
});

test('factory splits and fuses, temple eyes summon destructible worms', () => {
    const factory = new Battle(data, {level: 9}, () => .25);
    const target = factory.spawnEnemy('mecha_crab', {factory: 'original', y: 70});
    factory.hit(target, 100);
    assert.ok(factory.enemies.every(e => e.factory === 'child' && !e.counts));
    assert.equal(factory.kills, 1);
    for (let i = 0; i < 3; i++) factory.spawnEnemy('mecha_ray', {factory: 'original', y: 90});
    factory.updateFactoryLink();
    assert.equal(factory.link.group.length, 3);
    stepFor(factory, 2100);
    const mini = factory.enemies.find(e => e.kind === 'mecha_mini');
    assert.ok(mini);
    factory.hit(mini, 100);
    assert.equal(factory.kills, 4);

    const temple = new Battle(data, {level: 10}, () => .7);
    stepFor(temple, 10300);
    const eye = temple.enemies.find(e => e.kind === 'ancient_rift');
    assert.ok(eye);
    assert.ok(temple.enemies.some(e => e.kind === 'ancient_worm'));
    temple.hit(eye, 20);
    assert.ok(!temple.enemies.includes(eye));
    assert.equal(temple.kills, 0);
});

test('shop, retry, portrait resize and endless rollover use the selected rules', () => {
    const battle = new Battle(data, {tier: 2, level: 5, custom: {hp: 1.25}});
    assert.equal(battle.equip('weapon', 'rifle'), false);
    battle.gold = 12;
    assert.equal(battle.equip('weapon', 'rifle'), true);
    assert.equal(battle.gold, 0);
    battle.resize(true);
    assert.equal(battle.width, 480);
    assert.equal(battle.player.x, 240);
    battle.beginBoss();
    assert.equal(battle.boss.maxHp, Math.ceil(122 * 1.25));
    battle.hurt(99, 'test');
    assert.ok(battle.revive());
    assert.equal(battle.lives, 2);
    battle.retry();
    assert.equal(battle.weapon, 'pistol');
    assert.equal(battle.lives, 3);

    const endless = new Battle(data, {mode: 'endless', level: 11, tier: 1});
    assert.ok(endless.equip('weapon', 'sniper'));
    assert.ok(endless.equip('character', 'radiation'));
    endless.finishLevel();
    assert.equal(endless.phase, 'clear');
    endless.next();
    assert.equal(endless.round, 1);
    endless.beginBoss();
    assert.equal(endless.boss.maxHp, 36);
});

test('whale absorption can be interrupted and Orochi bubbles decide storm healing', () => {
    const whale = new Battle(data, {level: 10, tier: 1}, () => .6);
    whale.beginBoss();
    const w = whale.boss;
    w.y = 120;
    w.pattern = 3;
    w.attackAt = 0;
    whale.step();
    assert.ok(w.pull);
    const before = whale.player.y;
    stepFor(whale, 340);
    assert.ok(whale.player.y < before);
    while (w.hp > w.pull.hp) whale.hit(w, 2);
    whale.step();
    assert.equal(w.pull, null);
    assert.equal(whale.phase, 'boss');

    const serpent = new Battle(data, {level: 11, tier: 1}, () => .6);
    const b = serpent.boss;
    b.y = 150;
    serpent.invulnerable = Infinity;
    while (!b.stormUntil) serpent.hit(b, 2);
    assert.equal(b.stormStep, 1);
    assert.equal(serpent.enemies.filter(e => e.kind === 'orochi_bubble').length, 8);
    const hp = b.hp;
    for (const bubble of [...serpent.enemies]) serpent.hit(bubble, bubble.hp);
    stepFor(serpent, 10025);
    assert.equal(b.hp, hp);
    while (!b.stormUntil) serpent.hit(b, 2);
    assert.equal(b.stormStep, 2);
    stepFor(serpent, 10025);
    assert.ok(b.hp > b.maxHp * .01);
});

test('mobile campaign uses the original playfield, movement and firing cadence', async () => {
    const {mobileView} = await import('../src/layout.js');
    const {controlLayout} = await import('../src/touch-layout.js');
    const view = mobileView(844, 390);
    const battle = new Battle(data, {view}, () => .6);
    assert.equal(view.canvasWidth, 960);
    assert.equal(view.offset, 240);
    assert.equal(view.height, 444);
    assert.equal(battle.bottom, 364);
    assert.equal(battle.width, 480);
    const controls = controlLayout(view);
    assert.deepEqual(controls.attack, [918, 372, 34]);
    assert.notDeepEqual(controls.attack, controls.fire);
    const x = battle.player.x;
    battle.step({x: 1, fire: true});
    assert.ok(Math.abs(battle.player.x - x - 5.2) < .0001);
    assert.equal(battle.bullets.length, 1);
    stepFor(battle, 375, {x: 1, fire: true});
    assert.equal(battle.bullets.length, 1);
    stepFor(battle, 40, {x: 1, fire: true});
    assert.equal(battle.bullets.length, 2);
    stepFor(battle, 650, {x: 1});
    assert.equal(battle.player.x, 480 - battle.player.w / 2);
    battle.beginBoss();
    assert.equal(battle.boss.w, battle.boss.baseW * .48);
    battle.resize(mobileView(390, 844));
    assert.equal(battle.view.canvasWidth, 480);
    assert.equal(battle.boss.w, battle.boss.baseW * .8);
    assert.equal(battle.player.h, 66 * .8);
});

test('crab bubbles hatch two chasing enemies and the plasma whip damages only while lashing', async () => {
    const {attack, railShape} = await import('../src/bosses.js');
    const crab = new Battle(data, {level: 2, tier: 1}, () => .6);
    crab.beginBoss();
    crab.boss.y = 95;
    attack(crab, crab.boss, 0);
    stepFor(crab, 890);
    const hatchlings = crab.enemies.filter(e => e.chases);
    assert.equal(hatchlings.length, 2);
    assert.deepEqual(hatchlings.map(e => e.maxHp), [8, 8]);
    const oldX = hatchlings[0].x;
    crab.player.x = oldX + 100;
    stepFor(crab, 100);
    assert.ok(hatchlings[0].x > oldX);

    const factory = new Battle(data, {level: 9, tier: 1}, () => .6);
    factory.beginBoss();
    factory.boss.y = 95;
    attack(factory, factory.boss, 0);
    const whip = factory.zones[0];
    assert.equal(railShape(whip, factory.boss, factory.bottom, whip.impact + 500).striking, false);
    assert.equal(railShape(whip, factory.boss, factory.bottom, whip.impact + 950).striking, true);
    assert.equal(railShape(whip, factory.boss, factory.bottom, whip.impact + 1500).striking, false);
    assert.equal(railShape(whip, factory.boss, factory.bottom, whip.impact + 2400).lash, 1);
});
