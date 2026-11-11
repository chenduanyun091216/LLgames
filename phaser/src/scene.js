import {bossBoxes, STEP, zoneX} from './battle.js';
import {bubbleColors, railShape, tentacleShape} from './bosses.js';

const weaponArt = {pistol: 'pistol', rifle: 'rifle', shotgun: 'shortgun', sniper: 'awm'};
export const weaponImage = (id, group = 'weapons') => group + '/weapon_' + weaponArt[id];
const fxColors = {fire: 0xff6335, ice: 0x71e6ff, water: 0x67dbf8, energy: 0xc387ff};
const bulletColors = {pistol: 0xffe76a, rifle: 0x63ccff, shotgun: 0xff8750, sniper: 0xcf9cff};
const soundKeys = ['pistol', 'rifle', 'shotgun', 'sniper', 'hit', 'hurt', 'coin', 'skill', 'boss', 'clear'];

export class OceanScene extends Phaser.Scene {
    constructor() {
        super('ocean');
        this.objects = new Map();
        this.lag = 0;
        this.particles = [];
    }

    create() {
        this.background = this.add.image(0, 0, '__WHITE').setOrigin(.5, 0).setDepth(-10).setVisible(false);
        this.floor = this.add.graphics().setDepth(-5);
        this.zones = this.add.graphics().setDepth(1);
        this.effects = this.add.graphics().setDepth(6);
        this.playerSprite = this.add.image(0, 0, '__WHITE').setDepth(4).setVisible(false);
        this.weaponSprite = this.add.image(0, 0, '__WHITE').setDepth(5).setVisible(false);
        this.hooks.ready(this);
    }

