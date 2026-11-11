import {attack, storm, railShape, tentacleShape} from './bosses.js';
import {fixedView} from './layout.js';

export const STEP = 1000 / 60;
export const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const angleDiff = (a, b) => Math.atan2(Math.sin(a - b), Math.cos(a - b));
const intersects = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;
const specialEnemies = {
    ancient_worm: {name: '远古虫', base_speed: 1.3, gold: 0},
    ancient_rift: {name: '裂隙之眼', base_speed: 0, gold: 0},
    mecha_mini: {name: '小型机械蜥蜴', base_speed: .8, gold: 5},
    orochi_head: {name: '分裂蛇首', base_speed: 2.6, gold: 0},
    orochi_bubble: {name: '雷暴气泡', base_speed: 0, gold: 0},
};

export class Battle {
    constructor(data, options = {}, random = Math.random) {
        this.data = data;
        this.random = random;
        this.tier = options.tier ?? 0;
        this.mode = options.mode ?? 'campaign';
        this.custom = {speed: 1, hp: 1, attack: 1, spawn: 1, homing: 1, ...options.custom};
        this.time = 0;
        this.id = 0;
        this.view = options.view ?? fixedView(options.portrait);
        this.width = this.view.width;
        this.bottom = this.view.bottom;
        this.maxHp = this.mode === 'endless' ? 5 : [6, 5, 4][this.tier];
        this.hp = this.maxHp;
        this.lives = 3;
        this.gold = 0;
        this.score = 0;
        this.weapon = 'pistol';
        this.character = 'player1';
        this.weapons = new Set(['pistol']);
        this.weaponUpgrades = {};
        this.sniperShots = 0;
        this.characters = new Set(['player1']);
        this.events = [];
        this.round = 0;
        if (this.mode === 'endless') {
            this.weapons = new Set(Object.keys(data.weapons));
            this.characters = new Set(['player1', ...Object.keys(data.characters)]);
            this.weapon = 'rifle';
        }
        this.player = {w: 56 * this.view.entityScale, h: 66 * this.view.entityScale};
        this.startLevel(options.level ?? 1);
    }

    value(key) { return this.data[key][this.level - 1][this.tier]; }
    event(type, extra = {}) { this.events.push({type, ...extra}); }
    key() { return ++this.id; }
    heal(amount) { this.hp = Math.min(this.maxHp, this.hp + amount); }

    startLevel(level) {
        this.level = level;
        this.stage = this.data.levels[level - 1];
        this.phase = 'wave';
        this.started = this.time;
        this.spawnAt = this.time + 1200;
        this.enemyShotAt = this.time;
        this.lastElite = false;
        this.giftAt = this.time + 18000;
        this.riftAt = this.time + 8500;
        this.riftsDestroyed = 0;
        this.waterKills = 0;
        this.gift = null;
        this.hasteUntil = 0;
        this.waveSpawns = 0;
        this.kills = 0;
        this.spawned = 0;
        this.enemies = [];
        this.bullets = [];
        this.shots = [];
        this.zones = [];
        this.tasks = [];
        this.drops = [];
        this.boss = null;
        this.link = null;
        this.lastFire = -Infinity;
        this.cooldowns = [0, 0, 0, 0];
        this.slowUntil = this.liftUntil = this.boostUntil = this.invulnerable = 0;
        this.player.x = this.width / 2;
        this.player.y = this.bottom - 14;
        this.checkpoint = {gold: this.gold, score: this.score, hp: this.hp, weapon: this.weapon,
            character: this.character, weapons: [...this.weapons], characters: [...this.characters],
            weaponUpgrades: {...this.weaponUpgrades}, sniperShots: this.sniperShots};
        this.event('level', {level});
        if (this.stage.boss_on_start) this.beginBoss();
    }

    resize(view) {
        if (typeof view === 'boolean') view = fixedView(view);
        if (view.canvasWidth === this.view.canvasWidth && view.height === this.view.height
                && view.entityScale === this.view.entityScale) return;
        const horizontal = view.width / this.width;
        const vertical = view.bottom / this.bottom;
        for (const entity of [this.player, ...this.enemies, ...this.bullets, ...this.shots, ...this.drops, this.boss]) {
            if (!entity) continue;
            entity.x *= horizontal;
            entity.y *= vertical;
            if (entity.anchor != null) entity.anchor *= horizontal;
        }
        const ratio = view.entityScale / this.view.entityScale;
        for (const entity of [this.player, ...this.enemies]) {
            entity.w *= ratio;
            entity.h *= ratio;
        }
        for (const enemy of this.enemies) enemy.speed *= vertical;
        this.view = view;
        this.width = view.width;
        this.bottom = view.bottom;
        this.player.x = clamp(this.player.x, this.player.w / 2, this.width - this.player.w / 2);
        this.player.y = clamp(this.player.y, 80, this.view.height - this.player.h / 2 - 8);
        this.zones = [];
        this.tasks = [];
        if (this.boss) {
            this.boss.w = this.boss.baseW * view.bossScale;
            this.boss.h = this.boss.baseH * view.bossScale;
            this.boss.destination = this.boss.pull = this.boss.rush = null;
        }
    }

    beginBoss() {
        this.phase = 'boss';
        this.tasks = [];
        this.bullets = [];
        this.shots = [];
        this.enemies = this.enemies.filter(e => e.kind !== 'ancient_rift' && e.kind !== 'ancient_worm');
        const def = this.data.bosses[this.stage.boss_idx];
        const base = this.mode === 'endless' ? this.data.INFINITE_BOSS_HP[this.level - 1] * (1 + .20 * Math.min(6, this.round))
            : this.value('CAMPAIGN_BOSS_HP');
        const hp = Math.ceil(base * this.custom.hp);
        const [baseW, baseH] = def.size ?? [130, 120];
        const h = baseH * this.view.bossScale;
        const interval = (this.mode === 'endless' ? this.data.INFINITE_BOSS_ATTACK_MS[this.level - 1]
            : this.value('CAMPAIGN_BOSS_ATTACK_MS')) * this.custom.attack;
        this.boss = {id: this.key(), def, level: this.level, x: this.width / 2, y: -h / 2, baseW, baseH,
            w: baseW * this.view.bossScale, h, hp, maxHp: hp, interval, patrol: 0,
            attackAt: this.time + 3000, direction: 1, pattern: 0, shieldStep: 0, stormStep: 0,
            halfHealthCast: false};
        if (this.level === 8) this.boss.bodyHp = [hp / 2, hp / 2];
        this.spawnAt = this.time + this.reinforcement('MS');
        this.event('boss');
    }

