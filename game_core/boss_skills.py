"""Animated Web-only Boss attacks, with collision geometry shared by their art."""
import math
from functools import lru_cache

import pygame

from . import config
from .asset_loader import image_asset, scale_surface_cached
from .render import Draw, RenderSurface, blit_effect, effect_layer
from .sprites import blit_lit_sprite
from .visuals import draw_glow


CLAW_DROP_MS = 990
CLAW_DELAY_MS = 240

SIGNATURES = {
    'boss_lobster': ('赤钳合击', (255, 105, 78), 1, CLAW_DROP_MS + CLAW_DELAY_MS + 50),
    'boss_crab': ('潮汐横扫', (92, 221, 255), 1, 1260),
    'boss_octopus': ('墨涌陷阱', (192, 110, 255), 1, 2040),
    'boss_shark': ('猎潮突进', (87, 202, 255), 2, 1320),
    'boss_dragon': ('火龙突击', (255, 137, 61), 1, 4000),
    'boss': ('深渊封潮', (236, 115, 255), 2, 2120),
}
BOSS_COLORS = {key: values[1] for key, values in SIGNATURES.items()}
BOSS_COLORS.update(boss_niu=(255, 117, 50), boss_zongzong=(116, 237, 255))
TRIDENT_IMAGES = ('effects/boss_trident_gold.png', 'effects/boss_trident_red.png')
TRIDENT_INTERVAL_MS = 220
CRAB_BURST_IMAGE = 'effects/boss_crab_burst.png'
DRAGON_FIREBALL_IMAGE = 'effects/boss_dragon_fireball.png'
SKILL_IMAGES = ('effects/boss_bite.png', 'effects/boss_claw.png', *TRIDENT_IMAGES,
                CRAB_BURST_IMAGE, DRAGON_FIREBALL_IMAGE,
                'effects/bubble_crab.png', 'effects/bubble_crab_red.png')

LASH_MS = 680
CHASE_MS = 1322
BITE_REPEAT_MS = CHASE_MS + 2000
BITE_RETURN_MS = 600
CRAB_BUBBLE_BURST_MS = 860
CRAB_BUBBLE_COLORS = ((255, 99, 92), (255, 222, 88))


def _clamp(value, low, high):
    return max(low, min(high, value))


def circle_hits_rect(rect, x, y, radius):
    return math.hypot(x - _clamp(x, rect.left, rect.right),
                      y - _clamp(y, rect.top, rect.bottom)) <= radius


def _tentacle_hits_rect(rect, points):
    if any(circle_hits_rect(rect, *point) for point in points):
        return True
    for (x1, y1, width1), (x2, y2, width2) in zip(points, points[1:]):
        padding = 2 * int(min(width1, width2))
        if rect.inflate(padding, padding).clipline((round(x1), round(y1)), (round(x2), round(y2))):
            return True
    return False


def _ripples(surface, x, y, radius, color, phase):
    for i in range(2):
        r = max(2, round(radius * (.53 + .47 * ((phase + i / 2) % 1))))
        Draw.circle(surface, (*color, 175 - i * 58), (x, y), r, 2)
    for i in range(5):
        angle = i * math.tau / 5 + phase
        r = radius * (.68 + .25 * phase)
        Draw.circle(surface, (*color, 160), (x + math.cos(angle) * r, y + math.sin(angle) * r), 2)


