"""Cached artwork for Web controls and effects; no game or input state."""
import math
import random
from functools import lru_cache

import pygame

from .config import make_font
from .render import Draw, RenderSurface


@lru_cache(maxsize=96)
def panel_surface(w, h, accent, fill, radius, alpha, stroke=1):
    # Draw the contour at 2× so rounded edges survive narrow-screen scaling.
    size = (w * 2, h * 2)
    panel = pygame.Surface(size, pygame.SRCALPHA)
    mask = pygame.Surface(size, pygame.SRCALPHA)
    radius *= 2
    pygame.draw.rect(mask, 'white', mask.get_rect(), border_radius=radius)
    for row in range(size[1]):
        light = 1 - row / max(1, size[1] - 1)
        rgb = tuple(min(255, base + int((16 + tint * 0.13) * light))
                    for base, tint in zip(fill, accent))
        pygame.draw.line(panel, (*rgb, alpha), (0, row), (size[0] - 1, row))
    panel.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.rect(panel, (*accent, 216), panel.get_rect(), 2 * stroke, border_radius=radius)
    pygame.draw.rect(panel, (*accent, 54), panel.get_rect().inflate(-4 * stroke, -4 * stroke),
                     2, border_radius=max(1, radius - 2 * stroke))
    return pygame.transform.smoothscale(panel, (w, h))


@lru_cache(maxsize=128)
def _native_label(text, size, bold, color):
    return make_font(size, bold=bold).render(text, True, color)


@lru_cache(maxsize=256)
def small_desktop_label(font, text, color, size, *, alpha=255):
    # Average the coverage of a 2× glyph raster at the final pixel size.
    image = pygame.transform.smoothscale(font.render(text, True, color), size)
    if alpha != 255:
        image.set_alpha(alpha)
    return image


def blit_label(target, font, text, color, center, size, *, bold=False, alpha=255):
    native = isinstance(target, RenderSurface) and target.desktop_ui
    if native:
        image = _native_label(text, target.length(size), bold, color)
        center = target.point(center)
        blit = target.blit_pixels
    else:
        image = font.render(text, True, color)
        blit = target.blit
    if alpha != 255:
        image = image.copy()
        image.set_alpha(alpha)
    blit(image, image.get_rect(center=center))


@lru_cache(maxsize=32)
def _glow(radius, color):
    size = radius * 2 + 1
    glow = pygame.Surface((size, size), pygame.SRCALPHA)
    for ring in range(radius, 0, -1):
        alpha = round(180 * (1 - ring / (radius + 1)) ** 2)
        pygame.draw.circle(glow, (*color, alpha), (radius, radius), ring)
    return glow


@lru_cache(maxsize=16)
def _scaled_glow(glow, diameter):
    return pygame.transform.smoothscale(glow, (diameter, diameter))


def draw_glow(surface, center, radius, color, opacity=255):
    glow = _glow(radius, tuple(color[:3]))
    position = glow.get_rect(center=center)
    alpha = max(0, min(255, opacity))
    if isinstance(surface, RenderSurface):
        diameter = surface.length(glow.get_width())
        if diameter != glow.get_width():
            glow = _scaled_glow(glow, diameter)
        glow.set_alpha(alpha)
        surface.blit_pixels(glow, surface.point(position.topleft))
    else:
        glow.set_alpha(alpha)
        surface.blit(glow, position)


@lru_cache(maxsize=48)
def _bubble(radius, opacity):
    bubble = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    center = (radius + 1, radius + 1)
    pygame.draw.circle(bubble, (187, 235, 249, round(154 * opacity / 8)), center, radius, 1)
    pygame.draw.circle(bubble, (239, 252, 255, round(225 * opacity / 8)),
                       (center[0] - radius // 3, center[1] - radius // 2),
                       2 if radius >= 6 else 1)
    return bubble


@lru_cache(maxsize=48)
def _scaled_bubble(radius, opacity, diameter):
    bubble = _bubble(radius, opacity)
    if diameter == bubble.get_width():
        return bubble
    return pygame.transform.smoothscale(bubble, (diameter, diameter))


def draw_water_drift(surface, now):
    width, height = surface.get_size()
    rendered = isinstance(surface, RenderSurface)
    radii = (3, 4, 6, 8)
    if rendered:
        diameters = {radius: surface.length(radius * 2 + 2) for radius in radii}
    margin = max(radii) + 2  # Wrap fully outside the visible area.
    for rise, count, seed in ((height, 30, 0), (max(1, height // 3), 16, 30)):
        travel = rise + 2 * margin
        for index in range(count):
            i = index + seed
            radius = radii[0] if seed else radii[i % len(radii)]
            speed = 0.025 + (radius - 3) * 0.006 + (i % 4) * 0.002
            distance = now * speed
            position = (travel * index / count - distance) % travel - margin
            opacity = round(8 * max(0, min(1, position / (rise * 0.45))))
            if opacity == 0:
                continue
            y = height - rise + position
            x = width * (0.06 + 0.88 * ((i * 47 + 13) % 97) / 97)
            x += math.sin(distance * 0.045 + i) * (radius + 4)
            position = (round(x) - radius - 1, round(y) - radius - 1)
            if rendered:
                bubble = _scaled_bubble(radius, opacity, diameters[radius])
                surface.blit_pixels(bubble, surface.point(position))
            else:
                surface.blit(_bubble(radius, opacity), position)


def draw_electric_arc(surface, start, end, color, alpha, now, seed=0, thickness=2):
    x, y = start
    dx, dy = end[0] - x, end[1] - y
    distance = math.hypot(dx, dy)
    if distance < 3:
        return
    jitter = min(14, distance * 0.22)
    nx, ny = -dy / distance, dx / distance
    rng = random.Random((now // 55) * 7919 + seed)
    points = [start]
    for i in range(1, 6):
        t = i / 6
        offset = rng.uniform(-jitter, jitter)
        points.append((x + dx * t + nx * offset, y + dy * t + ny * offset))
    points.append(end)
    Draw.lines(surface, (*color, alpha // 4), False, points, thickness + 5)
    Draw.lines(surface, (*color, alpha), False, points, thickness + 1)
    Draw.lines(surface, (242, 255, 255, alpha), False, points, 1)
