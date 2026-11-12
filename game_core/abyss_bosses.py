"""Shared factory/temple boss rules, including collision and telegraphs.

PC, browser and authoritative multiplayer use these exact objects.  Network
adapters may serialize ABYSS_PROJECTILE_FIELDS, but must not reimplement damage.
Angles use the game's convention: zero points down, positive points right.
"""
import math
import random
import pygame

from . import animation, config
from .asset_loader import image_asset
from .entities import Boss, BossProjectile
from .render import Draw, RenderSurface, blit_effect, effect_layer
from .visuals import draw_glow, draw_missile_trail


ABYSS_PROJECTILE_FIELDS = (
    'skill', 'warning_ms', 'active_ms', 'origin_x', 'origin_y', 'last_update',
    'width', 'height', 'ring_radius', 'ring_speed', 'ring_thickness',
    'visual_scale', 'whip_directions', 'missile_pass', 'unblockable',
    'persistent', 'self_telegraphed', 'pearl_burst_at',
)
EFFECT_ASSETS = {
    'plasma_rail': 'effects/mecha_plasma_rail.png',
    'guided_missile': 'effects/mecha_guided_missile.png',
    'emp_ring': 'effects/mecha_emp_ring.png',
    'molten_burst': 'effects/mecha_molten_burst.png',
    'tidal_crescent': 'effects/whale_tidal_crescent.png',
    'rune_geyser': 'effects/whale_rune_geyser.png',
    'ancient_pearl': 'effects/whale_ancient_pearl.png',
}
RINGS = ('emp_ring',)
LANES = ('plasma_rail', 'rune_geyser')
GEYSER_PEEK_MS = 460
GEYSER_BREAK_MS = 430
GEYSER_SHATTER_MS = 300
FACTORY_SKILLS = ('plasma_rail', 'guided_missile', 'emp_ring', 'molten_burst')
RAIL_EXTEND_MS = 650
RAIL_LASH_MS = 620
RAIL_GAP_MS = 1000
RAIL_WINDUP_MS = 150
RAIL_CYCLE_MS = RAIL_LASH_MS + RAIL_GAP_MS
RAIL_ACTIVE_MS = RAIL_EXTEND_MS + 2 * RAIL_CYCLE_MS + RAIL_LASH_MS
MISSILE_WINDUP_MS = 540
MISSILE_LAUNCH_GAP_MS = 850
EMP_CHARGE_MS = 3000
EMP_BURST_AT_MS = EMP_CHARGE_MS + 1500
EMP_DASH_MS = 360
EMP_RETURN_MS = 480
EMP_ORB_COUNT = 8
EMP_ORB_ASSET = 'effects/mecha_emp_iron_ball.png'


def _blit(surf, image, center, size):
    """Scale from the source PNG at the actual output resolution."""
    scale = surf.scale if isinstance(surf, RenderSurface) else 1
    size = tuple(max(1, round(v * scale)) for v in size)
    if image.get_size() != size:
        image = pygame.transform.smoothscale(image, size)
    center = surf.point(center) if isinstance(surf, RenderSurface) else center
    position = image.get_rect(center=(round(center[0]), round(center[1]))).topleft
    if isinstance(surf, RenderSurface):
        surf.blit_pixels(image, position)
    else:
        surf.blit(image, position)


