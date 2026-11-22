"""Fossil trench waves, warning geometry and the shieldfish encounter."""
from functools import lru_cache
import math
import random

import pygame

from . import config
from .abyss_bosses import AbyssBoss, AbyssProjectile, _blit
from .asset_loader import image_asset, scale_surface_cached
from .entities import BossProjectile
from .render import Draw, RenderSurface, blit_effect, effect_layer, scaled_surface
from .visuals import draw_glow


def wave_key(index):
    return config.TRENCH_WAVES[index // 4 % 3][index % 4]


def enemy_shots(enemy, target, now, tier=1):
    delay, speed, aimed = config.TRENCH_ATTACKS[enemy.edef['key']]
    enemy.last_attack_time = now
    enemy.attack_interval = random.randint(enemy.attack_interval_min, enemy.attack_interval_max)
    x, y = enemy.x, enemy.y + enemy.h * .72
    dx, dy = target.rect().centerx - x, target.rect().centery - y
    angle = math.degrees(math.atan2(dx, dy)) if aimed else 0
    shots = []
    for offset in config.TRENCH_FAN_ANGLES[tier]:
        shot = AbyssProjectile('pearl_fragment', x, y, angle=angle + offset,
                               speed=speed, warning_ms=delay, active_ms=3600, scale=enemy.size_scale)
        shot.spawn_time = shot.last_update = now
        shots.append(shot)
    return shots


def _cannon_layout():
    return 'wide' if config.SCREEN_WIDTH >= config.SCREEN_HEIGHT else 'portrait'


def cannon_muzzle(side):
    layout = _cannon_layout()
    x, y = config.TRENCH_CANNON['muzzles'][layout][side]
    return x * config.SCREEN_WIDTH, y * config.SCREEN_HEIGHT


def cannon_shots(side):
    x, y = cannon_muzzle(side)
    element, damage = ('fire', 2) if side == 0 else ('ice', 1)
    direction = 1 if side == 0 else -1
    layout = _cannon_layout()
    return [TrenchBolt(element, x, y, direction * angle, speed=5.4, damage=damage)
            for angle in config.TRENCH_CANNON['angles'][layout]]


def draw_cannon_charge(surf, now, fire_at, side, *, visual_scale=1):
    width, height = config.TRENCH_CANNON['mouth_size'][_cannon_layout()]
    size = (round(width * config.SCREEN_WIDTH), round(height * config.SCREEN_HEIGHT))
    radius = max(size) / 2
    for index, kind in enumerate(('fire', 'ice')):
        color = config.TRENCH_CANNON['colors'][kind]
        muzzle = cannon_muzzle(index)
        target = scaled_surface(surf, muzzle, visual_scale)
        layer = effect_layer(target, size)
        mouth = pygame.Rect((0, 0), size)
        Draw.ellipse(layer, (*color, 160), mouth)
        mouth.center = muzzle
        blit_effect(target, layer, mouth.topleft)
        if index == side and 0 <= fire_at - now <= config.TRENCH_CANNON['warning']:
            pulse = .5 + .5 * math.sin(now / 42)
            draw_glow(target, muzzle, round(radius * (1 + .55 * pulse)), color, 195)


class TrenchBolt(AbyssProjectile):
    """Delayed aimed shots use the existing projectile lifecycle and collision."""
    COLORS = {'bone': (255, 230, 166), 'armor': (225, 208, 173),
              **config.TRENCH_CANNON['colors']}

    def __init__(self, kind, x, y, angle=0, *, speed, damage=1, delay=0,
                 boss=None, offset=0, scale=1):
        super().__init__('pearl_fragment', x, y, angle=angle, speed=speed,
                         warning_ms=delay, active_ms=3400, damage=damage, scale=scale)
        self.kind = kind
        self.owner = boss
        self.offset = offset
        self.launched = boss is None
        self.r = max(5, round(config.TRENCH_BOLT_RADIUS[kind] * scale))

    def update(self, target_x=None, target_y=None):
        now = config.game_ticks()
        if not self.launched:
            age = now - self.spawn_time
            boss = self.owner
            self.x, self.y = boss.x, boss.y + boss.h * .78
            if self.kind == 'armor':
                phase = self.offset + age * .18
                self.x += math.sin(math.radians(phase)) * boss.w * .62
                self.y = boss.y + boss.h * (.5 + .47 * math.cos(math.radians(phase)))
                self.x = max(config.GAME_AREA_LEFT + self.r, min(config.GAME_AREA_RIGHT - self.r, self.x))
                self.y = max(self.r, min(config.GAME_AREA_BOTTOM - self.r, self.y))
            if age >= self.warning_ms and target_x is not None and target_y is not None:
                self.angle = math.degrees(math.atan2(target_x - self.x, target_y - self.y))
                if self.kind == 'bone':
                    self.angle += self.offset
                self.launched = True
        bounds = (0, config.SCREEN_WIDTH) if self.kind in ('fire', 'ice') else None
        super().update(target_x, target_y, horizontal_bounds=bounds)

    def draw(self, surf):
        if not self.alive or (not self.launched and self.kind != 'armor'):
            return
        color = self.COLORS[self.kind]
        if self.kind in ('fire', 'ice'):
            draw_glow(surf, (self.x, self.y), self.r + 6, color, 165)
        rad = math.radians(self.angle)
        forward = pygame.Vector2(math.sin(rad), math.cos(rad)) * self.r
        across = forward.rotate(90) * .60
        center = pygame.Vector2(self.x, self.y)
        tip = center + forward * (1.65 if self.kind == 'bone' else 1)
        points = (tip, center + across, center - forward, center - across)
        Draw.polygon(surf, color, points)
        Draw.polygon(surf, (255, 252, 223), (tip, center + across, center), 1)


class TrenchSpire(BossProjectile):
    """Ground crack followed by one rising, damaging fossil spike."""
    def __init__(self, x, y, width, height, warning):
        super().__init__(x, y, 0, 0, damage=2)
        self.width, self.height = width, height
        self.warning_ms = warning
        self.max_lifetime = warning + 540
        self.last_update = self.spawn_time
        self.persistent = self.unblockable = True
        self._hit_players = set()

    def update(self, target_x=None, target_y=None):
        self.alive = config.game_ticks() - self.spawn_time < self.max_lifetime

    def rise(self, age):
        return self.height * min(1, max(0, (age - self.warning_ms) / 135))

    def hits_rect(self, rect):
        age = config.game_ticks() - self.spawn_time
        if not self.alive or not self.warning_ms <= age < self.max_lifetime:
            return False
        height = self.rise(age)
        if height <= 0 or not rect.top < self.y or rect.bottom <= self.y - height:
            return False
        widest = self.width / 2 * min(1, (rect.bottom - self.y + height) / height)
        return rect.right > self.x - widest and rect.left < self.x + widest

    def draw(self, surf):
        age = config.game_ticks() - self.spawn_time
        if not self.alive or not self.warning_ms - 380 <= age < self.max_lifetime:
            return
        x, y = self.x, self.y
        w = self.width / 2
        path = [(x + w * a, y + b) for a, b in ((-1, 2), (-.55, -4), (-.14, 2), (.28, -6), (.63, 0), (1, -3))]
        Draw.lines(surf, (36, 33, 45), False, path, 7)
        Draw.lines(surf, (255, 155, 72), False, path, 2)
        height = self.rise(age)
        if height > 0:
            tip = (x, y - height)
            Draw.polygon(surf, (225, 205, 175), ((x - w, y), tip, (x + w, y)))
            Draw.polygon(surf, (136, 121, 133), (tip, (x + w, y), (x + w * .12, y)))
            Draw.line(surf, (255, 241, 213), (x - w, y), tip, 2)
            for step in (.28, .53, .76):
                Draw.line(surf, (184, 159, 143),
                          (x - w * step, y - height * (1 - step)),
                          (x + w * .11, y - height * (1 - step) * .82), 2)


@lru_cache(maxsize=60)
def _pose(atlas, row, index):
    w, h = atlas.get_width() // 6, atlas.get_height() // 5
    return atlas.subsurface((w * index, h * row, w, h))


class ShieldfishBoss(AbyssBoss):
    LABELS = dict(trench_roll='化岩冲锋', trench_bones='裂颚骨刺', trench_spires='怒吼地裂')
    SKILLS = ('trench_roll', 'trench_bones', 'trench_spires')
    TIMINGS = {'trench_roll': config.TRENCH_ROLL_TIMING,
               'trench_bones': (480, 1260, 820),
               'trench_spires': (620, 1280, 920)}

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.skill_end_at = 0
        self.recovery_at = 0
        self.motion_start = self.motion_end = (self.x, self.y)
        self.roll_locked = False
        self.armor_threshold = .75
        self.armor_pending = 0
        self.patrol_direction = 1

    def _next_attack_skill(self):
        if self._last_attack_skill is None:
            self._pending_attack_skill = self._choose_attack_skill(('trench_roll',))
        return super()._next_attack_skill()

    def should_attack(self, now):
        return now >= self.skill_end_at and super().should_attack(now)

    def exposed(self, now):
        return (bool(self.current_skill) and now < self.skill_end_at
                and (now >= self.recovery_at or self.current_skill == 'trench_bones'))

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        now = config.game_ticks()
        previous_hp = self.hp
        super().hit_by(weapon_name, amount if self.exposed(now) else amount * .60, source, hit_rect)
        if 0 < self.hp < previous_hp:
            while self.armor_threshold > 0 and self.hp <= self.max_hp * self.armor_threshold:
                self.armor_threshold -= .25
                self.armor_pending += 1

    def armor_shots(self):
        shots = [TrenchBolt('armor', self.x, self.y, speed=10.5, delay=1000,
                            boss=self, offset=i * 90 + wave * 26, scale=self.size_scale)
                 for wave in range(self.armor_pending) for i in range(4)]
        self.armor_pending = 0
        return shots

    def _skill_shots(self, skill, player_x, player_y):
        warning, active, recovery = self.TIMINGS[skill]
        self.recovery_at = self.skill_started_at + warning + active
        self.skill_end_at = self.recovery_at + recovery
        self.motion_start = self.motion_end = (self.x, self.y)
        bottom = config.GAME_AREA_BOTTOM
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        if skill == 'trench_roll':
            self.roll_locked = False
            self._aim_roll(player_x, bottom if player_y is None else player_y)
            return []
        if skill == 'trench_bones':
            return [TrenchBolt('bone', self.x, self.y, speed=4.7, delay=warning + wave * 420,
                               boss=self, offset=offset, scale=self.size_scale)
                    for wave in range(4) for offset in (-7, 7)]
        span = right - left
        lanes = random.sample(range(7), 5)
        return [TrenchSpire(left + span * (lane + random.uniform(.28, .72)) / 7,
                            bottom - random.uniform(0, bottom * .055),
                            min(span / 8, 74 * self.size_scale),
                            bottom * random.uniform(.24, .36), warning + i * 170)
                for i, lane in enumerate(lanes)]

    def _aim_roll(self, x, y):
        start_x, start_y = self.motion_start
        target_y = y - self.h / 2
        self.roll_target = x, target_y
        bottom = config.SCREEN_HEIGHT + self.h * .65
        exit_x = x
        if target_y > start_y:
            exit_x += (x - start_x) * (bottom - target_y) / (target_y - start_y)
        exit_x = max(config.GAME_AREA_LEFT, min(config.GAME_AREA_RIGHT, exit_x))
        self.motion_end = exit_x, bottom
        first = math.hypot(x - start_x, target_y - start_y)
        remaining = math.hypot(exit_x - x, bottom - target_y)
        self.roll_fraction = first / (first + remaining)

    def rolling(self, now):
        return self.current_skill == 'trench_roll' and (
            self.skill_started_at + self.TIMINGS['trench_roll'][0] <= now < self.recovery_at)

    def hitboxes(self):
        now = config.game_ticks()
        if self.rolling(now):
            radius = self.h * .36
            return (pygame.Rect(self.x - radius, self.y + self.h / 2 - radius, radius * 2, radius * 2),)
        return super().hitboxes()

    def collides(self, rect):
        return any(box.colliderect(rect) for box in self.hitboxes())

    def update(self, target=None):
        if not self.entered:
            super().update()
            return
        now = config.game_ticks()
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        half = min(self.w / 2, (right - left) / 2)
        if now >= self.skill_end_at:
            self.x += self.patrol_direction * self.speed * 2
            if self.x >= right - half or self.x <= left + half:
                self.x = max(left + half, min(right - half, self.x))
                self.patrol_direction *= -1
            target_y = 38 + 17 * math.sin((now - self.fight_start_time) / 530)
            self.y += max(-5, min(5, target_y - self.y))
        elif self.rolling(now):
            warning, active, _ = self.TIMINGS['trench_roll']
            if target is not None and not self.roll_locked:
                self._aim_roll(*target.rect().center)
                self.roll_locked = True
            fraction = (now - self.skill_started_at - warning) / active
            if fraction < self.roll_fraction:
                start, end = self.motion_start, self.roll_target
                step = fraction / self.roll_fraction
            else:
                start, end = self.roll_target, self.motion_end
                step = (fraction - self.roll_fraction) / (1 - self.roll_fraction)
            self.x, self.y = (a + (b - a) * step for a, b in zip(start, end))
        elif self.current_skill == 'trench_roll' and now >= self.recovery_at:
            fraction = (now - self.recovery_at) / (self.skill_end_at - self.recovery_at)
            self.x = max(left + half, min(right - half, self.motion_end[0]))
            self.y = -self.h + (self.h + 48) * fraction

    def draw(self, surf, *, visual_scale=1):
        atlas = image_asset('animations/bosses/anim_boss_shieldfish.png')
        if atlas is None:
            super().draw(surf, visual_scale=visual_scale)
            return
        now = config.game_ticks()
        skill = self.current_skill if now < self.skill_end_at else ''
        age = max(0, now - self.skill_started_at)
        row, index = 0, max(0, now - self.breath_start_time) // 132 % 6
        roll = skill == 'trench_roll' and now < self.recovery_at
        if skill:
            row = {'trench_roll': 1, 'trench_bones': 2, 'trench_spires': 4}[skill]
            warning, active, _ = self.TIMINGS[skill]
            index = min(5, age * 3 // warning) if age < warning else 2 + (age - warning) // 100 % 3
        mid = (self.x, self.y + self.h / 2)
        scale = surf.scale if isinstance(surf, RenderSurface) else 1
        size = (self.w * visual_scale, self.h * visual_scale)
        art = scale_surface_cached(_pose(atlas, row, index), tuple(round(v * scale) for v in size))
        if roll and (rock := image_asset('effects/trench_roll.png')) is not None:
            morph = min(1, age / 850)
            turn = age * (.19 + .40 * morph)
            if morph < 1:
                fish = pygame.transform.rotate(art, -turn)
                fish.set_alpha(round(255 * (1 - morph)))
                _blit(surf, fish, mid, tuple(v / scale for v in fish.get_size()))
            diameter = self.h * visual_scale * (.40 + .36 * morph)
            rock = scale_surface_cached(rock, (round(diameter * scale),) * 2)
            rock = pygame.transform.rotate(rock, -turn)
            rock.set_alpha(round(255 * morph))
            _blit(surf, rock, mid, tuple(v / scale for v in rock.get_size()))
        else:
            _blit(surf, art, mid, size)
        if self.exposed(now):
            pulse = .5 + .5 * math.sin(age / 80)
            draw_glow(surf, (self.x - self.w * .12, self.y + self.h * .79),
                      round(self.w * (.06 + pulse * .02)), (95, 223, 255), 85)