class BossSignature:
    def __init__(self, boss, player, now, warning, *, campaign=False):
        self.key = boss.bdef['key']
        self.name, self.color, self.damage, duration = SIGNATURES[self.key]
        self.impact_at = now + warning
        self.end_at = self.impact_at + duration
        self.last_hit = -1
        self.origin = None
        self.chasing = False
        self.campaign = campaign
        self.left, self.right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        self.bottom = config.SCREEN_HEIGHT
        self.target_x = _clamp(player.x, self.left + 80, self.right - 80)
        self.target_y = _clamp(player.y, 100, self.bottom - 14)
        if campaign or self.key == 'boss':
            self.target_x, self.target_y = player.rect().center
        if self.key == 'boss':
            self.end_at = self.impact_at + BITE_REPEAT_MS + CHASE_MS + BITE_RETURN_MS
            self.second_target_x = None
        self.launch_y = max(32, round(boss.y + boss.h * .55))
        if campaign:
            self.launch_y = min(self.launch_y, self.target_y - 48)
        if self.key == 'boss_dragon':
            self.next_fireball_at = self.impact_at
        if self.key == 'boss_shark':
            self.trident_lanes = []
            self.trident_hits = set()
        if self.key == 'boss_crab':
            self.bubble_x = boss.x
            self.bubble_spacing = min(48, boss.w * .3)
            self.bubble_released = [False, False]
            self.bubble_crabs = [None, None]

    def stop(self, boss):
        if self.origin is not None:
            boss.x, boss.y = self.origin

    def move(self, boss, now, player=None):
        """Update timed throws and move the abyss boss during its chase."""
        age = now - self.impact_at
        if self.key == 'boss_shark' and len(self.trident_lanes) < 3:
            if age >= len(self.trident_lanes) * TRIDENT_INTERVAL_MS:
                x = player.rect().centerx if player is not None else self.target_x
                self.trident_lanes.append((age, x))
        if self.key != 'boss' or age < 0:
            return
        if self.origin is None:
            self.origin = (boss.x, boss.y)
        if age >= BITE_REPEAT_MS and self.second_target_x is None:
            self.second_target_x = player.rect().centerx if player is not None else self.target_x
        second = age >= BITE_REPEAT_MS
        rush_age = age - BITE_REPEAT_MS if second else age
        self.chasing = rush_age < CHASE_MS
        below = self.bottom + boss.h * .22 + 22
        if self.chasing:
            boss.x = (self.second_target_x if second else
                      self.origin[0] + (self.target_x - self.origin[0]) * rush_age / CHASE_MS)
            start_y, end_y = (below, self.origin[1]) if second else (self.origin[1], below)
            boss.y = start_y + (end_y - start_y) * rush_age / CHASE_MS
        elif second:
            t = _clamp((rush_age - CHASE_MS) / BITE_RETURN_MS, 0, 1)
            boss.y = self.origin[1]
            boss.x = self.second_target_x + (self.origin[0] - self.second_target_x) * t
        else:
            boss.x, boss.y = self.target_x, below

    def _claws(self, age):
        lanes = ((self.target_x - 46, self.target_x + 46) if self.campaign
                 else (self.left + 60, self.right - 60))
        claws = []
        for index, x in enumerate(lanes):
            t = _clamp((age - index * CLAW_DELAY_MS) / CLAW_DROP_MS, 0, 1)
            drop = self.launch_y + (self.bottom + 150 - self.launch_y) * t ** 1.25
            claws.append((x, drop, 39))
        return claws

    def _bubbles(self, age):
        t = _clamp(age / CRAB_BUBBLE_BURST_MS, 0, 1)
        y = self.launch_y + (self.bottom * .5 - self.launch_y) * t
        return [(self.bubble_x + side * self.bubble_spacing, y, 45) for side in (-1, 1)]

    def _tentacles(self, boss, age):
        progress = _clamp(age % LASH_MS / LASH_MS, 0, 1)
        lash = math.sin(math.pi * progress)
        for side in (-1, 1):
            start = (boss.x + side * boss.w * .32, boss.y + boss.h * .58)
            steps = 24
            reach = max(0, self.bottom - start[1])
            segment = reach / steps
            target_angle = math.atan2(self.target_y - start[1], self.target_x - start[0])
            angle = target_angle + side * .28 * math.sin(progress * math.tau)
            target_fraction = min(1, math.hypot(self.target_x - start[0], self.target_y - start[1])
                                  / max(1, reach))
            x, y = start
            points = [(x, y, 23)]
            for i in range(1, steps + 1):
                t = i / steps
                phase = (t - .5 / steps - target_fraction / 2) * math.tau
                wave = math.sin(phase - (progress - .5) * math.tau)
                tangent = angle + wave * (.46 + .10 * (1 - lash))
                x += math.cos(tangent) * segment
                y += math.sin(tangent) * segment
                points.append((x, y, max(3, 23 * (1 - t) ** .7)))
            yield points

    def _tridents(self, age):
        speed = max(.70, (self.bottom - self.launch_y + 100) / 780)
        return [(index, x, self.launch_y + (age - launch) * speed)
                for index, (launch, x) in enumerate(self.trident_lanes) if age >= launch]

    def hit(self, boss, rect, now):
        age = now - self.impact_at
        if age < 0 or now >= self.end_at:
            return False
        tick = 0
        if self.key == 'boss_lobster':
            hit = any(circle_hits_rect(rect, x, y, radius)
                      or rect.colliderect(pygame.Rect(round(x) - 10, round(y) - 95, 20, 60))
                      for index, (x, y, radius) in enumerate(self._claws(age))
                      if 110 <= age - index * CLAW_DELAY_MS < CLAW_DROP_MS)
        elif self.key == 'boss_crab':
            return False
        elif self.key == 'boss_octopus':
            tick = age // LASH_MS
            if not 150 <= age % LASH_MS < 475:
                return False
            hit = tick != self.last_hit and any(
                _tentacle_hits_rect(rect, points) for points in self._tentacles(boss, age))
        elif self.key == 'boss_shark':
            for index, x, y in self._tridents(age):
                if index in self.trident_hits:
                    continue
                shaft = pygame.Rect(round(x) - 5, round(y) - 53, 11, 80)
                if rect.colliderect(shaft) or circle_hits_rect(rect, x, y + 21, 20):
                    self.trident_hits.add(index)
                    return True
            return False
        elif self.key == 'boss_dragon':
            return False
        else:
            if not self.chasing:
                return False
            tick = int(age >= BITE_REPEAT_MS)
            hit = circle_hits_rect(rect, boss.x, boss.y + boss.h * .80, boss.w * .28)
        if tick != self.last_hit and hit:
            self.last_hit = tick
            return True
        return False

    def draw(self, surface, boss, now):
        age = now - self.impact_at
        phase = (now % 570) / 570
        if self.key == 'boss_lobster':
            for i, (x, y, radius) in enumerate(self._claws(age)):
                if age < 0:
                    _draw_drop_warning(surface, x, y, self.bottom, self.color)
                _draw_claw(surface, x, y, i)
        elif self.key == 'boss_crab':
            if age >= 0:
                for i, ((x, y, radius), color) in enumerate(zip(self._bubbles(age), CRAB_BUBBLE_COLORS)):
                    if age < CRAB_BUBBLE_BURST_MS and not self.bubble_released[i]:
                        _draw_bubble(surface, x, y, radius, now, color)
                        draw_bubble_crab(surface, x, y, radius, color, now)
                    elif self.bubble_released[i] and age < CRAB_BUBBLE_BURST_MS + 180:
                        burst = image_asset(CRAB_BURST_IMAGE)
                        if burst is not None:
                            size = round(radius * 2 + (age - CRAB_BUBBLE_BURST_MS) / 6)
                            _blit_art(surface, burst, (x - size / 2, y - size / 2), (size, size))
        elif self.key == 'boss_octopus':
            for tentacle in self._tentacles(boss, max(0, age)):
                _draw_tentacle(surface, tentacle)
            if age < 0:
                for side in (-1, 1):
                    _ripples(surface, boss.x + side * boss.w * .32, self.bottom - 16, 24, self.color, phase)
        elif self.key == 'boss_shark':
            for index, x, y in self._tridents(age):
                _draw_trident(surface, x, y, index == 1)
        elif self.key == 'boss_dragon':
            if age >= 0:
                x, y = boss.x, boss.y + boss.h * .65
                flash_age = now - self.next_fireball_at + 400
                flash = 1 - _clamp(flash_age / 100, 0, 1)
                draw_glow(surface, (round(x), round(y + 4)), round(10 + 10 * flash),
                          (255, 132, 60), round(55 + 145 * flash))
                if flash > 0:
                    Draw.circle(surface, (255, 225, 156), (round(x), round(y + 4)), round(2 + 2 * flash))
        elif age < 0:
            _ripples(surface, boss.x, boss.y + boss.h * .8, boss.w * .30, self.color, phase)
        elif self.chasing:
            for side in (-1, 1):
                x = boss.x + side * boss.w * .62
                y = boss.y + boss.h * .22
                for i in range(4):
                    travel = (phase + i / 4) % 1
                    dx, dy = side * 18 * travel, -40 * travel
                    origin = x + dx, y + dy
                    Draw.polygon(surface, (106, 172, 198),
                                 (origin, (origin[0] + side * 8, origin[1] - 3),
                                  (origin[0] + side * 18, origin[1] - 24)))

    def draw_bite(self, surface, boss):
        if not self.chasing:
            return False
        image = image_asset('effects/boss_bite.png', (round(boss.w * 1.47), round(boss.h * 1.45)))
        if image is None:
            return False
        blit_lit_sprite(surface, image, (boss.x - image.get_width() / 2,
                                        boss.y - boss.h * .22), (130, 189, 207), 84,
                        source='effects/boss_bite.png')
        return True


