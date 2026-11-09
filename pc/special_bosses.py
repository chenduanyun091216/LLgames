"""第七、八关 Boss 的专属攻击与阶段。"""
import math
import random
import pygame

from . import config
from .asset_loader import scale_surface_cached
from .entities import Boss, BossProjectile
from .sprites import _circle, _rect


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
        now = pygame.time.get_ticks()
        age = now - self.spawn_time
        if age >= self.max_lifetime:
            self.alive = False
            return
        self.prev_x, self.prev_y = self.x, self.y
        dt = max(0, min(80, now - self.last_update))
        self.last_update = now
        if age < self.OUTBOUND_MS:
            if target_x is not None:
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
        angle = pygame.time.get_ticks() * 0.0462
        glow = pygame.Surface((110, 110), pygame.SRCALPHA)
        gc = (55, 55)
        red = self.red
        pygame.draw.circle(glow, (255, 55, 15, 28) if red else (30, 100, 255, 35), gc, 54)
        pygame.draw.circle(glow, (255, 120, 30, 65) if red else (65, 155, 255, 75), gc, 46)
        pygame.draw.circle(glow, (255, 215, 70, 85) if red else (145, 220, 255, 105), gc, 39, 5)
        for offset in (0, math.pi):
            a = angle + offset
            dx, dy = math.cos(a), math.sin(a)
            px, py = gc[0] + dx * 29, gc[1] + dy * 29
            pygame.draw.line(glow, (90, 60, 50) if red else (35, 70, 120), gc, (px, py), 12)
            blade = [(px + dx * 22, py + dy * 22),
                     (px + dy * 22 - dx * 4, py - dx * 22 - dy * 4),
                     (px - dx * 7, py - dy * 7),
                     (px - dy * 22 - dx * 4, py + dx * 22 - dy * 4)]
            pygame.draw.polygon(glow, (255, 225, 145) if red else (205, 240, 255), blade)
            pygame.draw.polygon(glow, (255, 95, 35) if red else (40, 125, 255), blade, 3)
        pygame.draw.circle(glow, (255, 245, 190) if red else (225, 250, 255), gc, 8)
        pygame.draw.circle(glow, (100, 35, 35), gc, 4)
        surf.blit(glow, (cx - 55, cy - 55))


class CrescentWave(BossProjectile):
    def __init__(self, x, y):
        super().__init__(x, y, 0, 8.5, damage=1)
        self.r = 112
        self.unblockable = True

    def rect(self):
        return pygame.Rect(int(self.x - 112), int(self.y - 4), 224, 72)

    def draw(self, surf):
        wave = pygame.Surface((248, 102), pygame.SRCALPHA)
        outer = [(124 + x, int(18 + 58 * (1 - (x / 112) ** 2))) for x in range(-112, 113, 7)]
        inner = [(124 + x, int(18 + 21 * (1 - (x / 112) ** 2))) for x in range(112, -113, -7)]
        pygame.draw.lines(wave, (45, 150, 255, 65), False, outer, 22)
        pygame.draw.polygon(wave, (35, 105, 225, 120), outer + inner)
        pygame.draw.polygon(wave, (105, 220, 255, 185), outer + inner, 4)
        pygame.draw.lines(wave, (235, 255, 255, 250), False, outer, 6)
        pygame.draw.lines(wave, (125, 240, 255, 190), False, inner, 3)
        for x in (12, 45, 78):
            y = int(18 + 55 * (1 - ((x - 124) / 112) ** 2))
            pygame.draw.circle(wave, (245, 255, 255, 220), (x, y), 3)
            pygame.draw.circle(wave, (245, 255, 255, 220), (248 - x, y), 3)
        surf.blit(wave, (int(self.x - 124), int(self.y - 18)))