class AbyssProjectile(BossProjectile):
    """One serializable attack object, harmless until its visible warning ends.

    Persistent attacks keep their path after contact. They record which players
    they hit so a single pass cannot keep dealing damage every frame.
    """
    def __init__(self, skill, x, y, *, angle=0, speed=0, warning_ms=1000,
                 active_ms=4000, damage=1, scale=1):
        super().__init__(x, y, angle, speed, damage=damage)
        self.skill = skill
        self.warning_ms = warning_ms
        self.active_ms = active_ms
        self.max_lifetime = warning_ms + active_ms
        self.origin_x, self.origin_y = x, y
        self.last_update = self.spawn_time
        self.visual_scale = scale
        self.r = {'guided_missile': 14, 'molten_burst': 30, 'emp_ring': 23,
                  'ancient_pearl': 30, 'pearl_fragment': 8}.get(skill, 12) * scale
        self.width = (148 if skill == 'tidal_crescent' else 54) * scale
        self.height = (40 if skill == 'tidal_crescent' else 28) * scale
        self.ring_radius = 0.0
        self.ring_speed = (150 if skill == 'emp_ring' else 170) * scale
        self.ring_thickness = 13 * scale
        self.pearl_bounces = 0
        self.pearl_burst_at = 0
        self.whip_directions = random.randrange(8) if skill == 'plasma_rail' else 0
        self.missile_pass = 0
        self.missile_turn_rate = 150
        self.missile_tracking_offset = 0
        self.unblockable = skill in RINGS + LANES or skill == 'guided_missile'
        self.persistent = self.unblockable or skill == 'ancient_pearl'
        self._hit_players = set()
        self.self_telegraphed = True

    def is_active(self, now=None):
        age = (config.game_ticks() if now is None else now) - self.spawn_time
        return self.alive and self.warning_ms <= age < self.max_lifetime

    def update(self, target_x=None, target_y=None):
        now = config.game_ticks()
        age = now - self.spawn_time
        self.prev_x, self.prev_y = self.x, self.y
        if age >= self.max_lifetime:
            self.alive = False
            return
        dt = max(0, now - max(self.last_update, self.spawn_time + self.warning_ms)) / 1000
        previous_age = self._active_age()
        self.last_update = now
        if not self.is_active(now):
            return
        active_age = age - self.warning_ms
        if self.skill == 'plasma_rail':
            lash = self._rail_lash(active_age)
            if lash is not None and lash != self._rail_lash(previous_age):
                self._hit_players.clear()
        elif self.skill == 'emp_ring':
            if previous_age < EMP_BURST_AT_MS <= active_age:
                self._hit_players.clear()
            self.ring_radius = 5 * self.visual_scale + min(active_age, EMP_CHARGE_MS) / 1000 * self.ring_speed
            self.ring_thickness = min(13 * self.visual_scale, self.ring_radius * .06)
        elif self.skill == 'ancient_pearl':
            self._update_pearl(dt, now)
        elif self.skill == 'guided_missile':
            self._update_missile(dt, target_x, target_y)
        elif self.skill not in LANES:
            rad = math.radians(self.angle)
            self.x += math.sin(rad) * self.speed * 60 * dt
            self.y += math.cos(rad) * self.speed * 60 * dt
            if (self.y > config.SCREEN_HEIGHT + 100 or self.y < -100
                    or self.x < config.GAME_AREA_LEFT - 100 or self.x > config.GAME_AREA_RIGHT + 100):
                self.alive = False

    def _update_pearl(self, dt, now):
        if self.pearl_burst_at:
            self.alive = now < self.pearl_burst_at
            return
        left = config.GAME_AREA_LEFT + self.r
        right = config.GAME_AREA_RIGHT - self.r
        top, bottom = self.r, config.GAME_AREA_BOTTOM - self.r
        self.x = max(left, min(right, self.x))
        self.y = max(top, min(bottom, self.y))
        rad = math.radians(self.angle)
        age = (now - self.spawn_time - self.warning_ms) / 1000
        # Integrate the speed ramp across the entire step, including bounces.
        start, end = max(0, age - dt), age
        ramp = 2.5
        start_ramp, end_ramp = min(ramp, start), min(ramp, end)
        travel = dt - .75 * (end_ramp - start_ramp) * (1 - (start_ramp + end_ramp) / (2 * ramp))
        vx, vy = math.sin(rad) * self.speed * 60, math.cos(rad) * self.speed * 60
        dt = travel
        while dt > 0:
            tx = ((right if vx > 0 else left) - self.x) / vx if abs(vx) > 1e-8 else math.inf
            ty = ((bottom if vy > 0 else top) - self.y) / vy if abs(vy) > 1e-8 else math.inf
            step = min(dt, tx, ty)
            self.x += vx * step
            self.y += vy * step
            dt -= step
            if tx == step:
                self.x = right if vx > 0 else left
                vx = -vx
                self.pearl_bounces += 1
            if ty == step:
                self.y = bottom if vy > 0 else top
                vy = -vy
                self.pearl_bounces += 1
            if tx == step or ty == step:
                self.angle = math.degrees(math.atan2(vx, vy))
                self._hit_players.clear()
            if self.pearl_bounces >= 6:
                self.pearl_bounces = 6
                self.pearl_burst_at = now + 3000
                return

    def pearl_fragments(self):
        return [AbyssProjectile('pearl_fragment', self.x, self.y, angle=angle,
                                speed=4.5 * self.visual_scale, warning_ms=0,
                                active_ms=2300, damage=self.damage, scale=self.visual_scale)
                for angle in range(0, 360, 60)]

    def _update_missile(self, dt, target_x, target_y):
        bottom = config.SCREEN_HEIGHT + self.r
        if self.missile_pass == 0 and self.y >= bottom:
            self.missile_pass = 1
        elif self.missile_pass == 1 and self.y <= self.origin_y:
            self.missile_pass = 2
            self._hit_players.clear()
        elif self.missile_pass == 2 and self.y >= bottom and math.cos(math.radians(self.angle)) > 0:
            self.alive = False
            return

        if self.missile_pass == 1:
            desired = 180
        else:
            dx = 0 if target_x is None else target_x + self.missile_tracking_offset - self.x
            dy = config.GAME_AREA_BOTTOM if target_y is None else target_y
            desired = max(-50, min(50, math.degrees(math.atan2(dx, max(85, dy - self.y)))))
        delta = (desired - self.angle + 180) % 360 - 180
        turning_back = self.missile_pass == 1 or math.cos(math.radians(self.angle)) < 0
        turn = (320 if turning_back else self.missile_turn_rate) * dt
        self.angle += max(-turn, min(turn, delta))
        rad = math.radians(self.angle)
        self.x = max(config.GAME_AREA_LEFT + self.r, min(config.GAME_AREA_RIGHT - self.r,
                     self.x + math.sin(rad) * self.speed * 60 * dt))
        self.y += math.cos(rad) * self.speed * 60 * dt
        if dt and hasattr(self, 'missile_trail'):
            rear = self.r * 6
            self.missile_trail.append((round(self.x - math.sin(rad) * rear),
                                       round(self.y - math.cos(rad) * rear)))
            if len(self.missile_trail) > 23:
                del self.missile_trail[0]

    def _active_age(self):
        return max(0, self.last_update - self.spawn_time - self.warning_ms)

    @staticmethod
    def _rail_lash(age):
        lash, phase = divmod(age - RAIL_EXTEND_MS, RAIL_CYCLE_MS)
        return lash if 0 <= lash < 3 and phase < RAIL_LASH_MS else None

    def _rail_points(self):
        age = self._active_age()
        height = self.height * min(1, age / RAIL_EXTEND_MS)
        lash_age = max(0, age - RAIL_EXTEND_MS)
        lash, progress = divmod(lash_age, RAIL_CYCLE_MS)
        if progress >= RAIL_LASH_MS:
            drift = math.sin(math.pi * (progress - RAIL_LASH_MS) / RAIL_GAP_MS)
            return [(self.x + height * .10 * drift * t * math.sin(age * .004 - t * 3),
                     self.y + height * (1 - .07 * drift) * t)
                    for t in (i / 32 for i in range(33))]
        phase = progress / RAIL_LASH_MS
        direction = 1 if self.whip_directions & (1 << int(lash)) else -1
        swing = direction * min(285, height * .62) * math.sin(math.pi * phase)
        # The S-curve travels from the grip down to the tip as the whip uncoils.
        reach = 1 - .18 * math.sin(math.tau * phase) ** 2
        return [(self.x + swing * t ** .75 * math.sin(math.pi * (1.75 * t - 2 * phase)),
                 self.y + height * reach * t) for t in (i / 32 for i in range(33))]

    def _emp_orbs(self):
        age = self._active_age()
        burst_age = max(0, age - EMP_BURST_AT_MS) / 1000
        radius = self.ring_radius + burst_age * 290
        count = min(EMP_ORB_COUNT, int(age // 320))
        angle = min(age, EMP_BURST_AT_MS) * .0035
        for i in range(count):
            a = angle + i * math.tau / EMP_ORB_COUNT
            flight = min(1, (age - (i + 1) * 320) / 440)
            spread = min(.18, .035 + burst_age * .38) if age >= EMP_BURST_AT_MS else 0
            for offset in (-spread, spread) if spread else (0,):
                yield (self.x + math.cos(a + offset) * radius * flight,
                       self.y + math.sin(a + offset) * radius * flight)

    def _emp_link_points(self):
        age = self._active_age()
        if not EMP_CHARGE_MS < age < EMP_BURST_AT_MS:
            return []
        sweep = math.tau * (age - EMP_CHARGE_MS) / (EMP_BURST_AT_MS - EMP_CHARGE_MS)
        segments = math.ceil(64 * sweep / math.tau)
        start = age * .0035
        return [(self.x + self.ring_radius * math.cos(start + sweep * i / segments),
                 self.y + self.ring_radius * math.sin(start + sweep * i / segments))
                for i in range(segments + 1)]

    def _emp_orb_radius(self):
        return 3 * self.r * (.6 if self._active_age() >= EMP_BURST_AT_MS else 1)

    def _geyser_height(self):
        elapsed = config.game_ticks() - self.spawn_time - self.warning_ms
        tip = self.height * .12
        if elapsed < 0:
            return tip * max(0, min(1, (elapsed + GEYSER_PEEK_MS) / 180))
        progress = min(1, elapsed / 330)
        return tip + (self.height - tip) * progress ** 2

    def bounds(self):
        if self.skill == 'plasma_rail':
            points = self._rail_points()
            xs, ys = zip(*points)
            pad = self.width / 2
            return pygame.Rect(math.floor(min(xs) - pad), math.floor(self.y - pad),
                               math.ceil(max(xs) - min(xs) + self.width + 2),
                               math.ceil(max(ys) - self.y + self.width + 2))
        if self.skill in LANES:
            height = self.height
            if self.skill == 'rune_geyser':
                height = self._geyser_height()
            return pygame.Rect(round(self.x - self.width / 2), round(self.y + self.height - height),
                               round(self.width), round(height))
        if self.skill in RINGS:
            radius = self.ring_radius + self.ring_thickness / 2
            if self.skill == 'emp_ring':
                radius = self.ring_radius + max(0, self._active_age() - EMP_BURST_AT_MS) * .29 + self.r
            return pygame.Rect(round(self.x - radius), round(self.y - radius),
                               math.ceil(2 * radius), math.ceil(2 * radius))
        if self.skill == 'tidal_crescent':
            return pygame.Rect(round(self.x - self.width / 2), round(self.y - self.height / 2),
                               round(self.width), round(self.height))
        return super().rect()

    def rect(self):
        return self.bounds() if self.is_active() else pygame.Rect(0, 0, 0, 0)

    def block_rect(self):
        if not self.is_active():
            return pygame.Rect(0, 0, 0, 0)
        return self.bounds() if self.skill in RINGS + LANES else self.bounds().union(
            self.bounds().move(round(self.prev_x - self.x), round(self.prev_y - self.y)))

    def hits_rect(self, rect):
        """Shared narrow phase; never treat a ring's transparent center as solid."""
        if not self.is_active() or not self.bounds().colliderect(rect):
            return False
        if self.skill == 'plasma_rail':
            if self._rail_lash(self._active_age()) is None:
                return False
            hitbox = rect.inflate(round(self.width), round(self.width))
            points = self._rail_points()
            return any(hitbox.clipline(a, b) for a, b in zip(points, points[1:]))
        if self.skill == 'emp_ring':
            radius = self._emp_orb_radius()
            if any(math.hypot(x - max(rect.left, min(x, rect.right)),
                              y - max(rect.top, min(y, rect.bottom))) <= radius
                   for x, y in self._emp_orbs()):
                return True
            points = self._emp_link_points()
            band = rect.inflate(round(self.ring_thickness), round(self.ring_thickness))
            return any(band.clipline(a, b) for a, b in zip(points, points[1:]))
        if self.skill == 'rune_geyser':
            return self._active_age() < GEYSER_BREAK_MS
        if self.skill in LANES or self.skill == 'tidal_crescent':
            return True
        nearest_x = max(rect.left, min(self.x, rect.right))
        nearest_y = max(rect.top, min(self.y, rect.bottom))
        nearest = math.hypot(nearest_x - self.x, nearest_y - self.y)
        return nearest <= self.r

    def _missile_art(self, image):
        # The PNG includes a long exhaust above its downward-facing nose.
        # Preserve its aspect ratio and anchor the nose, not the whole canvas,
        # to the circular gameplay hitbox. Rotation shares that same pivot.
        factor = self.r * 3 / image.get_width()
        height = image.get_height() * factor
        rad = math.radians(self.angle)
        center = (self.x - math.sin(rad) * height * .40,
                  self.y - math.cos(rad) * height * .40)
        if self.angle:
            image = pygame.transform.rotate(image, self.angle)
        return image, tuple(v * factor for v in image.get_size()), center

    def draw(self, surf):
        if not self.alive:
            return
        active = self.is_active()
        color = (255, 179, 65) if self.skill in ('molten_burst', 'ancient_pearl') else (95, 230, 255)
        if self.skill == 'plasma_rail':
            grip = self.x, self.y
            charge = min(1, max(0, (config.game_ticks() - self.spawn_time) / self.warning_ms))
            draw_glow(surf, grip, max(7, round(self.width * (1 + charge))), color, round(60 + 85 * charge))
            Draw.circle(surf, (26, 55, 76), grip, max(4, round(self.width * .5)))
            Draw.circle(surf, (196, 249, 255), grip, max(2, round(self.width * .23)))
            if active and self._active_age() > 0:
                points = self._rail_points()
                striking = self._rail_lash(self._active_age()) is not None
                width = self.width if striking else self.width * .64
                core = (235, 255, 255) if striking else (136, 210, 242)
                Draw.lines(surf, (35, 85, 150), False, points, max(1, round(width)))
                Draw.lines(surf, (64, 182, 230), False, points, max(1, round(width * .6)))
                Draw.lines(surf, core, False, points, max(1, round(width * .19)))
                phase = self._active_age() / 260
                for offset in (0, .33, .66):
                    position = ((phase + offset) % 1) * (len(points) - 1)
                    index = int(position)
                    a = pygame.Vector2(points[index])
                    b = pygame.Vector2(points[index + 1])
                    spark = a.lerp(b, position - index)
                    Draw.circle(surf, (232, 255, 255), spark, max(1, round(width * .16)))
                tip = points[-1]
                draw_glow(surf, tip, max(4, round(width * .8)), color, 130)
                Draw.circle(surf, core, tip, max(2, round(width * .23)))
            return
        if self.skill == 'emp_ring' and active:
            burst_age = self._active_age() - EMP_BURST_AT_MS
            points = self._emp_link_points()
            if points:
                width = max(2, round(self.ring_thickness))
                Draw.lines(surf, (36, 104, 185), False, points, width + 5)
                Draw.lines(surf, color, False, points, width)
                Draw.lines(surf, (230, 255, 255), False, points, max(1, width // 3))
                Draw.circle(surf, color, points[-1], width + 2)
            iron_ball = image_asset(EMP_ORB_ASSET)
            radius = self._emp_orb_radius()
            for x, y in self._emp_orbs():
                if iron_ball is None:
                    Draw.circle(surf, (85, 101, 121), (x, y), round(radius))
                    Draw.circle(surf, color, (x, y), max(1, round(radius * .35)))
                else:
                    _blit(surf, iron_ball, (x, y), (2.35 * radius, 2.35 * radius))
                if 0 <= burst_age < 280:
                    Draw.circle(surf, color, (x, y), round(self.r + burst_age * .07), 2)
            return
        if self.skill == 'pearl_fragment':
            if not active:
                return
            rad = math.radians(self.angle)
            dx, dy = math.sin(rad) * self.r, math.cos(rad) * self.r
            points = [(self.x + dx, self.y + dy), (self.x - dy * .55, self.y + dx * .55),
                      (self.x - dx * .9, self.y - dy * .9), (self.x + dy * .55, self.y - dx * .55)]
            Draw.polygon(surf, (255, 222, 156), points)
            Draw.polygon(surf, (189, 118, 52), points, 1)
            return
        if self.skill == 'rune_geyser':
            self._draw_geyser(surf, color)
            return
        if self.skill == 'tidal_crescent' and not active:
            return
        scale = surf.scale if isinstance(surf, RenderSurface) else 1
        effect_size = None
        if self.skill == 'ancient_pearl':
            effect_size = (max(1, round(self.r * 3 * scale)),) * 2
        elif self.skill == 'tidal_crescent':
            effect_size = (max(1, round(self.width * scale)),
                           max(1, round(self.height * 2.2 * scale)))
        image = image_asset(EFFECT_ASSETS[self.skill], effect_size)
        if not active:
            if self.skill in FACTORY_SKILLS:
                if image is not None and self.skill == 'guided_missile' and self.missile_pass == 2:
                    preview, size, center = self._missile_art(image.copy())
                    preview.set_alpha(115)
                    _blit(surf, preview, center, size)
                return
            rad = math.radians(self.angle)
            Draw.line(surf, color, (self.x, self.y),
                      (self.x + math.sin(rad) * 65, self.y + math.cos(rad) * 65), 2)
            Draw.circle(surf, color, (round(self.x), round(self.y)), max(2, round(self.r + 5)), 1)
            if image is not None and self.skill not in LANES + RINGS:
                preview = image.copy()
                preview.set_alpha(100)
                if self.skill == 'guided_missile':
                    preview, size, center = self._missile_art(preview)
                    _blit(surf, preview, center, size)
                else:
                    _blit(surf, preview, (self.x, self.y), (self.r * 3, self.r * 3))
            return
        if self.skill == 'guided_missile':
            draw_missile_trail(surf, getattr(self, 'missile_trail', ()), 9)
        if image is None:
            Draw.rect(surf, color, self.bounds(), 2)
            return
        if self.skill in LANES:
            size = (self.width * 1.35, self.height)
            center = (self.x, self.y + self.height / 2)
        elif self.skill == 'guided_missile':
            image, size, center = self._missile_art(image)
        elif self.skill == 'tidal_crescent':
            size, center = (self.width, self.height * 2.2), (self.x, self.y)
        else:
            size, center = (self.r * 3, self.r * 3), (self.x, self.y)
            if self.angle and self.skill not in ('ancient_pearl', 'pearl_fragment'):
                image = pygame.transform.rotate(image, self.angle)
        _blit(surf, image, center, size)
        if self.skill == 'ancient_pearl' and self.pearl_burst_at:
            remaining = max(0, self.pearl_burst_at - config.game_ticks())
            Draw.circle(surf, (255, 242, 165) if remaining % 500 < 250 else (255, 107, 48),
                        (self.x, self.y), round(self.r * (1 + remaining / 6000)), 3)
            for i in range(math.ceil(remaining / 1000)):
                Draw.circle(surf, (255, 244, 186),
                            (self.x + (i - 1) * self.r * .45, self.y - self.r * 1.25), 3)


    def _draw_geyser(self, surf, color):
        age = self._active_age()
        if age >= GEYSER_BREAK_MS:
            progress = (age - GEYSER_BREAK_MS) / GEYSER_SHATTER_MS
            for i in range(24):
                spread = (i % 8 - 3.5) * self.width / 8
                x = self.x + spread * (.45 + progress * 1.65)
                y = self.y + self.height * (i // 8) / 5 - 50 * progress + 90 * progress ** 2
                Draw.circle(surf, color, (x, y), max(1, round((4 + i % 5) * (1 - progress))))
            return
        height = self._geyser_height()
        if height <= 0:
            return
        scale = surf.scale if isinstance(surf, RenderSurface) else 1
        size = max(1, round(self.width * scale)), max(1, round(self.height * scale))
        top = self.y + self.height - height
        art = image_asset(EFFECT_ASSETS[self.skill], size)
        if art is not None:
            _blit(surf, art, (self.x, top + self.height / 2), (self.width, self.height))
        else:
            Draw.ellipse(surf, color, self.bounds())


class AbyssBoss(Boss):
    SKILLS = ()

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self._pending_attack_skill = None
        self.current_skill = ''
        self.skill_started_at = 0
        self.signature_opening_pending = False
        self.self_telegraphed = True
        self.sprite_asset = 'bosses/' + bdef['key'] + '.png'

    def can_laser(self):
        return False

    def should_attack(self, now):
        # The interval includes warning and recovery time.
        if self.hp <= 0 or not self.entered:
            return False
        if self._last_attack_skill is None:
            return now - self.fight_start_time >= config.BOSS_OPENING_DELAY_MS
        return now - self.last_attack_time >= self.attack_interval

    def attack(self, now, player_x, player_y=None):
        if self.hp <= 0:
            return []
        self.last_attack_time = self.skill_started_at = now
        self.current_skill = self._next_attack_skill()
        self._pending_attack_skill = None
        shots = self._skill_shots(self.current_skill, player_x, player_y)
        for shot in shots:
            shot.spawn_time = shot.last_update = now
        return shots

    def _next_attack_skill(self):
        if self._pending_attack_skill is None:
            self._pending_attack_skill = self._choose_attack_skill(self.SKILLS)
        return self._pending_attack_skill

    def _shot(self, skill, x, y, **kwargs):
        return AbyssProjectile(skill, x, y, scale=self.size_scale, **kwargs)

    def draw(self, surf, *, visual_scale=1):
        art = image_asset(self.sprite_asset)
        if art is None:
            super().draw(surf, visual_scale=visual_scale)
            return
        pulse = visual_scale * (1 + .018 * math.sin((config.game_ticks() - self.breath_start_time) * .003))
        _blit(surf, art, (self.x, self.y + self.h / 2), (self.w * pulse, self.h * pulse))


class MechaLizardBoss(AbyssBoss):
    SKILLS = FACTORY_SKILLS
    EMP_ACTION_MS = EMP_DASH_MS + EMP_BURST_AT_MS + EMP_RETURN_MS
    CAST_POSES = {
        'plasma_rail': (4, RAIL_WINDUP_MS + RAIL_ACTIVE_MS),
        'guided_missile': (5, MISSILE_WINDUP_MS + 2 * MISSILE_LAUNCH_GAP_MS + 240),
        'emp_ring': (6, EMP_ACTION_MS),
        'molten_burst': (7, 1860),
    }

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self._emp_dash_origin = None
        self._emp_dash_hitboxes = ()

    def should_attack(self, now):
        if (self.current_skill == 'plasma_rail'
                and now - self.skill_started_at < RAIL_WINDUP_MS + RAIL_ACTIVE_MS):
            return False
        return self._emp_dash_origin is None and super().should_attack(now)

    def update(self):
        self._emp_dash_hitboxes = ()
        if self._emp_dash_origin is None:
            super().update()
            return
        age = config.game_ticks() - self.skill_started_at
        start_x, start_y = self._emp_dash_origin
        center_x = config.SCREEN_WIDTH / 2
        center_y = (config.SCREEN_HEIGHT - self.h) / 2
        if age <= EMP_DASH_MS:
            before = self.rect()
            progress = 1 - (1 - max(0, age) / EMP_DASH_MS) ** 2
            self.x = start_x + (center_x - start_x) * progress
            self.y = start_y + (center_y - start_y) * progress
            self._record_emp_dash(before)
            return
        if self.x != center_x or (self.y != center_y and age < EMP_DASH_MS + EMP_BURST_AT_MS):
            before = self.rect()
            self.x, self.y = center_x, center_y
            self._record_emp_dash(before)
        retreat = max(0, age - EMP_DASH_MS - EMP_BURST_AT_MS)
        self.y = center_y + (start_y - center_y) * min(1, retreat / EMP_RETURN_MS)
        if retreat >= EMP_RETURN_MS:
            self.movement_timer = 0
            self._emp_dash_origin = None

    def _record_emp_dash(self, before):
        after = self.rect()
        dx, dy = after.x - before.x, after.y - before.y
        steps = max(1, math.ceil(math.hypot(dx, dy) / (min(self.w, self.h) / 3)))
        self._emp_dash_hitboxes = tuple(before.move(round(dx * i / steps), round(dy * i / steps))
                                        for i in range(steps + 1))

    def hitboxes(self):
        return self._emp_dash_hitboxes or super().hitboxes()

    def draw(self, surf, *, visual_scale=1):
        now = config.game_ticks()
        age = now - self.skill_started_at
        pose, duration = self.CAST_POSES.get(self.current_skill, (0, 0))
        elapsed = now - self.breath_start_time
        stride = math.cos(self.movement_timer * .02)
        if 0 <= age < duration:
            recoil = math.sin(math.pi * min(1, age / 320))
            y_offset = -self.h * .045 * recoil
            stretch = 1 + .045 * recoil
        elif not self.entered or abs(stride) > .30:
            step = elapsed // 165 if not self.entered else int(self.movement_timer / 6)
            pose = 2 + step % 2
            y_offset = -self.h * .025 * abs(math.sin(elapsed * .012))
            stretch = 1
        else:
            pose = elapsed // 460 % 2
            y_offset = self.h * .012 * math.sin(elapsed * .005)
            stretch = 1 + .018 * math.sin(elapsed * .005)
        sprite = animation.frame('boss_mecha_lizard', pose)
        if sprite is None:
            super().draw(surf, visual_scale=visual_scale)
            return
        _blit(surf, sprite, (self.x, self.y + self.h / 2 + y_offset),
              (self.w * visual_scale / stretch, self.h * visual_scale * stretch))

    def sync_weapon_mount(self, shot, now):
        if shot.skill == 'plasma_rail':
            # Grip is at the forward claw of the casting sprite.
            recoil = math.sin(math.pi * max(0, min(1, (now - self.skill_started_at) / 320)))
            shot.x = self.x + self.w * .16 / (1 + .045 * recoil)
            shot.y = self.y + self.h * (.78 - .0324 * recoil)
            shot.height = max(0, config.GAME_AREA_BOTTOM - shot.y)
        elif (shot.skill == 'guided_missile' and
              shot.last_update < shot.spawn_time + shot.warning_ms):
            shot.origin_x = shot.x = self.x + shot.angle * self.size_scale
            shot.origin_y = shot.y = self.y + self.h * .75

    def _skill_shots(self, skill, player_x, player_y):
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        origin_y = self.y + self.h * .75
        tier = self.bdef.get('campaign_tier', 1)
        if skill == 'plasma_rail':
            shot = self._shot(skill, self.x, origin_y, warning_ms=RAIL_WINDUP_MS,
                              active_ms=RAIL_ACTIVE_MS, damage=2)
            shot.width = max(4, 24 * self.size_scale)
            self.sync_weapon_mount(shot, shot.spawn_time)
            return [shot]
        if skill == 'guided_missile':
            shots = []
            for i, angle in enumerate((-32, 0, 32)):
                shot = self._shot(skill, self.x + angle * self.size_scale, origin_y, angle=angle,
                                  speed=4.5 + tier * .25,
                                  warning_ms=MISSILE_WINDUP_MS + i * MISSILE_LAUNCH_GAP_MS, active_ms=20000)
                shot.missile_tracking_offset = (i - 1) * 90
                shot.missile_trail = []
                shots.append(shot)
            return shots
        if skill == 'emp_ring':
            self._emp_dash_origin = self.x, self.y
            shot = self._shot(skill, config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2,
                              warning_ms=EMP_DASH_MS, active_ms=EMP_BURST_AT_MS + 2200)
            start_radius = 5 * shot.visual_scale
            expansion_seconds = EMP_CHARGE_MS / 1000
            previous_max = start_radius + min(right - left, config.SCREEN_HEIGHT) * .064 * expansion_seconds
            shot.ring_speed = (previous_max * .8 - start_radius) / expansion_seconds
            return [shot]
        # Two offset salvos leave a substantial center channel, not a solid wall.
        return [self._shot(skill, self.x, origin_y, angle=a,
                           speed=(3.0 + tier * .15) * self.size_scale,
                           warning_ms=1100 + wave * 500, active_ms=6500)
                for wave in range(2) for a in (-56, -32, -16, 16, 32, 56)]


class AncientWhaleBoss(AbyssBoss):
    SKILLS = ('tidal_crescent', 'rune_geyser', 'ancient_pearl', 'whale_suction')
    CAST_SKILLS = SKILLS
    SUCTION_MS = 5000
    SWALLOW_MS = 700
    CAST_MS = {'tidal_crescent': 5000, 'rune_geyser': 3730, 'ancient_pearl': 1900,
               'whale_suction': SUCTION_MS}

    # Each motion occupies one row of eight frames.
    ANIMATION = {
        '': (0, 660), 'tidal_crescent': (1, 400), 'rune_geyser': (2, 1100),
        'ancient_pearl': (3, 640), 'whale_suction': (4, 520), 'whale_swallow': (5, SWALLOW_MS),
    }

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.suction_start_hp = 0
        self.swim_direction = 1
        self.swim_turn_at = -1000
        self.centering = False

    def _casting(self, now):
        return self.current_skill in self.CAST_SKILLS and (
            now - self.skill_started_at < self.CAST_MS[self.current_skill])

    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        if self.current_skill == 'tidal_crescent' and self._casting(config.game_ticks()):
            amount *= .5
        super().hit_by(weapon_name, amount, source=source, hit_rect=hit_rect)

    @property
    def swallowing(self):
        return self.current_skill == 'whale_swallow'

    def swallow_progress(self, now):
        return min(1, max(0, now - self.skill_started_at) / self.SWALLOW_MS)

    def suction_interrupted(self):
        return self.suction_start_hp - self.hp >= self.max_hp * .20

    def suction_active(self, now):
        return (self.current_skill == 'whale_suction' and self.hp > 0
                and now - self.skill_started_at < self.SUCTION_MS
                and not self.suction_interrupted())

    def _center_x(self):
        return (config.GAME_AREA_LEFT + config.GAME_AREA_RIGHT) / 2

    def update(self):
        now = config.game_ticks()
        if not self.entered:
            super().update()
            return
        if (not self._casting(now) and super().should_attack(now)
                and self._next_attack_skill() == 'whale_suction'):
            center = self._center_x()
            self.centering = True
            if center != self.x:
                self.swim_direction = 1 if self.x < center else -1
            self.x += max(-6, min(6, center - self.x))
            self.y += max(-3, min(3, 18 - self.y))
            return
        self.centering = False
        if not self._casting(now):
            left = config.GAME_AREA_LEFT + self.w / 2
            right = config.GAME_AREA_RIGHT - self.w / 2
            self.x += self.swim_direction * self.speed * 2.1
            if self.x >= right or self.x <= left:
                self.x = max(left, min(right, self.x))
                direction = -1 if self.x >= right else 1
                if direction != self.swim_direction:
                    self.swim_direction = direction
                    self.swim_turn_at = now
            target_y = 55 + 27 * math.sin((now - self.fight_start_time) * .002)
            self.y += max(-2, min(2, target_y - self.y))

    def should_attack(self, now):
        if self._casting(now) or not super().should_attack(now):
            return False
        if self._next_attack_skill() == 'whale_suction':
            return abs(self.x - self._center_x()) < 1 and abs(self.y - 18) < 1
        return True

    def _next_attack_skill(self):
        if self._pending_attack_skill is None and self._last_attack_skill is None:
            self._pending_attack_skill = self._choose_attack_skill(('tidal_crescent', 'rune_geyser', 'ancient_pearl'))
        return super()._next_attack_skill()

    def draw(self, surf, *, visual_scale=1):
        scale = surf.scale if isinstance(surf, RenderSurface) else 1
        height = max(1, round(self.h * scale * visual_scale))
        now = config.game_ticks()
        age = now - self.skill_started_at
        skill = self.current_skill if self._casting(now) or self.swallowing else ''
        if self.swallowing:
            self._draw_suction(surf, self.SUCTION_MS + age * 2)
        elif self.suction_active(now):
            self._draw_suction(surf, age)
        action, period = self.ANIMATION[skill]
        elapsed = max(0, age if skill else now - self.breath_start_time)
        tick = min(period - 1, elapsed) if self.swallowing else elapsed % period
        frame = tick * 8 // period
        atlas = image_asset('animations/bosses/anim_boss_ancient_whale.png')
        if atlas is None:
            art = image_asset(self.sprite_asset, (height, height))
            if art is None:
                super().draw(surf, visual_scale=visual_scale)
                return
        else:
            edge = atlas.get_width() // 8
            art = atlas.subsurface((frame * edge, action * edge, edge, edge))
            if edge != height:
                art = pygame.transform.smoothscale(art, (height, height))
        if skill == 'tidal_crescent' and self.swim_direction < 0:
            art = pygame.transform.flip(art, True, False)
        elif not skill:
            turn = min(1, max(0, (now - self.swim_turn_at) / 420))
            tilt = -7 * self.swim_direction * math.cos(math.pi * turn)
            art = pygame.transform.rotate(art, tilt)
        center = self.x, self.y + self.h / 2
        _blit(surf, art, center, tuple(side / scale for side in art.get_size()))
        if skill in ('whale_suction', 'whale_swallow'):
            mouth_y = self.y + self.h * .81
            for i in range(3):
                progress = (i / 3 - age / 520) % 1
                radius = self.h * (.035 + .115 * progress)
                points = [(self.x + radius * math.cos(a), mouth_y + radius * .46 * math.sin(a))
                          for a in (j * .30 + age * .009 for j in range(14))]
                Draw.lines(surf, (149, 244, 255), False, points, 2)
        elif skill:
            color = {'tidal_crescent': (77, 200, 250),
                     'rune_geyser': (131, 181, 255), 'ancient_pearl': (255, 220, 140)}[skill]
            pulse = .5 + .5 * math.sin(age * .012)
            mouth_offset = {'tidal_crescent': (.055 * self.swim_direction, .67),
                            'rune_geyser': (0, .56), 'ancient_pearl': (0, .73)}
            x, y = mouth_offset[skill]
            mouth = self.x + self.h * x, self.y + self.h * y
            Draw.circle(surf, color, mouth, max(3, round(self.h * (.04 + .075 * pulse))), 2)
            Draw.circle(surf, color, mouth, max(2, round(self.h * .02)))

    def _draw_suction(self, surf, age):
        mouth_y = self.y + self.h * .81
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        strength = min(1, age / 1200)
        layer = effect_layer(surf, (width, height))
        for i in range(8):
            angle = i * math.tau / 8
            dx, dy = width * math.cos(angle), height * math.sin(angle)
            phase = age * .006 + i * 1.8
            edges = [[], []]
            centerline = []
            for j in range(20):
                t = j / 19
                curl = .15 * t * math.sin(phase - 6 * t)
                x = self.x + dx * t - dy * curl
                y = mouth_y + dy * t + dx * curl
                centerline.append(pygame.Vector2(x, y))
                half = (4 + 13 * strength) * t
                for side, edge in zip((-1, 1), edges):
                    edge.append((x + side * half * math.sin(angle), y - side * half * math.cos(angle)))
            Draw.polygon(layer, (69, 189, 218, 39 + i % 3 * 10), edges[0] + edges[1][::-1])
            for offset in (0, .38, .76):
                travel = (offset + i * .23 - age / (1050 - strength * 290)) % 1
                position = travel * 19
                index = min(18, int(position))
                head = centerline[index].lerp(centerline[index + 1], position - index)
                trail = [head, *centerline[index + 1:min(20, index + 4)]]
                Draw.lines(layer, (163, 231, 244, round(100 + 60 * (1 - travel))),
                           False, trail, max(1, round(1 + travel)))
                Draw.circle(layer, (198, 243, 253, 125), head, max(2, round(4 * travel)), 1)
        blit_effect(surf, layer, (0, 0))
        draw_glow(surf, (round(self.x), round(mouth_y)), max(8, round(self.w * .24)), (104, 216, 237), 90)

    def _skill_shots(self, skill, player_x, player_y):
        if skill == 'whale_suction':
            self.suction_start_hp = self.hp
            return []
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        width = right - left
        bottom = config.GAME_AREA_BOTTOM
        origin_y = self.y + self.h * .7
        tier = self.bdef.get('campaign_tier', 1)
        if skill == 'tidal_crescent':
            shots = []
            lane_width = width / 4
            first_gap = random.choice((1, 2))
            for wave, delay in enumerate(range(0, 5000, 400)):
                gap = first_gap if wave // 3 % 2 == 0 else 3 - first_gap
                lanes = [lane for lane in range(4) if lane != gap]
                if wave % 2:
                    lanes.reverse()
                for order, lane in enumerate(lanes):
                    launch = delay + order * 110
                    if launch >= 5000:
                        break
                    shot = self._shot(skill, left + (lane + .5) * lane_width, -45,
                                      speed=11, warning_ms=launch, active_ms=1800)
                    shot.width = min(shot.width, lane_width * .97)
                    shots.append(shot)
            return shots
        if skill == 'rune_geyser':
            shots = []
            lanes = random.sample(range(6), 6)
            floor = config.SCREEN_HEIGHT
            height = floor - bottom * .26
            for wave in range(3):
                for lane in lanes[wave * 2:wave * 2 + 2]:
                    x = left + width * (lane + .5) / 6
                    shot = self._shot(skill, x, floor - height, warning_ms=800 + wave * 1100,
                                      active_ms=GEYSER_BREAK_MS + GEYSER_SHATTER_MS, damage=2)
                    shot.width = min(width * .23, 145 * self.size_scale)
                    shot.height = height
                    shots.append(shot)
            return shots
        aim = math.degrees(math.atan2(player_x - self.x, max(100, bottom - origin_y)))
        return [self._shot(skill, self.x, origin_y, angle=aim + a,
                           speed=(4.6 + tier * .2) * self.size_scale,
                           warning_ms=800, active_ms=120000)
                for a in (-48, 0, 48)]
