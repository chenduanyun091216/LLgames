"""第七、八关 Boss 的专属攻击与阶段。"""
import math
from functools import lru_cache
import random
import pygame
from .render import Draw, RenderSurface, blit_effect, effect_layer

from . import config
from .asset_loader import image_asset, scale_surface_cached
from .entities import Boss, BossProjectile, Enemy
from .sprites import _circle, _rect, blit_lit_sprite
from .visuals import blit_label, draw_electric_arc


class ReturningAxe(BossProjectile):
    OUTBOUND_MS = 1320
    RETURN_MS = 1270

    def __init__(self, boss, side, target_x, red):
        x = boss.x + side * 42
        y = boss.y + boss.h * 0.65
        super().__init__(x, y, 0, 0, damage=3 if red else 1, explode_radius=125)
        self.boss = boss
        self.origin = (x, y)
        self.side = side
        self.red = red
        self.target_x = target_x
        self.impact_x = None
        self.last_update = self.spawn_time
        self.r = 52
        self.impact_pending = False
        self.blast_reason = '被牛魔王的飞斧爆炸击败！'
        self.max_lifetime = self.OUTBOUND_MS + self.RETURN_MS + 80

    def update(self, target_x=None, target_y=None):
        now = config.game_ticks()
        age = now - self.spawn_time
        if age >= self.max_lifetime:
            self.alive = False
            return
        self.prev_x, self.prev_y = self.x, self.y
        dt = max(0, min(80, now - self.last_update))
        self.last_update = now
        if age < self.OUTBOUND_MS:
            if target_x is not None and 'campaign_tier' not in self.boss.bdef:
                delta = max(-dt * 0.30, min(dt * 0.30, target_x - self.target_x))
                self.target_x += delta
            progress = age / self.OUTBOUND_MS
            ox, oy = self.origin
            self.x = ox + (self.target_x - ox) * progress + self.side * 105 * math.sin(math.pi * progress)
            self.y = oy + (config.GAME_AREA_BOTTOM - 20 - oy) * progress
            return
        if self.impact_x is None:
            self.impact_x = self.x
            self.impact_pending = True
        progress = max(0.0, 1 - (age - self.OUTBOUND_MS) / self.RETURN_MS)
        boss_x = self.boss.x + self.side * 42
        boss_y = self.boss.y + self.boss.h * 0.65
        self.x = boss_x + (self.impact_x - boss_x) * progress + self.side * 105 * math.sin(math.pi * progress)
        self.y = boss_y + (config.GAME_AREA_BOTTOM - 20 - boss_y) * progress

    def rect(self):
        return self.block_rect()

    def draw(self, surf):
        cx, cy = int(self.x), int(self.y)
        angle = config.game_ticks() * 0.0462
        glow = effect_layer(surf, (110, 110))
        gc = (55, 55)
        red = self.red
        Draw.circle(glow, (255, 55, 15, 28) if red else (30, 100, 255, 35), gc, 54)
        Draw.circle(glow, (255, 120, 30, 65) if red else (65, 155, 255, 75), gc, 46)
        Draw.circle(glow, (255, 215, 70, 85) if red else (145, 220, 255, 105), gc, 39, 5)
        def rotate(point):
            x, y = point
            return (gc[0] + x * math.cos(angle) - y * math.sin(angle),
                    gc[1] + x * math.sin(angle) + y * math.cos(angle))
        Draw.line(glow, (55, 28, 27), rotate((0, 38)), rotate((0, -34)), 11)
        Draw.line(glow, (190, 135, 70), rotate((0, 36)), rotate((0, -34)), 5)
        blade = [rotate(p) for p in ((-4, -25), (13, -37), (37, -42), (30, -25),
                                      (27, -10), (38, 3), (12, -1), (-4, -12))]
        Draw.polygon(glow, (255, 218, 140) if red else (205, 240, 255), blade)
        Draw.polygon(glow, (175, 50, 25) if red else (35, 95, 175), blade, 3)
        Draw.lines(glow, (255, 250, 210), False, [rotate(p) for p in ((37, -42), (30, -25), (27, -10), (38, 3))], 3)
        arc_color = (255, 169, 70) if red else (105, 221, 255)
        for side in (0, math.pi):
            start = (angle + side) % math.tau
            Draw.arc(glow, (*arc_color, 215), (7, 7, 96, 96), start, start + 1.2, 3)
        Draw.circle(glow, (255, 245, 190) if red else (225, 250, 255), gc, 8)
        Draw.circle(glow, (100, 35, 35), gc, 4)
        blit_effect(surf, glow, (cx - 55, cy - 55))


class CrescentWave(BossProjectile):
    def __init__(self, x, y, half_width=112, angle=0):
        super().__init__(x, y, angle, 8.5, damage=1)
        self.r = max(1, round(half_width * .65))
        self.unblockable = True

    def draw(self, surf):
        scale = surf.scale if isinstance(surf, RenderSurface) else 1
        image = _taiji_art(self.r, scale)
        image = pygame.transform.rotate(image, (config.game_ticks() - self.spawn_time) * .6 % 360)
        center = surf.point((self.x, self.y)) if isinstance(surf, RenderSurface) else (round(self.x), round(self.y))
        position = image.get_rect(center=center).topleft
        if isinstance(surf, RenderSurface):
            surf.blit_pixels(image, position)
        else:
            surf.blit(image, position)


