"""Shared title screen, campaign picker and shop presentation for PC and Web."""
from functools import lru_cache
from textwrap import wrap

import pygame

from . import animation, config
from .asset_loader import image_asset, scale_surface_cached
from .mobile_controls import _CHAR_ASSETS, _WEAPON_ASSETS
from .render import Draw, RenderSurface, trim_transparent


ACCENT = (120, 235, 221)
EDGE = (57, 102, 114)
INK = (235, 253, 255)
MUTED = (176, 208, 217)
PAPER = (7, 25, 33)
SURFACE = (11, 37, 47)
DIFFICULTIES = (('easy', '简单'), ('medium', '中等'), ('hard', '困难'))

# Percentages of the poster area, ordered from the first Boss to the final Boss.
BOSS_POSTER = (
    (1, 69, 17, 17), (17, 74, 18, 16), (33, 77, 17, 15),
    (50, 77, 17, 15), (66, 74, 18, 16), (82, 69, 17, 17),
    (0, 40, 28, 30), (76, 45, 24, 25),
    (22, 48, 30, 28), (51, 47, 29, 28), (8, 0, 84, 62),
)
SKILL_DESCRIPTIONS = {
    'ice': (
        ('冰墙', 'ice_floor', '拦截敌弹，破碎时减速周围敌人。'),
        ('冰球', 'ice_balls', '扇形发射八枚冰球，可冻结小怪、减速首领。'),
    ),
    'water': (
        ('水疗', 'water_heal', '恢复一点生命并短暂无敌，满血时获得临时生命。'),
        ('潮汐强化', 'water_boost', '短时间提高队伍的移动速度和射速。'),
    ),
    'fire': (
        ('火墙', 'fire_wall', '挡住敌人与可拦截的子弹，灼烧碰到火墙的敌人。'),
        ('火球', 'fireball', '发射穿透火球和会爆炸的火箭。'),
    ),
    'radiation': (
        ('闪电链', 'lightning', '电击附近多个目标。'),
        ('磁暴', 'magnetic_storm', '吸附可拦截的弹幕，随后爆发范围伤害。'),
        ('辐射激光', 'radiation_laser', '向上发射持续光束，再次触发可横扫。'),
        ('飞镖护盾', 'dart_shield', '飞镖环绕拦截子弹，结束后向外飞出。'),
    ),
}
WEAPON_DESCRIPTIONS = {
    'pistol': '基础单发', 'rifle': '连续射击', 'shotgun': '扇形散射', 'sniper': '高伤害单发',
}


def _text(game, value, rect, *, font=None, color=INK, align='left'):
    game._draw_text_fit(value, font or game.font_small, color, rect, align=align)


def _panel(game, rect, *, selected=False, fill=SURFACE, radius=8):
    game._draw_panel(*rect, accent=ACCENT if selected else EDGE, fill=fill, r=radius, alpha=249)


def _button(game, rect, label, *, active=False, primary=False, radius=7):
    if primary:
        Draw.rect(config.SCR, ACCENT, rect, border_radius=radius)
        _text(game, label, rect.inflate(-10, -4), font=game.font_med, color=PAPER, align='center')
    else:
        _panel(game, rect, selected=active, fill=(25, 66, 73) if active else SURFACE, radius=radius)
        _text(game, label, rect.inflate(-8, -4), color=INK if active else MUTED, align='center')


def _blit(image, rect):
    target = config.SCR
    if isinstance(target, RenderSurface):
        target.blit(image, rect.topleft, logical_size=rect.size, static=True)
    else:
        target.blit(scale_surface_cached(image, rect.size), rect.topleft)


def _art(image, rect):
    if image is not None and rect.w > 0 and rect.h > 0:
        trimmed = trim_transparent(image)[0]
        if trimmed.get_width() and trimmed.get_height():
            _blit(trimmed, trimmed.get_rect().fit(rect))


def _boss_art(level):
    boss = config.BOSS_DEFS[config.LEVEL_CONFIGS[level - 1]['boss_idx']]
    return image_asset(boss.get('sprite_asset', f"bosses/{boss['key']}.png"))


