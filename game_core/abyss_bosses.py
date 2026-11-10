"""Shared factory/temple boss rules, including collision and telegraphs.

PC, browser and authoritative multiplayer use these exact objects.  Network
adapters may serialize ABYSS_PROJECTILE_FIELDS, but must not reimplement damage.
Angles use the game's convention: zero points down, positive points right.
"""
import math
import pygame

from . import config
from .asset_loader import image_asset
from .entities import Boss, BossProjectile
from .render import Draw, RenderSurface


ABYSS_PROJECTILE_FIELDS = (
    'skill', 'warning_ms', 'active_ms', 'origin_x', 'origin_y', 'last_update',
    'width', 'height', 'ring_radius', 'ring_speed', 'ring_thickness',
    'gap_angle', 'gap_degrees', 'visual_scale', 'turn_until', 'unblockable',
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

    Rings/lanes are unblocked environmental hazards; other shots can be blocked
    by every normal defensive weapon. Area hazards persist and hit each player at most once; shots vanish on contact.
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
        self.r = (14 if skill == 'guided_missile' else 12) * scale
        self.width = (96 if skill == 'tidal_crescent' else 54) * scale
        self.height = 28 * scale
        self.ring_radius = 0.0
        self.ring_speed = (150 if skill == 'emp_ring' else 170) * scale
        self.ring_thickness = 13 * scale
        self.gap_angle = 0.0
        self.gap_degrees = 76.0 if skill == 'sonar_ring' else 0.0
        self.turn_until = 650
        self.unblockable = skill in RINGS + LANES
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
        self.last_update = now
        if not self.is_active(now):
            return
        active_age = age - self.warning_ms
        if self.skill in RINGS:
            self.ring_radius = 24 * self.visual_scale + active_age / 1000 * self.ring_speed
            # A newborn PNG ring is thinner than a mature one. Keep its damage
            # band within the luminous core; large rings keep the original cap.
            self.ring_thickness = min(13 * self.visual_scale, self.ring_radius * .06)
        elif self.skill not in LANES:
            if self.skill == 'guided_missile' and active_age < self.turn_until and target_x is not None:
                desired = math.degrees(math.atan2(target_x - self.x,
                           max(90, (target_y if target_y is not None else config.GAME_AREA_BOTTOM) - self.y)))
                delta = (desired - self.angle + 180) % 360 - 180
                self.angle += max(-38 * dt, min(38 * dt, delta))
            rad = math.radians(self.angle)
            self.x += math.sin(rad) * self.speed * 60 * dt
            self.y += math.cos(rad) * self.speed * 60 * dt
            if (self.y > config.SCREEN_HEIGHT + 100 or self.y < -100
                    or self.x < config.GAME_AREA_LEFT - 100 or self.x > config.GAME_AREA_RIGHT + 100):
                self.alive = False

    def bounds(self):
        if self.skill in LANES:
            return pygame.Rect(round(self.x - self.width / 2), round(self.y),
                               round(self.width), round(self.height))
        if self.skill in RINGS:
            radius = self.ring_radius + self.ring_thickness / 2
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
        image = image_asset(EFFECT_ASSETS[self.skill])
        if not active:
            # Exact lane footprints and ring safe corridors are gameplay UI,
            # rather than generated effect artwork.
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
            source_band_fraction = .4393 if self.skill == 'emp_ring' else .4232
            size = (self.ring_radius / source_band_fraction,) * 2
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
    SKILLS = ('plasma_rail', 'guided_missile', 'emp_ring', 'molten_burst')

    def _skill_shots(self, skill, player_x, player_y):
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        origin_y = self.y + self.h * .75
        tier = self.bdef.get('campaign_tier', 1)
        if skill == 'plasma_rail':
            shot = self._shot(skill, max(left + 40, min(right - 40, player_x)), origin_y,
                              warning_ms=1400, active_ms=700, damage=2)
            shot.width = min((right - left) * .13, 68 * self.size_scale)
            shot.height = max(0, config.GAME_AREA_BOTTOM - origin_y)
            return [shot]
        if skill == 'guided_missile':
            return [self._shot(skill, self.x + a * self.size_scale, origin_y, angle=a,
                               speed=(2.6 + tier * .2) * self.size_scale,
                               warning_ms=1050 + i * 100, active_ms=6500)
                    for i, a in enumerate((-32, 0, 32))]
        if skill == 'emp_ring':
            y = config.GAME_AREA_BOTTOM * .65
            return [self._shot(skill, left + (right - left) * fraction, y,
                               warning_ms=1500 + i * 350, active_ms=1300)
                    for i, fraction in enumerate((.28, .72))]
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