class ZongBomb(BossProjectile):
    def draw(self, surf):
        super().draw(surf)
        now = pygame.time.get_ticks()
        halo = pygame.Surface((94, 94), pygame.SRCALPHA)
        center = (47, 47)
        pygame.draw.circle(halo, (65, 180, 255, 65), center, 44, 6)
        pygame.draw.circle(halo, (190, 235, 255, 170), center, 36, 3)
        for i in range(6):
            angle = now * 0.005 + i * math.tau / 6
            point = (int(47 + math.cos(angle) * 39), int(47 + math.sin(angle) * 39))
            pygame.draw.circle(halo, (245, 255, 255, 215), point, 3)
        surf.blit(halo, (int(self.x - 47), int(self.y - 47)))


class ZongFireball(BossProjectile):
    def draw(self, surf):
        super().draw(surf)
        rad = math.radians(self.angle)
        dx, dy = math.sin(rad), math.cos(rad)
        tail = (int(self.x - dx * 26), int(self.y - dy * 26))
        pygame.draw.line(surf, (255, 85, 30), tail, (int(self.x), int(self.y)), 10)
        pygame.draw.line(surf, (255, 230, 105), tail, (int(self.x), int(self.y)), 3)
        _circle(surf, (255, 235, 145), (int(self.x), int(self.y)), 7)


class ZongReflectBullet(BossProjectile):
    def __init__(self, x, y):
        super().__init__(x, y, 0, 6.0, damage=2)
        self.r = 11

    def draw(self, surf):
        center = (int(self.x), int(self.y))
        _circle(surf, (75, 190, 255), center, 16)
        _circle(surf, (160, 240, 255), center, 11)
        _circle(surf, (250, 255, 255), center, 6)
        pygame.draw.line(surf, (120, 225, 255), (center[0], center[1] - 17), center, 3)


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
        _circle(surf, body, center, self.r)
        _circle(surf, core, center, self.r - 5)
        _circle(surf, (255, 255, 235), (center[0] - 4, center[1] - 5), 3)