    reinforcement(table) {
        return this.mode === 'endless' ? this.data['INFINITE_REINFORCEMENT_' + table][this.level - 1]
            : this.value('CAMPAIGN_REINFORCEMENT_' + table);
    }

    later(delay, action) { this.tasks.push({at: this.time + delay, action}); }
    zone(x, y, w, h, damage, warning, active, art, extra = {}) {
        this.zones.push({id: this.key(), x, y, w, h, damage, start: this.time,
            impact: this.time + warning, end: this.time + warning + active, art, ...extra});
    }
    shot(x, y, angle, speed, art, extra = {}) {
        this.shots.push({id: this.key(), x, y, angle, speed, art, r: 11, damage: 1,
            born: this.time, expires: this.time + 12000, ...extra});
    }

    spawnEnemy(kind, extra = {}) {
        const def = this.data.enemies[kind] ?? specialEnemies[kind];
        const [baseW, baseH] = kind === 'ancient_rift' ? [Math.min(this.width * .55, 300), 96]
            : kind === 'ancient_worm' ? [33, 26] : kind === 'mecha_mini' ? [120, 86]
            : kind === 'orochi_head' ? [50, 78] : kind === 'orochi_bubble' ? [42, 42]
            : def.size ?? (def.is_large ? [110, 96] : def.zongzong ? [74, 66] : [64, 56]);
        const w = baseW * this.view.entityScale, h = baseH * this.view.entityScale;
        const x = w / 2 + this.random() * (this.width - w);
        const hp = def.campaign_hp ?? (def.is_large ? 9 : def.zongzong ? 8 : 3);
        const speed = def.base_speed * ((this.bottom + 20 + h) / (384 + baseH * .64)) * this.data.CAMPAIGN_SPEED[this.level - 1]
            * [.88, 1, 1.08][this.tier] * this.custom.speed * (.88 + this.random() * .24);
        const entity = {id: this.key(), kind, def, w, h, x, anchor: extra.x ?? x, y: -h / 2, hp, speed,
            counts: true, born: this.time, attackAt: this.time + [8500, 7500, 6400][this.tier], ...extra};
        entity.maxHp = entity.hp;
        this.enemies.push(entity);
        return entity;
    }

    spawnWave() {
        const normal = this.stage.enemy_pool.filter(k => !this.data.enemies[k].is_large && k !== 'zongzong');
        const large = this.stage.enemy_pool.filter(k => this.data.enemies[k].is_large);
        let pool = normal;
        if (this.level === 1 && this.waveSpawns < 6) pool = normal.filter(key => key !== 'goldfish');
        if (!this.lastElite && this.level >= 4 && !this.enemies.some(e => e.kind === 'zongzong') && this.random() < .04
                && this.stage.enemy_pool.includes('zongzong')) pool = ['zongzong'];
        else if (!this.lastElite && large.length && this.random() < this.data.CAMPAIGN_LARGE_CHANCE[this.level - 1]) pool = large;
        if (this.level === 1 && this.waveSpawns < 2) pool = [['lobster', 'crab'][this.waveSpawns]];
        if (!pool.length) return;
        if (this.phase === 'wave' && this.level === 2 && this.waveSpawns === 3) pool = ['octopus'];
        const kind = pool[Math.floor(this.random() * pool.length)];
        this.waveSpawns++;
        this.lastElite = kind === 'zongzong' || this.data.enemies[kind].is_large;
        this.spawnEnemy(kind, {factory: this.level === 9 ? 'original' : null,
            summons: this.level === 10 && this.random() < [.18, .24, .28][this.tier]});
    }

    updateSpawns() {
        const wave = this.phase === 'wave';
        if (wave && this.time - this.started + .001 >= 40000) {
            this.beginBoss();
            return;
        }
        const cap = wave ? this.mode === 'endless'
            ? Math.min(this.level >= 9 ? 7 : 12, 4 + Math.floor((this.round * 11 + this.level - 1) / 3))
            : this.value('CAMPAIGN_ENEMY_CAP') : this.reinforcement('CAP');
        if (cap && this.time >= this.spawnAt && this.enemies.filter(e => e.counts).length < cap) {
            this.spawnWave();
            const base = this.value('CAMPAIGN_SPAWN_MS') * this.custom.spawn;
            const interval = Math.max(Math.min(base, this.custom.minSpawn ?? base),
                base - this.kills * (this.custom.spawnDecrease ?? 0));
            this.spawnAt = this.time + (wave ? interval : this.reinforcement('MS'));
        }
        if (wave && this.level === 10 && this.time >= this.riftAt) {
            const eyes = this.enemies.filter(e => e.kind === 'ancient_rift');
            if (eyes.length + this.riftsDestroyed < 2) {
                this.spawnEnemy('ancient_rift', {x: this.width * (eyes.length ? .70 : .30),
                    y: 122 + eyes.length * 80, hp: 16, counts: false, noLeak: true, worms: 0, attackAt: this.time});
            }
            this.riftAt = this.time + [10000, 8500, 7000][this.tier];
        }
        if (this.time >= this.giftAt) {
            if (!this.drops.some(drop => drop.kind === 'gift')) {
                this.drops.push({id: this.key(), kind: 'gift', x: 60 + this.random() * (this.width - 120),
                    y: -25, w: 44, h: 44, life: this.time + 22000});
            }
            this.giftAt = this.time + (this.mode === 'endless' ? 15000 : 22000);
        }
    }

    worm(enemy) {
        const cap = [6, 8, 10][this.tier];
        if (this.enemies.filter(e => e.kind === 'ancient_worm').length >= cap) return false;
        this.spawnEnemy('ancient_worm', {x: enemy.x, y: enemy.y, hp: Math.max(1, Math.ceil(enemy.maxHp * .30)),
            counts: false, noLeak: true});
        return true;
    }

