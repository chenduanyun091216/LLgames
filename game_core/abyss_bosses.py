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
from .render import Draw, RenderSurface


ABYSS_PROJECTILE_FIELDS = (
    'skill', 'warning_ms', 'active_ms', 'origin_x', 'origin_y', 'last_update',
    'width', 'height', 'ring_radius', 'ring_speed', 'ring_thickness',
    'gap_angle', 'gap_degrees', 'visual_scale', 'whip_directions', 'missile_pass', 'unblockable',
    'persistent', 'self_telegraphed',
)
EFFECT_ASSETS = {
    'plasma_rail': 'effects/mecha_plasma_rail.png',
    'guided_missile': 'effects/mecha_guided_missile.png',
    'emp_ring': 'effects/mecha_emp_ring.png',
    'molten_burst': 'effects/mecha_molten_burst.png',
    'sonar_ring': 'effects/whale_sonar_ring.png',
    'tidal_crescent': 'effects/whale_tidal_crescent.png',
    'rune_geyser': 'effects/whale_rune_geyser.png',
    'ancient_pearl': 'effects/whale_ancient_pearl.png',
}
RINGS = ('emp_ring', 'sonar_ring')
LANES = ('plasma_rail', 'rune_geyser')
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
        self.r = {'guided_missile': 14, 'molten_burst': 30, 'emp_ring': 29}.get(skill, 12) * scale
        self.width = (96 if skill == 'tidal_crescent' else 54) * scale
        self.height = 28 * scale
        self.ring_radius = 0.0
        self.ring_speed = (150 if skill == 'emp_ring' else 170) * scale
        self.ring_thickness = 13 * scale
        self.gap_angle = 0.0
        self.gap_degrees = 76.0 if skill == 'sonar_ring' else 0.0
        self.whip_directions = random.randrange(8) if skill == 'plasma_rail' else 0
        self.missile_pass = 0
        self.missile_turn_rate = 150
        self.unblockable = skill in RINGS + LANES or skill == 'guided_missile'
        self.persistent = self.unblockable
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
        elif self.skill in RINGS:
            self.ring_radius = 24 * self.visual_scale + active_age / 1000 * self.ring_speed
            # A newborn PNG ring is thinner than a mature one. Keep its damage
            # band within the luminous core; large rings keep the original cap.
            self.ring_thickness = min(13 * self.visual_scale, self.ring_radius * .06)
        elif self.skill == 'guided_missile':
            self._update_missile(dt, target_x, target_y)
        elif self.skill not in LANES:
            rad = math.radians(self.angle)
            self.x += math.sin(rad) * self.speed * 60 * dt
            self.y += math.cos(rad) * self.speed * 60 * dt
            if (self.y > config.SCREEN_HEIGHT + 100 or self.y < -100
                    or self.x < config.GAME_AREA_LEFT - 100 or self.x > config.GAME_AREA_RIGHT + 100):
                self.alive = False

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
            dx = 0 if target_x is None else target_x - self.x
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
        return self.r * (.6 if self._active_age() >= EMP_BURST_AT_MS else 1)

    def bounds(self):
        if self.skill == 'plasma_rail':
            points = self._rail_points()
            xs, ys = zip(*points)
            pad = self.width / 2
            return pygame.Rect(math.floor(min(xs) - pad), math.floor(self.y - pad),
                               math.ceil(max(xs) - min(xs) + self.width + 2),
                               math.ceil(max(ys) - self.y + self.width + 2))
        if self.skill in LANES:
            return pygame.Rect(round(self.x - self.width / 2), round(self.y),
                               round(self.width), round(self.height))
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
        if self.skill in LANES or self.skill == 'tidal_crescent':
            return True
        nearest_x = max(rect.left, min(self.x, rect.right))
        nearest_y = max(rect.top, min(self.y, rect.bottom))
        nearest = math.hypot(nearest_x - self.x, nearest_y - self.y)
        if self.skill not in RINGS:
            return nearest <= self.r
        outer = self.ring_radius + self.ring_thickness / 2
        inner = max(0, self.ring_radius - self.ring_thickness / 2)
        corners = (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright)
        farthest = max(math.hypot(x - self.x, y - self.y) for x, y in corners)
        if nearest > outer or farthest < inner:
            return False
        if self.gap_degrees:
            # The full rectangle must fit in the indicated safe sector. A small
            # conservative margin avoids invisible slivers at the sector edge.
            angles = [((math.degrees(math.atan2(x - self.x, y - self.y))
                        - self.gap_angle + 180) % 360 - 180) for x, y in corners]
            if all(abs(a) < self.gap_degrees / 2 for a in angles):
                return False
        return True

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
            Draw.circle(surf, (30, 48, 65), grip, max(4, round(self.width * .55)))
            Draw.circle(surf, color, grip, max(2, round(self.width * .25)))
            if active and self._active_age() > 0:
                points = self._rail_points()
                striking = self._rail_lash(self._active_age()) is not None
                width = self.width if striking else self.width * .64
                core = (235, 255, 255) if striking else (136, 210, 242)
                Draw.lines(surf, (34, 104, 200), False, points, round(width))
                Draw.lines(surf, color, False, points, max(1, round(width * .68)))
                Draw.lines(surf, core, False, points, max(1, round(width * .24)))
                Draw.circle(surf, core, points[-1], max(2, round(width * .19)))
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
        image = image_asset(EFFECT_ASSETS[self.skill])
        if not active:
            # Exact lane footprints and ring safe corridors are gameplay UI,
            # rather than generated effect artwork.
            if self.skill in FACTORY_SKILLS:
                if image is not None and self.skill == 'guided_missile' and self.missile_pass == 2:
                    preview, size, center = self._missile_art(image.copy())
                    preview.set_alpha(115)
                    _blit(surf, preview, center, size)
                return
            if self.skill in LANES:
                Draw.rect(surf, color, self.bounds(), 2)
                Draw.line(surf, color, (self.x, self.y), (self.x, self.y + self.height), 1)
            elif self.skill in RINGS:
                radius = 36 * self.visual_scale
                Draw.circle(surf, color, (round(self.x), round(self.y)), max(1, round(radius)), 2)
                if self.gap_degrees:
                    for a in (self.gap_angle - self.gap_degrees / 2, self.gap_angle + self.gap_degrees / 2):
                        rad = math.radians(a)
                        Draw.line(surf, (150, 255, 190), (self.x, self.y),
                                  (self.x + math.sin(rad) * 1200, self.y + math.cos(rad) * 1200), 2)
            else:
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
        if image is None:
            if self.skill in RINGS:
                # Missing-art fallback still preserves the gap.
                for a in range(0, 360, 4):
                    if abs((a - self.gap_angle + 180) % 360 - 180) < self.gap_degrees / 2:
                        continue
                    rad = math.radians(a)
                    Draw.circle(surf, color, (round(self.x + math.sin(rad) * self.ring_radius),
                                round(self.y + math.cos(rad) * self.ring_radius)), max(1, round(self.ring_thickness / 2)))
            else:
                Draw.rect(surf, color, self.bounds(), 2)
            return
        if self.skill in RINGS:
            if self.gap_degrees:
                image = image.copy()
                cx, cy = image.get_width() / 2, image.get_height() / 2
                radius = max(image.get_size()) * 2
                points = [(cx, cy)] + [(cx + math.sin(math.radians(a)) * radius,
                           cy + math.cos(math.radians(a)) * radius) for a in
                           range(round(self.gap_angle - self.gap_degrees / 2),
                                 round(self.gap_angle + self.gap_degrees / 2) + 1, 1)]
                pygame.draw.polygon(image, (0, 0, 0, 0), points)
            # Measured luminous-band centroids of the final 512px PNGs.
            # Align the artwork's annulus to the collision radius, rather than
            # scaling its transparent/glow border as though it were the band.
            # The hit band remains conservatively narrower than the glow.
            size = (self.ring_radius / .4232,) * 2
            center = (self.x, self.y)
        elif self.skill in LANES:
            size = (self.width * 1.35, self.height)
            center = (self.x, self.y + self.height / 2)
        elif self.skill == 'guided_missile':
            image, size, center = self._missile_art(image)
        elif self.skill == 'tidal_crescent':
            size, center = (self.width * 1.15, self.height * 2.2), (self.x, self.y)
        else:
            size, center = (self.r * 3, self.r * 3), (self.x, self.y)
            if self.angle:
                image = pygame.transform.rotate(image, self.angle)
        _blit(surf, image, center, size)


