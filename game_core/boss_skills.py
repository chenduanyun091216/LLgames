"""Animated Web-only Boss attacks, with collision geometry shared by their art."""
import math
import random
from functools import lru_cache

import pygame

from . import config
from .asset_loader import image_asset
from .render import Draw, RenderSurface
from .sprites import blit_lit_sprite


SIGNATURES = {
    'boss_lobster': ('赤钳合击', (255, 105, 78), 1, 1040),
    'boss_crab': ('潮汐横扫', (92, 221, 255), 1, 1260),
    'boss_octopus': ('墨涌陷阱', (192, 110, 255), 1, 2040),
    'boss_shark': ('猎潮突进', (87, 202, 255), 2, 880),
    'boss_dragon': ('火龙突击', (255, 137, 61), 1, 4000),
    'boss': ('深渊封潮', (236, 115, 255), 2, 2120),
}
BOSS_COLORS = {key: values[1] for key, values in SIGNATURES.items()}
BOSS_COLORS.update(boss_niu=(255, 117, 50), boss_zongzong=(116, 237, 255))
TRIDENT_IMAGES = ('effects/boss_trident_gold.png', 'effects/boss_trident_red.png')
SKILL_IMAGES = ('effects/boss_bite.png', 'effects/boss_claw.png', 'effects/boss_ground_fire.png', *TRIDENT_IMAGES)

LASH_MS = 680
CHASE_MS = 1520
BUBBLE_BLAST_RADIUS = 105


def _clamp(value, low, high):
    return max(low, min(high, value))


def _circle_hit(rect, x, y, radius):
    return math.hypot(x - _clamp(x, rect.left, rect.right),
                      y - _clamp(y, rect.top, rect.bottom)) <= radius


def _ripples(surface, x, y, radius, color, phase):
    for i in range(2):
        r = max(2, round(radius * (.53 + .47 * ((phase + i / 2) % 1))))
        Draw.circle(surface, (*color, 175 - i * 58), (x, y), r, 2)
    for i in range(5):
        angle = i * math.tau / 5 + phase
        r = radius * (.68 + .25 * phase)
        Draw.circle(surface, (*color, 160), (x + math.cos(angle) * r, y + math.sin(angle) * r), 2)