class NiuBoss(Boss):
    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.last_pattern = None
        self.vortex_x = config.SCREEN_WIDTH // 2
        self.vortex_y = config.GAME_AREA_BOTTOM * 0.62
        self.vortex_until = 0
        self.vortex_next_tick = 0
        self.lightning_xs = ()
        self.lightning_warning_until = 0
        self.lightning_until = 0
        self.lightning_next_tick = 0
        self.shield_until = 0
        self.shield_damage = 0
        self.shield_thresholds = (0.75, 0.5, 0.25)
        self.shield_triggered = set()

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        previous_hp = self.hp
        super().hit_by(weapon_name, amount, source=source, hit_rect=hit_rect)
        dealt = max(0, previous_hp - self.hp)
        if pygame.time.get_ticks() < self.shield_until:
            self.shield_damage += dealt
            if self.shield_damage >= self.max_hp * 0.15:
                self.shield_until = 0
        for threshold in self.shield_thresholds:
            if threshold not in self.shield_triggered and previous_hp / self.max_hp > threshold >= self.hp / self.max_hp:
                self.shield_triggered.add(threshold)
                self.shield_until = pygame.time.get_ticks() + 5000
                self.shield_damage = 0
                break

    def update(self):
        was_entered = self.entered
        super().update()
        if self.entered and not was_entered:
            self.last_attack_time = pygame.time.get_ticks()

    def should_attack(self, now):
        if self.laser_warning_start or now < self.laser_active_until:
            return False
        interval = self.attack_interval
        if now < self.slowed_until:
            interval /= self.slow_mult
        return self.entered and now - self.last_attack_time >= interval

    def death_laser_xs(self):
        return tuple(max(36, min(config.SCREEN_WIDTH - 36, self.x + offset))
                     for offset in (-190, 0, 190))

    def attack(self, now, player_x):
        self.last_attack_time = now
        pattern = random.choice([p for p in ('axes', 'axes', 'vortex', 'lightning', 'bullets')
                                 if p != self.last_pattern])
        self.last_pattern = pattern
        if pattern == 'axes':
            return [ReturningAxe(self, -1, max(40, min(config.SCREEN_WIDTH - 40, player_x - 55)), True),
                    ReturningAxe(self, 1, max(40, min(config.SCREEN_WIDTH - 40, player_x + 55)), False)]
        if pattern == 'vortex':
            self.vortex_x = max(170, min(config.SCREEN_WIDTH - 170, player_x))
            self.vortex_y = config.GAME_AREA_BOTTOM * 0.62
            self.vortex_until = now + 4300
            self.vortex_next_tick = now
            return []
        if pattern == 'lightning':
            self.lightning_xs = tuple(max(35, min(config.SCREEN_WIDTH - 35, player_x + dx))
                                      for dx in (-150, 0, 150))
            self.lightning_warning_until = now + 900
            self.lightning_until = now + 2300
            self.lightning_next_tick = now + 800
            return []
        return [NiuFanBullet(self.x + (i - 2.5) * 18, self.y + self.h * 0.7,
                             angle, red=i % 2 == 0)
                for i, angle in enumerate((-40, -24, -8, 8, 24, 40))]

    def lightning_rects(self, now):
        if now >= self.lightning_until:
            return ()
        return tuple(pygame.Rect(int(x - 35), int(self.y + self.h // 2), 70,
                                 int(config.GAME_AREA_BOTTOM - self.y - self.h // 2))
                     for x in self.lightning_xs)

    def draw(self, surf):
        super().draw(surf)
        now = pygame.time.get_ticks()
        cx, cy = int(self.x), int(self.y + self.h // 2)
        for i in range(12):
            angle = now * 0.003 + i * math.tau / 12
            px = cx + math.cos(angle) * (self.w * 0.65 + 8 * self.size_scale)
            py = cy + math.sin(angle) * (self.h * 0.65 + 8 * self.size_scale)
            _circle(surf, (255, 135 + i % 3 * 35, 45), (int(px), int(py)),
                    max(1, round((3 + i % 3) * self.size_scale)))
        if now < self.vortex_until:
            vortex = pygame.Surface((340, 340), pygame.SRCALPHA)
            center = (170, 170)
            pygame.draw.circle(vortex, (95, 10, 45, 48), center, 154)
            pygame.draw.circle(vortex, (255, 60, 15, 60), center, 148, 9)
            for i in range(4):
                radius = 48 + i * 28
                rect = pygame.Rect(170 - radius, 170 - radius, radius * 2, radius * 2)
                start = (now * 0.004 + i * 1.25) % math.tau
                pygame.draw.arc(vortex, (255, 100 + i * 30, 35, 170), rect,
                                start, start + math.pi * 1.4, 9)
                pygame.draw.arc(vortex, (255, 235, 125, 220), rect,
                                start + 0.2, start + math.pi * 0.9, 3)
            for i in range(18):
                angle = now * 0.006 + i * math.tau / 18
                radius = 32 + i % 5 * 26
                point = (int(170 + math.cos(angle) * radius), int(170 + math.sin(angle) * radius))
                pygame.draw.circle(vortex, (255, 220, 95, 190), point, 3 + i % 3)
            pygame.draw.circle(vortex, (255, 235, 135, 105), center, 37)
            pygame.draw.circle(vortex, (255, 65, 30, 160), center, 24)
            surf.blit(vortex, (int(self.vortex_x - 170), int(self.vortex_y - 170)))
        if now < self.lightning_until:
            top = int(self.y + self.h // 2)
            height = max(1, config.GAME_AREA_BOTTOM - top)
            beam = pygame.Surface((130, height), pygame.SRCALPHA)
            if now < self.lightning_warning_until:
                pygame.draw.line(beam, (255, 65, 35, 45), (65, 0), (65, height), 70)
                pygame.draw.line(beam, (255, 65, 35, 110), (65, 0), (65, height), 24)
                pygame.draw.line(beam, (255, 230, 120, 220), (65, 0), (65, height), 3)
                pygame.draw.circle(beam, (255, 120, 55, 230), (65, height - 16), 27, 5)
            else:
                points = [(65 + (0 if i in (0, 12) else int(math.sin(now * 0.025 + i * 2.3) * 19)),
                           int(height * i / 12)) for i in range(13)]
                pygame.draw.lines(beam, (255, 65, 25, 50), False, points, 60)
                pygame.draw.lines(beam, (255, 155, 35, 150), False, points, 32)
                pygame.draw.lines(beam, (255, 250, 190, 245), False, points, 10)
                pygame.draw.lines(beam, (255, 255, 255), False, points, 4)
                for i in (3, 6, 9):
                    px, py = points[i]
                    side = -1 if i % 2 else 1
                    branch = [(px, py), (px + side * 21, py + 20), (px + side * 34, py + 40)]
                    pygame.draw.lines(beam, (255, 180, 60, 190), False, branch, 6)
                    pygame.draw.lines(beam, (255, 245, 190, 230), False, branch, 2)
                for i in range(3, 12, 3):
                    px, py = points[i]
                    pygame.draw.circle(beam, (255, 240, 150, 200), (px, py), 13)
                pygame.draw.circle(beam, (255, 240, 125, 180), (65, height - 18), 42, 6)
            for x in self.lightning_xs:
                surf.blit(beam, (int(x - 65), top))
        if now < self.shield_until:
            width, height = int(self.w * 3.8), round(58 * self.size_scale)
            shield = pygame.Surface((width + round(28 * self.size_scale),
                                     height + round(24 * self.size_scale)), pygame.SRCALPHA)
            cx, cy = shield.get_width() // 2, shield.get_height() // 2
            points = [(18, cy - 9), (cx - width // 2 + 22, 12),
                      (cx + width // 2 - 22, 12), (shield.get_width() - 18, cy - 9),
                      (cx + width // 2 - 22, cy + 13), (cx, shield.get_height() - 12),
                      (cx - width // 2 + 22, cy + 13)]
            pygame.draw.polygon(shield, (30, 130, 210, 42), points)
            pygame.draw.polygon(shield, (80, 205, 255, 215), points, 4)
            pygame.draw.lines(shield, (210, 250, 255, 240), False,
                              [(28, cy - 8), (cx - width // 2 + 30, 20),
                               (cx + width // 2 - 30, 20), (shield.get_width() - 28, cy - 8)], 2)
            pygame.draw.line(shield, (70, 175, 255, 150), (cx - width // 2 + 40, cy + 4),
                             (cx + width // 2 - 40, cy + 4), 2)
            for x in (cx - width // 3, cx, cx + width // 3):
                pygame.draw.polygon(shield, (185, 245, 255, 210),
                                    [(x, cy - 12), (x + 8, cy), (x, cy + 12), (x - 8, cy)])
            surf.blit(shield, (int(self.x - shield.get_width() // 2), int(self.y + self.h + 8)))


class ZongBoss(Boss):
    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.body_hp = [self.max_hp / 2, self.max_hp / 2]
        self.next_fusion_time = 0
        self.fusion_mode = None
        self.fusion_until = 0
        self.fusion_started_at = 0
        self.fusion_end_volley = False
        self.snow_until = 0
        self.pending_projectiles = []
        self.attack_phase = 0
        self.next_revive_check = 0

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
        return self.fusion_mode == 'shield'

    def update(self):
        super().update()
        if not self.entered:
            return
        now = pygame.time.get_ticks()
        alive = [i for i in range(2) if self.body_hp[i] > 0]
        if len(alive) == 1:
            if not self.next_revive_check:
                self.next_revive_check = now + 10000
            elif now >= self.next_revive_check:
                if random.random() < 0.25:
                    revived = 1 - alive[0]
                    self.body_hp[revived] = self.max_hp * 0.20
                    self.hp = sum(self.body_hp)
                self.next_revive_check = now + 10000
        else:
            self.next_revive_check = 0
        if not self.next_fusion_time:
            self.next_fusion_time = now + 8000
        if self.fusion_mode and now >= self.fusion_until:
            if self.fusion_mode == 'rage' and not self.fusion_end_volley:
                self.pending_projectiles.extend(self._fireball_fan())
            self.fusion_mode = None
            self.next_fusion_time = now + 8500
        elif self.fusion_mode == 'rage' and not self.fusion_end_volley and now >= self.fusion_until - 500:
            self.pending_projectiles.extend(self._fireball_fan())
            self.fusion_end_volley = True
        elif not self.fusion_mode and all(hp > 0 for hp in self.body_hp) and now >= self.next_fusion_time:
            self.fusion_mode = random.choice(('shield', 'rage'))
            self.fusion_until = now + 5000
            self.fusion_started_at = now
            self.fusion_end_volley = False
            if random.random() < 0.4:
                self.snow_until = now + 5000
            if self.fusion_mode == 'rage':
                self.pending_projectiles.extend(self._fireball_fan())

    def _fireball_fan(self):
        return [ZongFireball(self.x, self.y + self.h, -63 + i * 18, 4.5,
                             damage=3, big_fireball=True) for i in range(8)]

    def attack(self, now, player_x):
        self.last_attack_time = now
        if self.fusion_mode:
            return []
        self.attack_phase += 1
        if self.attack_phase % 2:
            bombs = [ZongBomb(self.body_x(i) + offset, self.y + self.h - 10, angle, 3.8,
                              homing=True, damage=3, bomb=True, explode_radius=125)
                     for i, offset, angle in ((0, -20, -20), (0, 20, 0), (1, 0, 20))
                     if self.body_hp[i] > 0]
            for bomb in bombs:
                bomb.r = 30
            return bombs
        alive = [i for i in range(2) if self.body_hp[i] > 0]
        if not alive:
            return []
        xs = [self.body_x(i) for i in alive] if len(alive) == 2 else [self.body_x(alive[0]) + dx for dx in (-55, 55)]
        return [CrescentWave(x, self.y + self.h - 8) for x in xs]

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        if self.fusion_mode == 'shield':
            return
        damage = amount * getattr(self, 'damage_mult', 1.0)
        alive = [i for i in range(2) if self.body_hp[i] > 0]
        if len(alive) == 1:
            i = alive[0]
            self.body_hp[i] = max(0, self.body_hp[i] - damage * 2)
        elif self.fusion_mode == 'rage':
            for i in alive:
                self.body_hp[i] = max(0, self.body_hp[i] - damage / len(alive))
        else:
            allowed = (1,) if source == 'bullet' else (0,)
            for i in allowed:
                if self.body_hp[i] <= 0:
                    continue
                box = pygame.Rect(int(self.body_x(i) - self.w // 2), int(self.y), self.w, self.h)
                if hit_rect is None or hit_rect.colliderect(box):
                    self.body_hp[i] = max(0, self.body_hp[i] - damage)
                    break
        self.hp = sum(self.body_hp)

    def _draw_aura(self, surf, x, cy, index, now):
        accent = ((65, 220, 255), (185, 115, 255))[index] if not self.fusion_mode else (
            (120, 225, 255) if self.fusion_mode == 'shield' else (255, 95, 50))
        radius = round((108 if self.fusion_mode else 80) * self.size_scale)
        halo = pygame.Surface((300, 300), pygame.SRCALPHA)
        center = (150, 150)
        pulse = round(5 * math.sin(now * 0.009) * self.size_scale)
        pygame.draw.circle(halo, (*accent, 30), center, radius + round(22 * self.size_scale))
        pygame.draw.circle(halo, (*accent, 100), center, radius + pulse,
                           max(1, round(10 * self.size_scale)))
        pygame.draw.circle(halo, (235, 250, 255, 175), center,
                           max(1, radius - round(8 * self.size_scale)),
                           max(1, round(3 * self.size_scale)))
        for i in range(12):
            angle = now * (0.003 if self.fusion_mode != 'rage' else -0.006) + i * math.tau / 12
            px = 150 + math.cos(angle) * (radius + 15 * self.size_scale)
            py = 150 + math.sin(angle) * (radius + 15 * self.size_scale)
            crystal = [(px, py - 6 * self.size_scale), (px + 4 * self.size_scale, py),
                       (px, py + 6 * self.size_scale), (px - 4 * self.size_scale, py)]
            pygame.draw.polygon(halo, (*accent, 185), crystal)
            pygame.draw.circle(halo, (245, 255, 255, 190), (int(px), int(py)),
                               max(1, round(2 * self.size_scale)))
        if self.fusion_mode == 'shield':
            corners = [(int(150 + math.cos(now * 0.001 + i * math.tau / 6) * 98 * self.size_scale),
                        int(150 + math.sin(now * 0.001 + i * math.tau / 6) * 98 * self.size_scale))
                       for i in range(6)]
            pygame.draw.polygon(halo, (175, 245, 255, 195), corners,
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
                pygame.draw.polygon(halo, (255, 170, 45, 125), points)
        if self.fusion_mode and now - self.fusion_started_at < 650:
            spread = round((85 + (now - self.fusion_started_at) / 650 * 55) * self.size_scale)
            pygame.draw.circle(halo, (*accent, 190), center, spread,
                               max(1, round(5 * self.size_scale)))
        surf.blit(halo, (int(x - 150), int(cy - 150)))

    @staticmethod
    def draw_snow(surf, until, font):
        now = pygame.time.get_ticks()
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
        label = font.render('极寒暴雪 · 移速与射速减半', True, (225, 250, 255))
        box = pygame.Rect(config.SCREEN_WIDTH // 2 - label.get_width() // 2 - 16, 246,
                          label.get_width() + 32, label.get_height() + 12)
        pygame.draw.rect(snow, (8, 38, 78, 175), box, border_radius=8)
        pygame.draw.rect(snow, (180, 235, 255, 190), box, 2, border_radius=8)
        surf.blit(snow, (0, 0))
        surf.blit(label, (box.x + 16, box.y + 6))

    def draw(self, surf):
        now = pygame.time.get_ticks()
        centers = ((self.x, '融合'),) if self.fusion_mode else tuple(
            (self.body_x(i), '技能免疫' if i == 1 else '子弹免疫')
            for i in range(2) if self.body_hp[i] > 0)
        for x, label in centers:
            cy = self.y + self.h // 2
            self._draw_aura(surf, x, cy, 0 if x < self.x else 1, now)
            scale = 1.45 if self.fusion_mode else 1.0
            size = (int((self.w + 20) * scale), int((self.h + 20) * scale))
            image = scale_surface_cached(self.surface, size) if self.fusion_mode else self.surface
            from . import animation
            sprite = animation.boss_frame(self, now)
            if sprite is not None:
                image = scale_surface_cached(sprite, size)
            surf.blit(image, (int(x - size[0] // 2), int(cy - size[1] // 2)))
            if not self.fusion_mode:
                i = 0 if x < self.x else 1
                bar_width, bar_height = round(110 * self.size_scale), max(1, round(7 * self.size_scale))
                _rect(surf, (55, 45, 55), (int(x - bar_width // 2), int(self.y + self.h + 5),
                                            bar_width, bar_height))
                _rect(surf, (255, 150, 70), (int(x - bar_width // 2), int(self.y + self.h + 5),
                                            int(bar_width * self.body_hp[i] / (self.max_hp / 2)),
                                            bar_height))
                title = self.font_hp.render(label, True, (255, 250, 215))
                surf.blit(title, (int(x - title.get_width() // 2), int(self.y + self.h + 16)))
        bx, by, width = config.SCREEN_WIDTH // 2 - 210, 8, 420
        _rect(surf, (25, 22, 35, 220), (bx - 2, by - 2, width + 4, 22), border_radius=5)
        _rect(surf, (60, 55, 65), (bx, by, width, 18), border_radius=4)
        _rect(surf, (255, 105, 60), (bx, by, int(width * max(0, self.hp / self.max_hp)), 18), border_radius=4)
        name = self.font_name.render('小粽粽 × 2' + (' · 护盾' if self.fusion_mode == 'shield' else ' · 狂暴' if self.fusion_mode else ''),
                                     True, (255, 255, 255))
        name_y = int(self.y + self.h + 36) if self.fusion_mode else by + 22
        surf.blit(name, (bx, name_y))