@lru_cache(maxsize=16)
def _taiji_art(radius, scale):
    # Draw at twice the output resolution for smooth circular edges.
    r = max(4, round(radius * scale * 2))
    margin = max(3, r // 8)
    size = 2 * (r + margin)
    cx = cy = size // 2
    art = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(art, (98, 213, 255, 55), (cx, cy), r + margin)
    pygame.draw.circle(art, (196, 244, 255, 210), (cx, cy), r + max(2, r // 22))
    pygame.draw.circle(art, (18, 33, 52), (cx, cy), r)
    white = (243, 250, 247)
    black = (18, 33, 52)
    art.set_clip(pygame.Rect(cx, cy-r, r, 2*r))
    pygame.draw.circle(art, white, (cx, cy), r)
    art.set_clip(None)
    pygame.draw.circle(art, white, (cx, cy-r//2), r//2)
    pygame.draw.circle(art, black, (cx, cy+r//2), r//2)
    pygame.draw.circle(art, black, (cx, cy-r//2), max(2, r//7))
    pygame.draw.circle(art, white, (cx, cy+r//2), max(2, r//7))
    return pygame.transform.smoothscale(art, (max(1, size // 2), max(1, size // 2)))


class ZongBomb(BossProjectile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proximity_detonated = False

    def update(self, target_x=None, target_y=None):
        super().update(target_x, target_y)
        if config.game_ticks() - self.spawn_time >= self.max_lifetime:
            return
        if (target_x is not None and target_y is not None
                and math.hypot(target_x - self.x, target_y - self.y) <= self.explode_radius):
            self.proximity_detonated = True
            self.alive = False

    def rect(self):
        return pygame.Rect(0, 0, 0, 0)

    def draw(self, surf):
        center = (int(self.x), int(self.y))
        scale = surf.scale if isinstance(surf, RenderSurface) else 1
        image = _zong_bomb_art(getattr(self, 'color', 'black'), self.r, scale)
        pixel_center = surf.point(center) if isinstance(surf, RenderSurface) else center
        position = image.get_rect(center=(pixel_center[0], pixel_center[1] - round(6 * scale))).topleft
        if isinstance(surf, RenderSurface):
            surf.blit_pixels(image, position)
        else:
            surf.blit(image, position)


@lru_cache(maxsize=24)
def _zong_bomb_art(color, radius, scale):
    palettes = {'black': ((25, 34, 48), (84, 106, 132)),
                'yellow': ((121, 72, 22), (250, 190, 61)),
                'red': ((111, 29, 35), (235, 81, 73))}
    dark, light = palettes.get(color, palettes['black'])
    size = max(1, round((radius * 2 + 28) * scale))
    art = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, round(size * .57)
    r = max(1, round(radius * scale))
    pygame.draw.circle(art, (12, 18, 27, 255), (cx, cy), r + max(1, round(2 * scale)))
    for i in range(r, 0, -1):
        t = (1 - i / r) * .65
        shade = tuple(round(dark[j] * (1 - t) + light[j] * t) for j in range(3))
        pygame.draw.circle(art, shade, (cx - (r - i) // 3, cy - (r - i) // 3), i)
    pygame.draw.arc(art, (*light, 255), (cx-r+3, cy-r+3, 2*r-6, 2*r-6), .28, 2.5, max(1, round(2*scale)))
    pygame.draw.ellipse(art, (245, 250, 255, 145), (cx-r//2, cy-r//2, max(2, r//3), max(2, r//6)))
    cap = pygame.Rect(cx-r//3, cy-r-max(1, round(3*scale)), 2*r//3, max(3, round(7*scale)))
    pygame.draw.rect(art, (34, 42, 48), cap, border_radius=max(1, round(2*scale)))
    pygame.draw.line(art, (231, 205, 151), (cx, cy-r-2*scale),
                     (cx+6*scale, cy-r-11*scale), max(1, round(3*scale)))
    spark = (round(cx+7*scale), round(cy-r-12*scale))
    pygame.draw.circle(art, (255, 130, 42), spark, max(1, round(4*scale)))
    pygame.draw.circle(art, (255, 244, 171), spark, max(1, round(2*scale)))
    return art


class ZongFireball(BossProjectile):
    def draw(self, surf):
        super().draw(surf)
        rad = math.radians(self.angle)
        dx, dy = math.sin(rad), math.cos(rad)
        tail = (int(self.x - dx * 26), int(self.y - dy * 26))
        Draw.line(surf, (255, 85, 30), tail, (int(self.x), int(self.y)), 10)
        Draw.line(surf, (255, 230, 105), tail, (int(self.x), int(self.y)), 3)
        _circle(surf, (255, 235, 145), (int(self.x), int(self.y)), 7)


class ZongReflectBullet(BossProjectile):
    def __init__(self, x, y):
        super().__init__(x, y, 0, 6.0, damage=2)
        self.r = 11

    def update(self, target_x=None, target_y=None):
        super().update()
        if self.alive and target_x is not None:
            self.x += max(-2, min(2, (target_x - self.x) * 0.01))

    def draw(self, surf):
        center = (int(self.x), int(self.y))
        _circle(surf, (75, 190, 255), center, 16)
        _circle(surf, (160, 240, 255), center, 11)
        _circle(surf, (250, 255, 255), center, 6)
        Draw.line(surf, (120, 225, 255), (center[0], center[1] - 17), center, 3)


class NiuFanBullet(BossProjectile):
    def __init__(self, x, y, angle, red):
        super().__init__(x, y, angle, 5.2, damage=1)
        self.red = red
        self.r = 18 if red else 16

    def draw(self, surf):
        center = (int(self.x), int(self.y))
        glow = (255, 65, 45, 65) if self.red else (55, 135, 255, 65)
        body = (235, 45, 35) if self.red else (35, 100, 235)
        core = (255, 170, 95) if self.red else (130, 225, 255)
        _circle(surf, glow, center, self.r + 7)
        phase = (config.game_ticks() * .016 + self.angle) % math.tau
        radius = self.r + 4
        Draw.arc(surf, (*core, 210), (center[0] - radius, center[1] - radius, radius * 2, radius * 2),
                 phase, phase + math.pi, 2)
        _circle(surf, body, center, self.r)
        _circle(surf, core, center, self.r - 5)
        _circle(surf, (255, 255, 235), (center[0] - 4, center[1] - 5), 3)


@lru_cache(maxsize=16)
def _niu_shield_fragments(shield):
    width, height = shield.get_size()
    fragments = []
    for index in range(5):
        left, right = width * index // 5, width * (index + 1) // 5
        piece = shield.subsurface((left, 0, right - left, height)).copy()
        w = piece.get_width()
        mask = pygame.Surface((w, height), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255),
                            [(0, 0), (w, 0), (w, height // 3), (w - w // 10, height // 2),
                             (w, height * 2 // 3), (w, height), (0, height),
                             (0, height * 2 // 3), (w // 10, height // 2), (0, height // 3)])
        piece.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        fragments.append(piece)
    return tuple(fragments)


@lru_cache(maxsize=160)
def _niu_rotated_shield_fragment(piece, angle):
    return pygame.transform.rotate(piece, angle)


class NiuBoss(Boss):
    AXE_SLAM_CYCLE_MS = 1500
    AXE_SLAM_COUNT = 3
    axe_slam_duration = AXE_SLAM_CYCLE_MS * AXE_SLAM_COUNT
    RUN_POSES = ('run_stride', 'run_pass', 'run_reverse', 'run_pass')

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.last_pattern = None
        self.opening_skill_pending = True
        self.lightning_xs = ()
        self.lightning_warning_until = 0
        self.lightning_until = 0
        self.lightning_next_tick = 0
        self.shield_until = 0
        self.shield_damage = 0
        self.shield_break_at = None
        self.axe_slam_start = None
        self.axe_slam_hit = -1
        self.shield_thresholds = bdef.get('shield_thresholds', (0.75, 0.5, 0.25))
        self.shield_triggered = set()
        self.next_hazard_time = 0
        self.running_left = False

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        previous_hp = self.hp
        super().hit_by(weapon_name, amount, source=source, hit_rect=hit_rect)
        dealt = max(0, previous_hp - self.hp)
        if config.game_ticks() < self.shield_until:
            self.shield_damage += dealt
            if self.shield_damage >= self.max_hp * 0.15:
                self.shield_until = 0
                self.shield_break_at = config.game_ticks()
        for threshold in self.shield_thresholds:
            if threshold not in self.shield_triggered and previous_hp / self.max_hp > threshold >= self.hp / self.max_hp:
                self.shield_triggered.add(threshold)
                self.shield_until = config.game_ticks() + (3000 if 'campaign_tier' in self.bdef else 5000)
                self.shield_damage = 0
                break

    def update(self):
        was_entered = self.entered
        previous_x = self.x
        super().update()
        if self.x != previous_x:
            self.running_left = self.x < previous_x
        now = config.game_ticks()
        if self.shield_until and now >= self.shield_until:
            self.shield_break_at = self.shield_until
            self.shield_until = 0
        if self.entered and not was_entered and 'campaign_tier' not in self.bdef:
            self.last_attack_time = config.game_ticks()

    @staticmethod
    @lru_cache(maxsize=3)
    def _left_run_frame(sprite):
        return pygame.transform.flip(sprite, True, False)

    def _body_frame(self, now):
        attack_at = getattr(self, 'animation_attack_at', None)
        running = False
        if self.laser_warning_start or now < self.laser_active_until:
            pose = 'laser'
        elif self.axe_slam_start is not None and 0 <= now - self.axe_slam_start < self.axe_slam_duration:
            pose = 'slam' if (now - self.axe_slam_start) % self.AXE_SLAM_CYCLE_MS < 800 else 'axes'
        elif now < self.lightning_until:
            pose = 'lightning'
        elif attack_at is not None and 0 <= now - attack_at < 600:
            pose = 'bullets' if self.last_pattern == 'bullets' else 'axes'
        elif self.entered:
            running = True
            pose = self.RUN_POSES[int(self.movement_timer / 8) % len(self.RUN_POSES)]
        else:
            return None
        sprite = image_asset(f'bosses/boss_niu_{pose}.png')
        if sprite is None:
            return super()._body_frame(now)
        return self._left_run_frame(sprite) if running and self.running_left else sprite

    def should_attack(self, now):
        if self.laser_warning_start or now < self.laser_active_until:
            return False
        if now < self.next_hazard_time:
            return False
        interval = self.attack_interval
        if now < self.slowed_until:
            interval /= self.slow_mult
        return self.entered and now - self.last_attack_time >= interval

    def death_laser_xs(self):
        left, right = self._safe_laser_x(-100000), self._safe_laser_x(100000)
        separation = min(120, max(0, (right - left) / 2))
        center = max(left + separation, min(right - separation, self.x))
        return center - separation, center + separation

    def laser_paths(self, now):
        top = int(self.y + self.h * .72)
        height = max(1, config.SCREEN_HEIGHT - top)
        swing = math.sin(now * .008) * 28
        return tuple([(round(x + math.sin(now * .008 + t * 4) * 12 * t + swing * t),
                       round(top + height * t)) for t in (i / 20 for i in range(21))]
                     for x in self.death_laser_xs())

    def laser_hits(self, rect, now):
        if now >= self.laser_active_until:
            return False
        target = rect.inflate(max(24, self.w // 2), max(24, self.w // 2))
        return any(target.clipline(a, b) for path in self.laser_paths(now) for a, b in zip(path, path[1:]))

    def attack(self, now, player_x, opening=False):
        self.last_attack_time = now
        pattern = (random.choice(('axes', 'slam', 'lightning', 'laser')) if opening else
                   random.choice([p for p in ('axes', 'axes', 'slam', 'lightning', 'bullets')
                                  if p != self.last_pattern]))
        self.last_pattern = pattern
        tier = self.bdef.get('campaign_tier')
        warning = 0 if opening else (1200, 1000, 850)[tier] if tier is not None else 900
        recovery = (2000, 1700, 1400)[tier] if tier is not None else 0
        if pattern == 'laser':
            self._keep_laser_inside()
            self.laser_active_until = now + 2000
            self.next_death_laser_time = now + random.randint(9000, 16000) * self.bdef.get('laser_interval_mult', 1)
            return []
        if pattern == 'axes':
            return [ReturningAxe(self, -1, max(40, min(config.SCREEN_WIDTH - 40, player_x - 55)), True),
                    ReturningAxe(self, 1, max(40, min(config.SCREEN_WIDTH - 40, player_x + 55)), False)]
        if pattern == 'slam':
            self.axe_slam_start = now
            self.axe_slam_hit = -1
            self.next_hazard_time = now + self.axe_slam_duration + recovery
            self.next_death_laser_time = max(self.next_death_laser_time, self.next_hazard_time)
            return []
        if pattern == 'lightning':
            self.lightning_xs = tuple(max(35, min(config.SCREEN_WIDTH - 35, player_x + dx))
                                      for dx in (-150, 0, 150))
            self.lightning_warning_until = now + warning
            self.lightning_until = self.lightning_warning_until + 1400
            self.lightning_next_tick = now + 800 if tier is None and not opening else self.lightning_warning_until
            if tier is not None:
                self.next_hazard_time = self.lightning_until + recovery
                self.next_death_laser_time = max(self.next_death_laser_time, self.next_hazard_time)
            return []
        return [NiuFanBullet(self.x + (i - 2.5) * 18, self.y + self.h * 0.7,
                             angle, red=i % 2 == 0)
                for i, angle in enumerate((-40, -24, -8, 8, 24, 40))]

    def lightning_rects(self, now):
        if now >= self.lightning_until:
            return ()
        return tuple(pygame.Rect(int(x - 35), int(self.y + self.h // 2), 70,
                                 int(config.SCREEN_HEIGHT - self.y - self.h // 2))
                     for x in self.lightning_xs)

    def axe_slam_rect(self, now):
        if self.axe_slam_start is None:
            return None
        age = now - self.axe_slam_start
        if not 0 <= age < self.axe_slam_duration:
            return None
        age %= self.AXE_SLAM_CYCLE_MS
        if not 800 <= age < 1500:
            return None
        top = round(self.y + self.h * .7)
        reach = min(1.0, (age - 800) / 300)
        bottom = round(top + (config.GAME_AREA_BOTTOM - top) * reach)
        width = max(30, round(self.w * .75))
        return pygame.Rect(round(self.x - width / 2), top, width, max(1, bottom - top))

    def _draw_axe_slam(self, surf, now):
        age = (now - self.axe_slam_start) % self.AXE_SLAM_CYCLE_MS
        top = round(self.y + self.h * .7)
        if age < 800:
            return
        hitbox = self.axe_slam_rect(now)
        if hitbox is None:
            return
        width = max(70, round(self.w * 1.25))
        height = max(1, hitbox.bottom - top + 65)
        art = effect_layer(surf, (width + 30, height))
        cx = (width + 30) // 2
        tip = min(height - 30, hitbox.bottom - top)
        Draw.line(art, (95, 25, 20, 230), (cx, 0), (cx, tip), 24)
        Draw.line(art, (195, 105, 40, 255), (cx, 0), (cx, tip), 14)
        Draw.line(art, (255, 218, 110, 255), (cx - 3, 0), (cx - 3, tip), 3)
        half = width // 2
        for side in (-1, 1):
            blade = [(cx, tip - 16), (cx + side * half * .58, tip - 38),
                     (cx + side * half, tip - 32), (cx + side * half * .8, tip - 10),
                     (cx + side * half * .82, tip + 8), (cx + side * half, tip + 22),
                     (cx + side * half * .52, tip + 17), (cx, tip + 6)]
            Draw.polygon(art, (180, 38, 20, 255), blade)
            Draw.polygon(art, (255, 184, 55, 255), blade, 4)
            edge = [(cx + side * half, tip - 32), (cx + side * half * .8, tip - 10),
                    (cx + side * half * .82, tip + 8), (cx + side * half, tip + 22)]
            Draw.lines(art, (255, 245, 205, 255), False, edge, 4)
        Draw.circle(art, (255, 195, 55, 255), (cx, tip - 5), 10)
        Draw.circle(art, (205, 35, 25, 255), (cx, tip - 5), 6)
        blit_effect(surf, art, (round(self.x - cx), top))

    def _draw_shield_break(self, surf, now):
        progress = (now - self.shield_break_at) / 900
        width = max(1, round(self.w * 3.8))
        height = max(1, round(self.h * 1.5))
        effect = effect_layer(surf, (width, height))
        cx, cy = width // 2, height // 2
        fade = max(0, 1 - progress)
        radius = max(1, round((20 + progress * 55) * self.size_scale))
        if progress < .35:
            Draw.circle(effect, (255, 245, 180, round(180 * (1 - progress / .35))),
                        (cx, cy), max(1, round(42 * self.size_scale)))
        Draw.circle(effect, (255, 175, 40, round(200 * fade)), (cx, cy), radius, max(1, round(4 * self.size_scale)))
        Draw.circle(effect, (255, 95, 25, round(180 * fade)), (cx, cy),
                    max(1, round(radius * 1.45)), max(1, round(3 * self.size_scale)))
        for i in range(20):
            angle = i * math.tau / 20
            distance = (25 + progress * 145) * self.size_scale
            x = cx + math.cos(angle) * distance
            y = cy + math.sin(angle) * distance * .52
            size = max(3, round((13 - progress * 6) * self.size_scale))
            points = [(x, y - size), (x + size, y), (x, y + size * 1.6), (x - size, y)]
            Draw.polygon(effect, (255, 135 + i % 3 * 40, 35, round(230 * fade)), points)
            Draw.line(effect, (255, 245, 170, round(240 * fade)), (x, y - size), (x + size, y), 2)
        blit_effect(surf, effect, (round(self.x - cx), round(self.y + self.h - cy)))
        shield_width = max(1, round(self.w * 2.5))
        shield_height = max(1, round(shield_width / 3))
        shield = image_asset('effects/boss_niu_shield.png', (shield_width, shield_height))
        if shield is not None:
            for i, piece in enumerate(_niu_shield_fragments(shield)):
                direction = i - 2
                angle = round(direction * progress * 30 / 5) * 5
                fragment = _niu_rotated_shield_fragment(piece, angle)
                if progress > .7:
                    fragment = fragment.copy()
                    fragment.set_alpha(round(255 * (1 - progress) / .3))
                x = (self.x - shield_width / 2 + shield_width * (i + .5) / 5
                     + direction * shield_width * .28 * progress)
                y = (self.y + self.h - shield_height * .22 + shield_height / 2
                     - (1.1 - abs(direction) * .2) * shield_height * progress
                     + shield_height * .6 * progress * progress)
                surf.blit(fragment, (round(x - fragment.get_width() / 2),
                                     round(y - fragment.get_height() / 2)))

    def draw(self, surf):
        super().draw(surf)
        now = config.game_ticks()
        if now < self.laser_active_until:
            for path, color in zip(self.laser_paths(now), ((255, 190, 25), (255, 40, 35))):
                left = min(point[0] for point in path) - 70
                right = max(point[0] for point in path) + 70
                top = path[0][1]
                beam = effect_layer(surf, (right - left, max(1, config.SCREEN_HEIGHT - top + 1)))
                points = [(x - left, y - top) for x, y in path]
                width = max(24, self.w // 2)
                Draw.lines(beam, (*color, 45), False, points, width + 35)
                Draw.lines(beam, (*color, 110), False, points, width + 15)
                Draw.lines(beam, (*color, 235), False, points, width)
                Draw.lines(beam, (255, 247, 190, 245), False, points, max(5, width // 4))
                for i in range(2, len(points) - 1, 3):
                    x, y = points[i]
                    d = math.sin(now * .025 + i) * width * .35
                    Draw.line(beam, (255, 255, 225, 190), (x - width//2, y + d),
                              (x + width//2, y - d), 2)
                blit_effect(surf, beam, (left, top))
                _circle(surf, (*color, 150), path[0], width // 2 + 9)
                _circle(surf, (255, 250, 210), path[0], max(5, width // 5))
        cx, cy = int(self.x), int(self.y + self.h // 2)
        for i in range(12):
            angle = now * 0.003 + i * math.tau / 12
            px = cx + math.cos(angle) * (self.w * 0.65 + 8 * self.size_scale)
            py = cy + math.sin(angle) * (self.h * 0.65 + 8 * self.size_scale)
            _circle(surf, (255, 135 + i % 3 * 35, 45), (int(px), int(py)),
                    max(1, round((3 + i % 3) * self.size_scale)))
        if now < self.lightning_until:
            top = int(self.y + self.h // 2)
            height = max(1, config.SCREEN_HEIGHT - top)
            beam = effect_layer(surf, (130, height))
            if now < self.lightning_warning_until:
                Draw.line(beam, (255, 65, 35, 45), (65, 0), (65, height), 70)
                Draw.line(beam, (255, 65, 35, 110), (65, 0), (65, height), 24)
                Draw.line(beam, (255, 230, 120, 220), (65, 0), (65, height), 3)
                Draw.circle(beam, (255, 120, 55, 230), (65, height - 16), 27, 5)
            else:
                phase = now // 90
                points = [(65 + (0 if i in (0, 16) else int(math.sin(phase * 2.17 + i * 5.31) * 23)),
                           int(height * i / 16)) for i in range(17)]
                Draw.lines(beam, (130, 65, 255, 45), False, points, 38)
                Draw.lines(beam, (105, 165, 255, 110), False, points, 18)
                Draw.lines(beam, (190, 225, 255, 230), False, points, 8)
                Draw.lines(beam, (255, 255, 255), False, points, 3)
                for i in (2, 5, 8, 11, 14):
                    px, py = points[i]
                    side = -1 if i % 2 else 1
                    branch = [(px, py), (px + side * 14, py + 13),
                              (px + side * 9, py + 25), (px + side * 27, py + 43)]
                    Draw.lines(beam, (110, 145, 255, 150), False, branch, 7)
                    Draw.lines(beam, (230, 245, 255, 235), False, branch, 2)
                for i in range(3, 16, 4):
                    px, py = points[i]
                    Draw.circle(beam, (210, 240, 255, 210), (px, py), 5)
                Draw.circle(beam, (125, 175, 255, 180), (65, height - 18), 32, 4)
            for x in self.lightning_xs:
                blit_effect(surf, beam, (int(x - 65), top))
        if now < self.shield_until:
            width = max(1, round(self.w * 2.5))
            height = max(1, round(width / 3))
            shield = image_asset('effects/boss_niu_shield.png', (width, height))
            if shield is not None:
                surf.blit(shield, (round(self.x - width / 2), round(self.y + self.h - height * .22)))
            else:
                Draw.line(surf, (255, 190, 55), (self.x - self.w, self.y + self.h + 8),
                          (self.x + self.w, self.y + self.h + 8), max(2, round(8 * self.size_scale)))
        if self.shield_break_at is not None and 0 <= now - self.shield_break_at < 900:
            self._draw_shield_break(surf, now)
        if self.axe_slam_start is not None and 0 <= now - self.axe_slam_start < self.axe_slam_duration:
            self._draw_axe_slam(surf, now)


class ZongBoss(Boss):
    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.body_hp = [self.max_hp / 2, self.max_hp / 2]
        self.easy_campaign = bdef.get('easy_campaign', False)
        self.next_fusion_time = 0
        self.fusion_mode = None
        self.fusion_until = 0
        self.fusion_started_at = 0
        self.fusion_end_volley = False
        self.snow_until = 0
        self.opening_snow_done = False
        self.expression_hit_at = None
        self.pending_projectiles = []
        self.crescent_projectiles = []
        self.crescent_started_at = None
        self.crescent_count = 0
        self.crescent_target = (0, 0)
        self.crescent_origin = 0
        self.attack_phase = 0
        self.next_revive_check = 0
        self.campaign_revived = False
        self.fusion_warning_mode = None
        self.last_reflect_times = []

    def expression_frame(self, now, index):
        if self.expression_hit_at is not None and 0 <= now - self.expression_hit_at < 900:
            return 2
        return (0, 1, 0, 2)[((now // 3000) + index) % 4]

    def body_x(self, index):
        return self.x + (-110 if index == 0 else 110) * self.size_scale

    def hitboxes(self):
        if self.fusion_mode:
            return (pygame.Rect(int(self.x - self.w * 0.68),
                                int(self.y - 14 * self.size_scale),
                                int(self.w * 1.36), self.h + round(28 * self.size_scale)),)
        return tuple(pygame.Rect(int(self.body_x(i) - self.w // 2), int(self.y), self.w, self.h)
                     for i in range(2) if self.body_hp[i] > 0)

    def rect(self):
        boxes = self.hitboxes()
        return boxes[0].unionall(boxes[1:]) if boxes else pygame.Rect(0, 0, 0, 0)

    def collides(self, rect):
        return any(rect.colliderect(box) for box in self.hitboxes())

    def reflects_bullet(self):
        if self.fusion_mode != 'shield':
            return False
        tier = self.bdef.get('campaign_tier')
        if tier is None:
            return True
        now = config.game_ticks()
        self.last_reflect_times[:] = [t for t in self.last_reflect_times if now - t < 1000]
        if len(self.last_reflect_times) >= (1, 2, 2)[tier]:
            return False
        self.last_reflect_times.append(now)
        return True

    def _move(self, speed_mult, laser=False):
        if self.crescent_started_at is None:
            super()._move(speed_mult, laser=laser)

    def should_attack(self, now):
        return self.crescent_started_at is None and super().should_attack(now)

    def update(self, target_x=None, target_y=None):
        super().update()
        if not self.entered:
            return
        now = config.game_ticks()
        tier = self.bdef.get('campaign_tier')
        if not self.opening_snow_done and now - self.fight_start_time >= 5000:
            duration = 5000 if tier is None else (2500, 3000, 3500)[tier]
            self.snow_until = max(self.snow_until, now + duration)
            self.opening_snow_done = True
        if self.crescent_started_at is not None:
            width_scale = (config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT) / 480
            half_width = 112 if tier is None else round(70 * width_scale)
            while self.crescent_count < 4 and now >= self.crescent_started_at + 1500 + self.crescent_count * 300:
                x, y = self.crescent_target if target_x is None or target_y is None else (target_x, target_y)
                angle = math.degrees(math.atan2(x - self.crescent_origin, y - (self.y + self.h - 8)))
                self.crescent_projectiles.append(CrescentWave(self.crescent_origin, self.y + self.h - 8,
                                                              half_width, angle))
                self.crescent_count += 1
            if self.crescent_count == 4:
                self.crescent_started_at = None
                self.last_attack_time = now
            return
        alive = [i for i in range(2) if self.body_hp[i] > 0]
        if tier is not None:
            if tier and len(alive) == 1 and not self.campaign_revived:
                if not self.next_revive_check:
                    self.next_revive_check = now + (18000 if tier == 1 else 15000)
                elif now >= self.next_revive_check:
                    self.body_hp[1 - alive[0]] = self.max_hp * (0.10 if tier == 1 else 0.12)
                    self.hp = sum(self.body_hp)
                    self.campaign_revived = True
            elif len(alive) != 1:
                self.next_revive_check = 0
        elif len(alive) == 1:
            if not self.next_revive_check:
                self.next_revive_check = now + (15000 if self.easy_campaign else 10000)
            elif now >= self.next_revive_check:
                if random.random() < (0.15 if self.easy_campaign else 0.25):
                    revived = 1 - alive[0]
                    self.body_hp[revived] = self.max_hp * 0.20
                    self.hp = sum(self.body_hp)
                self.next_revive_check = now + (15000 if self.easy_campaign else 10000)
        else:
            self.next_revive_check = 0
        if not self.next_fusion_time:
            self.next_fusion_time = now + (12000 if self.easy_campaign else 8000)
        if self.fusion_mode and now >= self.fusion_until:
            if self.fusion_mode == 'rage' and not self.fusion_end_volley:
                self.pending_projectiles.extend(self._fireball_fan())
            self.fusion_mode = None
            self.next_fusion_time = now + (14000 if self.easy_campaign else 8500)
        elif self.fusion_mode == 'rage' and not self.fusion_end_volley and now >= self.fusion_until - 500:
            self.pending_projectiles.extend(self._fireball_fan())
            self.fusion_end_volley = True
        elif not self.fusion_mode and all(hp > 0 for hp in self.body_hp) and now >= self.next_fusion_time:
            if tier is not None and self.fusion_warning_mode is None:
                self.fusion_warning_mode = random.choice(('shield', 'rage'))
                self.next_fusion_time = now + (1200, 1000, 850)[tier]
                return
            self.fusion_mode = self.fusion_warning_mode or random.choice(('shield', 'rage'))
            self.fusion_warning_mode = None
            shield_duration = (2000, 2500, 3000)[tier] if tier is not None else 5000
            self.fusion_until = now + (shield_duration if self.fusion_mode == 'shield' else 5000)
            self.fusion_started_at = now
            self.fusion_end_volley = False
            if (tier is None or self.fusion_mode == 'rage') and random.random() < 0.4:
                self.snow_until = now + (5000 if tier is None else (2500, 3000, 3500)[tier])
            if self.fusion_mode == 'rage':
                self.pending_projectiles.extend(self._fireball_fan())

    def _fireball_fan(self):
        shots = [ZongFireball(self.x + (i - 3.5) * 40, self.y + self.h, -63 + i * 18, 4.5,
                              damage=3, big_fireball=True) for i in range(8)]
        for i, shot in enumerate(shots):
            shot.lightning_previous = shots[i - 1] if i else None
        return shots

    def attack(self, now, player_x, player_y=None):
        self.last_attack_time = now
        if self.fusion_mode or self.fusion_warning_mode or self.crescent_started_at is not None:
            return []
        self.attack_phase += 1
        tier = self.bdef.get('campaign_tier')
        if self.attack_phase % 2:
            bombs = [ZongBomb(self.body_x(i) + offset, self.y + self.h - 10, angle, 3.8,
                              homing=True, damage=3, bomb=True, explode_radius=45)
                     for i, offset, angle in ((0, -20, -20), (0, 20, 0), (1, 0, 20))
                     if self.body_hp[i] > 0]
            for bomb, color in zip(bombs, (color for i, color in ((0, 'black'), (0, 'yellow'), (1, 'red')) if self.body_hp[i] > 0)):
                bomb.color = color
                bomb.r = 30
            return bombs
        alive = [i for i in range(2) if self.body_hp[i] > 0]
        if not alive:
            return []
        self.crescent_origin = self.x if len(alive) == 2 else self.body_x(alive[0])
        target_y = config.GAME_AREA_BOTTOM if player_y is None else player_y
        self.crescent_target = (player_x, target_y)
        self.crescent_started_at = now
        self.crescent_count = 0
        return []

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        if self.y < Enemy.ENTRY_DAMAGE_Y or self.fusion_mode == 'shield':
            return
        previous_hp = self.hp
        damage = amount * getattr(self, 'damage_mult', 1.0)
        alive = [i for i in range(2) if self.body_hp[i] > 0]
        if len(alive) == 1:
            i = alive[0]
            self.body_hp[i] = max(0, self.body_hp[i] - damage * 2)
        elif self.fusion_mode == 'rage':
            for i in alive:
                self.body_hp[i] = max(0, self.body_hp[i] - damage / len(alive))
        else:
            tier = self.bdef.get('campaign_tier')
            strong_side = 1 if source == 'bullet' else 0
            allowed = alive if self.easy_campaign or tier is not None else (strong_side,)
            for i in allowed:
                if self.body_hp[i] <= 0:
                    continue
                box = pygame.Rect(int(self.body_x(i) - self.w // 2), int(self.y), self.w, self.h)
                if hit_rect is None or hit_rect.colliderect(box):
                    effectiveness = 0.5 if tier == 2 and i != strong_side else 1
                    self.body_hp[i] = max(0, self.body_hp[i] - damage * effectiveness)
                    break
        self.hp = sum(self.body_hp)
        if self.hp < previous_hp:
            self.expression_hit_at = config.game_ticks()

    def _draw_aura(self, surf, x, cy, index, now):
        accent = ((65, 220, 255), (185, 115, 255))[index] if not self.fusion_mode else (
            (120, 225, 255) if self.fusion_mode == 'shield' else (255, 95, 50))
        radius = round((108 if self.fusion_mode else 80) * self.size_scale)
        halo = effect_layer(surf, (300, 300))
        center = (150, 150)
        pulse = round(5 * math.sin(now * 0.009) * self.size_scale)
        Draw.circle(halo, (*accent, 30), center, radius + round(22 * self.size_scale))
        Draw.circle(halo, (*accent, 100), center, radius + pulse,
                           max(1, round(10 * self.size_scale)))
        Draw.circle(halo, (235, 250, 255, 175), center,
                           max(1, radius - round(8 * self.size_scale)),
                           max(1, round(3 * self.size_scale)))
        for i in range(12):
            angle = now * (0.003 if self.fusion_mode != 'rage' else -0.006) + i * math.tau / 12
            px = 150 + math.cos(angle) * (radius + 15 * self.size_scale)
            py = 150 + math.sin(angle) * (radius + 15 * self.size_scale)
            crystal = [(px, py - 6 * self.size_scale), (px + 4 * self.size_scale, py),
                       (px, py + 6 * self.size_scale), (px - 4 * self.size_scale, py)]
            Draw.polygon(halo, (*accent, 185), crystal)
            Draw.circle(halo, (245, 255, 255, 190), (int(px), int(py)),
                               max(1, round(2 * self.size_scale)))
        if self.fusion_mode == 'shield':
            corners = [(int(150 + math.cos(now * 0.001 + i * math.tau / 6) * 98 * self.size_scale),
                        int(150 + math.sin(now * 0.001 + i * math.tau / 6) * 98 * self.size_scale))
                       for i in range(6)]
            Draw.polygon(halo, (175, 245, 255, 195), corners,
                                max(1, round(5 * self.size_scale)))
        elif self.fusion_mode == 'rage':
            for i in range(10):
                angle = now * 0.004 + i * math.tau / 10
                dx, dy = math.cos(angle), math.sin(angle)
                points = [(150 + (dx * 103 - dy * 10) * self.size_scale,
                           150 + (dy * 103 + dx * 10) * self.size_scale),
                          (150 + dx * 138 * self.size_scale, 150 + dy * 138 * self.size_scale),
                          (150 + (dx * 103 + dy * 10) * self.size_scale,
                           150 + (dy * 103 - dx * 10) * self.size_scale)]
                Draw.polygon(halo, (255, 170, 45, 125), points)
        if self.fusion_mode and now - self.fusion_started_at < 650:
            spread = round((85 + (now - self.fusion_started_at) / 650 * 55) * self.size_scale)
            Draw.circle(halo, (*accent, 190), center, spread,
                               max(1, round(5 * self.size_scale)))
            for side in (-1, 1):
                edge = (150 + side * spread, 150)
                draw_electric_arc(halo, center, edge, accent, 200, now, side)
        blit_effect(surf, halo, (int(x - 150), int(cy - 150)))

    @staticmethod
    def draw_snow(surf, until, font, reduction=50):
        now = config.game_ticks()
        if now >= until:
            return
        snow = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        snow.fill((70, 140, 225, 35))
        for i in range(96):
            x = (i * 137 + int(now * 0.023 * (1 + i % 3))) % config.SCREEN_WIDTH
            y = (i * 83 + int(now * 0.055 * (1 + i % 4))) % config.SCREEN_HEIGHT
            radius = 2 + i % 4
            pygame.draw.circle(snow, (225, 250, 255, 180), (x, y), radius)
            if i % 5 == 0:
                for dx, dy in ((8, 0), (4, 7), (-4, 7)):
                    pygame.draw.line(snow, (235, 255, 255, 190),
                                     (x - dx, y - dy), (x + dx, y + dy), 2)
        pygame.draw.rect(snow, (170, 230, 255, 95), snow.get_rect(), 5)
        message = '极寒暴雪 · 移速与射速减半' if reduction == 50 else f'极寒暴雪 · 移速与射速降低 {reduction}%'
        width, height = font.size(message)
        box = pygame.Rect(config.SCREEN_WIDTH // 2 - width // 2 - 16, 246,
                          width + 32, height + 12)
        if isinstance(surf, RenderSurface) and surf.desktop_ui:
            surf.blit(snow, (0, 0))
            Draw.rect(surf, (8, 38, 78, 175), box, border_radius=8)
            Draw.rect(surf, (180, 235, 255, 190), box, 2, 8)
        else:
            pygame.draw.rect(snow, (8, 38, 78, 175), box, border_radius=8)
            pygame.draw.rect(snow, (180, 235, 255, 190), box, 2, border_radius=8)
            surf.blit(snow, (0, 0))
        blit_label(surf, font, message, (225, 250, 255), box.center, 20)

    def draw(self, surf):
        now = config.game_ticks()
        labels = ('子弹免疫', '技能免疫')
        if self.easy_campaign:
            labels = ('', '')
        elif self.bdef.get('campaign_tier') == 2:
            labels = ('技能弱点', '子弹弱点')
        centers = ((self.x, '融合'),) if self.fusion_mode else tuple(
            (self.body_x(i), labels[i]) for i in range(2) if self.body_hp[i] > 0)
        for x, label in centers:
            cy = self.y + self.h // 2
            self._draw_aura(surf, x, cy, 0 if x < self.x else 1, now)
            scale = 1.45 if self.fusion_mode else 1.0
            size = (int((self.w + 20) * scale), int((self.h + 20) * scale))
            image = scale_surface_cached(self.surface, size) if self.fusion_mode else self.surface
            from . import animation
            sprite = animation.boss_frame(self, now)
            if not self.fusion_mode and self.crescent_started_at is not None:
                sprite = animation.frame('boss_zongzong_expressions', 3) or sprite
            elif (not self.fusion_mode and self.expression_hit_at is not None
                  and 0 <= now - self.expression_hit_at < 900):
                sprite = animation.frame('boss_zongzong_expressions', 2) or sprite
            if sprite is not None:
                size = animation.boss_action_size(sprite, self.surface, size)
                image = scale_surface_cached(sprite, size)
            elif not self.fusion_mode:
                body_index = 0 if x < self.x else 1
                sprite = (animation.frame('boss_zongzong_expressions', self.expression_frame(now, body_index))
                          or animation.frame('zongzong_hurt', self.expression_frame(now, body_index)))
                if sprite is not None:
                    size = animation.boss_action_size(sprite, self.surface, size)
                    image = scale_surface_cached(sprite, size)
                wobble = math.sin(now * .004 + body_index * 2) * 4
                image = pygame.transform.rotate(image, wobble)
                size = image.get_size()
                sprite = image
                phase = ((now // 3000) + body_index) % 4
                float_y = cy - self.h * .64 - (now % 3000) / 3000 * 12 * self.size_scale
                if phase in (0, 2):
                    heart_x = x + self.w * .43
                    r = max(2, round(5 * self.size_scale))
                    _circle(surf, (255, 137, 169), (heart_x-r, float_y), r)
                    _circle(surf, (255, 137, 169), (heart_x+r, float_y), r)
                    Draw.polygon(surf, (255, 137, 169), [(heart_x-2*r, float_y+1),
                                 (heart_x+2*r, float_y+1), (heart_x, float_y+2*r)])
                else:
                    star_x = x - self.w * .48
                    r = max(3, round(7 * self.size_scale))
                    Draw.line(surf, (211, 244, 255), (star_x-r, float_y), (star_x+r, float_y), 2)
                    Draw.line(surf, (211, 244, 255), (star_x, float_y-r), (star_x, float_y+r), 2)
            flashing = (self.crescent_started_at is not None
                        and 0 <= now - self.crescent_started_at < 1500
                        and (now - self.crescent_started_at) // 375 in (1, 3))
            if flashing:
                image = image.copy()
                image.fill((125, 125, 125), special_flags=pygame.BLEND_RGB_ADD)
            accent = (255, 172, 96) if self.fusion_mode == 'rage' else (
                (107, 226, 255) if x <= self.x else (211, 153, 255))
            blit_lit_sprite(surf, image, (x - size[0] // 2, cy - size[1] // 2), accent, 185,
                            source=None if flashing else sprite or self.sprite_asset)
            if not self.fusion_mode:
                i = 0 if x < self.x else 1
                bar_width, bar_height = round(110 * self.size_scale), max(1, round(7 * self.size_scale))
                _rect(surf, (55, 45, 55), (int(x - bar_width // 2), int(self.y + self.h + 5),
                                            bar_width, bar_height))
                _rect(surf, (255, 150, 70), (int(x - bar_width // 2), int(self.y + self.h + 5),
                                            int(bar_width * self.body_hp[i] / (self.max_hp / 2)),
                                            bar_height))
                if label:
                    center = (int(x), int(self.y + self.h + 16) + self.font_hp.get_height() // 2)
                    blit_label(surf, self.font_hp, label, (255, 250, 215), center, 14, bold=True)