class BossSignature:
    def __init__(self, boss, player, now, warning):
        self.key = boss.bdef['key']
        self.name, self.color, self.damage, duration = SIGNATURES[self.key]
        self.impact_at = now + warning
        self.end_at = self.impact_at + duration
        self.last_hit = -1
        self.origin = None
        self.chasing = False
        self.left, self.right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT
        self.bottom = config.SCREEN_HEIGHT
        width = self.right - self.left
        self.target_x = _clamp(player.x, self.left + 80, self.right - 80)
        self.target_y = _clamp(player.y, 100, self.bottom - 14)
        self.launch_y = max(32, round(boss.y + boss.h * .55))
        if self.key == 'boss_dragon':
            self.fire_patches = [(self.left + width * (i + random.uniform(.31, .69)) / 3,
                                  self.bottom * random.uniform(.42, .80), min(51, width * .11))
                                 for i in range(3)]

    def stop(self, boss):
        if self.origin is not None:
            boss.x, boss.y = self.origin

    def move(self, boss, now):
        """Only the chase takes over the Boss's actual position."""
        age = now - self.impact_at
        if self.key != 'boss' or age < 0:
            return
        if self.origin is None:
            self.origin = (boss.x, boss.y)
        self.chasing = age < CHASE_MS
        if self.chasing:
            if age < 340:
                boss.x = _clamp(boss.x + _clamp(self.target_x - boss.x, -4.8, 4.8),
                                self.left + boss.w / 2, self.right - boss.w / 2)
            start_y = self.origin[1]
            exit_y = self.bottom + boss.h * .30 + 22
            boss.y = start_y + (exit_y - start_y) * age / CHASE_MS
        else:
            return_ms = self.end_at - self.impact_at - CHASE_MS
            t = _clamp((age - CHASE_MS) / return_ms, 0, 1)
            boss.x, patrol_y = self.origin
            above = -boss.h - 20
            boss.y = above + (patrol_y - above) * t

    def _claws(self, age):
        t = _clamp(age / 990, 0, 1)
        drop = self.launch_y + (self.bottom + 150 - self.launch_y) * t ** 1.25
        return [(x, drop, 39) for x in (self.left + 60, self.right - 60)]

    def _bubbles(self, age):
        t = _clamp(age / 860, 0, 1)
        middle = (self.left + self.right) / 2
        return [(x + (middle - x) * t, self.target_y + side * math.sin(t * math.pi) * 17, 45)
                for x, side in ((self.left, -1), (self.right, 1))]

    def _tentacles(self, boss, age):
        progress = _clamp(age % LASH_MS / LASH_MS, 0, 1)
        lash = math.sin(math.pi * progress)
        for side in (-1, 1):
            start = (boss.x + side * boss.w * .32, boss.y + boss.h * .58)
            tip_y = start[1] + (self.bottom + 7 - start[1]) * lash
            points = []
            for i in range(13):
                t = i / 12
                curve = math.sin(t * math.tau - progress * 6) * 15 * math.sin(math.pi * t)
                x = start[0] + curve
                y = start[1] + (tip_y - start[1]) * t
                points.append((x, y, max(3, 23 * (1 - t) ** .7)))
            yield points

    def _tridents(self, age):
        y = self.launch_y + max(0, age) * max(.70, (self.bottom - self.launch_y + 100) / 780)
        return [(self.target_x + offset, y - (52 if offset else 0), 12) for offset in (-55, 0, 55)]

    def hit(self, boss, rect, now):
        age = now - self.impact_at
        if age < 0 or now >= self.end_at:
            return False
        tick = 0
        if self.key == 'boss_lobster':
            if not 110 <= age < 990:
                return False
            shapes = self._claws(age)
        elif self.key == 'boss_crab':
            if not 860 <= age < 1100:
                return False
            shapes = [((self.left + self.right) / 2, self.target_y, BUBBLE_BLAST_RADIUS)]
        elif self.key == 'boss_octopus':
            tick = age // LASH_MS
            if not 150 <= age % LASH_MS < 475:
                return False
            shapes = [point for tentacle in self._tentacles(boss, age) for point in tentacle]
        elif self.key == 'boss_shark':
            shapes = [(x, y + 17, radius + 4) for x, y, radius in self._tridents(age) if y >= self.launch_y]
        elif self.key == 'boss_dragon':
            if self.last_hit >= 0 and now - self.last_hit < 1000:
                return False
            tick = now
            shapes = self.fire_patches
        else:
            if not self.chasing:
                return False
            shapes = [(boss.x, boss.y + boss.h * .80, boss.w * .28)]
        if tick != self.last_hit and any(_circle_hit(rect, *shape) for shape in shapes):
            self.last_hit = tick
            return True
        return False

    def draw(self, surface, boss, now):
        age = now - self.impact_at
        phase = (now % 570) / 570
        if self.key == 'boss_lobster':
            for i, (x, y, radius) in enumerate(self._claws(age)):
                if age < 0:
                    Draw.line(surface, (*self.color, 95), (x, y), (x, self.bottom), 1)
                _draw_claw(surface, x, y, i)
        elif self.key == 'boss_crab':
            if age < 860:
                for i, (x, y, radius) in enumerate(self._bubbles(age)):
                    color = (255, 99, 92) if i == 0 else (255, 222, 88)
                    _draw_bubble(surface, x, y, radius, now, color)
            else:
                x = (self.left + self.right) / 2
                spread = _clamp((age - 860) / 400, 0, 1)
                _ripples(surface, x, self.target_y, BUBBLE_BLAST_RADIUS, self.color, spread)
                for i in range(22):
                    angle = i * math.tau / 22
                    px = x + math.cos(angle) * (30 + 111 * spread)
                    py = self.target_y + math.sin(angle) * (30 + 93 * spread)
                    tint = (255, 112, 94) if i % 2 else (255, 227, 113)
                    Draw.ellipse(surface, (*tint, round(225 * (1 - spread))), (px - 2, py - 5, 4, 9))
        elif self.key == 'boss_octopus':
            for tentacle in self._tentacles(boss, max(0, age)):
                _draw_tentacle(surface, tentacle)
            if age < 0:
                for side in (-1, 1):
                    _ripples(surface, boss.x + side * boss.w * .32, self.bottom - 16, 24, self.color, phase)
        elif self.key == 'boss_shark':
            for x, y, radius in self._tridents(age):
                if age < 0:
                    Draw.line(surface, (124, 213, 245, 100), (x, self.launch_y), (x, self.bottom), 1)
                if age < 0 or y >= self.launch_y:
                    _draw_trident(surface, x, y, x == self.target_x)
        elif self.key == 'boss_dragon':
            for index, (x, y, radius) in enumerate(self.fire_patches):
                if age < 0:
                    _ripples(surface, x, y, radius, self.color, phase)
                else:
                    _draw_fire(surface, x, y, radius, now, index)
        elif age < 0:
            _ripples(surface, boss.x, boss.y + boss.h * .8, boss.w * .30, self.color, phase)
        elif self.chasing:
            for side in (-1, 1):
                x = boss.x + side * boss.w * .62
                y = boss.y + boss.h * .22
                for i in range(4):
                    travel = (phase + i / 4) % 1
                    dx, dy = side * 18 * travel, -40 * travel
                    Draw.line(surface, (185, 224, 239, round(145 * (1 - travel))),
                              (x + dx, y + dy), (x + dx + side * 9, y + dy - 15), 2)

    def draw_bite(self, surface, boss):
        if not self.chasing:
            return False
        image = image_asset('effects/boss_bite.png', (round(boss.w * 1.47), round(boss.h * 1.45)))
        if image is None:
            return False
        blit_lit_sprite(surface, image, (boss.x - image.get_width() / 2,
                                        boss.y - boss.h * .22), (130, 189, 207), 155)
        return True


