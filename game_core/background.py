"""
海洋背景：深度渐变海洋、水底光柱、波浪、气泡、海草、珊瑚、沙滩 —— 优化版。
"""
import random, math
from functools import lru_cache
import pygame
from . import config
from .asset_loader import cover_image_asset
from .config import (
    OCEAN_BLUE, SAND_COLOR, SAND_DARK, BEACH_HEIGHT,
    OCEAN_SURFACE, OCEAN_MID, OCEAN_DEEP,
    lerp_color, random_variation, ROCK_GRAY,
    SEAWEED_GREEN, SEAWEED_LIGHT, CORAL, WAVE_COLOR, BUBBLE,
)
from .sprites import _circle, _ellipse, _aaline, _polygon, _line, _rect

_bg_surf = {}


def _gradient_line(surf, y, color_top, color_bottom, h):
    t = max(0, min(1, y / max(1, h)))
    c = lerp_color(color_top, color_bottom, t)
    pygame.draw.line(surf, c, (0, y), (config.SCREEN_WIDTH, y))


def _draw_water_ripple(surf, y_base, amplitude, color, alpha=80, frequency=0.02):
    pts = []
    for x in range(0, config.SCREEN_WIDTH + 2, 3):
        y = y_base + int(math.sin(x * frequency + y_base * 0.008) * amplitude)
        pts.append((x, y))
    if len(pts) >= 2:
        pygame.draw.lines(surf, (*color[:3], alpha), False, pts, 1)


@lru_cache(maxsize=4)
def background_art(level, size):
    for stem in (f'bg{level}', 'background'):
        for suffix in ('jpg', 'png'):
            image = cover_image_asset(f'backgrounds/{stem}.{suffix}', size)
            if image is not None:
                fade = pygame.Surface(size, pygame.SRCALPHA)
                fade.fill((20, 39, 48, 76))
                image.blit(fade, (0, 0))
                return image.convert()
    return None