    loadLevel(world, manifest) {
        const boss = world.data.bosses[world.stage.boss_idx].key;
        const enemies = new Set(world.stage.enemy_pool.map(key => 'enemies/enemy_' + key));
        const keys = Object.keys(manifest).filter(key =>
            key === 'backgrounds/bg' + world.level || key === 'bosses/' + boss ||
            (world.stage.enemy_pool.includes('zongzong') && key === 'bosses/zongzong') ||
            (world.level === 9 && key === 'animations/bosses/anim_boss_mecha_lizard') ||
            (world.level === 10 && /^enemies\/enemy_ancient_(rift|worm)/.test(key)) ||
            (world.level === 11 && key.startsWith('bosses/boss_orochi_')) ||
            key.startsWith('animations/bosses/anim_' + boss) ||
            key.startsWith('players/') || key.startsWith('animations/players/') ||
            key.startsWith('effects/') || key.startsWith('weapons/') ||
            enemies.has(key.replace(/_action$/, '')) || ['ui/coin', 'ui/gift_box'].includes(key));
        const soundNames = [...soundKeys, 'music-0', 'music-' + world.level, 'music-' + world.level + '-boss'];
        this.nextAssets = new Set(keys);
        this.nextAudio = new Set(soundNames);
        for (const key of keys) {
            if (this.textures.exists(key)) continue;
            const {url, frame} = manifest[key];
            if (frame) this.load.spritesheet(key, url, {frameWidth: frame[0], frameHeight: frame[1]});
            else this.load.image(key, url);
        }
        for (const name of soundNames) {
            if (!this.cache.audio.exists(name)) this.load.audio(name, 'audio/' + name + '.wav');
        }
        if (!this.load.list.size) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const failures = [];
            const fail = file => failures.push(file.key);
            this.load.on('loaderror', fail);
            this.load.once('complete', () => {
                this.load.off('loaderror', fail);
                if (failures.length) reject(new Error('无法加载资源：' + failures.join('、')));
                else resolve();
            });
            this.load.start();
        });
    }

    showWorld(world) {
        this.clearWorld();
        this.world = world;
        this.playerSprite.setVisible(true);
        this.weaponSprite.setVisible(true);
        this.background.setVisible(true).setTexture('backgrounds/bg' + world.level);
        this.resizeWorld();
        this.playMusic('music-' + world.level + (world.phase === 'boss' ? '-boss' : ''));
        for (const key of this.textures.getTextureKeys()) if (!this.nextAssets.has(key)) this.textures.remove(key);
        for (const key of this.cache.audio.getKeys()) if (!this.nextAudio.has(key)) this.cache.audio.remove(key);
        this.renderWorld();
    }

    clearWorld() {
        this.lag = 0;
        this.particles = [];
        this.world = null;
        for (const object of this.objects.values()) object.destroy();
        this.objects.clear();
        this.playerSprite.setVisible(false);
        this.weaponSprite.setVisible(false);
        this.background.setVisible(false);
        this.floor.clear();
        this.zones.clear();
        this.effects.clear();
    }

    resizeWorld() {
        const w = this.world;
        const {canvasWidth, height, offset} = w.view;
        this.scale.setGameSize(canvasWidth, height);
        this.cameras.main.setScroll(-offset, 0);
        const texture = this.background.texture.getSourceImage();
        const zoom = Math.max(canvasWidth / texture.width, height / texture.height);
        this.background.setDisplaySize(texture.width * zoom, texture.height * zoom);
        this.floor.clear().fillStyle(0x071622, .48).fillRect(-offset, w.bottom, canvasWidth, height - w.bottom);
        this.floor.lineStyle(1, 0xaddbdb, .5).lineBetween(-offset, w.bottom, canvasWidth - offset, w.bottom);
    }

    playMusic(key) {
        if (this.musicKey === key) return;
        this.music?.destroy();
        this.music = null;
        this.musicKey = key;
        if (key && this.cache.audio.exists(key)) {
            this.music = this.sound.add(key, {volume: .27, loop: true});
            this.music.play();
        }
    }

    update(_time, delta) {
        const world = this.world;
        if (!world || this.hooks.paused()) return;
        this.lag += Math.min(delta, 4 * STEP);
        while (this.lag + .0001 >= STEP) {
            this.lag -= STEP;
            world.step(this.hooks.input());
        }
        for (const event of world.events.splice(0)) this.feedback(event);
        this.renderWorld();
        this.hooks.frame(world);
    }

    feedback(event) {
        const sounds = {shoot: event.weapon, hit: 'hit', hurt: 'hurt', coin: 'coin', skill: 'skill', boss: 'boss', clear: 'clear'};
        const key = sounds[event.type];
        if (key && this.cache.audio.exists(key)) {
            const now = this.time.now;
            this.soundAt ??= {};
            if (now - (this.soundAt[key] ?? -1000) > 85) {
                this.sound.play(key, {volume: key === 'hit' ? .18 : .42});
                this.soundAt[key] = now;
            }
        }
        if (event.type === 'boss') this.playMusic('music-' + this.world.level + '-boss');
        if (event.type === 'clear') this.playMusic(null);
        if (event.type === 'gift') this.hooks.notice(event.name);
        if (event.type === 'noAmmo') this.hooks.notice('金币不足，已切回手枪');
        if (event.x == null) return;
        const amount = event.type === 'clear' ? 36 : event.type === 'pop' ? 12 : 4;
        for (let i = 0; i < amount; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 10 + Math.random() * 90;
            this.particles.push({x: event.x, y: event.y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
                color: event.type === 'hurt' ? 0xff514e : i % 3 ? 0xffbf66 : 0xffffff, born: this.time.now});
        }
    }

    sprite(id, key, x, y, w, h, depth, frame = '__BASE') {
        if (!this.textures.exists(key)) return null;
        let sprite = this.objects.get(id);
        if (!sprite) {
            sprite = this.add.image(x, y, key, frame).setDepth(depth);
            this.objects.set(id, sprite);
        }
        if (sprite.texture.key !== key || sprite.frame.name !== frame) sprite.setTexture(key, frame);
        sprite.setPosition(x, y).setDisplaySize(w, h);
        this.live.add(id);
        return sprite;
    }

    animated(key, time, pace = 125) {
        if (!this.textures.exists(key)) return null;
        const frames = this.textures.get(key).frameTotal - 1;
        return frames > 0 ? Math.floor(time / pace) % frames : null;
    }

    renderWorld() {
        const w = this.world, t = w.time, p = w.player;
        const progress = Math.min(1, (t - w.started) / 40000);
        this.background.setPosition(w.width / 2, (w.view.height - this.background.displayHeight) * (1 - progress));
        this.live = new Set();
        this.zones.clear();
        this.effects.clear();
        this.drawPlayer(w, p, t);
        for (const e of w.enemies) this.drawEnemy(e, t);
        if (w.boss) this.drawBoss(w.boss, t);
        for (const b of w.bullets) {
            const color = fxColors[b.element] ?? bulletColors[b.weapon];
            if (b.art) {
                this.sprite(b.id, 'effects/' + b.art, b.x, b.y, b.w * 1.5, b.h * 1.5, 3);
                continue;
            }
            if (!b.weapon) {
                this.effects.fillStyle(color, .25).fillCircle(b.x, b.y, b.w * .48);
                this.effects.fillStyle(color, .95).fillCircle(b.x, b.y, b.w * .30);
                this.effects.fillStyle(0xfff4d1, .9).fillCircle(b.x, b.y, b.w * .10);
                continue;
            }
            const tailX = b.x - Math.sin(b.angle) * 22, tailY = b.y + Math.cos(b.angle) * 22;
            this.effects.lineStyle(9, color, .24).lineBetween(tailX, tailY, b.x, b.y);
            this.effects.lineStyle(5, color, .93).lineBetween(tailX, tailY, b.x, b.y);
            this.effects.fillStyle(0xffffe3, .95).fillCircle(b.x, b.y, 2.5);
        }
        for (const s of w.shots) {
            const sprite = this.sprite(s.id, 'effects/' + s.art, s.x, s.y, s.r * 2.4, s.r * 2.4, 3);
            if (sprite) {
                const directional = /missile|crescent|axe|trident/.test(s.art);
                sprite.setRotation(s.spin ? t / 88 : directional ? s.angle - Math.PI / 2 : 0)
                    .setAlpha(s.fuseAt && Math.floor(t / 100) % 2 ? .55 : 1);
            }
        }
        for (const drop of w.drops) {
            const size = drop.kind === 'gift' ? 40 : 23;
            this.sprite(drop.id, drop.kind === 'gift' ? 'ui/gift_box' : 'ui/coin', drop.x, drop.y, size, size, 2);
        }
        for (const z of w.zones) this.drawZone(z, t);
        if (w.link) {
            const group = w.link.group;
            this.effects.lineStyle(3, 0x8df9ff, .92);
            for (let i = 1; i < group.length; i++) this.effects.lineBetween(group[i - 1].x, group[i - 1].y, group[i].x, group[i].y);
        }
        this.particles = this.particles.filter(particle => this.time.now - particle.born < 510);
        for (const q of this.particles) {
            const age = (this.time.now - q.born) / 1000;
            this.effects.fillStyle(q.color, Math.max(0, 1 - age * 2)).fillCircle(q.x + q.vx * age, q.y + q.vy * age, 2 + 2 * (1 - age));
        }
        for (const [id, object] of this.objects) {
            if (!this.live.has(id)) { object.destroy(); this.objects.delete(id); }
        }
    }

    drawPlayer(world, player, time) {
        const hero = world.character === 'player1' ? 'player1' : 'player_' + world.character;
        const action = world.lastFire + 165 > time ? 'attack' : player.moving ? 'run' : 'idle';
        const key = 'animations/players/anim_' + hero + '_' + action;
        const frame = this.animated(key, time, 100);
        this.playerSprite.setTexture(frame === null ? 'players/' + hero : key, frame ?? '__BASE')
            .setPosition(player.x, player.y).setDisplaySize(player.w, player.h)
            .setAlpha(world.invulnerable > time && Math.floor(time / 70) % 2 ? .5 : 1);
        this.weaponSprite.setTexture(weaponImage(world.weapon)).setPosition(player.x + player.w * .21, player.y - player.h * .15)
            .setDisplaySize(30 * world.view.entityScale, 24 * world.view.entityScale).setAngle(-78);
    }

    drawEnemy(e, t) {
        let key = 'enemies/enemy_' + e.kind, frame = '__BASE';
        if (e.kind === 'zongzong') key = 'bosses/zongzong';
        if (e.shotAt > t - 480 && this.textures.exists(key + '_action')) key += '_action';
        if (e.kind === 'orochi_bubble') key = 'effects/orochi_bubble_' + bubbleColors[e.index];
        if (e.kind === 'orochi_head') {
            key = 'animations/bosses/anim_boss_orochi_split';
            frame = this.animated(key, t + e.index * 60, 55) ?? '__BASE';
        }
        if (e.kind === 'mecha_mini') {
            key = 'animations/bosses/anim_boss_mecha_lizard';
            frame = this.animated(key, t, 160) ?? '__BASE';
        }
        const sprite = this.sprite(e.id, key, e.x, e.y, e.w, e.h, 2, frame);
        if (!sprite) return;
        sprite.setTint(e.hitAt > t - 130 ? 0xffbdb4 : e.frozenUntil > t ? 0x89e9ff : e.tint ?? 0xffffff);
        if (e.hp < e.maxHp || e.kind === 'ancient_rift') {
            this.effects.fillStyle(0x071824, .85).fillRect(e.x - e.w * .36, e.y - e.h / 2 - 4, e.w * .72, 4);
            this.effects.fillStyle(0xffa060, 1).fillRect(e.x - e.w * .36, e.y - e.h / 2 - 4, e.w * .72 * e.hp / e.maxHp, 3);
        }
    }

    drawBoss(b, t) {
        let key = 'bosses/' + (b.level === 8 ? 'zongzong' : b.def.key), frame = '__BASE';
        const attacking = b.skillUntil > t;
        const animation = 'animations/bosses/anim_' + b.def.key + (
            b.level === 11 ? '_idle' : b.level >= 9 ? '' : '_attack');
        if (b.level >= 9 || attacking) {
            const current = this.animated(animation, t, b.level === 11 ? 80 : 130);
            if (current !== null) { key = animation; frame = current; }
        }
        if (b.rush) {
            const age = t - b.rush.start;
            if (age < 1322 || (age >= 3322 && age < 4644)) {
                key = 'effects/boss_bite';
                frame = '__BASE';
            }
        }
        const breathe = 1 + Math.sin(t / 440) * .026;
        for (const box of bossBoxes(b, t)) {
            this.sprite(box.index == null ? b.id : b.id + ':' + box.index, key, box.x, box.y,
                box.w * breathe, box.h * breathe, 2, frame)
                ?.setTint(b.hitAt > t - 125 ? 0xffa198 : box.index === 1 ? 0xdbb6ff : 0xffffff);
        }
        if (b.shieldUntil > t) {
            this.effects.lineStyle(5, 0x80f4ff, .72).strokeEllipse(b.x, b.y, b.w * 1.25, b.h * 1.13);
        }
        if (b.pull) {
            this.effects.lineStyle(2, 0x8becff, .72);
            for (let i = 0; i < 5; i++) {
                const n = (t / 730 + i / 5) % 1;
                this.effects.strokeEllipse(b.x, b.y + 15 + n * 220, 15 + n * 190, 12 + n * 49);
            }
        }
    }

    drawZone(z, t) {
        const active = t >= z.impact;
        if (z.rail && this.world.boss) {
            const {points, striking, width} = railShape(z, this.world.boss, this.world.bottom, t);
            const [x, y] = points[0];
            this.zones.fillStyle(0x7eeaff, .7).fillCircle(x, y, width * .55);
            if (active) {
                const path = points.map(([px, py]) => ({x: px, y: py}));
                this.zones.lineStyle(width, 0x235596, .9).strokePoints(path);
                this.zones.lineStyle(width * .60, 0x40b6e6, .95).strokePoints(path);
                this.zones.lineStyle(width * .19, striking ? 0xebffff : 0x88d2f2, 1).strokePoints(path);
            }
            return;
        }
        if (z.tentacles && this.world.boss) {
            const {paths, striking} = tentacleShape(z, this.world.boss, this.world.view.height, t);
            for (const path of paths) for (let i = 1; i < path.length; i++) {
                const [x, y, width] = path[i];
                const [lastX, lastY] = path[i - 1];
                this.zones.lineStyle(width * 1.7, striking ? 0xa45ac6 : 0x72468c, .95).lineBetween(lastX, lastY, x, y);
                this.zones.lineStyle(width * .5, 0xf3a9dc, .8).lineBetween(lastX, lastY, x, y);
            }
            return;
        }
        if (z.claw) {
            if (active) this.sprite(z.id, 'effects/boss_claw', z.x, z.y - 48, 103, 145, 3)?.setFlipX(z.claw < 0);
            return;
        }
        if (z.artOnly) {
            if (active) this.sprite(z.id, 'effects/' + z.art, z.x, z.y,
                z.art.startsWith('boss_trident') ? 42 : z.w, z.h, 3);
            return;
        }
        if (!active && z.silent) return;
        const x = zoneX(z, t);
        const color = fxColors[z.effect] ?? (active ? 0xff8653 : 0xff505b);
        this.zones.fillStyle(color, active ? .30 : .14).lineStyle(active ? 3 : 2, color, .80);
        if (z.dart) {
            this.zones.fillCircle(x, z.y, z.w / 2).strokeCircle(x, z.y, z.w / 2);
            return;
        }
        if (z.circle) {
            if (!z.ring) this.zones.fillCircle(x, z.y, z.w / 2);
            this.zones.strokeCircle(x, z.y, z.w / 2);
        } else {
            this.zones.fillRect(x - z.w / 2, z.y - z.h / 2, z.w, z.h);
            this.zones.strokeRect(x - z.w / 2, z.y - z.h / 2, z.w, z.h);
        }
        if (z.art && active) this.sprite(z.id, 'effects/' + z.art, x, z.y, z.w, z.h, 3)?.setAlpha(.8);
    }
}