    updateEnemies() {
        for (const e of [...this.enemies]) {
            if (!this.enemies.includes(e)) continue;
            if (e.life && this.time >= e.born + e.life) { this.removeEnemy(e); continue; }
            if (e.kind === 'ancient_rift') {
                if (this.time >= e.attackAt && this.worm(e)) {
                    e.worms++;
                    if (e.worms === [3, 4, 6][this.tier]) {
                        e.worms = 0;
                        e.attackAt = this.time + [10000, 8500, 7000][this.tier];
                        e.x = this.width * (.23 + this.random() * .54);
                    } else e.attackAt = this.time + 400;
                }
                continue;
            }
            const slow = e.frozenUntil > this.time ? 0 : e.slowedUntil > this.time ? .75 : 1;
            if (e.kind === 'ancient_worm' || e.chases) {
                const dx = this.player.x - e.x, dy = this.player.y - e.y;
                const scale = e.speed * slow / Math.max(1, Math.hypot(dx, dy));
                e.x += dx * scale;
                e.y += dy * scale;
            } else if (e.kind === 'mecha_mini') {
                e.x += e.speed * slow * (e.direction ?? 1);
                if (e.x < e.w / 2 || e.x > this.width - e.w / 2) {
                    e.direction = e.x < e.w / 2 ? 1 : -1;
                    e.x = clamp(e.x, e.w / 2, this.width - e.w / 2);
                }
            } else if (e.kind !== 'orochi_bubble') {
                e.x = clamp(e.anchor + Math.sin(this.time / 700 + e.id) * 20, e.w / 2, this.width - e.w / 2);
                const entry = e.counts && this.time - e.born < 500 ? Math.max(0, (56 - e.y) / 11) : 0;
                e.y += Math.max(e.speed, entry) * slow;
                if (this.link?.group.includes(e)) e.y = Math.min(e.y, this.bottom - e.h);
            }
            if (e.summons && e.y > 65) {
                e.summons = false;
                for (let i = 0, n = 1 + Math.floor(this.random() * (this.tier === 2 ? 3 : 2)); i < n; i++) this.worm(e);
            }
            if (e.counts && !e.chases && e.y > 28 && e.y < this.bottom - 100 && this.time >= Math.max(e.attackAt, this.enemyShotAt)) {
                this.enemyShotAt = this.time + (this.phase === 'boss' ? 1000 : 500);
                const factory = this.level === 9;
                this.shot(e.x, e.y + 12, Math.atan2(this.player.y - e.y, this.player.x - e.x),
                    factory ? 2.7 : 2.1, factory ? 'mecha_guided_missile' : 'bubble_crab',
                    {homing: factory ? .014 : 0, r: factory ? 9 : 8});
                const min = this.custom.enemyMin ?? [10000, 8000, 6500][this.tier];
                const max = this.custom.enemyMax ?? [14000, 12000, 10000][this.tier];
                e.attackAt = this.time + min + this.random() * (max - min);
                e.shotAt = this.time;
            }
            if (e.kind !== 'orochi_bubble' && this.time >= (e.contactAt ?? 0) && intersects(e, this.player)) this.hurt(e.def.is_large ? 2 : 1, e.def.name);
            if (e.y - e.h / 2 > this.bottom) {
                this.removeEnemy(e);
                if (!e.noLeak) this.hurt(this.mode === 'endless' ? 1 : [1, 1, 2][this.tier], e.def.name + ' 入侵成功');
            }
        }
        if (this.level === 9) this.updateFactoryLink();
    }

    updateFactoryLink() {
        if (this.link) {
            const group = this.link.group.filter(e => this.enemies.includes(e));
            if (group.every(e => e.hp <= .01 * e.maxHp)) {
                this.link = null;
                for (const e of group) { e.factory = null; this.defeatEnemy(e); }
            } else if (this.time >= this.link.until) {
                this.link = null;
                const [first] = group;
                for (const e of group) this.removeEnemy(e);
                this.spawnEnemy('mecha_mini', {x: first.x, y: first.y, speed: 1.8, weight: 3,
                    hp: Math.ceil((this.boss?.maxHp ?? this.value('CAMPAIGN_BOSS_HP')) * [.12, .16, .20][this.tier])});
            }
            return;
        }
        if (this.enemies.some(e => e.kind === 'mecha_mini')) return;
        const group = this.enemies.filter(e => e.factory === 'original' && !e.linkTried && e.y > 32).slice(0, 3);
        if (group.length !== 3) return;
        group.forEach(e => { e.linkTried = true; });
        if (this.random() < .5) this.link = {group, until: this.time + 2000};
    }

    removeEnemy(enemy) { this.enemies = this.enemies.filter(e => e !== enemy); }

    defeatEnemy(enemy) {
        this.removeEnemy(enemy);
        if (enemy.kind === 'ancient_rift') this.riftsDestroyed++;
        if (enemy.counts) {
            this.kills += enemy.weight ?? 1;
            this.score += 10 * (enemy.weight ?? 1);
            if (this.character === 'water') {
                this.waterKills++;
                if (this.mode === 'endless' ? this.waterKills % 10 === 0 : [14, 28].includes(this.waterKills)) this.heal(1);
            }
        }
        this.event('pop', {x: enemy.x, y: enemy.y});
        if (enemy.def.gold) this.drops.push({id: this.key(), kind: 'coin', x: enemy.x, y: enemy.y,
            value: enemy.factory === 'child' ? 0 : enemy.def.gold, life: this.time + 13000});
        if (enemy.factory === 'original') {
            for (let i = 0, n = 1 + Math.floor(this.random() * 3); i < n; i++) {
                this.spawnEnemy(enemy.kind, {x: clamp(enemy.x + (i - (n - 1) / 2) * 48, 25, this.width - 25),
                    y: enemy.y, w: enemy.w * .55, h: enemy.h * .55, hp: enemy.maxHp * .25,
                    factory: 'child', counts: false});
            }
        }
    }

