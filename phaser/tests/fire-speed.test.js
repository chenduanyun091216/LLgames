import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {Battle} from '../src/battle.js';

const data = JSON.parse(readFileSync(new URL('../dist/campaign.json', import.meta.url)));

function assertShotGap(battle, time, gap) {
    battle.time = time;
    battle.lastFire = time - gap + 1;
    const count = battle.bullets.length;
    battle.fire();
    assert.equal(battle.bullets.length, count);
    battle.lastFire--;
    battle.fire();
    assert.equal(battle.bullets.length, count + 1);
}

test('campaign stacks tide, swift field and both haste gifts until each expires', () => {
    const battle = new Battle(data, {}, () => .7);
    battle.gold = 200;
    assert.ok(battle.equip('character', 'water'));
    battle.characterUpgrades.water = 1;
    battle.time = 10000;
    battle.random = () => 0;
    battle.cast(1);
    battle.random = () => .7;
    battle.openGift({});
    assertShotGap(battle, 10000, 103);
    battle.time = 11000;
    battle.openGift({});
    assertShotGap(battle, 11000, 52);
    assertShotGap(battle, 12000, 52);
    assertShotGap(battle, 16000, 100);
    assertShotGap(battle, 20000, 200);
    assertShotGap(battle, 21000, 400);
});

test('endless water heal grants fire speed and swift field instances expire separately', () => {
    const battle = new Battle(data, {mode: 'endless'}, () => 0);
    assert.ok(battle.equip('weapon', 'pistol'));
    assert.ok(battle.equip('character', 'water'));
    battle.characterUpgrades.water = 1;
    battle.time = 10000;
    battle.cast(0);
    assertShotGap(battle, 10000, 178);
    battle.time = 11000;
    battle.cast(1);
    assertShotGap(battle, 11000, 60);
    assertShotGap(battle, 12000, 60);
    assertShotGap(battle, 13000, 60);
    assertShotGap(battle, 15000, 200);
    assertShotGap(battle, 21000, 400);
});
