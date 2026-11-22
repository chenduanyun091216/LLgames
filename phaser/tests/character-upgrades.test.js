import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {Battle, STEP} from '../src/battle.js';

const data = JSON.parse(readFileSync(new URL('../dist/campaign.json', import.meta.url)));

test('every character uses its purchase price per level and checkpoints restore levels and gold', () => {
    for (const mode of ['campaign', 'endless']) {
        const battle = new Battle(data, {tier: 1, mode});
        for (const key of Object.keys(data.characters)) {
            const price = data.CAMPAIGN_CHARACTER_PRICES[key][mode === 'endless' ? 2 : 1];
            if (mode === 'campaign') {
                assert.equal(battle.characterUpgradePrice(key), null);
                battle.gold = price;
                assert.ok(battle.equip('character', key));
                assert.equal(battle.gold, 0);
            }
            for (let level = 1; level <= 3; level++) {
                assert.equal(battle.characterUpgradePrice(key), price);
                battle.gold = price - 1;
                assert.equal(battle.upgradeCharacter(key), false);
                assert.equal(battle.gold, price - 1);
                battle.gold = price;
                assert.ok(battle.upgradeCharacter(key));
                assert.equal(battle.gold, 0);
                assert.equal(battle.characterUpgrades[key], level);
            }
            assert.equal(battle.characterUpgradePrice(key), null);
        }
        battle.gold = 42;
        battle.startLevel(2);
        battle.characterUpgrades.ice = 1;
        battle.gold = 5;
        battle.retry();
        assert.equal(battle.characterUpgrades.ice, 3);
        assert.equal(battle.gold, 42);
    }
});

test('only successful upgraded casts roll at 25% and use all three durations', () => {
    const cases = [
        ['ice', 'enemyFreezeUntil', [1000, 2000, 3000], 0],
        ['water', 'swiftFieldUntil', [4000, 6000, 8000], 0],
        ['fire', 'fireShieldUntil', [10000, 10000, 10000], 0],
        ['radiation', 'radiationFieldUntil', [5000, 7000, 9000], 2],
    ];
    for (const [character, state, durations, skill] of cases) {
        for (const [index, duration] of durations.entries()) {
            for (const value of [.25, .249]) {
                let rolls = 0;
                const battle = new Battle(data, {mode: 'endless'}, () => { rolls++; return value; });
                battle.time = 10000;
                battle.equip('character', character);
                battle.characterUpgrades[character] = index + 1;
                battle.cast(skill);
                battle.cast(skill);
                assert.equal(rolls, 1);
                assert.equal(battle[state], value < .25 ? battle.time + duration : 0);
            }
        }
    }
});

test('ice holds boss, small enemies and delayed attacks while existing shots move', () => {
    const battle = new Battle(data, {mode: 'endless', level: 12}, () => 0);
    battle.equip('character', 'ice');
    battle.characterUpgrades.ice = 3;
    battle.boss.y = 70;
    const enemy = battle.spawnEnemy('zongzong', {y: 240});
    battle.shot(80, 130, Math.PI / 2, 2, 'bubble_crab');
    const [shot] = battle.shots;
    const bossX = battle.boss.x;
    let fires = 0, friendly = 0;
    battle.later(100, () => fires++);
    battle.later(100, () => friendly++, true);
    battle.cast(0);
    for (let i = 0; i < 179; i++) battle.step();
    assert.equal(enemy.y, 240);
    assert.equal(battle.boss.x, bossX);
    assert.equal(fires, 0);
    assert.equal(friendly, 1);
    assert.ok(shot.y > 130);
    battle.step();
    assert.ok(enemy.y > 240);
    assert.notEqual(battle.boss.x, bossX);
    for (let i = 0; i < 7; i++) battle.step();
    assert.equal(fires, 1);
});

test('swift movement and firing speed apply independently of the normal water skill', () => {
    const battle = new Battle(data, {tier: 0}, () => 0);
    battle.gold = 150;
    battle.equip('character', 'water');
    battle.upgradeCharacter('water');
    battle.cast(0);
    const before = battle.player.x;
    battle.step({x: 1});
    assert.ok(Math.abs(battle.player.x - before - 5.2 * 1.3) < .001);
    battle.lastFire = 0;
    battle.time = 266;
    battle.fire();
    assert.equal(battle.bullets.length, 0);
    battle.time = 267;
    battle.fire();
    assert.equal(battle.bullets.length, 1);
});

test('fire shield absorbs arbitrary damage and keeps an independent time and hit limit', () => {
    const battle = new Battle(data, {mode: 'endless'}, () => 0);
    battle.equip('character', 'fire');
    battle.characterUpgrades.fire = 3;
    battle.cast(0);
    for (const [index, amount] of [100, 1, 2, 3].entries()) {
        battle.hurt(amount, 'hit', index === 0);
        assert.equal(battle.hp, battle.maxHp);
        assert.equal(battle.fireShieldHits, 3 - index);
    }
    battle.hurt(1, 'hit');
    assert.equal(battle.hp, battle.maxHp - 1);
    battle.cooldowns[1] = 0;
    battle.cast(1);
    battle.time = battle.fireShieldUntil;
    battle.hurt(1, 'hit');
    assert.equal(battle.hp, battle.maxHp - 2);
});

test('radiation doubles damage and the wave at every level only clears enemy shots that have launched', () => {
    for (const level of [1, 2, 3]) {
        const battle = new Battle(data, {mode: 'endless', tier: 1, level: 11}, () => .1);
        battle.beginBoss();
        battle.equip('character', 'radiation');
        battle.characterUpgrades.radiation = level;
        battle.boss.y = 100;
        battle.boss.attackAt = Infinity;
        battle.cannonAt = Infinity;
        battle.time = 1000;
        battle.cast(2);
        const enemy = battle.spawnEnemy('trench_hermit', {x: 90, y: 150, hp: 100});
        battle.hit(enemy, 3);
        assert.equal(enemy.hp, 94);
        const hp = battle.boss.hp;
        battle.hit(battle.boss, 3);
        assert.ok(Math.abs(hp - battle.boss.hp - 3.6) < .001);
        battle.time = battle.radiationFieldUntil - STEP;
        battle.shot(60, 130, Math.PI / 2, 2, 'guided', {pierce: true});
        battle.shot(140, 130, Math.PI / 2, 2, 'armor',
            {orbit: {boss: battle.boss, phase: 0, until: battle.radiationFieldUntil}});
        battle.fire();
        const count = battle.bullets.length;
        battle.step();
        assert.equal(battle.bullets.length, count);
        assert.equal(battle.shots.length, 1);
        assert.ok(battle.airWave);
        battle.hit(enemy, 3);
        assert.equal(enemy.hp, 91);
    }
});
