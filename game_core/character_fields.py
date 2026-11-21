"""Timing and presentation shared by the character upgrade fields."""
import math
from functools import lru_cache

import pygame

from . import config
from .abyss_bosses import AbyssProjectile
from .asset_loader import image_asset
from .render import Draw, RenderSurface, blit_effect, effect_layer
from .special_bosses import NiuShieldShard, ReturningAxe
from .visuals import panel_surface


# These clocks drive actor motion and casts. Detached projectiles keep world time.
_BOSS_CLOCKS = (
    'next_signature_time', 'next_death_laser_time', 'next_absorb_time',
    'laser_warning_start', 'next_hazard_time', 'next_revive_check',
    'next_fusion_time', 'fusion_started_at', 'fusion_until', 'side_head_at',
    'spawned_at', 'split_next_dive', 'split_last_update', 'swim_turn_at',
    'skill_end_at', 'recovery_at',
)


def delay_boss_actions(boss, elapsed):
    if boss.entered:
        boss.fight_start_time += elapsed
        boss.last_attack_time += elapsed
    boss.breath_start_time += elapsed
    for field in _BOSS_CLOCKS:
        stamp = getattr(boss, field, 0)
        if stamp:
            setattr(boss, field, stamp + elapsed)
    for field in ('animation_attack_at', 'axe_slam_start', 'crescent_started_at', 'split_regroup_at'):
        stamp = getattr(boss, field, None)
        if stamp is not None:
            setattr(boss, field, stamp + elapsed)
    if getattr(boss, 'current_skill', None):
        boss.skill_started_at += elapsed
    if getattr(boss, 'skill', None):
        boss.skill_at += elapsed
    if getattr(boss, 'split_charge_until', None):
        boss.split_charge_until[:] = [stamp + elapsed if stamp else 0 for stamp in boss.split_charge_until]
    if getattr(boss, 'axe_slam_impact', None):
        x, y, at = boss.axe_slam_impact
        boss.axe_slam_impact = (x, y, at + elapsed)
    if boss.signature:
        boss.signature.impact_at += elapsed
        boss.signature.end_at += elapsed
        if hasattr(boss.signature, 'next_fireball_at'):
            boss.signature.next_fireball_at += elapsed


def is_flying_enemy_shot(shot, now):
    if not getattr(shot, 'launched', True) or getattr(shot, 'detonate_at', 0):
        return False
    if isinstance(shot, (ReturningAxe, NiuShieldShard)):
        return shot.alive
    if isinstance(shot, AbyssProjectile):
        return shot.speed > 0 and shot.is_active(now)
    return shot.alive and shot.speed > 0


_FIELD_COLORS = {'ice': (173, 231, 255), 'water': (88, 255, 226),
                 'fire': (255, 171, 88), 'radiation': (212, 150, 255)}


def draw_player_fields(surface, player, bounds, scale, now, font, *, ice_until=0, obstacles=()):
    hits = getattr(player, 'fire_shield_hits', 0) if now < getattr(player, 'fire_shield_until', 0) else 0
    deadlines = (('ice', ice_until), ('water', getattr(player, 'swift_field_until', 0)),
                 ('fire', player.fire_shield_until if hits else 0),
                 ('radiation', getattr(player, 'radiation_field_until', 0)))
    active = {field: until - now for field, until in deadlines if until > now}
    if not active:
        return
    radius = max(28, round(max(bounds.size) * scale * .82))
    swift = 'water' in active
    if hits:
        _draw_fire_armor(surface, bounds.center, radius)
    if swift or 'radiation' in active:
        water_radius = radius + (round(radius * .26) if hits else 0)
        radiation_radius = water_radius + (14 if swift else 0)
        extent = radiation_radius + 13
        layer = effect_layer(surface, (extent * 2 + 1, extent * 2 + 1))
        center = (extent, extent)
        if 'radiation' in active:
            _draw_aura(layer, center, radiation_radius, now, 'radiation')
        if swift:
            _draw_aura(layer, center, water_radius, now, 'water')
        blit_effect(surface, layer, (bounds.centerx - extent, bounds.centery - extent))
    _draw_field_badges(surface, bounds.center, radius, active, hits, font, obstacles)


