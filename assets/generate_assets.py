"""
生成项目内 PNG 图片素材。

这不是把运行时代码绘制的旧图形导出成 PNG，而是独立生成一套新的
霓虹卡通海洋风素材。运行时缺图仍会回退到旧绘制逻辑。
"""
import math
import os
import random
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame


ROOT = os.path.dirname(os.path.dirname(__file__))
ASSET_DIR = os.path.join(ROOT, 'assets', 'images')
sys.path.insert(0, ROOT)


def save(surf, name):
    path = os.path.join(ASSET_DIR, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pygame.image.save(surf, path)


def circle(surf, color, pos, radius, width=0):
    pygame.draw.circle(surf, color, (int(pos[0]), int(pos[1])), int(radius), width)


def ellipse(surf, color, rect, width=0):
    pygame.draw.ellipse(surf, color, rect, width)


def rect(surf, color, r, width=0, radius=0):
    pygame.draw.rect(surf, color, r, width, border_radius=radius)


def poly(surf, color, pts, width=0):
    pygame.draw.polygon(surf, color, [(int(x), int(y)) for x, y in pts], width)


def line(surf, color, a, b, width=1):
    pygame.draw.line(surf, color, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), width)


def glow_circle(surf, color, pos, radius):
    for i in range(5, 0, -1):
        circle(surf, (*color[:3], 16 + i * 9), pos, radius + i * 3)
    circle(surf, color, pos, radius)


def gradient(size, top, bottom):
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        line(surf, c, (0, y), (w, y))
    return surf