    hit(entity, amount, shape = null, source = 'skill', upgradeMultiplier = 1) {
        if (entity === this.boss) {
            if (entity.y < 30 || entity.shieldUntil > this.time || entity.stormUntil > this.time) return;
            const damage = Math.min(amount / upgradeMultiplier, this.mode === 'endless' ? 3 : [1, 2, 2][this.tier])
                * upgradeMultiplier * (entity.resistUntil > this.time ? .5 : 1);
            if (this.level === 11 && entity.hp - damage <= entity.maxHp * [0.5, 0.01][entity.stormStep]) {
                entity.hp = entity.maxHp * [0.5, 0.01][entity.stormStep];
                const final = entity.stormStep++ === 1;
                this.tasks = [];
                this.shots = [];
                this.zones = [];
                this.enemies = [];
                storm(this, entity, final);
                return;
            }
            if (entity.bodyHp) {
                const alive = bossBoxes(entity, this.time).filter(box => entity.bodyHp[box.index] > 0);
                const part = alive.find(box => !shape || intersects(box, shape));
                if (!part && !(entity.fusionUntil > this.time)) return;
                if (entity.fusionUntil > this.time) {
                    const parts = entity.bodyHp.filter(hp => hp > 0).length;
                    entity.bodyHp = entity.bodyHp.map(hp => Math.max(0, hp - damage / parts));
                } else {
                    const effectiveness = alive.length === 1 ? 2 : this.tier === 2
                        && part.index !== (source === 'bullet' ? 1 : 0) ? .5 : 1;
                    entity.bodyHp[part.index] = Math.max(0, entity.bodyHp[part.index] - damage * effectiveness);
                }
                entity.hp = entity.bodyHp[0] + entity.bodyHp[1];
            } else entity.hp -= damage;
            if (this.level === 7) {
                const threshold = [[.5], [.65, .30], [.75, .50, .25]][this.tier][entity.shieldStep];
                if (entity.hp > 0 && entity.hp <= entity.maxHp * threshold) {
                    entity.shieldStep++;
                    entity.shieldUntil = this.time + 2100;
                    entity.skill = '牛魔护盾';
                    entity.skillUntil = entity.shieldUntil;
                    this.later(2100, () => {
                        for (let i = 0; i < 5; i++) this.shot(entity.x, entity.y, .63 + i * .47, 3.1, 'boss_niu_shield');
                    });
                }
            }
            if (entity.hp <= 0) this.finishLevel();
        } else {
            if (this.link?.group.includes(entity)) entity.hp = Math.max(.01 * entity.maxHp, entity.hp - amount);
            else entity.hp -= amount;
            if (entity.hp <= 0) this.defeatEnemy(entity);
        }
        entity.hitAt = this.time;
        this.event('hit', {x: entity.x, y: entity.y});
    }

    finishLevel() {
        this.phase = this.level === 11 && this.mode === 'campaign' ? 'victory' : 'clear';
        this.score += 100;
        this.gold += this.data.CAMPAIGN_REWARDS[this.level - 1];
        this.heal(this.mode === 'endless' ? 1 : [2, 2, 1][this.tier]);
        this.enemies = this.bullets = this.shots = this.zones = this.tasks = this.drops = [];
        this.event('clear', {x: this.boss.x, y: this.boss.y});
        this.boss = null;
    }

    next() {
        if (this.phase !== 'clear') return;
        if (this.level === 11) this.round++;
        this.startLevel(this.level % 11 + 1);
    }

    hurt(amount, reason, fatal = false) {
        if (!['boss', 'wave'].includes(this.phase) || (!fatal && this.invulnerable > this.time)) return;
        this.hp = Math.max(0, this.hp - amount);
        this.invulnerable = this.time + [850, 650, 550][this.tier];
        this.event('hurt', {x: this.player.x, y: this.player.y});
        if (this.hp === 0) {
            this.reason = reason;
            this.phaseBeforeDeath = this.phase;
            this.phase = 'defeat';
        }
    }

    revive() {
        if (this.phase !== 'defeat' || this.lives <= 0) return false;
        this.lives--;
        this.hp = this.maxHp;
        this.phase = this.phaseBeforeDeath;
        this.invulnerable = this.time + 2400;
        this.player.x = this.width / 2;
        this.player.y = this.bottom - 14;
        return true;
    }

    retry() {
        const {weapons, characters, weaponUpgrades, ...saved} = this.checkpoint;
        Object.assign(this, saved);
        this.weaponUpgrades = {...weaponUpgrades};
        this.weapons = new Set(weapons);
        this.characters = new Set(characters);
        this.lives = 3;
        this.startLevel(this.level);
    }

    price(type, id) {
        if (this.mode === 'endless') return 0;
        return this.basePrice(type, id);
    }

    basePrice(type, id) {
        const weapon = type === 'weapon';
        const prices = weapon ? this.data.CAMPAIGN_WEAPON_PRICES : this.data.CAMPAIGN_CHARACTER_PRICES;
        return Math.round((prices[id]?.[this.tier] ?? 0) * (this.custom[type + 'Price'] ?? 1));
    }

    upgradePrice(id) {
        const level = this.weaponUpgrades[id] ?? 0;
        if (id === 'pistol' || !this.weapons.has(id) || level >= 3) return null;
        return this.basePrice('weapon', id) * (level + 1);
    }

    upgradeWeapon(id) {
        const price = this.upgradePrice(id);
        if (price === null || this.gold < price) return false;
        this.gold -= price;
        this.weaponUpgrades[id] = (this.weaponUpgrades[id] ?? 0) + 1;
        return true;
    }

    equip(type, id) {
        if (!['weapon', 'character'].includes(type)) return false;
        const weapon = type === 'weapon';
        if (weapon ? !this.data.weapons[id] : id !== 'player1' && !this.data.characters[id]) return false;
        const owned = weapon ? this.weapons : this.characters;
        const price = owned.has(id) ? 0 : this.price(type, id);
        if (this.gold < price) return false;
        this.gold -= price;
        owned.add(id);
        this[type] = id;
        return true;
    }

