"""Yamata no Orochi's campaign encounter."""
import math
import random
from functools import lru_cache

import pygame

from . import asset_loader, config
from .asset_loader import image_asset, scale_surface_cached
from .entities import Boss, BossProjectile, Enemy
from .render import Draw, RenderSurface
from .sounds import play_sound
from .visuals import draw_electric_arc, draw_glow


def _load_art(path):
    art = image_asset(path)
    if art is not None:
        return art.subsurface(art.get_bounding_rect(min_alpha=8))


def _blit_art(surf, art, rect):
    if isinstance(surf, RenderSurface):
        surf.blit(art, rect.topleft, logical_size=rect.size, static=True)
    else:
        surf.blit(scale_surface_cached(art, rect.size), rect.topleft)



@lru_cache(maxsize=72)
def _turn_fireball(sprite, angle):
    return pygame.transform.rotate(sprite, angle)


class OrochiFireball(BossProjectile):
    def __init__(self, x, y, color, art):
        super().__init__(x, y, 0, 4.6, homing=True)
        self.color = color
        self.damage = 2
        self.art = art
        self.r = 10

    def update(self, target_x=None, target_y=None):
        if target_x is not None and target_y is not None:
            angle = math.degrees(math.atan2(target_x - self.x, target_y - self.y))
            delta = (angle - self.angle + 180) % 360 - 180
            self.angle += max(-2, min(2, delta))
        super().update()

    def draw(self, surf):
        center = (round(self.x), round(self.y))
        draw_glow(surf, center, 21, self.color, 160)
        if self.art is None:
            Draw.circle(surf, self.color, center, self.r)
            return
        angle = round(self.angle / 10) * 10 % 360
        offset = pygame.Vector2(0, -12).rotate(-angle)
        position = self.x + offset.x, self.y + offset.y
        if isinstance(surf, RenderSurface):
            size = surf.length(25), surf.length(49)
            sprite = _turn_fireball(scale_surface_cached(self.art, size), angle)
            surf.blit_pixels(sprite, sprite.get_rect(center=surf.point(position)).topleft)
        else:
            sprite = _turn_fireball(scale_surface_cached(self.art, (25, 49)), angle)
            surf.blit(sprite, sprite.get_rect(center=tuple(round(value) for value in position)))