def make_background(level=1, *, art_size=None):
    cache_key = (level, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    # Prepare the display-sized art even if a logical surface survived a previous visit.
    image = background_art(level, art_size) if art_size is not None else None
    if cache_key in _bg_surf:
        return _bg_surf[cache_key]
    if art_size is None:
        image = background_art(level, cache_key[1:])
    if image is not None:
        if image.get_size() != cache_key[1:]:
            image = pygame.transform.smoothscale(image, cache_key[1:])
        _bg_surf[cache_key] = image
        return image
    surf = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))

    game_h = config.GAME_AREA_BOTTOM

    # ── 1. 海洋深度渐变 ──
    surface_color = (18, 115, 185)   # 浅水蓝
    mid_color = (10, 75, 150)         # 中水蓝
    deep_color = (5, 30, 80)          # 深水蓝
    abyss_color = (3, 12, 45)         # 深渊

    mid_point = game_h * 0.4
    deep_point = game_h * 0.75
    for y in range(game_h):
        if y < mid_point:
            _gradient_line(surf, y, surface_color, mid_color, mid_point)
        elif y < deep_point:
            _gradient_line(surf, y, mid_color, deep_color, mid_point)
        else:
            _gradient_line(surf, y, deep_color, abyss_color, game_h)

    # ── 2. 水面焦散线 ──
    caustic_surf = pygame.Surface((config.SCREEN_WIDTH, game_h), pygame.SRCALPHA)
    for i in range(20):
        base_y = random.randint(10, 80)
        for j in range(5):
            py = base_y + j * random.randint(6, 14)
            _draw_water_ripple(caustic_surf, py, random.uniform(2, 6),
                               (200, 235, 255), alpha=random.randint(15, 45),
                               frequency=random.uniform(0.015, 0.035))
    surf.blit(caustic_surf, (0, 0))

    # ── 3. 水底光柱 ──
    light_sources = [
        (120, -5, 50), (280, -15, 70), (450, 8, 55), (600, -3, 65), (780, -10, 48), (900, 5, 45),
    ]
    ray_surf = pygame.Surface((config.SCREEN_WIDTH, game_h), pygame.SRCALPHA)
    for rx, angle_offset, ray_width in light_sources:
        ray_wave = random.uniform(3, 8)
        for i in range(ray_width):
            alpha = max(0, int(16 - i * 0.22))
            if alpha <= 0:
                break
            x0 = rx - i * 5 + int(angle_offset * i * 0.12) + int(math.sin(i * 0.5) * ray_wave)
            x1 = rx + i * 5 + int(angle_offset * i * 0.12) + int(math.sin(i * 0.5) * ray_wave)
            if x0 < 0 and x1 < 0 or x0 > config.SCREEN_WIDTH and x1 > config.SCREEN_WIDTH:
                continue
            _polygon(ray_surf, (180, 220, 255, alpha),
                     [(int(x0), 0), (int(x1), 0), (int(rx + angle_offset * 1.8), game_h)])
    surf.blit(ray_surf, (0, 0))

    # ── 4. 浮游微粒和气泡 ──
    for _ in range(20):
        bx = random.randint(20, config.SCREEN_WIDTH - 20)
        by = random.randint(20, game_h - 40)
        br = random.randint(2, 5)
        alpha = random.randint(40, 100)
        _circle(surf, (170, 215, 255, alpha), (bx, by), br, 1)
        _circle(surf, (230, 245, 255, alpha), (bx - 1, by - 1), max(1, br // 2))
    # 悬浮微粒
    for _ in range(50):
        px = random.randint(5, config.SCREEN_WIDTH - 5)
        py = random.randint(5, game_h - 5)
        ps = random.randint(1, 2)
        _circle(surf, (200, 230, 255, random.randint(10, 40)), (px, py), ps)

    # ── 5. 水体波纹 ──
    wave_surf = pygame.Surface((config.SCREEN_WIDTH, game_h), pygame.SRCALPHA)
    for i in range(12):
        wy = random.randint(50, game_h - 100)
        amp = random.randint(4, 20)
        _draw_water_ripple(wave_surf, wy, amp, (120, 180, 230),
                           alpha=random.randint(10, 30), frequency=random.uniform(0.01, 0.04))
    surf.blit(wave_surf, (0, 0))

    # ── 6. 远景鱼群剪影 ──
    for _ in range(3):
        school_x = random.randint(100, config.SCREEN_WIDTH - 200)
        school_y = random.randint(60, game_h - 160)
        school_count = random.randint(3, 6)
        for si in range(school_count):
            sx = school_x + si * random.randint(10, 20)
            sy = school_y + random.randint(-8, 8)
            alpha = random.randint(10, 30)
            _ellipse(surf, (80, 140, 200, alpha), (sx - 4, sy - 2, 10, 5))
            _polygon(surf, (80, 140, 200, alpha), [(sx + 3, sy - 2), (sx + 8, sy - 5), (sx + 6, sy)])

    # ── 7. 海草 ──
    sand_top = game_h
    for sx in (30, 100, 180, 800, 870, 940):
        for stem_idx in range(random.randint(2, 4)):
            stem_x = sx + random.randint(-12, 12)
            stem_height = random.randint(40, 90)
            top_y = sand_top - stem_height
            control_x = stem_x + random.randint(-15, 15)
            # 海草主茎
            pts = [(stem_x, sand_top)]
            for seg in range(5):
                t = (seg + 1) / 5
                sx2 = stem_x + (control_x - stem_x) * t + math.sin(t * math.pi) * (control_x - stem_x) * 0.5
                sy2 = sand_top - stem_height * t
                pts.append((int(sx2), int(sy2)))
            if len(pts) >= 2:
                for pi in range(len(pts) - 1):
                    color = lerp_color((15, 80, 30), (40, 150, 60), pi / max(1, len(pts) - 1))
                    _line(surf, color, pts[pi], pts[pi + 1], 3)
            # 叶片
            mid_pt = pts[len(pts) // 2]
            leaf_h = random.randint(10, 18)
            leaf_w = random.randint(5, 9)
            for leaf_dir in [-1, 1]:
                lx = mid_pt[0] + leaf_dir * leaf_w
                ly = mid_pt[1] + leaf_h
                _ellipse(surf, random_variation((SEAWEED_LIGHT[0], SEAWEED_LIGHT[1], SEAWEED_LIGHT[2], 160), 15),
                         (lx - leaf_w, ly - leaf_h, leaf_w * 2, leaf_h * 2))

    # ── 8. 珊瑚 ──
    coral_positions = [(80, sand_top - 45), (150, sand_top - 35), (820, sand_top - 50), (890, sand_top - 40)]
    for cx, cy in coral_positions:
        # 橙色珊瑚
        for branch in range(4):
            bx = cx + branch * random.randint(3, 6)
            by = cy - branch * random.randint(3, 8)
            if by < sand_top - 60:
                break
            br = random.randint(4, 8)
            _circle(surf, random_variation((CORAL[0], CORAL[1], CORAL[2]), 30), (bx, by), br)
            # 高光
            _circle(surf, (255, 180, 140, 80), (bx - 1, by - 1), max(1, br - 3))

    # ── 9. 岩石 ──
    rock_positions = [(200, sand_top - 25), (760, sand_top - 30), (config.SCREEN_WIDTH // 2 - 30, sand_top - 20)]
    for rx, ry in rock_positions:
        rr = random.randint(12, 30)
        _ellipse(surf, random_variation(ROCK_GRAY, 15), (rx - rr, ry - rr // 2, rr * 2, rr))
        _ellipse(surf, random_variation((80, 90, 105), 15), (rx - rr + 3, ry - rr // 2 + 2, rr * 2 - 6, rr - 4))
        # 岩石高光边缘
        _ellipse(surf, (100, 110, 125, 60),
                 (rx - rr // 2, ry - rr // 3, rr, rr // 3))

    # ── 10. 沙滩 ──
    for y in range(sand_top, config.SCREEN_HEIGHT):
        t = (y - sand_top) / max(1, BEACH_HEIGHT)
        # 从深渊色渐变到沙滩色
        base = lerp_color(abyss_color, SAND_COLOR, t)
        surf.set_at((0, y), base)
        # 行像素
        for x in range(1, config.SCREEN_WIDTH):
            var = random_variation(base, 6)
            surf.set_at((x, y), var)

    # 沙滩纹理带
    for y_off in range(8, BEACH_HEIGHT - 2, 5):
        y = sand_top + y_off
        for x in range(0, config.SCREEN_WIDTH, 3):
            if random.random() < 0.3:
                surf.set_at((x, y), random_variation(SAND_DARK, 15))

    # 沙滩上的贝壳
    for _ in range(6):
        bx = random.randint(30, config.SCREEN_WIDTH - 30)
        by = sand_top + random.randint(6, BEACH_HEIGHT - 12)
        # 贝壳
        _ellipse(surf, random_variation((240, 225, 200), 20), (bx - 4, by - 2, 8, 5))
        _ellipse(surf, random_variation((255, 240, 220), 15), (bx - 3, by - 2, 6, 4))
        _line(surf, random_variation((180, 160, 120), 20), (bx, by - 1), (bx, by + 3), 1)

    # 沙滩上的鹅卵石
    for _ in range(10):
        sx = random.randint(15, config.SCREEN_WIDTH - 15)
        sy = sand_top + random.randint(3, BEACH_HEIGHT - 6)
        sr = random.randint(2, 6)
        _ellipse(surf, random_variation(ROCK_GRAY, 25), (sx - sr, sy - sr // 2, sr * 2, sr))
        _ellipse(surf, (100, 110, 120, 60), (sx - sr + 1, sy - sr // 2, sr, sr // 2))

    # 沙滩上的海星
    for _ in range(3):
        sx = random.randint(40, config.SCREEN_WIDTH - 40)
        sy = sand_top + random.randint(10, BEACH_HEIGHT - 20)
        for a in range(0, 360, 72):
            rad = a * math.pi / 180
            ex = sx + int(math.cos(rad) * 6)
            ey = sy + int(math.sin(rad) * 4)
            _aaline(surf, random_variation((220, 160, 100), 30), (sx, sy), (ex, ey))

    _bg_surf[cache_key] = surf
    return surf