    updateBoss() {
        const b = this.boss;
        if (!b) return;
        if (b.stormUntil && this.time >= b.stormUntil) {
            const intact = this.enemies.filter(e => e.kind === 'orochi_bubble');
            b.hp = Math.min(b.maxHp, b.hp + intact.length * b.maxHp * .023);
            this.enemies = this.enemies.filter(e => e.kind !== 'orochi_bubble');
            b.stormUntil = 0;
        }
        if (b.stormUntil > this.time) {
            b.x += (this.width / 2 - b.x) * .07;
        } else if (b.rush) {
            const rush = b.rush;
            const age = this.time - rush.start;
            const below = this.view.height + b.h * .72 + 22;
            if (age < 1322) {
                const progress = age / 1322;
                b.x = rush.x + (rush.targetX - rush.x) * progress;
                b.y = rush.y + (below - rush.y) * progress;
            } else if (age < 3322) {
                b.y = below;
            } else {
                rush.returnX ??= this.player.x;
                const progress = clamp((age - 3322) / 1322, 0, 1);
                b.x = rush.returnX + (rush.x - rush.returnX) * clamp((age - 4644) / 600, 0, 1);
                b.y = below + (rush.y - below) * progress;
                if (age >= 5244) b.rush = null;
            }
            if ((age < 1322 || (age >= 3322 && age < 4644)) && intersects(b, this.player)) {
                this.hurt(this.hp, '被深渊封潮击败');
            }
        } else if (b.destination) {
            const dx = b.destination.x - b.x, dy = b.destination.y - b.y;
            b.x += clamp(dx, -4.1, 4.1);
            b.y += clamp(dy, -4.1, 4.1);
            if (Math.abs(dx) + Math.abs(dy) < 4 && !b.pull) b.destination = null;
        } else if (b.level <= 6) {
            const entry = 60 + b.h / 2;
            b.y = Math.min(entry, b.y + 1.5);
            if (b.y >= entry) {
                b.patrol += b.def.speed * .02;
                b.x = this.width / 2 + Math.sin(b.patrol) * Math.min(250, (this.width - b.w) / 2);
            }
        } else {
            b.y += clamp(b.h * .56 + 24 - b.y, -1.55, 1.75);
            if (b.y >= 40) b.x += b.def.speed * 1.55 * b.direction;
            const edge = b.w / 2 + (b.bodyHp ? b.w * .70 : 0);
            if (b.x <= edge || b.x >= this.width - edge) b.direction = b.x <= edge ? 1 : -1;
        }
        if (b.pull) {
            if (b.hp <= b.pull.hp) {
                b.pull = b.destination = null;
                b.skill = '吸附已打断';
                b.skillUntil = this.time + 1200;
            } else if (this.time >= b.pull.until) {
                b.pull = b.destination = null;
                this.hurt(this.hp, '被远古巨鲸吞没', true);
            } else {
                for (const entity of [this.player, ...this.enemies]) {
                    entity.x += clamp((b.x - entity.x) * .008, -2.6, 2.6);
                    entity.y += clamp((b.y + 35 - entity.y) * .008, -2.7, 2.7);
                }
            }
        }
        const ready = b.level > 6 || b.y >= 60 + b.h / 2 - .001;
        const halfHealth = this.mode !== 'endless' && b.level <= 6 && b.pattern > 0 &&
            !b.halfHealthCast && b.hp > 0 && b.hp < b.maxHp * .5 && this.time >= b.skillUntil;
        if (ready && (halfHealth || this.time >= b.attackAt) && !b.stormUntil && !b.rush) {
            const [name, duration] = attack(this, b, halfHealth ? 0 : b.pattern++);
            if (halfHealth) b.halfHealthCast = true;
            b.skill = name;
            b.skillStarted = this.time;
            b.skillUntil = this.time + duration;
            b.attackAt = this.time + duration + b.interval;
        }
        if (!b.rush && b.y >= 35 && bossBoxes(b, this.time).some(box => intersects(box, this.player))) this.hurt(this.mode === 'endless' ? 2 : [1, 2, 2][this.tier], b.def.name);
    }

    fire() {
        const w = this.data.weapons[this.weapon];
        if (this.liftUntil > this.time) return;
        let rate = this.mode === 'endless' ? w.fire_rate
            : (this.data.CAMPAIGN_WEAPON_FIRE_RATES[this.weapon] ?? w.fire_rate);
        if (this.hasteUntil > this.time) rate /= 2;
        else if (this.boostUntil > this.time) rate /= this.mode === 'endless' ? 2 : 1.30;
        if (this.slowUntil > this.time) rate /= this.mode === 'endless' ? .5 : .8;
        const level = this.weaponUpgrades[this.weapon] ?? 0;
        const speed = this.weapon === 'rifle' ? 1 + .1 * level : 1;
        const delay = Math.ceil(Math.round(rate) / .70) * (this.boss?.pull ? 2 : 1) / speed;
        if (this.time - this.lastFire < delay) return;
        const cost = this.mode === 'endless' ? 0 : (this.custom.ammo?.[this.weapon] ?? this.data.difficulty[this.tier]['bullet_cost_' + this.weapon] ?? 0);
        if (this.gold < cost) {
            this.weapon = 'pistol';
            this.event('noAmmo');
            return;
        }
        this.gold -= cost;
        this.lastFire = this.time;
        if (this.weapon === 'sniper' && level) this.sniperShots = (this.sniperShots + 1) % 4;
        const missile = this.weapon === 'sniper' && level > 0 && this.sniperShots === 0;
        const multiplier = this.weapon === 'rifle' ? 1 + .1 * level : this.weapon === 'shotgun' ? 1 + .2 * level : 1;
        const baseDamage = missile ? .5 * (1 + level) : this.data.CAMPAIGN_BULLET_DAMAGE[this.weapon];
        const damage = baseDamage * multiplier * (this.boostUntil > this.time ? 1.35 : 1);
        const element = this.gift?.until > this.time ? this.gift.type : null;
        const fire = this.character === 'fire' ? (this.mode === 'endless' ? 1.5 : 1.2) : 1;
        const angles = missile ? [this.player.x < this.width / 2 ? .49 : -.49]
            : this.weapon === 'shotgun' ? [-Math.PI / 10, 0, Math.PI / 10] : [0];
        for (const angle of angles) this.bullets.push({id: this.key(), x: this.player.x, y: this.player.y - 28,
            dx: Math.sin(angle) * w.speed * .8, dy: -Math.cos(angle) * w.speed * .8,
            w: this.weapon === 'sniper' || (this.weapon === 'shotgun' && angle === 0) ? 26 : 20,
            h: this.weapon === 'sniper' || (this.weapon === 'shotgun' && angle === 0) ? 26 : 20,
            angle, weapon: this.weapon,
            damage, character: this.character, element, upgradeMultiplier: missile ? 1 + level : multiplier,
            ...(missile ? {missile: true, guided: true, splitCount: level, explosive: 64,
                dx: Math.sin(angle) * 7, dy: -Math.cos(angle) * 7, w: 24, h: 24,
                expires: this.time + 4500, blastDamage: damage * fire * (element === 'fire' ? 1.4 : 1)} : {}),
            pierce: this.weapon === 'sniper' && !missile, hit: new Set()});
        this.event('shoot', {weapon: this.weapon});
    }