@lru_cache(maxsize=2)
def _claw_image(image, side):
    return pygame.transform.flip(image, not side, False)


def _draw_claw(surface, x, y, side):
    image = image_asset('effects/boss_claw.png')
    if image is not None:
        image = _claw_image(image, side)
        Draw.line(surface, (255, 132, 113, 195), (x, y - 109), (x, y - 37), 4)
        Draw.line(surface, (255, 90, 75, 130), (x - 8, y - 94), (x - 8, y - 46), 2)
        _blit_art(surface, image, (round(x - 103 / 2), round(y - 145 + 24)), (103, 145))
        return
    # Procedural fallback preserves the pincer silhouette if image assets are disabled.
    Draw.ellipse(surface, (111, 29, 25), (x - 20, y - 95, 40, 68))
    Draw.ellipse(surface, (204, 61, 38), (x - 38, y - 49, 76, 56))
    for sign in (-1, 1):
        Draw.polygon(surface, (177, 46, 32),
                     ((x + sign * 10, y - 15), (x + sign * 38, y - 28),
                      (x + sign * 39, y + 9), (x + sign * 14, y + 25),
                      (x + sign * 21, y + 4)))
        Draw.line(surface, (250, 129, 65), (x + sign * 36, y - 20),
                  (x + sign * 37, y + 8), 3)


