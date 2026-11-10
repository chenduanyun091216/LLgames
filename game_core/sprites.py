"""
精灵绘制：玩家、敌人、武器图标、金币、子弹、Boss。
所有精灵通过 pygame 基本图形绘制——优化版，丰富的细节和渐变效果。
"""
import random
import math
import pygame
from .render import Draw, RenderSurface
from functools import lru_cache
from .asset_loader import image_asset
from .config import (
    WHITE, BLACK, GOLD_COLOR, make_font,
)

@lru_cache(maxsize=128)
def _lit_sprite(image, color, strength):
    """Trace the existing alpha silhouette and keep the original sprite on top."""
    width, height = image.get_size()
    mask = pygame.mask.from_surface(image, 100)
    result = pygame.Surface((width + 6, height + 6), pygame.SRCALPHA)
    for radius, alpha in ((3, strength // 4), (2, strength // 2), (1, strength)):
        for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius)):
            mask.to_surface(result, setcolor=(*color, alpha), unsetcolor=None,
                            dest=(3 + dx, 3 + dy))
    result.blit(image, (3, 3))
    return result


@lru_cache(maxsize=128)
def _resize_sprite(image, size):
    return pygame.transform.smoothscale(image, size)


def blit_lit_sprite(target, image, position, color, strength=140, source=None):
    if isinstance(target, RenderSurface):
        if isinstance(source, str):
            source = image_asset(source)
        size = tuple(target.length(value) for value in image.get_size())
        sprite = _resize_sprite(source or image, size)
        x, y = target.point(position)
        target.blit_pixels(_lit_sprite(sprite, color, strength), (x - 3, y - 3))
        return
    target.blit(_lit_sprite(image, color, strength), (int(position[0]) - 3, int(position[1]) - 3))


SPRITE_VISUAL_SCALE = 1.12


# ── 绘图辅助 ─────────────────────────────────────────────────────────────────

def _scaled_size(size):
    return tuple(max(1, int(round(v * SPRITE_VISUAL_SCALE))) for v in size)

def _circle(surf, color, pos, radius, width=0):
    Draw.circle(surf, color, (int(pos[0]), int(pos[1])), int(radius), width)

def _rect(surf, color, rect, width=0, border_radius=0):
    Draw.rect(surf, color, rect, width, border_radius)

def _ellipse(surf, color, rect, width=0):
    Draw.ellipse(surf, color, rect, width)

def _polygon(surf, color, points, width=0):
    Draw.polygon(surf, color, [(int(p[0]), int(p[1])) for p in points], width)

def _line(surf, color, start, end, width=1):
    Draw.line(surf, color, (int(start[0]), int(start[1])), (int(end[0]), int(end[1])), width)

def _aaline(surf, color, start, end):
    Draw.aaline(surf, color, (int(start[0]), int(start[1])), (int(end[0]), int(end[1])))


def make_sprite(size, draw_fn):
    """创建带透明通道的精灵Surface。"""
    s = pygame.Surface(size, pygame.SRCALPHA)
    draw_fn(s)
    return s


def make_player_surface(asset_name='players/player1.png'):
    """渔夫——戴斗笠、披蓑衣、持鱼竿的Q版形象（基础角色尺寸已降低 30%）。"""
    img = image_asset(asset_name, _scaled_size((67, 67)))
    if not img and asset_name != 'players/player.png':
        img = image_asset('players/player.png', _scaled_size((67, 67)))
    if img:
        return img
    def draw(surf):
        w, h = surf.get_size()  # 80x80
        cx, cy = w // 2, h // 2

        # -- 阴影 --
        _ellipse(surf, (0, 0, 0, 40), (cx - 16, cy + 28, 32, 8))

        # -- 蓑衣（身体） --
        # 外层蓑衣（棕色编织）
        _ellipse(surf, (120, 80, 40), (cx - 16, cy - 2, 32, 30))
        _ellipse(surf, (140, 100, 50), (cx - 14, cy, 28, 28))
        # 蓑衣纹理线条
        for si in range(-10, 12, 4):
            _aaline(surf, (100, 60, 30), (cx + si, cy - 4), (cx + si + 6, cy + 26))
        # 蓑衣下摆
        for si in range(-14, 16, 5):
            _aaline(surf, (160, 110, 50), (cx + si, cy + 20), (cx + si, cy + 28))
        # 腰带
        _rect(surf, (80, 50, 20), (cx - 14, cy + 10, 28, 4), border_radius=2)

        # -- 手臂 --
        _line(surf, (210, 180, 140), (cx - 14, cy + 4), (cx - 30, cy + 12), 5)
        _line(surf, (210, 180, 140), (cx + 14, cy + 4), (cx + 32, cy + 12), 5)
        # 手
        _circle(surf, (230, 200, 160), (cx - 30, cy + 12), 4)
        _circle(surf, (230, 200, 160), (cx + 32, cy + 12), 4)

        # -- 鱼竿（右手持） --
        rod_x, rod_y = cx + 32, cy + 12
        _line(surf, (140, 90, 50), (rod_x, rod_y), (rod_x + 16, rod_y - 34), 3)
        _line(surf, (160, 110, 60), (rod_x + 16, rod_y - 34), (rod_x + 30, rod_y - 40), 2)
        # 鱼线
        _aaline(surf, (180, 180, 180), (rod_x + 30, rod_y - 40), (rod_x + 28, rod_y + 8))
        # 鱼饵
        _circle(surf, (255, 80, 30), (rod_x + 28, rod_y + 10), 2)

        # -- 头 --
        _circle(surf, (240, 210, 170), (cx, cy - 18), 11)
        _circle(surf, (255, 230, 190), (cx - 2, cy - 21), 5)  # 脸部高光

        # -- 眼睛 --
        _circle(surf, (255, 255, 255), (cx - 5, cy - 20), 4)
        _circle(surf, (255, 255, 255), (cx + 5, cy - 20), 4)
        _circle(surf, (30, 30, 30), (cx - 4, cy - 20), 2)
        _circle(surf, (30, 30, 30), (cx + 6, cy - 20), 2)
        _circle(surf, (255, 255, 255), (cx - 5, cy - 21), 1)  # 眼神光
        _circle(surf, (255, 255, 255), (cx + 5, cy - 21), 1)

        # -- 鼻子 --
        _circle(surf, (220, 170, 130), (cx, cy - 17), 2)

        # -- 微笑 --
        _aaline(surf, (140, 80, 40), (cx - 3, cy - 13), (cx - 1, cy - 11))
        _aaline(surf, (140, 80, 40), (cx + 1, cy - 11), (cx + 3, cy - 13))

        # -- 腮红 --
        _circle(surf, (255, 180, 160, 60), (cx - 8, cy - 15), 3)
        _circle(surf, (255, 180, 160, 60), (cx + 8, cy - 15), 3)

        # -- 斗笠 --
        _polygon(surf, (180, 140, 80), [(cx - 18, cy - 28), (cx, cy - 48), (cx + 18, cy - 28)])
        _polygon(surf, (200, 155, 90), [(cx - 15, cy - 28), (cx, cy - 43), (cx + 15, cy - 28)])
        # 斗笠顶部圆钮
        _circle(surf, (160, 120, 60), (cx, cy - 45), 3)
        # 斗笠纹理
        for dx in [-10, -5, 0, 5, 10]:
            _aaline(surf, (160, 120, 70), (dx + cx, cy - 28), (cx, cy - 44))
        # 斗笠帽檐
        _rect(surf, (140, 100, 50), (cx - 20, cy - 30, 40, 5), border_radius=2)
        _rect(surf, (120, 80, 40), (cx - 18, cy - 29, 36, 3), border_radius=1)

        # -- 腿 --
        _rect(surf, (70, 60, 50), (cx - 10, cy + 18, 8, 12), border_radius=2)
        _rect(surf, (70, 60, 50), (cx + 2, cy + 18, 8, 12), border_radius=2)

        # -- 草鞋 --
        _rect(surf, (160, 140, 80), (cx - 14, cy + 28, 14, 7), border_radius=3)
        _rect(surf, (160, 140, 80), (cx + 0, cy + 28, 14, 7), border_radius=3)
        _rect(surf, (140, 120, 60), (cx - 14, cy + 30, 14, 3), border_radius=1)
        _rect(surf, (140, 120, 60), (cx + 0, cy + 30, 14, 3), border_radius=1)

    return make_sprite(_scaled_size((67, 67)), draw)