    cast(index) {
        if (this.liftUntil > this.time || this.time < this.cooldowns[index]) return;
        const character = this.character;
        const skill = this.data.characters[character]?.skills[index];
        const type = skill?.skill_type ?? (character === 'player1' && index === 0 ? 'grenade'
            : character === 'radiation' && index === 2 ? 'radiation_laser'
            : character === 'radiation' && index === 3 ? 'dart_shield' : null);
        if (!type) return;
        const infinite = this.mode === 'endless';
        const campaignMs = {grenade: 4000, fire_wall: 7000, fireball: 9000, ice_floor: 6000, ice_balls: 9000,
            lightning: 7000, magnetic_storm: 12000, water_heal: 12000, water_boost: 12000,
            radiation_laser: 14000, dart_shield: 14000}[type];
        const multiplier = this.custom.cooldown ?? [.9, 1, 1.15][this.tier];
        const cooldown = infinite ? (skill?.cooldown_ms ?? (index === 3 ? 20000 : 12000)) / 2
            : Math.round(campaignMs * multiplier);
        const {x, y} = this.player;
        const py = y - 28;
        const area = (cx, cy, w, h, damage, duration, effect, extra = {}) =>
            this.zone(cx, cy, w, h, -damage, 0, duration, null, {effect, ...extra});
        const projectile = (degrees, speed, radius, damage, extra) => {
            const angle = degrees * Math.PI / 180;
            this.bullets.push({id: this.key(), x, y: py, dx: Math.sin(angle) * speed,
                dy: -Math.cos(angle) * speed, w: radius * 2, h: radius * 2, angle, damage,
                hit: new Set(), expires: this.time + 2500, ...extra});
        };
        let duration = 0;
        switch (type) {
        case 'grenade':
            projectile(0, 6, 12, 0, {expires: this.time + 900, explosive: 90, blastDamage: 3,
                element: 'fire', art: 'fisher_grenade'});
            break;
        case 'fire_wall':
            duration = infinite ? 2500 : 4000;
            area(x, Math.max(100, py - 40) - 30, 200, 60, 1, duration, 'fire', {wall: true});
            break;
        case 'fireball':
            duration = 2500;
            for (const angle of [-32, 0, 32]) projectile(angle, 7, 28, 1.5, {element: 'fire', pierce: true});
            for (const angle of [-16, 16]) projectile(angle, 7, 8, 0, {element: 'fire', explosive: 55, blastDamage: 1.5});
            break;
        case 'ice_floor': {
            duration = infinite ? 8000 : 5000;
            area(x, py - 46, Math.floor(this.view.canvasWidth / 3), 92, 1, duration, 'ice', {
                wall: true, freeze: true, blocks: 5, trajectory: age => ({y: py - 46 - 3.5 * age / STEP}),
            });
            break;
        }
        case 'ice_balls':
            duration = 2500;
            for (const angle of [-56, -40, -24, -8, 8, 24, 40, 56]) {
                projectile(angle, 6, 18, 1, {element: 'ice', freeze: true});
            }
            break;
        case 'water_heal':
            duration = infinite ? 5000 : 0;
            this.heal(1);
            this.invulnerable = Math.max(this.invulnerable, this.time + (infinite ? 2000 : 800));
            area(x, y, 140, 85, 0, 450, 'water', {circle: true});
            break;
        case 'water_boost':
            duration = infinite ? 10000 : 6000;
            this.boostUntil = this.time + duration;
            area(x, y, 150, 105, 0, 650, 'water', {circle: true});
            break;
        case 'lightning': {
            const reach = Math.min(280, this.view.height * .55);
            const distance = entity => Math.hypot(entity.x - x, entity.y - py);
            const targets = [...this.enemies, ...(this.boss ? [this.boss] : [])]
                .filter(entity => entity.y > 0 && distance(entity) <= reach).sort((a, b) => distance(a) - distance(b))
                .slice(0, infinite ? 5 : 4);
            if (!targets.length) return;
            duration = 400;
            for (const entity of targets) this.zone(entity.x, entity.y, 70, 76, -2, 0, 230, 'lightning_reactor',
                {effect: 'energy', once: true});
            break;
        }
        case 'magnetic_storm': {
            const center = Math.max(120, y - 170);
            duration = 3000;
            area(x, center, 180, 180, 0, duration, 'energy', {circle: true, magnet: true});
            this.later(duration, () => area(x, center, 245, 245, 3, 300, 'energy', {circle: true, once: true}));
            break;
        }
        case 'radiation_laser':
            duration = infinite ? 5000 : 4000;
            area(x, y / 2, this.player.w * .65, y, infinite ? .45 : 1, duration, 'energy',
                {follow: true, interval: infinite ? 120 : 500});
            break;
        case 'dart_shield':
            duration = infinite ? 5000 : 3000;
            for (let i = 0; i < 8; i++) {
                const angle = i * Math.PI / 4;
                const position = age => ({x: this.player.x + 63 * Math.cos(angle + age / 165),
                    y: this.player.y + 63 * Math.sin(angle + age / 165)});
                const point = position(0);
                area(point.x, point.y, 23, 23, 1, duration, 'energy', {dart: true, wall: true, trajectory: position});
            }
            this.later(duration, () => {
                for (let i = 0; i < 8; i++) projectile(i * 45, 6, 11, 1.5, {element: 'energy', pierce: true});
            });
            break;
        }
        this.cooldowns[index] = this.time + (infinite && type === 'grenade' ? 3900 : cooldown + duration);
        this.event('skill');
    }

    openGift(drop) {
        drop.life = 0;
        const gifts = ['fire', 'ice', 'heal', 'haste', 'lightning'];
        const names = ['火弹礼包', '冰弹礼包', '血包礼包', '极速礼包', '闪电礼包'];
        const index = Math.floor(this.random() * gifts.length);
        const type = gifts[index];
        if (type === 'heal') this.heal(1);
        else if (type === 'haste') this.hasteUntil = this.time + 10000;
        else if (type === 'lightning') {
            const strikes = this.mode === 'endless' ? 3 : 2;
            for (let i = 0; i < strikes; i++) this.later(i * 3000, () => {
                const targets = [...this.enemies, ...(this.boss ? [this.boss] : [])];
                const nearest = targets.reduce((best, entity) => !best || Math.abs(entity.x - this.player.x)
                    < Math.abs(best.x - this.player.x) ? entity : best, null);
                if (nearest) this.zone(nearest.x, nearest.y, 90, 96, -3, 100, 240, 'lightning_reactor', {effect: 'energy'});
            });
        } else this.gift = {type, until: this.time + (type === 'fire' ? 7000 : 10000)};
        this.event('gift', {name: names[index]});
        this.event('pop', {x: drop.x, y: drop.y});
    }

    detonate(bullet, target = null) {
        const {x, y, explosive: radius, blastDamage} = bullet;
        this.zone(x, Math.max(0, y), radius * 2, radius * 2, -blastDamage, 0, 270, null,
            {circle: true, effect: 'fire', once: true, missile: bullet.missile,
                upgradeMultiplier: bullet.upgradeMultiplier, bossDamage: radius === 90 && this.mode !== 'endless' ? 2 : blastDamage});
        for (let i = 0; i < (bullet.splitCount ?? 0); i++) {
            const angle = bullet.angle + (target ? Math.PI : 0)
                + (i - (bullet.splitCount - 1) / 2) * Math.PI * 48 / 180;
            this.bullets.push({id: this.key(), x, y, angle, dx: Math.sin(angle) * 7, dy: -Math.cos(angle) * 7,
                w: bullet.w / 2, h: bullet.h / 2, guided: true, guideAt: this.time + 100, originalTarget: target,
                expires: this.time + 3000, weapon: bullet.weapon, character: bullet.character,
                element: bullet.element, damage: bullet.damage * .5, hit: new Set()});
        }
        bullet.y = -100;
    }