@lru_cache(maxsize=16)
def _tinted_crab(image, red):
    if not red:
        return image
    tinted = image.copy()
    tinted.fill((255, 115, 195, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


def draw_bubble_crab(surface, x, y, size, color, now):
    red = color == CRAB_BUBBLE_COLORS[0]
    red_image = image_asset('effects/bubble_crab_red.png') if red else None
    image = red_image or image_asset('effects/bubble_crab.png')
    if image is not None:
        width = round(size * 1.35)
        height = round(width * image.get_height() / image.get_width())
        bob = math.sin(now * .018) * 2
        _blit_art(surface, _tinted_crab(image, red and red_image is None),
                  (round(x - width / 2), round(y - height / 2 + bob)), (width, height))
        return
    r = size * .32
    for side in (-1, 1):
        for i in range(3):
            step = math.sin(now * .018 + i * 2 + side) * .20
            foot = (x + side * r * (1.1 + i * .22), y + r * (.95 - i * .23 + step))
            Draw.line(surface, color, (x + side * r * .58, y + r * .34), foot, 2)
        cx = x + side * r * 1.14
        Draw.line(surface, color, (x, y), (cx, y - r * .42), 3)
        Draw.polygon(surface, color, ((cx, y - r * .16), (cx - r * .36, y - r * .48),
                                     (cx - r * .30, y - r * .94), (cx, y - r * .65),
                                     (cx + r * .30, y - r * .94), (cx + r * .36, y - r * .48)))
    body = (x - r, y - r * .48, r * 2, r * 1.13)
    Draw.ellipse(surface, (74, 32, 38), body)
    Draw.ellipse(surface, color, (body[0] + 2, body[1] + 2, body[2] - 4, body[3] - 4))
    for side in (-1, 1):
        Draw.circle(surface, (55, 28, 38), (x + side * r * .34, y - r * .23), 2)


def _draw_bubble(surface, x, y, radius, now, tint):
    name = 'rose' if tint == CRAB_BUBBLE_COLORS[0] else 'gold'
    source = image_asset(f'effects/orochi_bubble_{name}.png')
    diameter = round(radius * 2)
    if source is not None:
        _blit_art(surface, _bubble_shell(source), (round(x - radius), round(y - radius)), (diameter, diameter))
    else:
        Draw.circle(surface, tint, (round(x), round(y)), round(radius), 2)


@lru_cache(maxsize=4)
def _bubble_shell(source):
    shell = source.copy()
    shell.set_alpha(145)
    return shell


def _draw_drop_warning(surface, x, y, bottom, color):
    height = round(bottom - y)
    if height <= 0:
        return
    lane = effect_layer(surface, (18, height))
    Draw.polygon(lane, (*color, 46), ((9, 0), (18, height), (0, height)))
    Draw.line(lane, (*color, 135), (9, 0), (9, height), 1)
    blit_effect(surface, lane, (round(x - 9), round(y)))


def _draw_tentacle(surface, points):
    left, right = [], []
    for i, (x, y, width) in enumerate(points):
        if i == 0:
            width *= .55
        a = points[max(0, i - 1)]
        b = points[min(len(points) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        distance = max(1, math.hypot(dx, dy))
        nx, ny = dy / distance, -dx / distance
        left.append((x + nx * width, y + ny * width))
        right.append((x - nx * width, y - ny * width))
    outline = left + right[::-1]
    Draw.polygon(surface, (94, 39, 116), outline)
    for fraction, color in ((.78, (135, 62, 151)), (.48, (166, 83, 165)),
                            (.24, (195, 113, 182))):
        edge = [(x + (lx - x) * fraction, y + (ly - y) * fraction)
                for (x, y, _), (lx, ly) in zip(points, left)]
        inner = [(x + (rx - x) * fraction * .22, y + (ry - y) * fraction * .22)
                 for (x, y, _), (rx, ry) in zip(points, right)]
        Draw.polygon(surface, color, edge + inner[::-1])
    Draw.lines(surface, (54, 24, 72), True, outline, 2)
    for i in range(2, len(points) - 2, 2):
        x, y, width = points[i]
        rx, ry = right[i]
        x, y = (x + rx) / 2, (y + ry) / 2
        r = max(2, width * .28)
        Draw.ellipse(surface, (232, 148, 201), (x - r, y - r * .8, 2 * r, 1.6 * r))
        Draw.ellipse(surface, (124, 49, 128), (x - r * .54, y - r * .37, r * 1.08, r * .74))


@lru_cache(maxsize=2)
def _crop_trident(image):
    bounds = image.get_bounding_rect(min_alpha=16)
    if not bounds:
        return None
    return image.subsurface(bounds)


def _trident_image(red):
    source = image_asset(TRIDENT_IMAGES[red])
    return _crop_trident(source) if source is not None else None


def _draw_trident(surface, x, y, red):
    metal = (251, 89, 74) if red else (255, 208, 66)
    image = _trident_image(red)
    if image is not None:
        width = _clamp(round(image.get_width() * 100 / image.get_height()), 35, 52)
        left = round(x - width / 2)
        top = round(y + 37 - 100)
        _draw_drop_warning(surface, x, top - 28, top + 4, metal)
        _blit_art(surface, image, (left, top), (width, 100))
        return
    shadow = (116, 33, 35) if red else (153, 96, 25)
    Draw.line(surface, shadow, (x, y - 53), (x, y + 27), 11)
    Draw.line(surface, metal, (x, y - 54), (x, y + 27), 5)
    Draw.lines(surface, shadow, False,
               ((x - 19, y + 22), (x - 19, y + 1), (x + 19, y + 1), (x + 19, y + 22)), 8)
    for offset, length in ((-19, 22), (0, 37), (19, 22)):
        tip = (x + offset, y + length)
        Draw.polygon(surface, metal, ((x + offset - 6, y + 10), tip, (x + offset + 6, y + 10)))
        Draw.line(surface, (255, 245, 199), (x + offset, y + 8), tip, 1)
    Draw.line(surface, (*metal, 110), (x, y - 45), (x, y - 64), 3)


def _blit_art(surface, image, position, size):
    if isinstance(surface, RenderSurface):
        surface.blit(image, position, static=True, logical_size=size)
    else:
        surface.blit(scale_surface_cached(image, size), position)