def _draw_fire_armor(surface, center, radius):
    diameter = round(radius * 2.65)
    size = (diameter, diameter)
    rendered = isinstance(surface, RenderSurface)
    armor = image_asset('effects/fire_armor.png', None if rendered else size)
    if armor is None:
        Draw.circle(surface, _FIELD_COLORS['fire'], center, radius, 5)
        Draw.circle(surface, (255, 241, 184), center, radius - 3, 2)
    elif rendered:
        surface.blit(armor, (center[0] - diameter // 2, center[1] - diameter // 2),
                     static=True, logical_size=size)
    else:
        surface.blit(armor, armor.get_rect(center=center))


def _draw_aura(layer, center, radius, now, field):
    water = field == 'water'
    color = _FIELD_COLORS[field]
    glow = (22, 196, 219) if water else (129, 47, 255)
    core = (209, 255, 249) if water else (252, 222, 255)
    Draw.circle(layer, (*glow, 48), center, radius + 9, 18)
    Draw.circle(layer, (*glow, 120), center, radius + 5, 10)
    Draw.circle(layer, (*color, 225), center, radius + 1, 3)
    Draw.circle(layer, (*color, 96), center, radius - 7, 1)
    cx, cy = center
    ring = (cx - radius, cy - radius, radius * 2, radius * 2)
    count = 2 if water else 3
    for index in range(count):
        angle = (now * (.007 if water else -.005) + index * math.tau / count) % math.tau
        Draw.arc(layer, (*core, 255), ring, angle, angle + 1.15, 3)
        x = cx + radius * math.cos(angle + 1.12)
        y = cy - radius * math.sin(angle + 1.12)
        if water:
            Draw.circle(layer, (*color, 156), (x, y), 6)
            Draw.circle(layer, (*core, 255), (x, y), 3)
        else:
            Draw.polygon(layer, (*core, 250), ((x, y - 6), (x + 4, y), (x, y + 6), (x - 4, y)))


@lru_cache(maxsize=128)
def _countdown_text(font, tenths):
    return font.render(f'{tenths / 10:.1f}s', True, (249, 251, 255))


def _draw_field_badges(surface, center, radius, active, hits, font, obstacles):
    w, h, gap = 58, 23, 3
    cx, cy = center
    width = surface.get_size()[0]
    base_x = max(4, min(width - w - 4, cx - round(radius * .42) - w))
    stack_height = h + (len(active) - 1) * (h + gap)
    base_top = max(6, cy - radius - stack_height)
    stack = pygame.Rect(base_x, base_top, w, stack_height)
    right_limit = min(cx, width - 4)
    while stack.right <= right_limit and (index := stack.collidelist(obstacles)) >= 0:
        stack.left = obstacles[index].right + gap
    if stack.right > right_limit:
        stack.left = base_x
        while (index := stack.collidelist(obstacles)) >= 0:
            stack.bottom = obstacles[index].top - gap
    x = stack.x
    y = (stack.top if stack.top >= 6 else base_top) + stack_height - h
    for field, remaining in active.items():
        color = _FIELD_COLORS[field]
        panel = panel_surface(w, h, color, (7, 16, 29), 6, 237)
        surface.blit(panel, (x, y))
        _draw_field_icon(surface, field, x + 11, y + h // 2, color)
        text = _countdown_text(font, math.ceil(remaining / 100))
        text_center = (x + 36, y + h // 2 - (2 if field == 'fire' else 0))
        surface.blit(text, text.get_rect(center=text_center))
        if field == 'fire':
            for i in range(hits):
                Draw.circle(surface, color, (x + 36 + (2 * i - hits + 1) * 3, y + h - 4), 2)
        y -= h + gap


def _draw_field_icon(surface, field, x, y, color):
    if field == 'ice':
        for dx, dy in ((6, 0), (3, 5), (-3, 5)):
            Draw.line(surface, color, (x - dx, y - dy), (x + dx, y + dy), 2)
    elif field == 'water':
        for shift in (-3, 2):
            Draw.lines(surface, color, False, ((x + shift - 2, y - 5), (x + shift + 2, y),
                                               (x + shift - 2, y + 5)), 2)
    elif field == 'fire':
        Draw.lines(surface, color, True, ((x - 5, y - 5), (x + 5, y - 5), (x + 4, y + 2),
                                          (x, y + 6), (x - 4, y + 2)), 2)
    else:
        Draw.polygon(surface, color, ((x + 1, y - 7), (x - 5, y + 1), (x, y + 1),
                                      (x - 1, y + 7), (x + 5, y - 2), (x + 1, y - 2)))


def draw_air_wave(surface, wave, now):
    if wave is None:
        return
    px, py, started = wave
    progress = (now - started) / config.CHARACTER_FIELDS['radiation']['wave_ms']
    if not 0 <= progress < 1:
        return
    x, y = round(px), round(py)
    width, height = surface.get_size()
    reach = math.hypot(max(x, width - x), max(y, height - y))
    radius = round(23 + reach * progress ** .86)
    extent = radius + 26
    visible = pygame.Rect(x - extent, y - extent, extent * 2 + 1, extent * 2 + 1)
    visible = visible.clip((0, 0, width, height))
    if not visible:
        return
    layer = effect_layer(surface, visible.size)
    cx, cy = center = (x - visible.x, y - visible.y)
    fade = (1 - progress) ** .7
    if progress < .3:
        Draw.circle(layer, (222, 204, 255, round(104 * (1 - progress / .3))), center, max(4, radius // 3))
    for offset, color, alpha, stroke in (
            (12, (118, 59, 255), 62, 27), (5, (148, 102, 255), 142, 14),
            (0, (222, 200, 255), 245, 7), (-2, (246, 255, 255), 255, 3),
            (-24, (166, 124, 255), 184, 3), (-44, (131, 208, 255), 148, 2)):
        if radius + offset > 0:
            Draw.circle(layer, (*color, round(alpha * fade)), center, radius + offset, stroke)
    for i in range(24):
        angle = i * math.tau / 24 + progress * .32
        dx, dy = math.cos(angle), math.sin(angle)
        distance = radius + 9 + i % 4 * 4
        end = (cx + dx * distance, cy + dy * distance)
        trail = distance - 8 - i % 3 * 8
        Draw.line(layer, (195, 147, 255, round(160 * fade)),
                  (cx + dx * trail, cy + dy * trail), end, 2 + i % 2)
        Draw.circle(layer, (241, 248, 255, round(247 * fade)), end, 2 + i % 2)
    blit_effect(surface, layer, visible.topleft)