    updateProjectiles() {
        const targets = [...this.enemies, ...(this.boss ? [this.boss] : [])];
        const gifts = this.drops.filter(drop => drop.kind === 'gift');
        for (const b of this.bullets.slice()) {
            if (b.guided && this.time >= (b.guideAt ?? 0)) {
                let nearest = null, distance = Infinity;
                const original = b.originalTarget;
                if (original && !b.leftOriginal) {
                    const boxes = original === this.boss ? bossBoxes(original, this.time) : [original];
                    b.leftOriginal = !boxes.some(box => intersects(b, box));
                }
                b.canHitOriginal = false;
                const visibleGifts = gifts.filter(drop => drop.life > this.time && drop.y + drop.h / 2 > 0);
                for (const enemy of visibleGifts.length ? visibleGifts : targets) {
                    const isOriginal = enemy === original;
                    if (isOriginal && (!b.leftOriginal || (nearest && !b.canHitOriginal))) continue;
                    if (enemy.hp <= 0 || (this.mode === 'endless' && enemy.def?.zongzong)) continue;
                    const boxes = enemy === this.boss ? bossBoxes(enemy, this.time) : [enemy];
                    for (const box of boxes) {
                        if (box.y + box.h / 2 <= 0) continue;
                        const squared = (box.x - b.x) ** 2 + (box.y - b.y) ** 2;
                        if ((!isOriginal && b.canHitOriginal) || squared < distance) {
                            nearest = box;
                            distance = squared;
                            b.canHitOriginal = isOriginal;
                        }
                    }
                }
                if (nearest) {
                    const desired = Math.atan2(nearest.x - b.x, b.y - nearest.y);
                    const maxTurn = b.canHitOriginal ? Math.PI / 10 : .122;
                    b.angle += clamp(angleDiff(desired, b.angle), -maxTurn, maxTurn);
                    b.dx = Math.sin(b.angle) * 7;
                    b.dy = -Math.cos(b.angle) * 7;
                }
            }
            b.x += b.dx;
            b.y += b.dy;
            if (b.guided) {
                const rear = b.missile ? 32 : 16;
                b.trail ??= [];
                b.trail.push([b.x - Math.sin(b.angle) * rear, b.y + Math.cos(b.angle) * rear]);
                if (b.trail.length > (b.missile ? 23 : 17)) b.trail.shift();
            }
            if (b.expires && (this.time >= b.expires || b.y < -24)) {
                if (b.explosive && !b.guided) this.detonate(b);
                else b.y = -100;
                continue;
            }
            if (this.time < (b.guideAt ?? 0)) continue;
            const gift = gifts.find(drop => drop.life > this.time && intersects(b, drop));
            if (gift) {
                this.openGift(gift);
                b.y = -100;
                continue;
            }
            for (const e of targets) {
                if (e.hp <= 0 || b.hit.has(e.id)) continue;
                if (e === b.originalTarget && !b.canHitOriginal) continue;
                const boxes = e === this.boss ? bossBoxes(e, this.time) : [e];
                if (!boxes.some(box => intersects(b, box))) continue;
                if (b.explosive) { this.detonate(b, e); break; }
                if (e !== this.boss) {
                    if (b.character === 'ice' || b.element === 'ice') e.slowedUntil = this.time + 2500;
                    if (b.element === 'ice' && !e.def.is_large && !e.def.zongzong) e.frozenUntil = this.time + (b.freeze ? 2000 : 800);
                }
                const boost = b.character === 'fire' ? (this.mode === 'endless' ? 1.5 : 1.2) : 1;
                this.hit(e, b.damage * boost * (b.weapon && b.element === 'fire' ? 1.4 : 1), b,
                    b.weapon ? 'bullet' : 'skill', b.upgradeMultiplier);
                if (this.phase === 'clear' || this.phase === 'victory') return;
                b.hit.add(e.id);
                if (!b.pierce) { b.y = -100; break; }
                if (b.weapon) b.damage *= this.mode === 'endless' ? .7 : .65;
            }
        }
        this.bullets = this.bullets.filter(b => b.y > -24 && b.x > -24 && b.x < this.width + 24);
        const barriers = this.zones.filter(z => this.time >= z.impact && this.time < z.end && (z.wall || z.magnet));
        for (const z of barriers) if (z.trajectory) Object.assign(z, z.trajectory(this.time - z.impact));
        for (const s of this.shots) {
            if (s.fuseAt) {
                if (this.time >= s.fuseAt) {
                    s.expires = 0;
                    for (let i = 0; i < 6; i++) this.shot(s.x, s.y, i * Math.PI / 3, 3.9, s.art, {r: 10});
                }
                continue;
            }
            if (s.homing) s.angle += clamp(angleDiff(Math.atan2(this.player.y - s.y, this.player.x - s.x), s.angle), -s.homing, s.homing);
            if (s.bounces) s.speed = Math.min(6.3, s.speed + .013);
            s.x += Math.cos(s.angle) * s.speed;
            s.y += Math.sin(s.angle) * s.speed;
            if (!s.pierce) {
                const wall = barriers.find(z => z.wall && z.end > this.time && intersects(z, {...s, w: s.r * 2, h: s.r * 2}));
                if (wall) {
                    s.expires = 0;
                    if (wall.blocks != null && --wall.blocks === 0) wall.end = this.time;
                    continue;
                }
                for (const z of barriers) if (z.magnet && Math.hypot(z.x - s.x, z.y - s.y) < 180) {
                    s.x += clamp((z.x - s.x) * .07, -5, 5);
                    s.y += clamp((z.y - s.y) * .07, -5, 5);
                    if (Math.hypot(z.x - s.x, z.y - s.y) < 20) s.expires = 0;
                }
                if (!s.expires) continue;
            }
            if (s.dragon && this.time - s.born >= 350) s.x += clamp((this.player.x - s.x) * .035, -2.5, 2.5);
            if (s.bounces && (s.x < s.r || s.x > this.width - s.r || s.y < s.r || s.y > this.bottom - s.r)) {
                if (s.x < s.r || s.x > this.width - s.r) s.angle = Math.PI - s.angle;
                if (s.y < s.r || s.y > this.bottom - s.r) s.angle = -s.angle;
                s.x = clamp(s.x, s.r, this.width - s.r);
                s.y = clamp(s.y, s.r, this.bottom - s.r);
                if (--s.bounces === 0) s.fuseAt = this.time + 3000;
            }
            if (s.returns && s.y > this.bottom + 22) {
                s.returns--;
                s.angle = -Math.PI / 2;
                s.homing = 0;
                s.turnAt = s.art === 'mecha_guided_missile' ? this.time + 2300 : 0;
            }
            if (s.turnAt && this.time >= s.turnAt) {
                s.turnAt = 0;
                s.angle = Math.PI / 2;
                s.homing = .038;
            }
            if (Math.hypot(s.x - this.player.x, s.y - this.player.y) < s.r + 17) {
                s.expires = 0;
                if (s.blast) this.zone(s.x, s.y, s.blast * 2, s.blast * 2, s.damage, 160, 300, null, {circle: true});
                else this.hurt(s.damage, '被敌方弹幕击败');
            }
        }
        this.shots = this.shots.filter(s => s.expires > this.time && (s.turnAt || (s.y > -90 && s.y < this.bottom + 100 && s.x > -95 && s.x < this.width + 95)));
        for (const z of this.zones) {
            if (this.time < z.impact || this.time >= z.end) continue;
            if (z.rail && this.boss) {
                const shape = railShape(z, this.boss, this.bottom, this.time);
                if (shape.striking && z.lastLash !== shape.lash && shape.points.some(([x, y]) =>
                    Math.abs(x - this.player.x) < (this.player.w + shape.width) / 2
                    && Math.abs(y - this.player.y) < (this.player.h + shape.width) / 2)) {
                    z.lastLash = shape.lash;
                    this.hurt(z.damage, '被等离子轨道炮击败');
                }
                continue;
            }
            if (z.tentacles && this.boss) {
                const shape = tentacleShape(z, this.boss, this.view.height, this.time);
                if (shape.striking && z.lastLash !== shape.lash && shape.paths.some(path => path.some(([x, y, r]) =>
                    Math.abs(x - this.player.x) < this.player.w / 2 + r && Math.abs(y - this.player.y) < this.player.h / 2 + r))) {
                    z.lastLash = shape.lash;
                    this.hurt(z.damage, '被墨涌陷阱击败');
                }
                continue;
            }
            if (z.trajectory) Object.assign(z, z.trajectory(this.time - z.impact));
            if (z.follow) {
                z.x = this.player.x;
                z.h = this.player.y;
                z.y = z.h / 2;
            }
            const hits = entity => {
                if (z.missile) {
                    const x = Math.max(0, Math.abs(z.x - entity.x) - entity.w / 2);
                    const y = Math.max(0, Math.abs(z.y - entity.y) - entity.h / 2);
                    return Math.hypot(x, y) <= z.w / 2;
                }
                return z.circle
                    ? Math.abs(Math.hypot(z.x - entity.x, z.y - entity.y) - (z.ring ? z.w / 2 : 0)) < (z.ring ? 25 : z.w / 2) + 15
                    : intersects({...z, x: zoneX(z, this.time)}, entity);
            };
            if (z.damage > 0 && this.time >= z.impact + (z.safeFor ?? 0) && !z.hit && hits(this.player)) {
                z.hit = true;
                this.hurt(z.damage, '被 Boss 技能击败');
                if (z.lift) this.liftUntil = this.time + 450;
            }
            if (z.damage < 0 && this.time >= (z.nextHit ?? 0)) {
                z.nextHit = z.once ? Infinity : this.time + (z.interval ?? 500);
                for (const e of targets) {
                    const boxes = e === this.boss ? bossBoxes(e, this.time) : [e];
                    const box = boxes.find(hits);
                    if (e.hp <= 0 || !box) continue;
                    this.hit(e, e === this.boss && z.bossDamage != null ? z.bossDamage : -z.damage, box,
                        'skill', z.upgradeMultiplier);
                    if (this.phase === 'clear' || this.phase === 'victory') return;
                    if (z.freeze) e.frozenUntil = this.time + 720;
                }
            }
        }
        this.zones = this.zones.filter(z => z.end > this.time);
    }