def make_background():
    random.seed(12)
    w, h = 960, 720
    surf = gradient((w, h), (12, 155, 210), (2, 14, 50))
    for y in range(45, 650, 58):
        pts = []
        for x in range(0, w + 5, 5):
            pts.append((x, y + math.sin(x * 0.018 + y * 0.04) * 9))
        pygame.draw.lines(surf, (120, 220, 255, 35), False, pts, 1)
    ray = pygame.Surface((w, h), pygame.SRCALPHA)
    for x in (120, 300, 520, 760, 900):
        poly(ray, (190, 240, 255, 22), [(x - 30, 0), (x + 45, 0), (x + random.randint(-90, 90), 660)])
    surf.blit(ray, (0, 0))
    for _ in range(70):
        x, y = random.randint(15, w - 15), random.randint(8, 650)
        r = random.randint(1, 4)
        circle(surf, (210, 245, 255, random.randint(35, 130)), (x, y), r, 1)
    for base in (40, 145, 810, 905):
        for _ in range(5):
            x = base + random.randint(-22, 22)
            height = random.randint(44, 94)
            line(surf, (18, 160, 95), (x, 665), (x + random.randint(-18, 18), 665 - height), 4)
            ellipse(surf, (40, 220, 140, 170), (x - 10, 624 - height // 3, 18, 36))
    for x, y, c in ((95, 630, (255, 105, 95)), (830, 628, (255, 155, 75)), (205, 640, (170, 110, 255))):
        for i in range(6):
            circle(surf, (*c, 220), (x + i * 7, y - i * 5), random.randint(5, 9))
    for y in range(660, h):
        t = (y - 660) / 60
        c = tuple(int((12, 20, 58)[i] + ((232, 207, 145)[i] - (12, 20, 58)[i]) * t) for i in range(3))
        line(surf, c, (0, y), (w, y))
    for _ in range(170):
        x, y = random.randint(0, w - 1), random.randint(668, h - 1)
        circle(surf, (255, 240, 185, random.randint(45, 130)), (x, y), 1)
    return surf.convert()


def make_guardian(color, accent, weapon='trident'):
    surf = pygame.Surface((80, 80), pygame.SRCALPHA)
    cx, cy = 40, 42
    ellipse(surf, (0, 0, 0, 55), (18, 66, 44, 8))
    glow_circle(surf, (*accent, 150), (cx, cy), 20)
    if weapon == 'blade':
        for i, r in enumerate((23, 18, 13)):
            circle(surf, (255, 70 + i * 45, 25, 115), (cx, cy - 16 - i * 2), r)
        poly(surf, (255, 105, 55, 255), [(25, 32), (32, 10), (40, 28), (48, 9), (57, 32), (40, 25)])
        ellipse(surf, (120, 24, 18, 255), (22, 31, 36, 34))
        rect(surf, (55, 20, 18, 255), (27, 50, 26, 11), radius=5)
    elif weapon == 'orb':
        ellipse(surf, (42, 62, 54, 255), (20, 27, 40, 38))
        rect(surf, (30, 42, 38, 255), (25, 47, 30, 16), radius=6)
        circle(surf, (132, 255, 105, 240), (40, 45), 10, 3)
        circle(surf, (210, 255, 160, 220), (40, 45), 4)
        for a in range(0, 360, 120):
            rad = math.radians(a)
            line(surf, (130, 255, 110, 170), (40, 45), (40 + math.cos(rad) * 14, 45 + math.sin(rad) * 14), 2)
    elif accent[0] > 200 and accent[1] > 230:
        poly(surf, (165, 235, 255, 245), [(20, 49), (31, 24), (40, 14), (50, 24), (60, 49), (50, 62), (30, 62)])
        ellipse(surf, (70, 180, 235, 255), (23, 30, 34, 31))
        for dx in (-18, -9, 0, 9, 18):
            line(surf, (220, 250, 255, 170), (40, 21), (40 + dx, 60), 2)
    else:
        ellipse(surf, (128, 86, 42, 255), (22, 31, 36, 34))
        for dx in range(-14, 17, 6):
            line(surf, (92, 62, 34, 210), (cx + dx, 34), (cx + dx + 7, 61), 1)
        poly(surf, (205, 160, 82, 255), [(17, 28), (40, 10), (63, 28), (40, 24)])
        rect(surf, (136, 91, 48, 255), (18, 28, 44, 5), radius=2)
    circle(surf, (244, 215, 178), (40, 35), 11)
    circle(surf, (255, 233, 198), (36, 31), 4)
    circle(surf, (255, 255, 255), (35, 35), 4)
    circle(surf, (255, 255, 255), (46, 35), 4)
    circle(surf, (12, 18, 28), (36, 35), 2)
    circle(surf, (12, 18, 28), (47, 35), 2)
    line(surf, (110, 65, 45), (37, 42), (43, 42), 1)
    if weapon == 'trident':
        if accent[0] > 200 and accent[1] > 230:
            line(surf, (230, 250, 255), (61, 55), (69, 17), 3)
            for dx in (-6, 0, 6):
                line(surf, (210, 250, 255, 255), (69, 17), (69 + dx, 7), 2)
        else:
            line(surf, (120, 82, 45), (61, 55), (72, 14), 3)
            line(surf, (215, 215, 205), (72, 14), (73, 47), 1)
            circle(surf, (255, 90, 45), (73, 50), 2)
    elif weapon == 'blade':
        poly(surf, (255, 220, 120, 245), [(58, 57), (73, 15), (69, 58)])
        line(surf, (255, 255, 210, 180), (68, 20), (63, 52), 2)
    else:
        circle(surf, (130, 255, 110, 220), (66, 26), 10, 3)
        circle(surf, (210, 255, 160, 230), (66, 26), 4)
        line(surf, (130, 255, 110, 220), (61, 31), (52, 47), 3)
    return surf


def make_enemy(kind, large=False):
    size = (100, 86) if large else (60, 52)
    surf = pygame.Surface(size, pygame.SRCALPHA)
    w, h = size
    cx, cy = w // 2, h // 2
    palettes = {
        'lobster': ((255, 72, 82), (255, 180, 90)),
        'crab': ((120, 95, 255), (250, 120, 190)),
        'goldfish': ((255, 175, 42), (255, 245, 120)),
        'octopus': ((180, 80, 255), (90, 245, 255)),
        'shark': ((90, 170, 230), (255, 90, 120)),
    }
    main, accent = palettes[kind]
    ellipse(surf, (0, 0, 0, 45), (w * 0.18, h * 0.78, w * 0.64, h * 0.13))
    if kind == 'shark':
        poly(surf, (*main, 255), [(10, cy), (cx + 25, 8), (w - 8, cy), (cx + 18, h - 12)])
        poly(surf, (*accent, 235), [(cx - 4, cy), (w - 8, cy - 16), (w - 8, cy + 16)])
        poly(surf, (235, 250, 255, 240), [(cx - 4, cy + 12), (w - 14, cy + 6), (w - 18, cy + 18)])
    elif kind == 'octopus':
        ellipse(surf, (*main, 255), (cx - w * 0.25, 7, w * 0.5, h * 0.52))
        for i in range(6):
            x = cx - 24 + i * 9
            line(surf, (*main, 235), (x, cy + 12), (x + math.sin(i) * 12, h - 9), 5)
            circle(surf, (*accent, 160), (x + math.sin(i) * 12, h - 9), 3)
    else:
        ellipse(surf, (*main, 255), (8, 10, w - 16, h - 20))
        poly(surf, (*accent, 240), [(w - 10, cy), (w - 1, cy - 11), (w - 1, cy + 11)])
        if kind in ('lobster', 'crab'):
            for side in (-1, 1):
                line(surf, (*accent, 230), (cx + side * 16, cy), (cx + side * 29, cy - 8), 4)
                circle(surf, (*accent, 240), (cx + side * 32, cy - 10), 6)
    circle(surf, (255, 255, 255), (cx - 9, cy - 5), 5)
    circle(surf, (255, 255, 255), (cx + 9, cy - 5), 5)
    circle(surf, (8, 15, 30), (cx - 8, cy - 5), 2)
    circle(surf, (8, 15, 30), (cx + 10, cy - 5), 2)
    ellipse(surf, (255, 255, 255, 55), (cx - 15, cy - 12, 16, 8))
    return surf


def make_boss(kind):
    base = kind.replace('boss_', '')
    if base in ('dragon', 'boss', 'niu', 'zongzong'):
        base = 'shark'
    surf = pygame.transform.smoothscale(make_enemy(base, large=True), (150, 140))
    aura = pygame.Surface((150, 140), pygame.SRCALPHA)
    for r in range(62, 18, -9):
        circle(aura, (255, 70, 120, 18), (75, 70), r, 3)
    surf.blit(aura, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    circle(surf, (255, 245, 120, 180), (112, 35), 8)
    return surf


def make_weapon(key):
    surf = pygame.Surface((56, 28), pygame.SRCALPHA)
    colors = {
        'pistol': ((255, 220, 80), (35, 55, 90)),
        'rifle': ((100, 200, 255), (35, 60, 110)),
        'shotgun': ((110, 235, 180), (35, 60, 55)),
        'sniper': ((255, 100, 120), (70, 40, 80)),
    }
    c, dark = colors[key]
    rect(surf, (*dark, 235), (9, 11, 30 if key == 'pistol' else 40, 8), radius=4)
    rect(surf, (*c, 240), (13, 8, 25 if key == 'pistol' else 35, 7), radius=3)
    line(surf, (*c, 255), (38, 11), (52, 11), 3)
    rect(surf, (*dark, 230), (17, 16, 8, 10), radius=3)
    circle(surf, (255, 255, 255, 120), (20, 11), 2)
    return surf


def make_bullet(color):
    surf = pygame.Surface((16, 16), pygame.SRCALPHA)
    glow_circle(surf, (*color, 220), (8, 6), 4)
    ellipse(surf, (*color, 110), (5, 7, 6, 8))
    return surf


def make_coin():
    surf = pygame.Surface((26, 26), pygame.SRCALPHA)
    glow_circle(surf, (255, 220, 60, 255), (13, 13), 10)
    circle(surf, (170, 110, 25, 255), (13, 13), 11, 2)
    line(surf, (150, 90, 20), (9, 13), (17, 13), 2)
    line(surf, (150, 90, 20), (13, 8), (13, 18), 2)
    return surf


def main():
    pygame.init()
    pygame.display.set_mode((1, 1))

    from game_core.config import WEAPON_DEFS, BOSS_DEFS

    save(make_background(), 'backgrounds/background.png')
    save(make_guardian((70, 190, 255), (255, 225, 90), 'trident'), 'players/player.png')
    save(make_guardian((255, 96, 64), (255, 210, 70), 'blade'), 'players/player_fire.png')
    save(make_guardian((90, 210, 255), (210, 250, 255), 'trident'), 'players/player_ice.png')
    save(make_guardian((180, 105, 255), (120, 255, 110), 'orb'), 'players/player_radiation.png')

    for key, large in (('lobster', False), ('crab', False), ('goldfish', False), ('octopus', True), ('shark', True)):
        save(make_enemy(key, large), f'enemies/enemy_{key}.png')

    for bdef in BOSS_DEFS:
        save(make_boss(bdef['key']), f"bosses/{bdef.get('sprite_key', bdef['key'])}.png")

    for key, wdef in WEAPON_DEFS.items():
        name = {'shotgun': 'shortgun', 'sniper': 'awm'}.get(key, key)
        save(make_weapon(key), f'weapons/weapon_{name}.png')
        color_key = f'{wdef.color[0]}_{wdef.color[1]}_{wdef.color[2]}'
        save(make_bullet(wdef.color), f'weapons/bullet_{color_key}.png')

    save(make_coin(), 'ui/coin.png')


if __name__ == '__main__':
    main()