class AbyssBoss(Boss):
    SKILLS = ()

    def __init__(self, bdef, difficulty):
        super().__init__(bdef, difficulty)
        self.skill_index = 0
        self.current_skill = ''
        self.skill_started_at = 0
        self.signature_opening_pending = False
        self.self_telegraphed = True
        self.sprite_asset = 'bosses/' + bdef['key'] + '.png'

    def can_laser(self):
        return False

    def should_attack(self, now):
        # No generic acceleration or random attacks: these four moves are the
        # entire repertoire. The interval includes warning and recovery time.
        return self.hp > 0 and self.entered and now - self.last_attack_time >= self.attack_interval

    def attack(self, now, player_x, player_y=None):
        if self.hp <= 0:
            return []
        self.last_attack_time = self.skill_started_at = now
        self.current_skill = self.SKILLS[self.skill_index % 4]
        self.skill_index += 1
        shots = self._skill_shots(self.current_skill, player_x, player_y)
        for shot in shots:
            shot.spawn_time = shot.last_update = now
        return shots

    def _shot(self, skill, x, y, **kwargs):
        return AbyssProjectile(skill, x, y, scale=self.size_scale, **kwargs)

    def draw(self, surf):
        art = image_asset(self.sprite_asset)
        if art is None:
            super().draw(surf)
            return
        pulse = 1 + .018 * math.sin((config.game_ticks() - self.breath_start_time) * .003)
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

    def draw(self, surf):
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
            super().draw(surf)
            return
        _blit(surf, sprite, (self.x, self.y + self.h / 2 + y_offset),
              (self.w / stretch, self.h * stretch))

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
            return [self._shot(skill, self.x + a * self.size_scale, origin_y, angle=a,
                               speed=4.5 + tier * .25,
                               warning_ms=MISSILE_WINDUP_MS + i * MISSILE_LAUNCH_GAP_MS, active_ms=20000)
                    for i, a in enumerate((-32, 0, 32))]
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
    SKILLS = ('sonar_ring', 'tidal_crescent', 'rune_geyser', 'ancient_pearl')

    def _skill_shots(self, skill, player_x, player_y):
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        width = right - left
        origin_y = self.y + self.h * .7
        tier = self.bdef.get('campaign_tier', 1)
        if skill == 'sonar_ring':
            shots = [self._shot(skill, self.x, origin_y, warning_ms=1400 + i * 700,
                                active_ms=6500) for i in range(2)]
            for shot in shots:
                shot.gap_angle = max(-35, min(35, math.degrees(math.atan2(
                    player_x - self.x, max(120, config.GAME_AREA_BOTTOM - origin_y)))))
            return shots
        if skill == 'tidal_crescent':
            return [self._shot(skill, left + width * fraction, origin_y,
                               speed=(2.9 + tier * .2) * self.size_scale,
                               warning_ms=1100 + i * 380, active_ms=6500)
                    for i, fraction in enumerate((.2, .8, .35, .65))]
        if skill == 'rune_geyser':
            # Alternating lanes always leave half the arena open; no retargeting.
            shots = []
            for i, fraction in enumerate((.18, .5, .82)):
                shot = self._shot(skill, left + width * fraction, origin_y,
                                  warning_ms=1550 + i * 220, active_ms=750, damage=2)
                shot.width = min(width * .12, 74 * self.size_scale)
                shot.height = max(0, config.GAME_AREA_BOTTOM - origin_y)
                shots.append(shot)
            return shots
        aim = math.degrees(math.atan2(player_x - self.x, max(100, config.GAME_AREA_BOTTOM - origin_y)))
        return [self._shot(skill, self.x, origin_y, angle=aim + a,
                           speed=(2.8 + tier * .2 + wave * .25) * self.size_scale,
                           warning_ms=1100 + wave * 380, active_ms=6500)
                for wave in range(3) for a in (-28, 0, 28)]