    step(input = {}) {
        if (!['wave', 'boss'].includes(this.phase)) return;
        this.time += STEP;
        const ready = this.tasks.filter(task => task.at <= this.time);
        this.tasks = this.tasks.filter(task => task.at > this.time);
        for (const task of ready) task.action();
        let speed = this.boss?.pull ? 2.6 : 5.2;
        if (this.boostUntil > this.time) speed *= this.mode === 'endless' ? 1.6 : 1.25;
        if (this.slowUntil > this.time) speed *= this.mode === 'endless' ? .5 : [.85, .80, .75][this.tier];
        const dx = input.x ?? 0, dy = input.y ?? 0;
        const p = this.player;
        p.moving = Boolean(dx || dy);
        const margin = this.view.offset ? p.w / 2 : Math.max(40, p.w / 2);
        p.x = clamp(p.x + dx * speed, margin, this.width - margin);
        p.y = clamp(p.y + (this.liftUntil > this.time ? -4.6 : dy * speed), 80, this.view.height - p.h / 2 - 8);
        if (input.fire) this.fire();
        if (input.skill != null) this.cast(input.skill);
        this.updateSpawns();
        this.updateBoss();
        this.updateEnemies();
        if (this.phase === 'defeat') return;
        this.updateProjectiles();
        for (const drop of this.drops) {
            drop.y = Math.min(this.bottom - 15, drop.y + (drop.kind === 'coin' ? 3.6 : 1.9));
            if (Math.hypot(p.x - drop.x, p.y - drop.y) > (drop.kind === 'coin' ? 49 : 37)) continue;
            if (drop.life <= this.time) continue;
            if (drop.kind === 'coin') {
                this.gold += drop.value;
                this.event('coin');
                drop.life = 0;
            } else this.openGift(drop);
        }
        this.drops = this.drops.filter(drop => drop.life > this.time);
    }
}

export function bossBoxes(boss, time) {
    if (!boss.bodyHp) return [boss];
    if (boss.fusionUntil > time) return [{...boss, w: boss.w * 1.36}];
    const single = boss.bodyHp.filter(hp => hp > 0).length === 1;
    return boss.bodyHp.flatMap((hp, index) => hp > 0
        ? [{x: boss.x + (single ? 0 : (index ? 1 : -1) * boss.w * .70), y: boss.y, w: boss.w, h: boss.h, index}]
        : []);
}

export function zoneX(zone, time) {
    return zone.x + (zone.sway ?? 0) * Math.sin((time - zone.impact) / 160);
}