def _home_boxes():
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    if config.MOBILE_LANDSCAPE_VIEW:
        left = pygame.Rect(38, h // 7, w * 44 // 100 - 48, h * 38 // 100)
        poster = pygame.Rect(w * 45 // 100, 20, w * 55 // 100 - 22, h - 40)
        button = pygame.Rect(left.x + 8, left.bottom + 18, min(310, left.w - 8), 50)
    else:
        title_height = min(215, h // 4)
        left = pygame.Rect(28, max(12, (h - 780) // 2), w - 56, title_height)
        button = pygame.Rect(56, min(h - 64, left.bottom + min(h * 56 // 100, 480) + 10), w - 112, 50)
        poster = pygame.Rect(25, left.bottom, w - 50, button.top - left.bottom - 10)
    return left, poster, button


def home_rects():
    return {'start': _home_boxes()[2]}


def draw_home(game):
    game._draw_scrim(86)
    title, poster, start = _home_boxes()
    if game.title_image is None:
        _text(game, '海洋生物入侵', title, font=game.font_large, align='center')
    else:
        _art(game.title_image, title)
    boss_height = poster.h * 74 // 100
    for index in (10, 6, 7, 8, 9, 0, 1, 2, 3, 4, 5):
        x, y, width, height = BOSS_POSTER[index]
        box = pygame.Rect(poster.x + poster.w * x // 100, poster.y + boss_height * y // 100,
                          poster.w * width // 100, boss_height * height // 100)
        _art(_boss_art(index + 1), box)
    team = ('fire', 'ice', None, 'water', 'radiation')
    cell = poster.w * 16 // 100
    team_left = poster.centerx - cell * len(team) // 2
    team_height = poster.h - boss_height
    for index, key in enumerate(team):
        height = team_height if key is None else team_height * 78 // 100
        bottom = poster.bottom - abs(index - 2) * team_height // 12
        rect = pygame.Rect(team_left + index * cell, bottom - height, cell, height)
        image = animation.frame(f'player_{key}_back', 0) if key else image_asset('players/player1.png')
        _art(image, rect)
    _button(game, start, '开始游戏  →', primary=True)


def campaign_rects(game):
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    landscape = config.MOBILE_LANDSCAPE_VIEW
    margin, gap = (24, 8) if landscape else (16, 7)
    inner = w - margin * 2
    home_x = margin if game.desktop_controls else max(margin, 66)
    rects = {'home': pygame.Rect(home_x, 12, 82, 40),
             'shop': pygame.Rect(w - margin - 86, 12, 86, 40)}
    for index, (key, _) in enumerate(DIFFICULTIES):
        rects[key] = pygame.Rect(w - margin - 238 + index * 80, 64, 78, 38)
    footer = ('infinite', 'custom', 'keys') if game.desktop_controls else ('infinite', 'custom')
    footer_width = min(150, (inner - gap * (len(footer) - 1)) // len(footer))
    left = (w - footer_width * len(footer) - gap * (len(footer) - 1)) // 2
    for index, key in enumerate(footer):
        rects[key] = pygame.Rect(left + index * (footer_width + gap), h - 50, footer_width, 38)
    area = pygame.Rect(margin, 112, inner, max(1, h - 172))
    if landscape:
        grid = area.copy()
        grid.w = (area.w - gap) * 65 // 100
        detail = pygame.Rect(grid.right + gap, area.y, area.right - grid.right - gap, area.h)
    else:
        detail = area.copy()
        detail.h = min(260, area.h * 46 // 100)
        grid = pygame.Rect(area.x, detail.bottom + gap, area.w, area.bottom - detail.bottom - gap)
    rects['detail'] = detail
    rects['start'] = pygame.Rect(detail.x + 12, detail.bottom - 45, detail.w - 24, 36)
    tile_w = (grid.w - gap * 2) // 3
    tile_h = (grid.h - gap * 3) // 4
    for index in range(len(config.LEVEL_CONFIGS)):
        row, col = divmod(index, 3)
        rects[f'level:{index + 1}'] = pygame.Rect(grid.x + col * (tile_w + gap),
                                                 grid.y + row * (tile_h + gap), tile_w, tile_h)
    return rects


@lru_cache(maxsize=24)
def _chapter_scene(atlas, level, size, dark):
    w, h = atlas.get_width() // 4, atlas.get_height() // 3
    row, col = divmod(level - 1, 4)
    image = atlas.subsurface((col * w, row * h, w, h))
    dest_w, dest_h = size
    crop_w = min(w, max(1, round(h * dest_w / dest_h)))
    crop_h = min(h, max(1, round(w * dest_h / dest_w)))
    crop = pygame.Rect(0, 0, crop_w, crop_h)
    crop.center = image.get_rect().center
    result = pygame.transform.smoothscale(image.subsurface(crop), size)
    shade = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(dest_h):
        weight = min(1, max(0, (y / max(1, dest_h - 1) - .38) / .62))
        pygame.draw.line(shade, (*PAPER, round(35 + weight * dark)), (0, y), (dest_w - 1, y))
    result.blit(shade, (0, 0))
    return result


def _scene(rect, level, darkness):
    atlas = image_asset('ui/chapter_scenes.png')
    if atlas is not None and rect.w > 0 and rect.h > 0:
        _blit(_chapter_scene(atlas, level, rect.size, darkness), rect)


def draw_campaign(game):
    rects = campaign_rects(game)
    w = config.SCREEN_WIDTH
    game._draw_scrim(251, PAPER)
    _button(game, rects['home'], '← 首页')
    _button(game, rects['shop'], '商店')
    margin = rects['detail'].x if not config.MOBILE_LANDSCAPE_VIEW else rects['level:1'].x
    _text(game, '战役选关', pygame.Rect(margin, 64, w - 280, 38), font=game.font_med)
    for key, label in DIFFICULTIES:
        _button(game, rects[key], label, active=game.selected_difficulty == key, radius=19)
    for level, info in enumerate(config.LEVEL_CONFIGS, 1):
        tile = rects[f'level:{level}']
        selected = level == game.selected_level
        _panel(game, tile, selected=selected)
        _scene(tile.inflate(-4, -4), level, 208)
        _text(game, f'{level:02}', pygame.Rect(tile.x + 8, tile.y + 3, tile.w - 16, 20),
              font=game.font_tiny, color=ACCENT)
        _text(game, info['title'], pygame.Rect(tile.x + 8, tile.bottom - 25, tile.w - 16, 21),
              font=game.font_tiny)
    level = game.selected_level
    info = config.LEVEL_CONFIGS[level - 1]
    detail = rects['detail']
    _panel(game, detail)
    _scene(detail.inflate(-4, -4), level, 215)
    _art(_boss_art(level), pygame.Rect(detail.x + 14, detail.y + 8, detail.w - 28, detail.h - 118))
    _text(game, info['title'], pygame.Rect(detail.x + 12, detail.bottom - 110, detail.w - 24, 36),
          font=game.font_med)
    boss = config.BOSS_DEFS[info['boss_idx']]['name']
    reward = config.CAMPAIGN_REWARDS[level - 1]
    description = f'首领 · {boss}' + (f'  /  +{reward} 金币' if reward else '')
    _text(game, description, pygame.Rect(detail.x + 12, detail.bottom - 74, detail.w - 24, 23),
          font=game.font_tiny, color=MUTED)
    _button(game, rects['start'], '出击  →', primary=True)
    for key, label in (('infinite', '无限模式'), ('custom', '自定义难度'), ('keys', '按键设置')):
        if key in rects:
            _button(game, rects[key], label)


def shop_rects(game):
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    width = min(w - 24, 910)
    height = min(h - 22, 564)
    x, y = (w - width) // 2, (h - height) // 2
    panel = pygame.Rect(x, y, width, height)
    rects = {'panel': panel,
             'close': pygame.Rect(panel.right - 52, y + 10, 40, 40),
             'weapon': pygame.Rect(panel.right - 204, y + 10, 68, 40),
             'character': pygame.Rect(panel.right - 128, y + 10, 68, 40)}
    cards_y = panel.bottom - 111
    rects['feature'] = pygame.Rect(x + 10, y + 56, width - 20, cards_y - y - 64)
    gap = 6
    card_w = (width - 20 - gap * 3) // 4
    characters = game.shop_category == 'character'
    keys = config._CHAR_KEYS_ORDERED if characters else config._WEAPON_KEYS_ORDERED
    for index, key in enumerate(keys):
        tile = pygame.Rect(x + 10 + index * (card_w + gap), cards_y, card_w, 70 if characters else 97)
        rects[f'{game.shop_category}:{key}'] = tile
        if characters:
            rects[f'skills:{key}'] = pygame.Rect(tile.x, tile.bottom + 2, tile.w, 26)
    return rects


def _shop_status(game, key, characters):
    player = game.player
    if characters:
        cost = game._character_cost(config.CHARACTER_DEFS[key])
        owned, equipped = key in player.owned_characters, key == player.character
    else:
        cost = game._weapon_cost(key)
        owned, equipped = key in player.owned_weapons, key == player.current_weapon
    if equipped:
        return '已装备'
    if owned:
        return '点击装备'
    return f'{cost} 金币'


def _draw_skills(game, key, rect):
    gap = 10
    cell_w = (rect.w - gap) // 2
    cell_h = rect.h // 2
    for index, (name, action, description) in enumerate(SKILL_DESCRIPTIONS[key]):
        row, col = divmod(index, 2)
        x, y = rect.x + col * (cell_w + gap), rect.y + row * cell_h
        thumb = pygame.Rect(x, y, min(56, cell_w // 3), min(57, cell_h - 5))
        _panel(game, thumb, fill=PAPER, radius=5)
        _art(animation.frame(f'player_{key}_{action}', 2), thumb.inflate(-6, -6))
        text_x = thumb.right + 6
        text_w = x + cell_w - text_x
        _text(game, name, pygame.Rect(text_x, y, text_w, 18), font=game.font_tiny, color=ACCENT)
        for line_index, line in enumerate(wrap(description, width=max(5, text_w // 15))):
            _text(game, line, pygame.Rect(text_x, y + 18 + line_index * 16, text_w, 15),
                  font=game.font_tiny, color=MUTED)


def draw_shop(game):
    rects = shop_rects(game)
    panel = rects['panel']
    feature = rects['feature']
    game._draw_scrim(231)
    _panel(game, panel, fill=PAPER, radius=12)
    _text(game, '商店', pygame.Rect(panel.x + 16, panel.y + 10, 61, 40), font=game.font_med)
    _art(image_asset('ui/coin.png'), pygame.Rect(panel.x + 80, panel.y + 21, 19, 19))
    _text(game, str(game.player.gold), pygame.Rect(panel.x + 104, panel.y + 11, 72, 38),
          color=config.GOLD_COLOR)
    for tab, label in (('weapon', '武器'), ('character', '角色'), ('close', '×')):
        _button(game, rects[tab], label, active=tab == game.shop_category)

    characters = game.shop_category == 'character'
    selected = game.shop_character if characters else game.shop_weapon
    assets = _CHAR_ASSETS if characters else _WEAPON_ASSETS
    definitions = config.CHARACTER_DEFS if characters else config.WEAPON_DEFS
    _panel(game, feature)
    text_x = feature.x + 16
    half = feature.w // 2
    if characters:
        portrait = not config.MOBILE_LANDSCAPE_VIEW
        art = pygame.Rect(feature.x + (half if portrait else feature.w * 58 // 100),
                          feature.y + 10, half - 19 if portrait else feature.w * 40 // 100,
                          min(140, feature.h - 160) if portrait else feature.h - 20)
        skills = pygame.Rect(text_x, feature.y + (158 if portrait else 83),
                             feature.w - 32 if portrait else feature.w * 57 // 100 - 16,
                             feature.h - (166 if portrait else 89))
        title_y = feature.y + (35 if portrait else 9)
        _art(image_asset(assets[selected]), art)
        _draw_skills(game, selected, skills)
    else:
        title_y = feature.centery - 57
        art = pygame.Rect(feature.x + feature.w * 40 // 100, feature.y + 15,
                          feature.w * 57 // 100, feature.h - 30)
        filename = assets[selected].rsplit('/', 1)[1]
        _art(image_asset(f'ui/weapon_showcase/{filename}') or image_asset(assets[selected]), art)
        _text(game, WEAPON_DESCRIPTIONS[selected], pygame.Rect(text_x, title_y + 49, half - 23, 21),
              font=game.font_tiny, color=MUTED)
    _text(game, definitions[selected].name, pygame.Rect(text_x, title_y, half - 15, 43),
          font=game.font_large)
    status_y = title_y + (46 if characters else 76)
    _text(game, game.shop_notice or _shop_status(game, selected, characters),
          pygame.Rect(text_x, status_y, half - 20, 23), font=game.font_tiny, color=config.GOLD_COLOR)

    for key, path in assets.items():
        tile = rects[f'{game.shop_category}:{key}']
        _panel(game, tile, selected=key == selected, fill=(21, 61, 66) if key == selected else SURFACE)
        image_box = pygame.Rect(tile.x + 7, tile.y + 4, tile.w - 14, tile.h - 41)
        _art(image_asset(path), image_box)
        _text(game, definitions[key].name, pygame.Rect(tile.x + 4, tile.bottom - 37, tile.w - 8, 20),
              font=game.font_tiny, align='center')
        _text(game, _shop_status(game, key, characters),
              pygame.Rect(tile.x + 4, tile.bottom - 18, tile.w - 8, 15),
              font=game.font_tiny, color=MUTED, align='center')
        if characters:
            _button(game, rects[f'skills:{key}'], '看技能', active=key == selected)