@lru_cache(maxsize=2)
def _claw_image(side):
    image = image_asset('effects/boss_claw.png', (103, 145))
    return pygame.transform.flip(image, not side, False) if image is not None else None


def _draw_claw(surface, x, y, side):
    image = _claw_image(side)
    if image is not None:
        _blit_art(surface, image, (round(x - image.get_width() / 2), round(y - image.get_height() + 24)))
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


def _draw_bubble(surface, x, y, radius, now, tint):
    center = (round(x), round(y))
    bounds = (x - radius, y - radius, 2 * radius, 2 * radius)
    Draw.circle(surface, (*tint, 49), center, radius)
    for color, start, width in (((*tint, 235), .32, 3),
                                ((*tint, 154), 3.4, 4),
                                ((229, 252, 255, 242), .81, 2)):
        Draw.arc(surface, color, bounds, start, start + 2.1, width)
    Draw.ellipse(surface, (216, 251, 255, 184), (x - 24, y - 27, 18, 6))
    for i in range(4):
        phase = (now * .002 + i / 4) % 1
        Draw.circle(surface, (*tint, 155), (x + (i - 1.5) * 13, y + 27 - 53 * phase), 2 + i % 2, 1)


def _draw_tentacle(surface, points):
    left, right = [], []
    for i, (x, y, width) in enumerate(points):
        a = points[max(0, i - 1)]
        b = points[min(len(points) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        distance = max(1, math.hypot(dx, dy))
        nx, ny = dy / distance, -dx / distance
        left.append((x + nx * width, y + ny * width))
        right.append((x - nx * width, y - ny * width))
    Draw.polygon(surface, (56, 23, 49), left + right[::-1])
    center = [(x, y) for x, y, _ in points]
    Draw.polygon(surface, (132, 63, 91), left + center[::-1])
    Draw.lines(surface, (204, 120, 135), False, left, 2)
    for i, (x, y, width) in enumerate(points[1:-1], 1):
        rx, ry = right[i]
        x, y = (x + rx) / 2, (y + ry) / 2
        r = max(2, width * .28)
        Draw.ellipse(surface, (219, 155, 137), (x - r, y - r * .8, 2 * r, 1.6 * r))
        Draw.ellipse(surface, (112, 48, 63), (x - r * .54, y - r * .37, r * 1.08, r * .74))


@lru_cache(maxsize=2)
def _trident_image(red):
    image = image_asset(TRIDENT_IMAGES[red])
    if image is None:
        return None
    bounds = image.get_bounding_rect(min_alpha=16)
    if not bounds:
        return None
    size = (_clamp(round(bounds.w * 81 / bounds.h), 28, 42), 81)
    return pygame.transform.smoothscale(image.subsurface(bounds), size)


def _draw_trident(surface, x, y, red):
    metal = (251, 89, 74) if red else (255, 208, 66)
    image = _trident_image(red)
    if image is not None:
        left = round(x - image.get_width() / 2)
        top = round(y + 30 - image.get_height())
        Draw.line(surface, (*metal, 115), (x, top + 4), (x, top - 19), 3)
        _blit_art(surface, image, (left, top))
        return
    shadow = (116, 33, 35) if red else (153, 96, 25)
    Draw.line(surface, shadow, (x, y - 43), (x, y + 22), 9)
    Draw.line(surface, metal, (x, y - 44), (x, y + 22), 4)
    Draw.lines(surface, shadow, False,
               ((x - 15, y + 18), (x - 15, y + 1), (x + 15, y + 1), (x + 15, y + 18)), 7)
    for offset, length in ((-15, 18), (0, 30), (15, 18)):
        tip = (x + offset, y + length)
        Draw.polygon(surface, metal, ((x + offset - 5, y + 8), tip, (x + offset + 5, y + 8)))
        Draw.line(surface, (255, 245, 199), (x + offset, y + 8), tip, 1)
    Draw.line(surface, (*metal, 110), (x, y - 45), (x, y - 64), 3)


def _blit_art(surface, image, position):
    if isinstance(surface, RenderSurface):
        surface.blit(image, position, static=True)
    else:
        surface.blit(image, position)


def _draw_fire(surface, x, y, radius, now, seed):
    for scale, alpha in ((1, 26), (.86, 44), (.68, 63)):
        Draw.circle(surface, (117, 43, 21, alpha), (x, y), round(radius * scale))
    Draw.circle(surface, (255, 108, 43, 117), (x, y), radius, 1)
    image = image_asset('effects/boss_ground_fire.png', (round(radius * 2.1),
                        round(radius * (1.2 + .05 * ((now // 95 + seed) % 4)))))
    if image is not None:
        _blit_art(surface, image, (round(x - image.get_width() / 2), round(y + radius * .37 - image.get_height())))
        foreground = image_asset('effects/boss_ground_fire.png', (round(radius * 1.58),
                                 round(radius * (.86 + .05 * ((now // 110 + seed) % 3)))))
        _blit_art(surface, foreground, (round(x - foreground.get_width() / 2 + radius * .08),
                                       round(y + radius * .71 - foreground.get_height())))
        for i in range(8):
            phase = (now * .0014 + i * .17 + seed * .2) % 1
            px = x + math.sin(i * 2.4 + phase * 3) * radius * .8
            py = y + 5 - phase * radius * 1.5
            Draw.circle(surface, (255, 200, 95, round(210 * (1 - phase))), (px, py), 1 + i % 2)
        return
    for i in range(15):
        angle = i * 2.399
        spread = radius * .81 * math.sqrt((i + .5) / 15)
        px, py = x + math.cos(angle) * spread, y + math.sin(angle) * spread
        flicker = (1 + math.sin(now * .021 + i * 3.7 + seed)) / 2
        h = 10 + flicker * 24
        w = 4 + i % 4
        drift = math.sin(now * .015 + i) * 7
        tip = (px + drift, py - h)
        Draw.polygon(surface, (195, 48, 16, 215),
                     ((px - w, py), (px - w * .7, py - h * .46), tip,
                      (px + w, py - h * .26), (px + w, py)))
        Draw.polygon(surface, (255, 125 + int(flicker * 49), 29),
                     ((px - w * .66, py), (px - 2, py - h * .45),
                      (px + drift * .8, py - h * .83), (px + w * .55, py)))
        Draw.polygon(surface, (255, 223, 119),
                     ((px - 2, py), (px + drift * .43, py - h * .55), (px + 3, py)))
        Draw.circle(surface, (255, 201, 91, round(185 * flicker)), (tip[0] + 2, tip[1] - 7), 2)
