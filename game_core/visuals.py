"""Cached artwork for Web controls and effects; no game or input state."""
import math
import random
from functools import lru_cache

import pygame

from .render import Draw


@lru_cache(maxsize=96)
def panel_surface(w, h, accent, fill, radius, alpha):
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
    pygame.draw.rect(panel, (*accent, 216), panel.get_rect(), 2, border_radius=radius)
    pygame.draw.rect(panel, (*accent, 54), panel.get_rect().inflate(-4, -4),
                     2, border_radius=max(1, radius - 2))
    return pygame.transform.smoothscale(panel, (w, h))


@lru_cache(maxsize=32)
def _glow(radius, color):
    size = radius * 2 + 1
    glow = pygame.Surface((size, size), pygame.SRCALPHA)
    for ring in range(radius, 0, -1):
        alpha = round(180 * (1 - ring / (radius + 1)) ** 2)
        pygame.draw.circle(glow, (*color, alpha), (radius, radius), ring)
    return glow


def draw_glow(surface, center, radius, color, opacity=255):
    glow = _glow(radius, tuple(color[:3]))
    glow.set_alpha(max(0, min(255, opacity)))
    surface.blit(glow, glow.get_rect(center=center))


@lru_cache(maxsize=3)
def _bubble(radius):
    bubble = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    center = (radius + 1, radius + 1)
    pygame.draw.circle(bubble, (140, 223, 240, 54), center, radius, 1)
    pygame.draw.circle(bubble, (223, 249, 255, 98), (radius, radius), 1)
    return bubble


def draw_water_drift(surface, left, right, bottom, now):
    if bottom <= 0:
        return
    width = right - left
    for i in range(18):
        x = left + width * (((i * 47 + 13) % 97) / 97)
        x += math.sin(now * 0.0008 + i) * 7
        near = i % 3 == 0
        y = (i * 71 - now * (0.032 if near else 0.013)) % bottom
        bubble = _bubble(4 if near else 2 + i % 2)
        surface.blit(bubble, bubble.get_rect(center=(round(x), round(y))))


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