class OrochiBoss(Boss):
    SKILLS = ('volley', 'slam', 'split', 'laser')
    FIRE_COLORS = ((255, 58, 43), (255, 211, 41))
    HEAD_MOUTHS = ((.045, .66), (.13, .49), (.13, .32), (.30, .22),
                   (.70, .20), (.87, .35), (.86, .51), (.96, .67))
    HEAD_CENTERS = ((.068, .626), (.158, .452), (.154, .275), (.326, .159),
                    (.665, .149), (.851, .273), (.829, .453), (.945, .628))
    IDLE_COLUMNS = 6
    IDLE_ROWS = 4
    IDLE_STEP = 80
    IDLE_PERIOD = IDLE_COLUMNS * IDLE_ROWS * IDLE_STEP
    # The original 624×432 cell has 24 pixels of padding on each side.
    IDLE_ART_SIZE = (624, 432)
    IDLE_PADDING = 24
    SLAM_ROUND = 1350
    SLAM_IMPACT = 900
    SLAM_FALL_MS = 190
    SLAM_HOLD_MS = 90
    SPLIT_EXIT = 2750
    SPLIT_RETURN = 3100
    SPLIT_END = 4150
    LASER_WARNING = 850
    LASER_END = LASER_WARNING + 3000
    LASER_WIDTH = 18
    STORM_DURATION = 10000
    HEAD_HP_RATIO = .03
    THUNDER_INTERVAL = 1200
    DEATH_DURATION = 1600

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.skill = None
        self.skill_at = 0
        self.next_skill = 0
        self.opening_pending = True
        self.spawned_at = config.game_ticks()
        self.emitted = 0
        self.shots = []
        self.impacts = []
        self.head_hp = []
        self.storm_thresholds = [.5, .01]
        self.final_storm = False
        self.invincible_until = 0
        self.death_at = None
        self.death_particles = ()
        self.hazard_hit = None
        self.hit_flashes = []
        self.last_head_hit_sound = -1000
        self._load_artwork()

    def _load_artwork(self):
        self._hd_artwork = asset_loader.web_hd_assets
        self.idle_frames = self._load_idle_frames()
        self.slam_art = _load_art('bosses/boss_orochi_slam.png')
        self.laser_art = _load_art('bosses/boss_orochi_laser.png')
        self.split_art = _load_art('bosses/boss_orochi_split.png')
        self.fire_art = _load_art('effects/orochi_fireball.png')
        self.gold_fire_art = None
        if self.fire_art is not None:
            self.gold_fire_art = self.fire_art.copy()
            self.gold_fire_art.fill((0, 138, 10), special_flags=pygame.BLEND_RGB_ADD)

    def should_attack(self, now):
        return (self.entered and self.skill is None and self.death_at is None
                and now >= self.invincible_until
                and (now - self.fight_start_time >= 5000 if self.opening_pending
                     else now - self.last_attack_time >= self.attack_interval))

    def attack(self, now, player_x):
        if self.opening_pending:
            self.opening_pending = False
            skill = random.choice(self.SKILLS)
        else:
            skill = self.SKILLS[self.next_skill]
            self.next_skill = (self.next_skill + 1) % len(self.SKILLS)
        self._start_skill(skill, now)
        return []

    def _start_skill(self, skill, now):
        self.skill = skill
        self.skill_at = now
        self.emitted = 0
        self.hazard_hit = None
        if skill == 'split':
            self.split_hp = [self.head_max_hp] * 8
            self.split_xy = [[self._lane_x(i), 150] for i in range(8)]
            self.split_dive = None
            self.split_next_dive = now + 700
            self.split_charged = [False] * 8
            self.split_charge_until = [0] * 8
            self.split_velocity = [(0, 0)] * 8
            self.split_last_update = now
            self.split_regroup_at = None
            self.split_target = (self._center_x(), config.GAME_AREA_BOTTOM * .7)
        if skill == 'storm':
            self.head_hp = [self.head_max_hp] * len(self.HEAD_CENTERS)

    @property
    def head_max_hp(self):
        return self.max_hp * self.HEAD_HP_RATIO

    def _finish_skill(self, now):
        self.skill = None
        self.last_attack_time = now

    def age(self, now):
        return max(0, now - self.skill_at)

    def _center_x(self):
        return (config.GAME_AREA_LEFT + config.GAME_AREA_RIGHT) / 2

    def _lane_x(self, index):
        width = config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT
        return config.GAME_AREA_LEFT + width * (index + .5) / 8

    @classmethod
    def _load_idle_frames(cls):
        sheet = image_asset('animations/anim_boss_orochi_idle.png')
        if sheet is None:
            return ()
        return cls._slice_idle_sheet(sheet)

    @classmethod
    @lru_cache(maxsize=2)
    def _slice_idle_sheet(cls, sheet):
        width = sheet.get_width() // cls.IDLE_COLUMNS
        height = sheet.get_height() // cls.IDLE_ROWS
        return tuple(sheet.subsurface((col * width, row * height, width, height))
                     for row in range(cls.IDLE_ROWS) for col in range(cls.IDLE_COLUMNS))

    def _idle_index(self, now):
        return (now - self.spawned_at) % self.IDLE_PERIOD // self.IDLE_STEP

    def _idle_frame(self, now):
        return self.idle_frames[self._idle_index(now)] if self.idle_frames else None

    @classmethod
    def _idle_displacement(cls, x, y, frame):
        """Normalized mesh displacement, shared by the baked poses and mouth anchors."""
        phase = math.tau * frame / (cls.IDLE_COLUMNS * cls.IDLE_ROWS)
        # The bottom of each neck is anchored where it meets the coil.
        weight = max(0, min(1, (.745 - y) / .135))
        weight = weight * weight * (3 - 2 * weight)
        dx = dy = total = 0
        for i, (cx, cy) in enumerate(cls.HEAD_CENTERS):
            influence = math.exp(-((x - cx) / .102) ** 2 - ((y - cy) / .122) ** 2)
            step = phase + i * 1.21
            dx += influence * (.025 * math.sin(step) + .007 * math.sin(2 * step))
            dy += influence * .043 * math.cos(step + .55)
            total += influence
        scale = weight / max(1, total)
        return dx * scale, dy * scale

    @classmethod
    @lru_cache(maxsize=192)
    def _idle_mouth(cls, index, pose):
        source_x, source_y = cls.HEAD_MOUTHS[index]
        x, y = source_x, source_y
        # The sprite samples backwards through the mesh; solve for the visible point.
        for _ in range(4):
            dx, dy = cls._idle_displacement(x, y, pose)
            x, y = source_x + dx, source_y + dy
        return x, y

    def _mouth(self, index, now=None):
        if now is not None and self.idle_frames:
            x, y = self._idle_mouth(index, self._idle_index(now))
        else:
            x, y = self.HEAD_MOUTHS[index]
        body = self._body_art_rect()
        return body.x + x * body.w, body.y + y * body.h

    def update(self, target_x=None, target_y=None):
        now = config.game_ticks()
        if self.death_at is not None:
            return
        if self.skill is None:
            entering = not self.entered
            super().update()
            if entering and self.entered:
                self.fight_start_time = self.spawned_at
            return
        age = self.age(now)
        if self.skill == 'volley':
            while self.emitted < 8 and age >= self.emitted * 200:
                color = self.emitted % 2
                art = self.gold_fire_art if color else self.fire_art
                self.shots.append(OrochiFireball(*self._mouth(self.emitted, now), self.FIRE_COLORS[color], art))
                self.emitted += 1
            if age >= 1600:
                self._finish_skill(now)
        elif self.skill == 'slam':
            while self.emitted < 8 and age >= self.emitted * self.SLAM_ROUND + self.SLAM_IMPACT:
                self.impacts.extend((self._lane_x(i), config.GAME_AREA_BOTTOM)
                                    for i in self._slam_pair(self.emitted))
                self.emitted += 1
            if age >= 8 * self.SLAM_ROUND:
                self._finish_skill(now)
        elif self.skill == 'split':
            if target_x is not None and target_y is not None:
                self.split_target = (target_x, target_y)
            if self.split_regroup_at is not None:
                if now - self.split_regroup_at >= 900:
                    self._finish_skill(now)
            else:
                dt = min(100, max(0, now - self.split_last_update)) / 1000
                if self.split_dive is not None and self.split_hp[self.split_dive] <= 0:
                    self.split_dive = None
                    self.split_next_dive = now + 400
                if self.split_dive is None and now >= self.split_next_dive:
                    available = [i for i, hp in enumerate(self.split_hp)
                                 if hp > 0 and now >= self.split_charge_until[i]]
                    if available:
                        self.split_dive = random.choice(available)
                for i, position in enumerate(self.split_xy):
                    if self.split_hp[i] <= 0:
                        continue
                    if now < self.split_charge_until[i]:
                        vx, vy = self.split_velocity[i]
                        position[0] = max(config.GAME_AREA_LEFT + 22, min(config.GAME_AREA_RIGHT - 22, position[0] + vx * dt))
                        position[1] = max(120, min(config.GAME_AREA_BOTTOM - 10, position[1] + vy * dt))
                    elif i == self.split_dive:
                        position[1] += 800 * dt
                        if self._snake_rect(*position).top >= config.SCREEN_HEIGHT:
                            position[:] = [self._lane_x(i), 150]
                            self.split_dive = None
                            self.split_next_dive = now + random.randint(350, 750)
                    else:
                        dx, dy = self._lane_x(i) - position[0], 150 - position[1]
                        distance = math.hypot(dx, dy)
                        if distance:
                            step = min(distance, 260 * dt)
                            position[0] += dx * step / distance
                            position[1] += dy * step / distance
            self.split_last_update = now
        elif self.skill == 'laser' and age >= self.LASER_END:
            self._finish_skill(now)
        elif self.skill == 'storm':
            if age >= self.STORM_DURATION:
                surviving = sum(hp > 0 for hp in self.head_hp)
                self.hp = min(self.max_hp, self.hp + surviving * self.head_max_hp)
                self.invincible_until = now + 3000
                self._finish_skill(now)
            elif age // self.THUNDER_INTERVAL >= self.emitted:
                self.emitted = age // self.THUNDER_INTERVAL + 1
                play_sound('orochi_thunder')

    def _slam_pair(self, index):
        index %= 4
        return 3 - index, 4 + index

    def _slam_rects(self, age):
        index, elapsed = divmod(age, self.SLAM_ROUND)
        start = self.SLAM_IMPACT - self.SLAM_FALL_MS
        if index >= 8 or not start <= elapsed < self.SLAM_IMPACT + self.SLAM_HOLD_MS:
            return ()
        width = min(88, max(62, self.w // 4))
        height = round(width * 1.18)
        progress = min(1, (elapsed - start) / self.SLAM_FALL_MS)
        bottom = round(config.GAME_AREA_BOTTOM * progress ** 1.5)
        return tuple(pygame.Rect(round(self._lane_x(i) - width / 2), bottom - height, width, height)
                     for i in self._slam_pair(index))

    def split_positions(self):
        return tuple(tuple(position) for position in self.split_xy)

    def _laser_head_rects(self, age):
        size = min(self.w // 2, 108, max(36, config.GAME_AREA_BOTTOM // 5))
        spacing = size * 1.15
        shift = spacing * .35 * math.sin(age * .0035)
        return tuple(pygame.Rect(round(self._center_x() + shift + (i - 1) * spacing - size / 2),
                                 85, size, size) for i in range(3))

    def laser_paths(self, age):
        return [[(head.centerx, head.y + round(head.h * .74)),
                 (head.centerx, config.SCREEN_HEIGHT)]
                for head in self._laser_head_rects(age)]

    def hazard_hits(self, rect, age):
        if self.skill == 'laser' and self.LASER_WARNING <= age < self.LASER_END:
            expanded = rect.inflate(self.LASER_WIDTH, self.LASER_WIDTH)
            return any(expanded.clipline(a, b) for path in self.laser_paths(age)
                       for a, b in zip(path, path[1:]))
        if self.skill == 'slam':
            if rect.collidelist(self._slam_rects(age)) >= 0:
                return True
            index, elapsed = divmod(age, self.SLAM_ROUND)
            if index < 8 and self.SLAM_IMPACT <= elapsed < self.SLAM_IMPACT + 160:
                return any(rect.colliderect(pygame.Rect(self._lane_x(i) - 55,
                           config.GAME_AREA_BOTTOM - 54, 110, 54)) for i in self._slam_pair(index))
        if self.skill == 'split' and self.split_regroup_at is None:
            return any(hp > 0 and rect.colliderect(self._snake_rect(x, y))
                       for hp, (x, y) in zip(self.split_hp, self.split_positions()))
        return False

    def _snake_rect(self, x, y):
        return pygame.Rect(round(x - 22), round(y - 122), 44, 135)

    def _body_art_rect(self):
        width = round((self.base_w + 20) * self.size_scale)
        height = round((self.base_h + 20) * self.size_scale)
        return pygame.Rect(round(self.x - width / 2), round(self.y + (self.h - height) / 2), width, height)

    def head_rect(self, index):
        body = self._body_art_rect()
        x, y = self.HEAD_CENTERS[index]
        rect = pygame.Rect(0, 0, round(body.w * .123), round(body.h * .155))
        rect.center = (round(body.x + x * body.w), round(body.y + y * body.h))
        return rect

    def _active_heads(self, now):
        if self.age(now) >= self.STORM_DURATION:
            return
        for i, hp in enumerate(self.head_hp):
            if hp > 0:
                yield i, self.head_rect(i)

    def hitboxes(self):
        if self.death_at is not None:
            return ()
        now = config.game_ticks()
        if self.skill == 'storm':
            return tuple(rect for _, rect in self._active_heads(now))
        if self.skill == 'split':
            return tuple(self._snake_rect(x, y) for hp, (x, y) in zip(self.split_hp, self.split_positions()) if hp > 0)
        if self.skill == 'laser':
            return self._laser_head_rects(self.age(now))
        return (self.rect(),)

    def collides(self, rect):
        return any(rect.colliderect(box) for box in self.hitboxes())

    def lightning_hitbox(self, x, y):
        return min(self.hitboxes(), key=lambda rect: (rect.centerx - x) ** 2 + (rect.centery - y) ** 2,
                   default=None)

    def lightning_target(self, x, y):
        rect = self.lightning_hitbox(x, y)
        return rect.center if rect else (self.x, self.y + self.h // 2)

    def _hit_flash(self, rect, hit_rect, now, head=False):
        point = rect.clip(hit_rect).center if hit_rect is not None and rect.colliderect(hit_rect) else rect.center
        self.hit_flashes = [flash for flash in self.hit_flashes if now - flash[2] < 180][-11:]
        self.hit_flashes.append((*point, now))
        if head and now - self.last_head_hit_sound >= 100:
            play_sound('hit')
            self.last_head_hit_sound = now

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        now = config.game_ticks()
        if amount <= 0 or self.death_at is not None or now < self.invincible_until:
            return
        if self.skill == 'split':
            if hit_rect is None or self.split_regroup_at is not None:
                return
            for i, (x, y) in enumerate(self.split_positions()):
                if self.split_hp[i] > 0 and hit_rect.colliderect(self._snake_rect(x, y)):
                    self._hit_flash(self._snake_rect(x, y), hit_rect, now, head=True)
                    self.split_hp[i] = max(0, self.split_hp[i] - amount)
                    if 0 < self.split_hp[i] <= self.head_max_hp * .3 and not self.split_charged[i]:
                        dx, dy = self.split_target[0] - x, self.split_target[1] - y
                        distance = max(1, math.hypot(dx, dy))
                        self.split_velocity[i] = (360 * dx / distance, 360 * dy / distance)
                        self.split_charge_until[i] = now + 600
                        self.split_charged[i] = True
                    if not any(self.split_hp):
                        self.split_regroup_at = now
                    return
            return
        if self.skill == 'storm':
            if hit_rect is None:
                return
            for i, rect in self._active_heads(now):
                if hit_rect.colliderect(rect):
                    self._hit_flash(rect, hit_rect, now, head=True)
                    remaining = self.head_hp[i] - amount
                    self.head_hp[i] = remaining if remaining > 1e-9 else 0
                    if not any(self.head_hp):
                        if self.final_storm:
                            self._start_death(now)
                        else:
                            self._finish_skill(now)
                    return
            return
        if self.y < Enemy.ENTRY_DAMAGE_Y:
            return
        hitbox = next((rect for rect in self.hitboxes() if hit_rect and rect.colliderect(hit_rect)), self.rect())
        self._hit_flash(hitbox, hit_rect, now)
        super().hit_by(weapon_name, amount, source, hit_rect)
        if self.storm_thresholds and self.hp <= self.max_hp * self.storm_thresholds[0]:
            threshold = self.storm_thresholds.pop(0)
            self.hp = self.max_hp * threshold
            self.final_storm = threshold == .01
            self._start_skill('storm', now)
        elif self.hp <= 0:
            self._start_death(now)

    def _start_death(self, now):
        self.hp = 0
        self.skill = None
        self.death_at = now
        self.shots.clear()
        self.impacts.clear()
        art = self.surface
        w, h = art.get_size()
        particles = []
        for row in range(24):
            for col in range(36):
                u, v = (col + .5) / 36, (row + .5) / 24
                color = art.get_at((int(u * w), int(v * h)))
                if color.a > 125:
                    particles.append((u, v, color, random.uniform(-72, 72),
                                      random.uniform(22, 110), random.uniform(.45, 1)))
        self.death_particles = particles

    def is_killed(self):
        return self.death_at is not None and config.game_ticks() >= self.death_at + self.DEATH_DURATION

    def _draw_skill_sprite(self, surf, art, rect):
        if art is not None:
            _blit_art(surf, art, rect)
        else:
            Draw.ellipse(surf, (32, 159, 105), rect)
            Draw.ellipse(surf, (10, 48, 42), rect, 2)

    def storm_pulse(self, now):
        elapsed = self.age(now) % self.THUNDER_INTERVAL
        first = max(0, 1 - elapsed / 180)
        echo = .45 * max(0, 1 - (elapsed - 220) / 150) if elapsed >= 220 else 0
        return max(first, echo)

    def draw_storm_lightning(self, surf, now):
        pulse = self.storm_pulse(now)
        if pulse <= 0:
            return
        strike = self.age(now) // self.THUNDER_INTERVAL
        width = config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT
        center = self._center_x()
        bottom = config.GAME_AREA_BOTTOM
        for side in (-1, 1):
            x = center + side * width * (.32 if (strike + side) % 3 else .40)
            start = (x + side * width * .06, 0)
            fork = (x - side * width * .04, round(bottom * .36))
            end = (x + side * width * .045, round(bottom * .78))
            alpha = round(220 * pulse)
            color = (114, 159, 255)
            draw_electric_arc(surf, start, fork, color, alpha, now, strike + side, 5)
            draw_electric_arc(surf, fork, end, color, alpha, now, strike - side + 7, 4)
            draw_electric_arc(surf, fork, (x - side * width * .13, round(bottom * .57)),
                              (166, 136, 255), round(alpha * .76), now, strike + side + 18, 2)

    def _draw_slam(self, surf, age):
        index, elapsed = divmod(age, self.SLAM_ROUND)
        if index >= 8:
            return
        bottom = config.GAME_AREA_BOTTOM
        after_impact = elapsed - self.SLAM_IMPACT
        for i in self._slam_pair(index):
            x = self._lane_x(i)
            if 0 <= after_impact < 420:
                fade = round(220 * (1 - after_impact / 420))
                for side in (-1, 1):
                    crack = [(x, bottom), (x + 16 * side, bottom - 10),
                             (x + 26 * side, bottom - 4), (x + 51 * side, bottom - 17)]
                    Draw.lines(surf, (39, 22, 18, fade), False, crack, 5)
                    Draw.lines(surf, (255, 154, 76, fade), False, crack, 2)
        for head in self._slam_rects(age):
            if after_impact < 0:
                for offset in (-head.w // 4, 0, head.w // 4):
                    x = head.centerx + offset
                    Draw.line(surf, (124, 231, 176, 155), (x, head.top - 28),
                              (x, head.top + 9), 2)
            self._draw_skill_sprite(surf, self.slam_art, head)

    def _draw_idle(self, surf, now):
        art = self._idle_frame(now)
        if art is None:
            super().draw(surf)
            return
        body = self._body_art_rect()
        pad = self.IDLE_PADDING
        pad_x = round(body.w * pad / (self.IDLE_ART_SIZE[0] - 2 * pad))
        pad_y = round(body.h * pad / (self.IDLE_ART_SIZE[1] - 2 * pad))
        _blit_art(surf, art, body.inflate(2 * pad_x, 2 * pad_y))

    def _draw_storm(self, surf, now):
        art = image_asset(self.sprite_asset) if isinstance(surf, RenderSurface) else None
        _blit_art(surf, art or self.surface, self._body_art_rect())
        pulse = self.storm_pulse(now)
        for i, rect in self._active_heads(now):
            radius = max(7, rect.w // 2)
            Draw.circle(surf, (115, 204, 255, 90 + round(75 * pulse)), rect.center, radius + 5, 2)
            Draw.ellipse(surf, (170, 231, 255), rect.inflate(4, 4), 2)
            ratio = self.head_hp[i] / self.head_max_hp
            blink = .5 + .5 * math.sin(now * .012)
            marker = (rect.centerx, rect.top - 5)
            Draw.circle(surf, (255, 54, 62, round(100 + 155 * blink)), marker, 3 + round(3 * ratio))

    def draw(self, surf):
        if self._hd_artwork != asset_loader.web_hd_assets:
            self._load_artwork()
        now = config.game_ticks()
        age = self.age(now)
        if self.death_at is not None:
            progress = (now - self.death_at) / self.DEATH_DURATION
            for u, v, color, vx, vy, life in self.death_particles:
                if progress < life:
                    x = self.x + (u - .5) * self.w + vx * progress
                    y = self.y + v * self.h - vy * progress
                    opacity = round(255 * (1 - progress / life))
                    Draw.circle(surf, (*color[:3], opacity), (round(x), round(y)),
                                max(1, round(self.w / 90 * (1 - progress))))
        elif self.skill == 'split':
            if self.split_regroup_at is not None:
                progress = min(1, (now - self.split_regroup_at) / 900)
                for i, (x, y) in enumerate(self.split_positions()):
                    tx, ty = self._mouth(i, now)
                    self._draw_skill_sprite(surf, self.split_art, self._snake_rect(x + (tx - x) * progress, y + (ty - y) * progress))
            else:
                for hp, (x, y) in zip(self.split_hp, self.split_positions()):
                    if hp > 0:
                        self._draw_skill_sprite(surf, self.split_art, self._snake_rect(x, y))
        elif self.skill == 'laser':
            heads = self._laser_head_rects(age)
            small = max(22, heads[0].w * 2 // 3)
            for i in range(5):
                rect = pygame.Rect(0, 0, small, small)
                rect.center = (round(heads[0].centerx + i * (heads[-1].centerx - heads[0].centerx) / 4), 48)
                self._draw_skill_sprite(surf, self.laser_art, rect)
            for head in heads:
                self._draw_skill_sprite(surf, self.laser_art, head)
            for left, right in zip(heads, heads[1:]):
                draw_electric_arc(surf, left.center, right.center, (150, 196, 255), 220, now, left.x, 2)
            for path in self.laser_paths(age):
                if age < self.LASER_WARNING:
                    Draw.line(surf, (255, 100, 65, 125), path[0], path[-1], 2)
                else:
                    x, y = path[0]
                    bottom = path[-1][1]
                    half = self.LASER_WIDTH / 2
                    neck = y + 28
                    Draw.polygon(surf, (255, 80, 40, 100),
                                 ((x - 6, y), (x + 6, y), (x + half + 7, neck),
                                  (x + half + 7, bottom), (x - half - 7, bottom), (x - half - 7, neck)))
                    Draw.polygon(surf, (255, 95, 43, 245),
                                 ((x - 3, y), (x + 3, y), (x + half, neck),
                                  (x + half, bottom), (x - half, bottom), (x - half, neck)))
                    Draw.line(surf, (255, 247, 220), (x, y), (x, bottom), max(3, self.LASER_WIDTH // 5))
                    Draw.circle(surf, (255, 95, 43, 225), (x, y), 8)
                    Draw.circle(surf, (255, 247, 220), (x, y), 4)
        elif self.skill == 'storm':
            self._draw_storm(surf, now)
        elif self.skill == 'slam':
            self._draw_idle(surf, now)
            self._draw_slam(surf, age)
        else:
            self._draw_idle(surf, now)
            if now < self.invincible_until:
                Draw.ellipse(surf, (125, 205, 255, 200), self.rect().inflate(30, 18), 3)
        self.hit_flashes = [flash for flash in self.hit_flashes if now - flash[2] < 180]
        for x, y, at in self.hit_flashes:
            progress = max(0, (now - at) / 180)
            radius = round(5 + progress * 9)
            alpha = round(255 * (1 - progress))
            Draw.circle(surf, (255, 145, 55, alpha), (x, y), radius, 2)
            Draw.line(surf, (255, 245, 200, alpha), (x - radius, y), (x + radius, y), 2)
            Draw.line(surf, (255, 245, 200, alpha), (x, y - radius), (x, y + radius), 2)