def make_fire_player_surface():
    """火人战士——火焰铠甲、烈焰大剑的炫酷形象。"""
    img = image_asset('players/player_fire.png', _scaled_size((80, 80)))
    if img:
        return img
    def draw(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2

        # -- 脚下火焰光环 --
        _ellipse(surf, (255, 40, 20, 50), (cx - 18, cy + 27, 36, 8))
        for fi in range(3):
            fx = cx - 10 + fi * 10
            _polygon(surf, (255, 120, 30, 80), [(fx, cy + 28), (fx + 3, cy + 36), (fx + 6, cy + 28)])
            _polygon(surf, (255, 160, 50, 80), [(fx + 2, cy + 26), (fx + 4, cy + 34), (fx + 6, cy + 26)])

        # -- 火焰披风 --
        _polygon(surf, (200, 40, 10, 100), [(cx - 14, cy - 2), (cx - 22, cy + 22), (cx - 8, cy + 26), (cx, cy - 2)])
        _polygon(surf, (200, 40, 10, 100), [(cx + 14, cy - 2), (cx + 22, cy + 22), (cx + 8, cy + 26), (cx, cy - 2)])
        for px in [-18, 18]:
            for py_off in range(4):
                _aaline(surf, (255, 100, 30, 80), (cx + px, cy + 4 + py_off * 5), (cx + px + px * 0.2, cy + 12 + py_off * 5))

        # -- 身体/铠甲 --
        _rect(surf, (180, 30, 15), (cx - 14, cy - 4, 28, 24), border_radius=4)
        _rect(surf, (200, 40, 20), (cx - 12, cy - 2, 24, 20), border_radius=3)
        # 铠甲高光
        _rect(surf, (240, 80, 40, 80), (cx - 6, cy, 12, 8), border_radius=2)
        # 胸甲火焰纹
        for fx in [-6, 0, 6]:
            _polygon(surf, (255, 140, 30, 80), [(cx + fx - 3, cy + 6), (cx + fx, cy + 2), (cx + fx + 3, cy + 6)])

        # -- 腰带 --
        _rect(surf, (140, 15, 8), (cx - 14, cy + 10, 28, 5), border_radius=1)
        _rect(surf, (255, 180, 40), (cx - 4, cy + 9, 8, 7), border_radius=2)
        _circle(surf, (255, 220, 80), (cx, cy + 12), 3)

        # -- 护臂/肩甲 --
        _circle(surf, (255, 80, 30), (cx - 28, cy + 4), 8)
        _circle(surf, (255, 100, 40), (cx - 28, cy + 4), 6)
        _circle(surf, (255, 80, 30), (cx + 28, cy + 4), 8)
        _circle(surf, (255, 100, 40), (cx + 28, cy + 4), 6)
        # 火焰护肩
        for sa in [-28, 28]:
            for fi in range(3):
                sx = cx + sa - 4 + fi * 4
                _polygon(surf, (255, 180, 60, 100), [(sx, cy + 2), (sx + 2, cy - 4), (sx + 4, cy + 2)])

        # -- 手臂 --
        _line(surf, (255, 180, 130), (cx - 14, cy + 4), (cx - 28, cy + 10), 5)
        _line(surf, (255, 180, 130), (cx + 14, cy + 4), (cx + 32, cy + 10), 5)
        _circle(surf, (255, 200, 150), (cx - 28, cy + 10), 4)
        _circle(surf, (255, 200, 150), (cx + 32, cy + 10), 4)

        # -- 烈焰大剑 (右手) --
        sword_x = cx + 32
        sword_y = cy + 10
        # 剑柄
        _rect(surf, (100, 80, 60), (sword_x - 2, sword_y - 4, 6, 14), border_radius=2)
        _rect(surf, (180, 140, 90), (sword_x - 1, sword_y - 3, 4, 12), border_radius=1)
        _circle(surf, (255, 200, 60), (sword_x + 1, sword_y - 4), 3)
        # 剑身（火焰形）
        _polygon(surf, (255, 180, 40), [(sword_x + 5, sword_y - 2), (sword_x + 3, sword_y - 28), (sword_x + 10, sword_y - 16),
                                        (sword_x + 5, sword_y - 6)])
        _polygon(surf, (255, 100, 20), [(sword_x + 4, sword_y - 4), (sword_x + 2, sword_y - 22), (sword_x + 8, sword_y - 12)])
        _polygon(surf, (255, 220, 100), [(sword_x + 5, sword_y - 2), (sword_x + 4, sword_y - 16), (sword_x + 7, sword_y - 8)])
        # 剑尖火焰粒子
        _circle(surf, (255, 255, 150, 120), (sword_x + 5, sword_y - 28), 3)
        _circle(surf, (255, 200, 80, 100), (sword_x + 3, sword_y - 30), 2)

        # -- 头 --
        _circle(surf, (255, 200, 140), (cx, cy - 16), 10)
        _circle(surf, (255, 230, 180), (cx - 2, cy - 19), 5)

        # -- 火焰头盔 --
        _polygon(surf, (255, 70, 20), [(cx - 16, cy - 26), (cx, cy - 50), (cx + 16, cy - 26)])
        _polygon(surf, (255, 120, 40), [(cx - 12, cy - 26), (cx, cy - 44), (cx + 12, cy - 26)])
        # 头盔火焰装饰
        for fi in range(4):
            fx = cx - 9 + fi * 6
            _polygon(surf, (255, 180, 50, 150), [(fx, cy - 36), (fx + 2, cy - 48), (fx + 4, cy - 36)])
        # 头盔前额护甲
        _rect(surf, (200, 50, 15), (cx - 14, cy - 28, 28, 4), border_radius=2)
        _rect(surf, (240, 80, 30, 120), (cx - 8, cy - 27, 16, 2), border_radius=1)

        # -- 眼睛（发光） --
        _circle(surf, (255, 255, 100), (cx - 5, cy - 18), 3)
        _circle(surf, (255, 255, 100), (cx + 5, cy - 18), 3)
        _circle(surf, (255, 150, 30), (cx - 5, cy - 18), 2)
        _circle(surf, (255, 150, 30), (cx + 5, cy - 18), 2)
        _circle(surf, (255, 255, 255), (cx - 4, cy - 19), 1)
        _circle(surf, (255, 255, 255), (cx + 6, cy - 19), 1)

        # -- 嘴 --
        _aaline(surf, (160, 40, 10), (cx - 3, cy - 12), (cx + 3, cy - 12))
        _aaline(surf, (200, 80, 20), (cx - 3, cy - 12), (cx - 1, cy - 11))
        _aaline(surf, (200, 80, 20), (cx + 1, cy - 11), (cx + 3, cy - 12))

        # -- 腿/裤 --
        _rect(surf, (80, 20, 20), (cx - 12, cy + 15, 10, 12), border_radius=2)
        _rect(surf, (80, 20, 20), (cx + 2, cy + 15, 10, 12), border_radius=2)
        # 裤子火焰纹
        for lx in [-10, 4]:
            _line(surf, (255, 80, 20, 60), (cx + lx, cy + 18), (cx + lx + 3, cy + 24), 2)

        # -- 战靴 --
        _rect(surf, (160, 50, 20), (cx - 14, cy + 26, 14, 6), border_radius=3)
        _rect(surf, (160, 50, 20), (cx + 0, cy + 26, 14, 6), border_radius=3)
        _rect(surf, (200, 70, 30, 100), (cx - 12, cy + 27, 10, 3), border_radius=1)
        _rect(surf, (200, 70, 30, 100), (cx + 2, cy + 27, 10, 3), border_radius=1)

    return make_sprite(_scaled_size((80, 80)), draw)


def make_ice_player_surface():
    """冰人战士——冰晶铠甲、寒冰长剑的凛冽形象。"""
    img = image_asset('players/player_ice.png', _scaled_size((80, 80)))
    if img:
        return img
    def draw(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2

        # -- 脚下冰晶光环 --
        _ellipse(surf, (60, 140, 220, 60), (cx - 18, cy + 27, 36, 8))
        for fi in range(3):
            fx = cx - 10 + fi * 10
            _polygon(surf, (150, 210, 255, 100), [(fx, cy + 28), (fx + 3, cy + 36), (fx + 6, cy + 28)])
            _polygon(surf, (180, 230, 255, 100), [(fx + 2, cy + 26), (fx + 4, cy + 34), (fx + 6, cy + 26)])

        # -- 冰霜披风 --
        _polygon(surf, (40, 100, 180, 100), [(cx - 14, cy - 2), (cx - 24, cy + 20), (cx - 8, cy + 26), (cx, cy - 2)])
        _polygon(surf, (40, 100, 180, 100), [(cx + 14, cy - 2), (cx + 24, cy + 20), (cx + 8, cy + 26), (cx, cy - 2)])
        for px in [-20, 20]:
            for py_off in range(4):
                _aaline(surf, (120, 180, 255, 80), (cx + px, cy + 4 + py_off * 5), (cx + int(px * 0.7), cy + 12 + py_off * 5))

        # -- 身体/冰甲 --
        _rect(surf, (40, 100, 200), (cx - 14, cy - 4, 28, 24), border_radius=4)
        _rect(surf, (60, 130, 220), (cx - 12, cy - 2, 24, 20), border_radius=3)
        # 铠甲高光和冰晶纹理
        _rect(surf, (150, 200, 255, 80), (cx - 4, cy, 8, 8), border_radius=2)
        _line(surf, (100, 170, 240), (cx - 8, cy + 2), (cx + 8, cy + 8), 1)
        _line(surf, (100, 170, 240), (cx + 8, cy + 2), (cx - 8, cy + 8), 1)

        # -- 腰带 --
        _rect(surf, (20, 60, 140), (cx - 14, cy + 10, 28, 5), border_radius=1)
        _rect(surf, (150, 210, 255), (cx - 4, cy + 9, 8, 7), border_radius=2)
        _circle(surf, (200, 240, 255), (cx, cy + 12), 3)

        # -- 护臂/冰霜肩甲 --
        _circle(surf, (100, 180, 255), (cx - 28, cy + 4), 8)
        _circle(surf, (140, 210, 255), (cx - 28, cy + 4), 6)
        _circle(surf, (100, 180, 255), (cx + 28, cy + 4), 8)
        _circle(surf, (140, 210, 255), (cx + 28, cy + 4), 6)
        for sa in [-28, 28]:
            for fi in range(3):
                sx = cx + sa - 4 + fi * 4
                _polygon(surf, (180, 230, 255, 100), [(sx, cy + 2), (sx + 2, cy - 4), (sx + 4, cy + 2)])

        # -- 手臂 --
        _line(surf, (180, 210, 255), (cx - 14, cy + 4), (cx - 28, cy + 10), 5)
        _line(surf, (180, 210, 255), (cx + 14, cy + 4), (cx + 32, cy + 10), 5)
        _circle(surf, (200, 230, 255), (cx - 28, cy + 10), 4)
        _circle(surf, (200, 230, 255), (cx + 32, cy + 10), 4)

        # -- 寒冰长剑 (右手) --
        sword_x = cx + 32
        sword_y = cy + 10
        _rect(surf, (60, 80, 140), (sword_x - 2, sword_y - 4, 6, 14), border_radius=2)
        _rect(surf, (180, 210, 255), (sword_x - 1, sword_y - 3, 4, 12), border_radius=1)
        _circle(surf, (200, 240, 255), (sword_x + 1, sword_y - 4), 3)
        # 剑身
        _polygon(surf, (100, 180, 255), [(sword_x + 5, sword_y - 2), (sword_x + 3, sword_y - 28), (sword_x + 10, sword_y - 16),
                                         (sword_x + 5, sword_y - 6)])
        _polygon(surf, (150, 220, 255), [(sword_x + 4, sword_y - 4), (sword_x + 2, sword_y - 22), (sword_x + 8, sword_y - 12)])
        _polygon(surf, (200, 240, 255), [(sword_x + 5, sword_y - 2), (sword_x + 4, sword_y - 16), (sword_x + 7, sword_y - 8)])
        # 剑尖冰晶
        _circle(surf, (220, 250, 255, 120), (sword_x + 5, sword_y - 28), 3)
        _circle(surf, (255, 255, 255, 150), (sword_x + 4, sword_y - 30), 2)

        # -- 头 --
        _circle(surf, (200, 225, 255), (cx, cy - 16), 10)
        _circle(surf, (230, 245, 255), (cx - 2, cy - 19), 5)

        # -- 冰晶头盔 --
        _polygon(surf, (60, 140, 240), [(cx - 16, cy - 26), (cx, cy - 50), (cx + 16, cy - 26)])
        _polygon(surf, (100, 180, 255), [(cx - 12, cy - 26), (cx, cy - 44), (cx + 12, cy - 26)])
        for ci in range(4):
            cx2 = cx - 9 + ci * 6
            _polygon(surf, (180, 225, 255, 150), [(cx2, cy - 36), (cx2 + 2, cy - 48), (cx2 + 4, cy - 36)])
        _rect(surf, (40, 100, 200), (cx - 14, cy - 28, 28, 4), border_radius=2)
        _rect(surf, (180, 225, 255, 120), (cx - 8, cy - 27, 16, 2), border_radius=1)

        # -- 眼睛（冰蓝发光） --
        _circle(surf, (180, 240, 255), (cx - 5, cy - 18), 3)
        _circle(surf, (180, 240, 255), (cx + 5, cy - 18), 3)
        _circle(surf, (80, 150, 255), (cx - 5, cy - 18), 2)
        _circle(surf, (80, 150, 255), (cx + 5, cy - 18), 2)
        _circle(surf, (255, 255, 255), (cx - 4, cy - 19), 1)
        _circle(surf, (255, 255, 255), (cx + 6, cy - 19), 1)

        # -- 嘴 --
        _aaline(surf, (60, 120, 200), (cx - 3, cy - 12), (cx + 3, cy - 12))

        # -- 腿/裤 --
        _rect(surf, (30, 50, 100), (cx - 12, cy + 15, 10, 12), border_radius=2)
        _rect(surf, (30, 50, 100), (cx + 2, cy + 15, 10, 12), border_radius=2)
        for lx in [-10, 4]:
            _line(surf, (100, 160, 230, 60), (cx + lx, cy + 18), (cx + lx + 3, cy + 24), 2)

        # -- 冰靴 --
        _rect(surf, (100, 160, 220), (cx - 14, cy + 26, 14, 6), border_radius=3)
        _rect(surf, (100, 160, 220), (cx + 0, cy + 26, 14, 6), border_radius=3)
        _rect(surf, (150, 200, 240, 100), (cx - 12, cy + 27, 10, 3), border_radius=1)
        _rect(surf, (150, 200, 240, 100), (cx + 2, cy + 27, 10, 3), border_radius=1)

    return make_sprite(_scaled_size((80, 80)), draw)


def make_radiation_player_surface():
    """辐射工程师——高科技防护服、辐射装置。"""
    img = image_asset('players/player_radiation.png', _scaled_size((80, 80)))
    if img:
        return img
    def draw(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2

        # -- 脚下辐射光环 --
        _ellipse(surf, (80, 255, 50, 40), (cx - 16, cy + 27, 32, 8))
        _circle(surf, (100, 255, 50, 30), (cx, cy + 28), 12, 1)

        # -- 身体/防护服 --
        _rect(surf, (160, 70, 220), (cx - 14, cy - 4, 28, 24), border_radius=4)
        _rect(surf, (180, 90, 230), (cx - 12, cy - 2, 24, 20), border_radius=3)
        # 防护服高光
        _rect(surf, (200, 140, 255, 60), (cx - 4, cy, 8, 8), border_radius=2)
        # 防护服接缝
        _line(surf, (120, 50, 200), (cx, cy - 4), (cx, cy + 10), 1)
        _line(surf, (120, 50, 200), (cx - 10, cy + 6), (cx + 10, cy + 6), 1)

        # -- 胸部辐射标志 --
        # 背景辉光
        _circle(surf, (255, 255, 80, 40), (cx, cy + 3), 11)
        _circle(surf, (255, 220, 30), (cx, cy + 3), 8)
        _circle(surf, (255, 255, 100, 80), (cx, cy + 3), 6)
        _circle(surf, (180, 80, 255), (cx, cy + 3), 4)
        # 辐射扇叶
        for a in [0, 120, 240]:
            rad_a = a * math.pi / 180
            px = cx + int(5 * math.cos(rad_a))
            py = cy + 3 + int(5 * math.sin(rad_a))
            _ellipse(surf, (255, 220, 30), (px - 2, py - 5, 4, 10))
            # 扇叶高光
            _ellipse(surf, (255, 255, 150, 120), (px - 1, py - 4, 2, 6))

        # -- 腰带 --
        _rect(surf, (80, 30, 150), (cx - 14, cy + 10, 28, 5), border_radius=1)
        _rect(surf, (100, 255, 50), (cx - 4, cy + 9, 8, 7), border_radius=2)
        # 腰带指示灯
        _circle(surf, (100, 255, 50), (cx - 8, cy + 12), 2)
        _circle(surf, (100, 255, 50), (cx, cy + 12), 2)
        _circle(surf, (100, 255, 50), (cx + 8, cy + 12), 2)

        # -- 护肩/肩甲 --
        _circle(surf, (140, 60, 200), (cx - 28, cy + 4), 7)
        _circle(surf, (140, 60, 200), (cx + 28, cy + 4), 7)
        _circle(surf, (180, 100, 220, 80), (cx - 28, cy + 4), 5)
        _circle(surf, (180, 100, 220, 80), (cx + 28, cy + 4), 5)
        # 肩部指示灯
        _circle(surf, (100, 255, 50), (cx - 28, cy + 4), 2)
        _circle(surf, (100, 255, 50), (cx + 28, cy + 4), 2)

        # -- 手臂 --
        _line(surf, (200, 130, 240), (cx - 14, cy + 4), (cx - 28, cy + 10), 5)
        _line(surf, (200, 130, 240), (cx + 14, cy + 4), (cx + 32, cy + 10), 5)
        _circle(surf, (180, 220, 180), (cx - 28, cy + 10), 4)
        _circle(surf, (180, 220, 180), (cx + 32, cy + 10), 4)

        # -- 辐射装置 (右手) --
        dev_x = cx + 32
        dev_y = cy + 10
        _rect(surf, (100, 60, 160), (dev_x - 2, dev_y - 6, 10, 14), border_radius=3)
        _rect(surf, (140, 90, 200, 120), (dev_x - 4, dev_y - 8, 6, 18), border_radius=2)
        _rect(surf, (160, 100, 180), (dev_x - 1, dev_y - 4, 8, 10), border_radius=2)
        # 辐射能量核心
        _circle(surf, (100, 255, 50, 60), (dev_x + 3, dev_y + 2), 7)
        _circle(surf, (180, 255, 80), (dev_x + 3, dev_y + 2), 5)
        _circle(surf, (255, 255, 200), (dev_x + 3, dev_y + 2), 3)
        # 能量波纹
        _circle(surf, (100, 255, 50, 40), (dev_x + 3, dev_y + 2), 9, 1)

        # -- 头/头盔 --
        _rect(surf, (80, 40, 140), (cx - 16, cy - 32, 32, 20), border_radius=9)
        _rect(surf, (100, 60, 160), (cx - 14, cy - 30, 28, 16), border_radius=7)
        # 头盔高光
        _ellipse(surf, (140, 100, 200, 80), (cx - 6, cy - 34, 12, 6))

        # -- 面罩/护目镜 --
        _rect(surf, (40, 20, 80), (cx - 12, cy - 27, 24, 10), border_radius=4)
        _rect(surf, (60, 180, 100, 80), (cx - 10, cy - 25, 20, 7), border_radius=3)
        # 护目镜镜片
        _circle(surf, (100, 255, 50, 80), (cx - 7, cy - 22), 6)
        _circle(surf, (100, 255, 50, 80), (cx + 7, cy - 22), 6)
        _circle(surf, (150, 255, 100, 100), (cx - 6, cy - 23), 4)
        _circle(surf, (150, 255, 100, 100), (cx + 8, cy - 23), 4)
        _circle(surf, (255, 255, 255, 150), (cx - 8, cy - 24), 2)  # 镜片反光
        _circle(surf, (255, 255, 255, 150), (cx + 6, cy - 24), 2)

        # -- 脸（头盔内） --
        _circle(surf, (220, 200, 170), (cx, cy - 16), 8)
        _circle(surf, (40, 20, 60), (cx - 3, cy - 16), 2)
        _circle(surf, (40, 20, 60), (cx + 3, cy - 16), 2)

        # -- 呼吸器 --
        _rect(surf, (60, 60, 70), (cx - 5, cy - 12, 10, 6), border_radius=3)
        _ellipse(surf, (80, 180, 80, 80), (cx - 3, cy - 11, 6, 4))

        # -- 腿/裤 --
        _rect(surf, (60, 30, 100), (cx - 12, cy + 15, 10, 12), border_radius=2)
        _rect(surf, (60, 30, 100), (cx + 2, cy + 15, 10, 12), border_radius=2)
        # 裤子上的管线
        for lx in [-10, 4]:
            _line(surf, (100, 255, 50, 40), (cx + lx + 3, cy + 18), (cx + lx + 3, cy + 24), 2)

        # -- 防护靴 --
        _rect(surf, (80, 40, 120), (cx - 14, cy + 26, 14, 7), border_radius=3)
        _rect(surf, (80, 40, 120), (cx + 0, cy + 26, 14, 7), border_radius=3)
        _rect(surf, (100, 60, 140, 80), (cx - 12, cy + 28, 10, 3), border_radius=1)
        _rect(surf, (100, 60, 140, 80), (cx + 2, cy + 28, 10, 3), border_radius=1)
        # 靴子指示灯
        _circle(surf, (100, 255, 50, 60), (cx - 7, cy + 29), 2)
        _circle(surf, (100, 255, 50, 60), (cx + 7, cy + 29), 2)

    return make_sprite(_scaled_size((80, 80)), draw)


def make_water_player_surface():
    """水人——水流护甲和潮汐法杖。"""
    img = image_asset('players/player_water.png', _scaled_size((96, 96)))
    if img:
        return img
    def draw(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2
        _ellipse(surf, (40, 180, 220, 55), (cx - 19, cy + 27, 38, 8))
        for r in (20, 15, 10):
            _circle(surf, (80, 220, 240, 30), (cx, cy + 8), r, 2)
        _polygon(surf, (20, 120, 190, 115), [(cx - 16, cy - 3), (cx - 25, cy + 22), (cx - 8, cy + 27), (cx, cy - 2)])
        _polygon(surf, (20, 120, 190, 115), [(cx + 16, cy - 3), (cx + 25, cy + 22), (cx + 8, cy + 27), (cx, cy - 2)])
        _rect(surf, (45, 160, 210), (cx - 14, cy - 4, 28, 24), border_radius=5)
        _rect(surf, (70, 205, 230), (cx - 11, cy - 2, 22, 20), border_radius=4)
        _circle(surf, (190, 250, 255, 140), (cx, cy + 4), 7)
        _circle(surf, (40, 140, 210), (cx, cy + 4), 3)
        _line(surf, (170, 235, 255), (cx - 14, cy + 4), (cx - 29, cy + 11), 5)
        _line(surf, (170, 235, 255), (cx + 14, cy + 4), (cx + 31, cy + 10), 5)
        _circle(surf, (210, 250, 255), (cx - 29, cy + 11), 4)
        _circle(surf, (210, 250, 255), (cx + 31, cy + 10), 4)
        _line(surf, (80, 210, 230), (cx + 31, cy + 10), (cx + 39, cy - 26), 3)
        _circle(surf, (160, 245, 255, 160), (cx + 39, cy - 26), 7)
        _circle(surf, (230, 255, 255, 220), (cx + 39, cy - 26), 3)
        _circle(surf, (190, 235, 245), (cx, cy - 16), 10)
        _circle(surf, (230, 255, 255), (cx - 2, cy - 19), 5)
        _polygon(surf, (40, 170, 220), [(cx - 16, cy - 26), (cx, cy - 48), (cx + 16, cy - 26)])
        _polygon(surf, (90, 220, 240), [(cx - 11, cy - 26), (cx, cy - 42), (cx + 11, cy - 26)])
        for bx in (-9, -3, 3, 9):
            _circle(surf, (190, 250, 255, 130), (cx + bx, cy - 35), 3)
        _circle(surf, (180, 250, 255), (cx - 5, cy - 18), 3)
        _circle(surf, (180, 250, 255), (cx + 5, cy - 18), 3)
        _circle(surf, (30, 110, 180), (cx - 5, cy - 18), 2)
        _circle(surf, (30, 110, 180), (cx + 5, cy - 18), 2)
        _aaline(surf, (40, 120, 180), (cx - 3, cy - 12), (cx + 3, cy - 12))
        _rect(surf, (30, 95, 150), (cx - 12, cy + 15, 10, 12), border_radius=2)
        _rect(surf, (30, 95, 150), (cx + 2, cy + 15, 10, 12), border_radius=2)
        _rect(surf, (75, 190, 220), (cx - 14, cy + 26, 14, 6), border_radius=3)
        _rect(surf, (75, 190, 220), (cx, cy + 26, 14, 6), border_radius=3)
    return make_sprite(_scaled_size((80, 80)), draw)


# ═══════════════════════════════════════════════════════════════════════════════
#  敌人精灵 —— 优化版：更生动的海洋生物
# ═══════════════════════════════════════════════════════════════════════════════

def make_enemy_surface(key):
    """按 key 生成 Q 版海洋敌人精灵。"""
    is_large = key in ('octopus', 'shark')
    base_size = (100, 86) if is_large else (60, 52)
    if key == 'seahorse':
        base_size = (30, 56)
    elif key == 'zongzong':
        base_size = (72, 66)
    elif key in ('crab_red', 'jellyfish', 'octopus_pink', 'starfish', 'turtle'):
        base_size = (56, 56)
    size = _scaled_size(base_size)
    asset_name = 'bosses/zongzong.png' if key == 'zongzong' else f'enemies/enemy_{key}.png'
    img = image_asset(asset_name, size)
    if img:
        return img

    def draw_lobster(surf):
        w, h = surf.get_size()  # 60x52
        cx, cy = w // 2, h // 2

        # 尾巴
        _ellipse(surf, (200, 30, 25), (cx - 14, cy + 4, 28, 20))
        _ellipse(surf, (180, 20, 20), (cx - 10, cy + 10, 20, 14))
        # 尾巴纹理
        for si in range(-8, 10, 4):
            _aaline(surf, (160, 20, 20), (cx + si, cy + 6), (cx + si, cy + 16))
        # 尾扇
        _polygon(surf, (200, 30, 30), [(cx - 6, cy + 18), (cx - 12, cy + 30), (cx, cy + 30), (cx + 6, cy + 18)])
        _polygon(surf, (220, 50, 40), [(cx - 4, cy + 20), (cx - 8, cy + 28), (cx, cy + 28), (cx + 4, cy + 20)])

        # 身体
        _ellipse(surf, (220, 40, 40), (cx - 16, cy - 8, 32, 22))
        _ellipse(surf, (240, 60, 50), (cx - 14, cy - 7, 28, 18))
        # 身体高光
        _ellipse(surf, (255, 120, 80, 60), (cx - 8, cy - 6, 8, 10))

        # 头部
        _ellipse(surf, (200, 30, 30), (cx - 12, cy - 14, 24, 18))
        _ellipse(surf, (220, 50, 40), (cx - 10, cy - 13, 20, 14))

        # 触角
        _aaline(surf, (200, 30, 30), (cx - 4, cy - 18), (cx - 14, cy - 34))
        _aaline(surf, (200, 30, 30), (cx + 4, cy - 18), (cx + 14, cy - 34))
        _circle(surf, (240, 60, 40), (cx - 14, cy - 34), 3)
        _circle(surf, (240, 60, 40), (cx + 14, cy - 34), 3)

        # 眼睛
        _circle(surf, (255, 255, 255), (cx - 6, cy - 10), 6)
        _circle(surf, (255, 255, 255), (cx + 6, cy - 10), 6)
        _circle(surf, (255, 255, 255), (cx - 5, cy - 11), 5)
        _circle(surf, (255, 255, 255), (cx + 7, cy - 11), 5)
        _circle(surf, (20, 20, 20), (cx - 5, cy - 10), 3)
        _circle(surf, (20, 20, 20), (cx + 7, cy - 10), 3)
        _circle(surf, (255, 255, 255), (cx - 6, cy - 11), 1)
        _circle(surf, (255, 255, 255), (cx + 6, cy - 11), 1)
        # 凶眉
        _aaline(surf, (60, 20, 20), (cx - 9, cy - 14), (cx - 1, cy - 12))
        _aaline(surf, (60, 20, 20), (cx + 9, cy - 14), (cx + 1, cy - 12))

        # 钳子
        _line(surf, (220, 50, 50), (cx - 16, cy - 4), (cx - 30, cy - 14), 4)
        _line(surf, (220, 50, 50), (cx + 16, cy - 4), (cx + 30, cy - 14), 4)
        _circle(surf, (240, 60, 40), (cx - 30, cy - 14), 5)
        _circle(surf, (240, 60, 40), (cx + 30, cy - 14), 5)
        _circle(surf, (255, 100, 60), (cx - 31, cy - 15), 3)
        _circle(surf, (255, 100, 60), (cx + 29, cy - 15), 3)
        # 钳子开口
        _aaline(surf, (200, 20, 20), (cx - 30, cy - 14), (cx - 34, cy - 16))
        _aaline(surf, (200, 20, 20), (cx + 30, cy - 14), (cx + 34, cy - 16))

        # 脚
        for i in range(3):
            ox = -10 + i * 10
            _line(surf, (200, 30, 30), (cx + ox, cy + 8), (cx + ox - 2, cy + 22), 2)

    def draw_crab(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2

        # 身体
        _ellipse(surf, (230, 90, 25), (cx - 18, cy - 6, 36, 28))
        _ellipse(surf, (255, 120, 40), (cx - 14, cy - 4, 28, 24))
        # 身体高光
        _ellipse(surf, (255, 160, 80, 70), (cx - 10, cy - 10, 8, 10))
        # 蟹壳纹理
        for si in range(-10, 12, 4):
            _aaline(surf, (200, 70, 20), (cx + si, cy - 2), (cx + si, cy + 10))

        # 眼睛柄
        _line(surf, (230, 90, 25), (cx - 8, cy - 14), (cx - 10, cy - 24), 3)
        _line(surf, (230, 90, 25), (cx + 8, cy - 14), (cx + 10, cy - 24), 3)
        # 眼睛
        _circle(surf, (255, 255, 255), (cx - 10, cy - 26), 5)
        _circle(surf, (255, 255, 255), (cx + 10, cy - 26), 5)
        _circle(surf, (20, 20, 20), (cx - 9, cy - 26), 3)
        _circle(surf, (20, 20, 20), (cx + 11, cy - 26), 3)
        _circle(surf, (255, 255, 255), (cx - 10, cy - 27), 1)
        _circle(surf, (255, 255, 255), (cx + 10, cy - 27), 1)
        # 瞳孔
        _circle(surf, (60, 60, 60), (cx - 9, cy - 26), 1)
        _circle(surf, (60, 60, 60), (cx + 11, cy - 26), 1)

        # 嘴
        _aaline(surf, (180, 60, 15), (cx - 2, cy - 2), (cx + 2, cy - 2))
        _aaline(surf, (180, 60, 15), (cx - 2, cy - 2), (cx - 4, cy))
        _aaline(surf, (180, 60, 15), (cx + 2, cy - 2), (cx + 4, cy))

        # 大钳子
        _ellipse(surf, (220, 70, 20), (cx - 34, cy - 10, 18, 14))
        _ellipse(surf, (220, 70, 20), (cx + 16, cy - 10, 18, 14))
        _ellipse(surf, (240, 90, 30), (cx - 36, cy - 14, 14, 10))
        _ellipse(surf, (240, 90, 30), (cx + 22, cy - 14, 14, 10))
        # 钳子开口
        _aaline(surf, (180, 40, 10), (cx - 30, cy - 10), (cx - 24, cy - 6))
        _aaline(surf, (180, 40, 10), (cx + 30, cy - 10), (cx + 24, cy - 6))

        # 脚
        for i in range(3):
            ox = -10 + i * 10
            _line(surf, (200, 60, 18), (cx + ox, cy + 14), (cx + ox - 6, cy + 30), 2)
            _line(surf, (200, 60, 18), (cx + ox + 4, cy + 14), (cx + ox + 8, cy + 30), 2)

    def draw_goldfish(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2

        # 尾巴
        _polygon(surf, (255, 140, 20), [(cx - 14, cy + 2), (cx - 28, cy - 12), (cx - 26, cy + 8)])
        _polygon(surf, (255, 170, 50), [(cx - 12, cy + 2), (cx - 24, cy - 8), (cx - 22, cy + 6)])
        _polygon(surf, (255, 200, 80), [(cx - 10, cy + 2), (cx - 20, cy - 4), (cx - 18, cy + 4)])

        # 身体
        _ellipse(surf, (255, 180, 30), (cx - 14, cy - 10, 28, 22))
        _ellipse(surf, (255, 210, 70), (cx - 12, cy - 8, 24, 18))
        # 鳞片纹理
        for si in range(-8, 10, 3):
            _aaline(surf, (255, 180, 40), (cx + si, cy - 6), (cx + si + 1, cy + 6))

        # 背鳍
        _polygon(surf, (255, 160, 30), [(cx - 4, cy - 10), (cx - 8, cy - 22), (cx + 2, cy - 14)])
        _polygon(surf, (255, 200, 60), [(cx - 2, cy - 11), (cx - 6, cy - 19), (cx + 1, cy - 13)])
        # 腹鳍
        _polygon(surf, (255, 160, 30), [(cx - 4, cy + 10), (cx - 8, cy + 22), (cx + 2, cy + 14)])
        _polygon(surf, (255, 200, 60), [(cx - 2, cy + 11), (cx - 6, cy + 19), (cx + 1, cy + 13)])

        # 眼睛
        _circle(surf, (255, 255, 255), (cx + 8, cy - 4), 6)
        _circle(surf, (255, 255, 255), (cx + 9, cy - 5), 5)
        _circle(surf, (20, 20, 20), (cx + 10, cy - 4), 3)
        _circle(surf, (255, 255, 255), (cx + 9, cy - 5), 1)

        # 嘴
        _circle(surf, (220, 100, 20), (cx + 16, cy + 2), 3)
        _aaline(surf, (200, 80, 15), (cx + 16, cy + 2), (cx + 20, cy + 1))

        # 鳃
        _aaline(surf, (240, 150, 30), (cx - 2, cy - 4), (cx + 2, cy - 2))
        _aaline(surf, (240, 150, 30), (cx - 2, cy - 2), (cx + 2, cy))
        _aaline(surf, (240, 150, 30), (cx - 2, cy, 1), (cx + 2, cy + 2))

    def draw_octopus(surf):
        w, h = surf.get_size()  # 100x86
        cx, cy = w // 2, h // 2

        # 触手（底部）
        for i, (dx, dy) in enumerate([(-20, 22), (-14, 26), (-6, 30), (6, 30), (14, 26), (20, 22)]):
            ex = cx + dx * 1.5 + random.choice([-6, 0, 6])
            ey = cy + 20 + dy
            mid_x = cx + dx + (ex - cx - dx) * 0.5
            mid_y = cy + 16 + (ey - cy - 16) * 0.5
            _line(surf, (140, 40, 180), (cx + dx, cy + 16), (mid_x, mid_y), 7)
            _aaline(surf, (120, 30, 160), (mid_x, mid_y), (ex, ey))
            # 吸盘
            for si in range(2):
                sx = cx + dx + (ex - cx - dx) * (0.3 + si * 0.3)
                sy = cy + 16 + (ey - cy - 16) * (0.3 + si * 0.3)
                _circle(surf, (200, 120, 220, 80), (sx, sy), 2)

        # 身体
        _ellipse(surf, (150, 45, 190), (cx - 24, cy - 16, 48, 40))
        _ellipse(surf, (180, 70, 220), (cx - 20, cy - 14, 40, 34))
        _ellipse(surf, (200, 100, 240), (cx - 14, cy - 10, 28, 28))
        # 身体高光
        _ellipse(surf, (220, 140, 255, 60), (cx - 10, cy - 18, 10, 14))

        # 头部斑点
        for si in range(3):
            sx = cx - 8 + si * 8
            sy = cy - 8 + (si % 2) * 5
            _circle(surf, (200, 100, 240, 80), (sx, sy), 2)

        # 眼睛
        _circle(surf, (255, 255, 255), (cx - 12, cy - 4), 8)
        _circle(surf, (255, 255, 255), (cx + 12, cy - 4), 8)
        _circle(surf, (255, 255, 255), (cx - 11, cy - 5), 7)
        _circle(surf, (255, 255, 255), (cx + 13, cy - 5), 7)
        # 虹膜
        _circle(surf, (60, 20, 140), (cx - 11, cy - 4), 5)
        _circle(surf, (60, 20, 140), (cx + 13, cy - 4), 5)
        # 瞳孔
        _circle(surf, (20, 10, 60), (cx - 10, cy - 4), 3)
        _circle(surf, (20, 10, 60), (cx + 14, cy - 4), 3)
        _circle(surf, (255, 255, 255), (cx - 12, cy - 5), 1)
        _circle(surf, (255, 255, 255), (cx + 12, cy - 5), 1)

        # 嘴
        _ellipse(surf, (120, 20, 160), (cx - 4, cy + 4, 8, 5))
        _ellipse(surf, (140, 40, 180, 80), (cx - 3, cy + 5, 6, 3))

    def draw_shark(surf):
        w, h = surf.get_size()
        cx, cy = w // 2, h // 2

        # 身体
        _ellipse(surf, (100, 130, 180), (cx - 24, cy - 12, 48, 24))
        _ellipse(surf, (130, 160, 210), (cx - 20, cy - 10, 40, 20))
        _ellipse(surf, (160, 190, 230), (cx - 14, cy - 8, 28, 16))
        # 腹部
        _ellipse(surf, (220, 230, 240), (cx - 12, cy, 24, 14))

        # 尾鳍
        _polygon(surf, (100, 120, 160), [(cx - 22, cy - 2), (cx - 42, cy - 16), (cx - 36, cy - 2)])
        _polygon(surf, (100, 120, 160), [(cx - 22, cy + 2), (cx - 42, cy + 16), (cx - 36, cy + 2)])
        _polygon(surf, (120, 140, 180), [(cx - 20, cy), (cx - 38, cy - 12), (cx - 34, cy)])

        # 背鳍
        _polygon(surf, (100, 120, 160), [(cx - 4, cy - 12), (cx + 2, cy - 32), (cx + 8, cy - 12)])
        _polygon(surf, (130, 150, 190), [(cx - 2, cy - 12), (cx + 2, cy - 28), (cx + 6, cy - 12)])

        # 胸鳍
        _polygon(surf, (100, 120, 160), [(cx, cy + 8), (cx - 8, cy + 22), (cx + 4, cy + 10)])
        _polygon(surf, (100, 120, 160), [(cx + 2, cy + 10), (cx - 6, cy + 26), (cx + 6, cy + 12)])

        # 眼睛
        _circle(surf, (255, 255, 255), (cx + 14, cy - 6), 6)
        _circle(surf, (255, 255, 255), (cx + 15, cy - 7), 5)
        _circle(surf, (20, 20, 20), (cx + 17, cy - 6), 3)
        _circle(surf, (255, 255, 255), (cx + 16, cy - 7), 1)
        # 凶眼
        _aaline(surf, (60, 80, 100), (cx + 8, cy - 8), (cx + 18, cy - 4))

        # 嘴
        _aaline(surf, (60, 60, 80), (cx + 18, cy + 2), (cx + 28, cy + 2))
        _aaline(surf, (60, 60, 80), (cx + 18, cy + 2), (cx + 20, cy + 4))

        # 牙齿
        for tx in [22, 25, 28]:
            _polygon(surf, WHITE, [(cx + tx, cy + 1), (cx + tx + 1, cy - 2), (cx + tx + 2, cy + 1)])

        # 鳃裂
        for gx in [cx - 10, cx - 6, cx - 2]:
            _aaline(surf, (70, 100, 140), (gx, cy - 4), (gx - 2, cy + 6))

    drawers = {
        'lobster': draw_lobster,
        'crab': draw_crab,
        'goldfish': draw_goldfish,
        'octopus': draw_octopus,
        'shark': draw_shark,
    }
    fallback_key = {
        'crab_red': 'crab',
        'jellyfish': 'octopus',
        'octopus_pink': 'octopus',
        'seahorse': 'goldfish',
        'starfish': 'goldfish',
        'turtle': 'crab',
        # Keep missing-art/headless operation safe; release builds ship bespoke PNGs.
        'mecha_crab': 'crab', 'mecha_ray': 'shark', 'mecha_jelly': 'octopus',
        'ancient_nautilus': 'octopus', 'ancient_trilobite': 'lobster', 'ancient_ray': 'shark',
    }.get(key, key)
    return make_sprite(size, drawers[fallback_key])


# ═══════════════════════════════════════════════════════════════════════════════
#  Boss 精灵 —— 优化版：巨大化+威压感
# ═══════════════════════════════════════════════════════════════════════════════

def make_boss_surface(boss_key, size=(150, 140)):
    """每个 Boss 有独特的巨大化+发光设计。"""
    visual_size = _scaled_size(size)
    img = image_asset(f'bosses/{boss_key}.png', visual_size)
    if img:
        return img

    def draw_boss_lobster(surf):
        cx, cy = visual_size[0] // 2, visual_size[1] // 2

        # 外圈辉光
        for r in range(35, 15, -5):
            _circle(surf, (255, 40, 20, 15), (cx, cy + 8), r, 2)
        # 暗影
        _ellipse(surf, (100, 10, 10, 80), (cx - 24, cy + 30, 48, 10))

        # 尾巴
        _ellipse(surf, (180, 20, 20), (cx - 20, cy + 10, 40, 28))
        _ellipse(surf, (160, 15, 15), (cx - 14, cy + 16, 28, 20))
        for si in range(-10, 12, 4):
            _aaline(surf, (140, 15, 15), (cx + si, cy + 12), (cx + si, cy + 22))
        _polygon(surf, (180, 20, 20), [(cx - 8, cy + 26), (cx - 16, cy + 40), (cx, cy + 40), (cx + 8, cy + 26)])
        _polygon(surf, (200, 40, 30), [(cx - 4, cy + 28), (cx - 10, cy + 36), (cx, cy + 36), (cx + 4, cy + 28)])

        # 身体
        _ellipse(surf, (200, 30, 30), (cx - 24, cy - 4, 48, 30))
        _ellipse(surf, (220, 50, 40), (cx - 20, cy - 2, 40, 26))
        _ellipse(surf, (255, 80, 50, 60), (cx - 8, cy, 12, 14))

        # 头部
        _ellipse(surf, (180, 20, 20), (cx - 18, cy - 16, 36, 24))
        _ellipse(surf, (200, 40, 30), (cx - 14, cy - 14, 28, 20))

        # 触角
        _line(surf, (200, 30, 30), (cx - 4, cy - 22), (cx - 18, cy - 42), 5)
        _line(surf, (200, 30, 30), (cx + 4, cy - 22), (cx + 18, cy - 42), 5)
        _circle(surf, (255, 60, 40), (cx - 18, cy - 42), 6)
        _circle(surf, (255, 60, 40), (cx + 18, cy - 42), 6)

        # 发光眼睛
        _circle(surf, (255, 255, 100, 60), (cx - 9, cy - 10), 10)
        _circle(surf, (255, 255, 100, 60), (cx + 9, cy - 10), 10)
        _circle(surf, (255, 255, 180), (cx - 9, cy - 10), 8)
        _circle(surf, (255, 255, 180), (cx + 9, cy - 10), 8)
        _circle(surf, (255, 40, 20), (cx - 8, cy - 10), 5)
        _circle(surf, (255, 40, 20), (cx + 10, cy - 10), 5)
        _circle(surf, (20, 0, 0), (cx - 8, cy - 10), 3)
        _circle(surf, (20, 0, 0), (cx + 10, cy - 10), 3)

        # 凶眉
        _line(surf, (80, 10, 10), (cx - 15, cy - 16), (cx - 2, cy - 14), 3)
        _line(surf, (80, 10, 10), (cx + 15, cy - 16), (cx + 2, cy - 14), 3)

        # 巨钳
        _line(surf, (220, 30, 30), (cx - 22, cy - 4), (cx - 48, cy - 20), 8)
        _line(surf, (220, 30, 30), (cx + 22, cy - 4), (cx + 48, cy - 20), 8)
        _circle(surf, (240, 50, 30), (cx - 48, cy - 20), 10)
        _circle(surf, (240, 50, 30), (cx + 48, cy - 20), 10)
        _circle(surf, (255, 80, 50), (cx - 49, cy - 21), 7)
        _circle(surf, (255, 80, 50), (cx + 47, cy - 21), 7)
        _aaline(surf, (180, 15, 15), (cx - 48, cy - 20), (cx - 54, cy - 24))
        _aaline(surf, (180, 15, 15), (cx + 48, cy - 20), (cx + 54, cy - 24))

        # 脚
        for i in range(5):
            ox = -16 + i * 8
            _line(surf, (180, 20, 20), (cx + ox, cy + 14), (cx + ox - 4, cy + 28), 3)
        # 背上锯齿
        for sx in [-12, -4, 4, 12]:
            _polygon(surf, (180, 30, 30), [(cx + sx - 3, cy - 14), (cx + sx, cy - 24), (cx + sx + 3, cy - 14)])

    def draw_boss_crab(surf):
        cx, cy = size[0] // 2, size[1] // 2
        for r in range(35, 15, -7):
            _circle(surf, (255, 140, 20, 15), (cx, cy + 8), r, 2)
        _ellipse(surf, (120, 50, 15, 80), (cx - 24, cy + 30, 48, 10))

        _ellipse(surf, (220, 140, 20), (cx - 26, cy - 8, 52, 38))
        _ellipse(surf, (240, 170, 40), (cx - 22, cy - 6, 44, 34))
        _ellipse(surf, (255, 200, 80, 50), (cx - 14, cy - 14, 14, 14))

        for si in range(-16, 18, 5):
            _aaline(surf, (200, 120, 20), (cx + si, cy - 2), (cx + si, cy + 16))
        # 背上尖刺
        for sx in [-14, -6, 2, 10]:
            _polygon(surf, (200, 120, 20), [(cx + sx - 3, cy - 16), (cx + sx, cy - 28), (cx + sx + 3, cy - 16)])

        # 眼柄
        _line(surf, (220, 140, 20), (cx - 10, cy - 20), (cx - 14, cy - 36), 5)
        _line(surf, (220, 140, 20), (cx + 10, cy - 20), (cx + 14, cy - 36), 5)
        _circle(surf, (255, 255, 200), (cx - 14, cy - 38), 7)
        _circle(surf, (255, 255, 200), (cx + 14, cy - 38), 7)
        _circle(surf, (255, 50, 20), (cx - 13, cy - 38), 4)
        _circle(surf, (255, 50, 20), (cx + 15, cy - 38), 4)
        _circle(surf, (0, 0, 0), (cx - 13, cy - 38), 2)
        _circle(surf, (0, 0, 0), (cx + 15, cy - 38), 2)

        # 嘴
        _aaline(surf, (160, 80, 20), (cx - 4, cy - 2), (cx + 4, cy))

        # 巨钳
        _ellipse(surf, (200, 140, 20), (cx - 46, cy - 14, 24, 18))
        _ellipse(surf, (200, 140, 20), (cx + 22, cy - 14, 24, 18))
        _ellipse(surf, (220, 160, 30), (cx - 50, cy - 18, 18, 14))
        _ellipse(surf, (220, 160, 30), (cx + 32, cy - 18, 18, 14))
        _aaline(surf, (160, 100, 20), (cx - 40, cy - 14), (cx - 32, cy - 8))
        _aaline(surf, (160, 100, 20), (cx + 40, cy - 14), (cx + 32, cy - 8))

        for i in range(4):
            ox = -12 + i * 8
            _line(surf, (190, 120, 20), (cx + ox, cy + 18), (cx + ox - 6, cy + 34), 3)
            _line(surf, (190, 120, 20), (cx + ox + 8, cy + 18), (cx + ox + 14, cy + 34), 3)

    def draw_boss_octopus(surf):
        cx, cy = size[0] // 2, size[1] // 2
        for r in range(38, 18, -5):
            _circle(surf, (100, 20, 160, 15), (cx, cy + 8), r, 2)
        _ellipse(surf, (60, 10, 100, 80), (cx - 28, cy + 32, 56, 10))

        _ellipse(surf, (100, 20, 160), (cx - 28, cy - 20, 56, 50))
        _ellipse(surf, (130, 40, 190), (cx - 24, cy - 16, 48, 42))
        _ellipse(surf, (160, 60, 220), (cx - 16, cy - 10, 32, 34))
        _ellipse(surf, (190, 100, 240, 50), (cx - 12, cy - 22, 12, 16))

        for si in range(4):
            sx = cx - 10 + si * 7
            sy = cy - 6 + (si % 2) * 6
            _circle(surf, (180, 80, 220, 60), (sx, sy), 3)

        offsets = [(-24, 24), (-18, 28), (-10, 32), (-2, 34), (2, 34), (10, 32), (18, 28), (24, 24)]
        for i, (dx, dy) in enumerate(offsets):
            ex = cx + dx * 2 + random.choice([-8, 0, 8])
            ey = cy + 24 + dy
            mid_x = cx + dx + (ex - cx - dx) * 0.5
            mid_y = cy + 20 + (ey - cy - 20) * 0.5
            _line(surf, (100, 20, 160), (cx + dx, cy + 20), (mid_x, mid_y), 8)
            _aaline(surf, (80, 15, 140), (mid_x, mid_y), (ex, ey))
            for si in range(3):
                sxx = cx + dx + (ex - cx - dx) * (0.2 + si * 0.25)
                syy = cy + 20 + (ey - cy - 20) * (0.2 + si * 0.25)
                _circle(surf, (180, 100, 200, 60), (sxx, syy), 3)

        _circle(surf, (100, 255, 100, 40), (cx - 14, cy - 6), 12)
        _circle(surf, (100, 255, 100, 40), (cx + 14, cy - 6), 12)
        _circle(surf, (100, 255, 50), (cx - 14, cy - 6), 9)
        _circle(surf, (100, 255, 50), (cx + 14, cy - 6), 9)
        _circle(surf, (255, 255, 100), (cx - 13, cy - 7), 5)
        _circle(surf, (255, 255, 100), (cx + 15, cy - 7), 5)
        _circle(surf, (0, 0, 0), (cx - 13, cy - 6), 3)
        _circle(surf, (0, 0, 0), (cx + 15, cy - 6), 3)

        _ellipse(surf, (60, 5, 100), (cx - 8, cy + 6, 16, 8))

    def draw_boss_shark(surf):
        cx, cy = size[0] // 2, size[1] // 2
        for r in range(38, 15, -6):
            _circle(surf, (70, 100, 150, 15), (cx, cy + 8), r, 2)
        _ellipse(surf, (30, 50, 90, 80), (cx - 28, cy + 30, 56, 10))

        _ellipse(surf, (70, 100, 150), (cx - 30, cy - 16, 60, 32))
        _ellipse(surf, (90, 130, 180), (cx - 26, cy - 12, 52, 26))
        _ellipse(surf, (120, 160, 210), (cx - 16, cy - 8, 36, 20))
        _ellipse(surf, (220, 230, 240, 60), (cx - 12, cy + 2, 28, 16))

        _polygon(surf, (70, 100, 150), [(cx + 22, cy - 8), (cx + 56, cy - 2), (cx + 22, cy + 6)])
        _polygon(surf, (50, 80, 130), [(cx - 30, cy), (cx - 56, cy - 22), (cx - 44, cy)])
        _polygon(surf, (50, 80, 130), [(cx - 30, cy), (cx - 56, cy + 22), (cx - 44, cy)])
        _polygon(surf, (60, 90, 140), [(cx - 6, cy - 16), (cx, cy - 44), (cx + 10, cy - 16)])
        _polygon(surf, (60, 90, 140), [(cx + 2, cy + 14), (cx - 6, cy + 34), (cx + 6, cy + 18)])
        _polygon(surf, (80, 130, 180), [(cx - 4, cy - 14), (cx + 2, cy - 36), (cx + 6, cy - 14)])

        _aaline(surf, (40, 60, 100), (cx - 12, cy - 8), (cx + 10, cy))
        _aaline(surf, (40, 60, 100), (cx, cy - 10), (cx + 14, cy - 6))

        _circle(surf, (255, 255, 200), (cx + 18, cy - 8), 8)
        _circle(surf, (255, 80, 30), (cx + 21, cy - 8), 5)
        _circle(surf, (0, 0, 0), (cx + 21, cy - 8), 3)
        _circle(surf, (255, 255, 255), (cx + 20, cy - 9), 1)

        _aaline(surf, (40, 50, 80), (cx + 18, cy + 4), (cx + 32, cy + 4))
        for tx in [26, 30, 34, 38, 42]:
            _polygon(surf, WHITE, [(cx + tx, cy + 3), (cx + tx + 1, cy - 2), (cx + tx + 2, cy + 3)])

        for gx in [cx - 14, cx - 8, cx - 2]:
            _aaline(surf, (50, 80, 120), (gx, cy - 4), (gx - 3, cy + 8))

        # 胸鳍（加强）
        _polygon(surf, (70, 100, 150), [(cx + 4, cy + 10), (cx - 10, cy + 28), (cx + 6, cy + 14)])
        _polygon(surf, (70, 100, 150), [(cx + 8, cy + 12), (cx - 4, cy + 32), (cx + 10, cy + 16)])

    def draw_boss_dragon(surf):
        cx, cy = size[0] // 2, size[1] // 2
        for r in range(42, 18, -6):
            _circle(surf, (40, 160, 80, 15), (cx, cy + 8), r, 2)
        _ellipse(surf, (20, 80, 40, 80), (cx - 28, cy + 30, 56, 10))

        _ellipse(surf, (30, 140, 70), (cx - 26, cy - 10, 52, 28))
        _ellipse(surf, (40, 160, 90), (cx - 22, cy - 8, 44, 24))
        _ellipse(surf, (60, 180, 110), (cx - 14, cy - 6, 28, 20))
        _ellipse(surf, (180, 220, 180, 50), (cx - 10, cy + 4, 22, 12))

        _polygon(surf, (30, 140, 70), [(cx + 18, cy - 8), (cx + 48, cy - 16), (cx + 44, cy - 2),
                                       (cx + 30, cy + 4), (cx + 18, cy + 6)])
        for sx in [22, 28]:
            _polygon(surf, (80, 120, 50), [(cx + sx, cy - 14), (cx + sx + 4, cy - 34), (cx + sx + 8, cy - 12)])
        _polygon(surf, (80, 120, 50), [(cx + 26, cy - 14), (cx + 34, cy - 30), (cx + 36, cy - 12)])

        _circle(surf, (255, 255, 100, 40), (cx + 30, cy - 10), 8)
        _circle(surf, (255, 255, 50), (cx + 30, cy - 10), 6)
        _circle(surf, (255, 80, 20), (cx + 31, cy - 10), 3)
        _circle(surf, (0, 0, 0), (cx + 31, cy - 10), 2)

        _polygon(surf, (30, 140, 70), [(cx - 26, cy), (cx - 50, cy - 18), (cx - 44, cy)])
        _polygon(surf, (30, 140, 70), [(cx - 26, cy), (cx - 50, cy + 18), (cx - 44, cy)])
        _polygon(surf, (50, 150, 80), [(cx - 6, cy - 12), (cx - 16, cy - 30), (cx + 4, cy - 16)])
        _polygon(surf, (50, 150, 80), [(cx - 4, cy + 12), (cx - 14, cy + 30), (cx + 4, cy + 16)])
        _polygon(surf, (50, 150, 80), [(cx + 2, cy + 14), (cx - 10, cy + 34), (cx + 6, cy + 18)])

        for sx in [-14, -6, 2, 10, 18]:
            _polygon(surf, (80, 140, 60), [(cx + sx - 3, cy - 12), (cx + sx, cy - 24), (cx + sx + 3, cy - 12)])

    drawers = {
        "boss_lobster": draw_boss_lobster,
        "boss_crab": draw_boss_crab,
        "boss_octopus": draw_boss_octopus,
        "boss_shark": draw_boss_shark,
        "boss_dragon": draw_boss_dragon,
    }
    return make_sprite(visual_size, drawers.get(boss_key, draw_boss_dragon))


# ═══════════════════════════════════════════════════════════════════════════════
#  武器图标 —— 优化版
# ═══════════════════════════════════════════════════════════════════════════════

def make_weapon_icon(key):
    """更精致的武器图标。"""
    asset_names = {
        'pistol': 'weapons/weapon_pistol.png',
        'rifle': 'weapons/weapon_rifle.png',
        'shotgun': 'weapons/weapon_shortgun.png',
        'sniper': 'weapons/weapon_awm.png',
    }
    img = image_asset(asset_names.get(key, f'weapons/weapon_{key}.png'), (56, 28))
    if img:
        return img

    def draw_pistol(surf):
        cx, cy = surf.get_size()[0] // 2, surf.get_size()[1] // 2

        # 枪柄
        _rect(surf, (100, 80, 50), (cx - 12, cy - 2, 8, 14), border_radius=3)
        _rect(surf, (120, 95, 60), (cx - 13, cy, 6, 12), border_radius=2)
        _rect(surf, (80, 60, 40), (cx - 10, cy + 1, 5, 10), border_radius=2)
        # 握把纹理
        for gx in [cx - 10, cx - 7]:
            _line(surf, (140, 110, 70), (gx, cy), (gx, cy + 10), 1)

        # 枪身
        _rect(surf, (140, 140, 150), (cx - 4, cy - 6, 24, 10), border_radius=3)
        _rect(surf, (160, 160, 170), (cx - 2, cy - 5, 20, 8), border_radius=2)
        _rect(surf, (180, 180, 190, 80), (cx, cy - 4, 14, 6), border_radius=1)
        _rect(surf, (120, 120, 130), (cx - 3, cy - 6, 2, 4))  # 照门
        _rect(surf, (120, 120, 130), (cx + 16, cy - 6, 2, 4))  # 准星

        # 扳机护圈
        _rect(surf, (180, 160, 120), (cx - 10, cy + 4, 7, 6), border_radius=2)
        _ellipse(surf, (180, 160, 120), (cx - 12, cy + 4, 10, 6))

        # 枪管
        _polygon(surf, (180, 180, 190), [(cx + 20, cy - 2), (cx + 28, cy - 5), (cx + 28, cy + 5), (cx + 20, cy + 2)])
        _polygon(surf, (200, 200, 210, 120), [(cx + 22, cy - 1), (cx + 27, cy - 4), (cx + 27, cy + 4), (cx + 22, cy + 1)])

        # 枪口辉光
        _circle(surf, (255, 255, 100, 100), (cx + 27, cy), 3)

    def draw_rifle(surf):
        cx, cy = surf.get_size()[0] // 2, surf.get_size()[1] // 2

        # 枪托
        _rect(surf, (90, 70, 50), (cx - 22, cy - 3, 10, 14), border_radius=3)
        _rect(surf, (110, 90, 60), (cx - 23, cy - 1, 6, 12), border_radius=2)
        _rect(surf, (130, 105, 70, 80), (cx - 22, cy - 2, 4, 6))
        # 托底板
        _rect(surf, (70, 50, 40), (cx - 22, cy + 9, 10, 4), border_radius=1)

        # 枪身
        _rect(surf, (70, 110, 180), (cx - 12, cy - 5, 32, 10), border_radius=2)
        _rect(surf, (90, 130, 200), (cx - 10, cy - 4, 28, 8), border_radius=1)
        _rect(surf, (130, 160, 220, 80), (cx - 6, cy - 3, 20, 6), border_radius=1)

        # 弹匣
        _rect(surf, (80, 70, 50), (cx - 4, cy + 4, 8, 10), border_radius=2)
        _rect(surf, (100, 90, 60), (cx - 3, cy + 5, 6, 8), border_radius=1)
        _line(surf, (60, 50, 30), (cx - 4, cy + 6), (cx + 4, cy + 6), 1)
        _line(surf, (60, 50, 30), (cx - 4, cy + 10), (cx + 4, cy + 10), 1)

        # 提把/照门
        _rect(surf, (100, 120, 160), (cx + 2, cy - 8, 12, 4), border_radius=1)
        _rect(surf, (80, 100, 140), (cx + 3, cy - 10, 3, 2))

        # 枪管
        _polygon(surf, (180, 190, 210), [(cx + 20, cy - 1), (cx + 30, cy - 5), (cx + 30, cy + 5), (cx + 20, cy + 1)])
        _rect(surf, (200, 200, 220, 100), (cx + 22, cy - 2, 6, 4))

        # 枪口火焰
        _polygon(surf, (255, 200, 80, 100), [(cx + 29, cy - 1), (cx + 34, cy - 3), (cx + 34, cy + 3), (cx + 29, cy + 1)])

    def draw_sniper(surf):
        cx, cy = surf.get_size()[0] // 2, surf.get_size()[1] // 2

        # 枪管（加长）
        _rect(surf, (50, 70, 110), (cx - 24, cy - 4, 44, 8), border_radius=1)
        _rect(surf, (60, 80, 130), (cx - 22, cy - 3, 40, 6), border_radius=1)
        _rect(surf, (90, 110, 160, 100), (cx - 12, cy - 2, 30, 4))
        # 枪管散热槽
        for gx in [cx - 16, cx - 8, cx, cx + 8]:
            _line(surf, (40, 60, 100), (gx, cy - 2), (gx, cy + 1), 1)

        # 瞄准镜
        _rect(surf, (80, 90, 110), (cx + 4, cy - 10, 14, 12), border_radius=4)
        _rect(surf, (60, 70, 90), (cx + 6, cy - 9, 10, 10), border_radius=3)
        # 镜片
        _circle(surf, (100, 160, 220), (cx + 11, cy - 4), 5)
        _circle(surf, (180, 210, 255), (cx + 11, cy - 4), 3)
        _circle(surf, (255, 255, 255, 200), (cx + 10, cy - 5), 1)
        # 镜架
        _rect(surf, (100, 100, 120), (cx + 2, cy - 8, 4, 8), border_radius=1)

        # 枪托
        _rect(surf, (70, 50, 40), (cx - 26, cy - 2, 10, 12), border_radius=3)
        _rect(surf, (90, 70, 50), (cx - 27, cy - 0, 6, 10), border_radius=2)

        # 弹匣
        _rect(surf, (60, 80, 60), (cx - 2, cy + 3, 8, 12), border_radius=2)
        _rect(surf, (80, 100, 70), (cx - 1, cy + 4, 6, 10), border_radius=1)

        # 制退器
        _polygon(surf, (160, 180, 210), [(cx + 20, cy), (cx + 32, cy - 6), (cx + 32, cy + 6)])
        _rect(surf, (180, 190, 220), (cx + 22, cy - 2, 8, 4), border_radius=1)

        # 枪口辉光
        _circle(surf, (255, 180, 60, 60), (cx + 30, cy), 5)
        _circle(surf, (255, 230, 150, 30), (cx + 31, cy), 3)

    def draw_shotgun(surf):
        cx, cy = surf.get_size()[0] // 2, surf.get_size()[1] // 2
        _rect(surf, (90, 60, 42), (cx - 25, cy - 3, 14, 13), border_radius=3)
        _rect(surf, (120, 78, 48), (cx - 24, cy - 1, 10, 10), border_radius=2)
        _rect(surf, (80, 140, 125), (cx - 12, cy - 6, 31, 11), border_radius=3)
        _rect(surf, (105, 185, 160), (cx - 9, cy - 5, 25, 8), border_radius=2)
        _rect(surf, (70, 110, 100), (cx - 3, cy + 4, 8, 10), border_radius=2)
        _rect(surf, (190, 220, 205), (cx + 18, cy - 5, 16, 4), border_radius=1)
        _rect(surf, (165, 200, 190), (cx + 18, cy + 1, 16, 4), border_radius=1)
        for oy in (-4, 3):
            _circle(surf, (120, 255, 205, 90), (cx + 34, cy + oy), 4)

    drawers = {'pistol': draw_pistol, 'rifle': draw_rifle, 'shotgun': draw_shotgun, 'sniper': draw_sniper}
    s = pygame.Surface((56, 28), pygame.SRCALPHA)
    drawers[key](s)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  金币 —— 优化版：3D旋转金币
# ═══════════════════════════════════════════════════════════════════════════════

_COIN_SURFACE_CACHE = None


def make_coin_surface():
    global _COIN_SURFACE_CACHE
    if _COIN_SURFACE_CACHE is not None:
        return _COIN_SURFACE_CACHE
    img = image_asset('ui/coin.png', (26, 26))
    if img:
        _COIN_SURFACE_CACHE = img
        return img
    def draw(surf):
        cx, cy = surf.get_size()[0] // 2, surf.get_size()[1] // 2
        # 外圈暗金
        _circle(surf, (180, 140, 20), (cx, cy), 11)
        # 主体金色
        _circle(surf, (255, 215, 0), (cx, cy), 10)
        # 内圈渐变
        _circle(surf, (255, 235, 80), (cx - 1, cy - 1), 8)
        _circle(surf, (255, 250, 150), (cx - 2, cy - 2), 6)
        # 高光
        _ellipse(surf, (255, 255, 220, 120), (cx - 6, cy - 7, 6, 4))
        # 边缘刻痕
        for a in range(0, 360, 45):
            rad = a * math.pi / 180
            nx = cx + int(9.5 * math.cos(rad))
            ny = cy + int(9.5 * math.sin(rad))
            _circle(surf, (200, 160, 30), (nx, ny), 1)
        # 符号
        font = make_font(16, bold=True)
        txt = font.render('$', True, (200, 160, 30))
        surf.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))
        # 内圈发光
        _circle(surf, (255, 255, 200, 40), (cx, cy), 5, 1)
    _COIN_SURFACE_CACHE = make_sprite((26, 26), draw)
    return _COIN_SURFACE_CACHE
