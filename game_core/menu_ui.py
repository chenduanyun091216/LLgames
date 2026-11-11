"""Shared title screen, campaign picker and shop presentation for PC and Web."""
from functools import lru_cache
from math import cos, tau
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
HOME_ACTIONS = (
    ('easy', '简单', pygame.K_1), ('medium', '中等', pygame.K_2),
    ('hard', '困难', pygame.K_3), ('infinite', '无限', pygame.K_4),
    ('custom', '自定义难度', pygame.K_c), ('keys', '按键设置', pygame.K_k),
)

# Percentages of the poster area, ordered from the first Boss to the final Boss.
BOSS_POSTER = (
    (0, 62, 24, 31), (15, 67, 25, 30), (31, 71, 23, 30),
    (47, 71, 23, 30), (63, 67, 25, 30), (76, 62, 24, 31),
    (2, 27, 31, 52), (67, 27, 31, 52),
    (20, 39, 34, 43), (47, 39, 34, 43), (16, 0, 68, 74),
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
SHOP_SHELVES = (
    ('weapon', '装备', config._WEAPON_KEYS_ORDERED, _WEAPON_ASSETS, config.WEAPON_DEFS),
    ('character', '角色', config._CHAR_KEYS_ORDERED, _CHAR_ASSETS, config.CHARACTER_DEFS),
)


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


@lru_cache(maxsize=2)
def _boss_poster(width, height, sprites):
    # The front row extends to 101% of the layout height.
    layer = pygame.Surface((width, height * 101 // 100), pygame.SRCALPHA)
    for index in (10, 6, 7, 8, 9, 0, 1, 2, 3, 4, 5):
        image = sprites[index]
        if image is None:
            continue
        x, y, w, h = BOSS_POSTER[index]
        box = pygame.Rect(width * x // 100, height * y // 100,
                          width * w // 100, height * h // 100)
        trimmed = trim_transparent(image)[0]
        if trimmed.get_width() and trimmed.get_height() and box.w and box.h:
            fitted = trimmed.get_rect().fit(box)
            layer.blit(pygame.transform.smoothscale(trimmed, fitted.size), fitted.topleft)
    return layer


def _home_boxes():
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    if config.MOBILE_LANDSCAPE_VIEW:
        title = pygame.Rect(0, 0, w // 4, h * 19 // 100)
        action_height = max(36, h * 6 // 100)
        actions = pygame.Rect(0, h - action_height - h * 3 // 100, w * 80 // 100, action_height)
        poster_top = h * 16 // 100
        poster = pygame.Rect(0, poster_top, w * 70 // 100, actions.top - poster_top - h * 3 // 100)
    else:
        title = pygame.Rect(28, 14, w - 56, min(180, h // 5))
        action_height = 3 * 44 - 6
        actions = pygame.Rect(28, h - action_height - 20, w - 56, action_height)
        poster = pygame.Rect(10, title.bottom, w - 20, actions.top - title.bottom - 12)
    title.centerx = poster.centerx = actions.centerx = w // 2
    return title, poster, actions


def home_rects():
    actions = _home_boxes()[2]
    columns, gap = (6, 8) if config.MOBILE_LANDSCAPE_VIEW else (2, 6)
    rows = len(HOME_ACTIONS) // columns
    width = (actions.w - gap * (columns - 1)) // columns
    height = (actions.h - gap * (rows - 1)) // rows
    left = actions.centerx - (width * columns + gap * (columns - 1)) // 2
    return {
        key: pygame.Rect(left + index % columns * (width + gap),
                         actions.y + index // columns * (height + gap), width, height)
        for index, (key, _, _) in enumerate(HOME_ACTIONS)
    }


def draw_home(game):
    game._draw_scrim(70 if game.web else 96)
    title, poster, _ = _home_boxes()
    elapsed = pygame.time.get_ticks()
    title_float = (1 - cos(tau * (elapsed % 4800) / 4800)) / 2
    title.y += round(title.h * 0.035 * title_float)
    if game.title_image is None:
        _text(game, '海洋生物入侵', title, font=game.font_large, align='center')
    else:
        _art(game.title_image, title)
    bosses = pygame.Rect(0, poster.y, round(poster.w * 0.88), round((poster.h * 83 // 100) * 0.88))
    bosses.centerx = poster.centerx
    target = config.SCR
    rendered = isinstance(target, RenderSurface)
    if rendered:
        bosses = pygame.Rect(target.rect(bosses))
    if bosses.w > 0 and bosses.h > 0:
        sprites = tuple(_boss_art(level) for level in range(1, len(BOSS_POSTER) + 1))
        layer = _boss_poster(bosses.w, bosses.h, sprites)
        bounds = layer.get_rect(topleft=bosses.topleft)
        breath = (1 - cos(tau * (elapsed % 7200) / 7200)) / 2
        inset = 0.05 * (1 - breath)
        # Round the inset once per axis so opposite edges move symmetrically.
        frame = bounds.inflate(-2 * round(bounds.w * inset), -2 * round(bounds.h * inset))
        image = layer if frame.size == bounds.size else pygame.transform.smoothscale(layer, frame.size)
        if rendered:
            target.blit_pixels(image, frame.topleft)
        else:
            target.blit(image, frame.topleft)
    team = ('player_fire', 'player_ice', 'player1', 'player_water', 'player_radiation')
    cell = poster.w * 10 // 100
    team_left = poster.centerx - cell * len(team) // 2
    team_height = poster.h * 24 // 100
    for index, key in enumerate(team):
        height = team_height if key == 'player1' else team_height * 80 // 100
        bottom = poster.bottom - abs(index - 2) * team_height // 12
        rect = pygame.Rect(team_left + index * cell, bottom - height, cell, height)
        step_ms = 240 if key == 'player1' else 360
        step = (elapsed + index * 80) // step_ms
        _art(animation.frame(f'{key}_run', step) or animation.frame(f'{key}_back', 0), rect)
    rects = home_rects()
    if game.web:
        actions = _home_boxes()[2].inflate(14, 12)
        _panel(game, actions, fill=PAPER, radius=12)
    for key, label, shortcut in HOME_ACTIONS:
        rect = rects[key]
        primary = key == 'easy' and not game.web
        if primary:
            Draw.rect(config.SCR, ACCENT, rect, border_radius=7)
        else:
            _panel(game, rect, radius=7)
        cap = pygame.Rect(rect.x + 8, rect.centery - 10, 21, 20)
        Draw.rect(config.SCR, PAPER, cap, border_radius=4)
        if not primary:
            Draw.rect(config.SCR, EDGE, cap, width=1, border_radius=4)
        _text(game, pygame.key.name(shortcut).upper(), cap, font=game.font_tiny, color=ACCENT, align='center')
        label_rect = pygame.Rect(cap.right + 7, rect.y, rect.right - cap.right - 12, rect.h)
        _text(game, label, label_rect, font=game.font_small if game.web else game.font_tiny,
              color=PAPER if primary else INK)


def campaign_rects(game):
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    landscape = config.MOBILE_LANDSCAPE_VIEW
    margin, gap = (24, 8) if landscape else (16, 7)
    inner = w - margin * 2
    home_x = margin if game.desktop_controls else max(margin, 66)
    rects = {'home': pygame.Rect(home_x, 12, 108, 40)}
    area = pygame.Rect(margin, 64, inner, h - 64 - margin)
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
        target = config.SCR
        if isinstance(target, RenderSurface):
            size = (target.length(rect.w), target.length(rect.h))
            target.blit_pixels(_chapter_scene(atlas, level, size, darkness), target.point(rect.topleft))
        else:
            _blit(_chapter_scene(atlas, level, rect.size, darkness), rect)


def draw_campaign(game):
    rects = campaign_rects(game)
    w = config.SCREEN_WIDTH
    game._draw_scrim(251, PAPER)
    home = rects['home']
    _button(game, home, 'Esc · 首页')
    _text(game, '战役选关  ·  ↑↓←→ / WASD', pygame.Rect(home.right + 14, home.y, w - home.right - 30, home.h),
          font=game.font_med)
    for level, info in enumerate(config.LEVEL_CONFIGS, 1):
        tile = rects[f'level:{level}']
        selected = level == game.selected_level
        _panel(game, tile, selected=selected)
        _scene(tile.inflate(-4, -4), level, 208)
        number = pygame.Rect(tile.x + 8, tile.y + 5, 28, 20)
        if selected:
            Draw.rect(config.SCR, ACCENT, tile, width=3, border_radius=8)
            Draw.rect(config.SCR, ACCENT, number, border_radius=4)
        _text(game, f'{level:02}', number, font=game.font_tiny, color=PAPER if selected else ACCENT, align='center')
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
    _button(game, rects['start'], '出击  ·  Enter', primary=True)


def shop_rects(game):
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    width = min(w - 24, 910)
    height = min(h - 22, 402)
    x, y = (w - width) // 2, (h - height) // 2
    panel = pygame.Rect(x, y, width, height)
    rects = {'panel': panel,
             'close': pygame.Rect(panel.right - 48, y + 8, 36, 34)}
    gap = 6
    card_w = (width - 24 - gap * 3) // 4
    card_h = min(78, max(47, (height - 224) // 2))
    cards_y = y + 66
    for category, _, keys, _, _ in SHOP_SHELVES:
        for index, key in enumerate(keys):
            tile = pygame.Rect(x + 12 + index * (card_w + gap), cards_y, card_w, card_h)
            if category == 'weapon' and game._weapon_upgrade_cost(key) is not None:
                rects[f'upgrade:{key}'] = pygame.Rect(tile.right - 59, tile.y + 4, 55, 20)
            rects[f'{category}:{key}'] = tile
            if category == 'character':
                rects[f'skills:{key}'] = pygame.Rect(tile.x, tile.bottom + 2, tile.w, 24)
        cards_y += card_h + 28
    rects['feature'] = pygame.Rect(x + 12, cards_y + 4, width - 24, panel.bottom - cards_y - 14)
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
        return '已购'
    return f'{cost} 金币'


def _draw_skills(game, key, rect):
    skills = SKILL_DESCRIPTIONS[key]
    gap = 8
    cell_w = (rect.w - gap * (len(skills) - 1)) // len(skills)
    y = rect.y
    for index, (name, action, description) in enumerate(skills):
        x = rect.x + index * (cell_w + gap)
        thumb = pygame.Rect(x, y, min(44, cell_w // 4), min(42, rect.h))
        _panel(game, thumb, fill=PAPER, radius=5)
        _art(animation.frame(f'player_{key}_{action}', 2), thumb.inflate(-6, -6))
        text_x = thumb.right + 4
        text_w = x + cell_w - text_x
        _text(game, name, pygame.Rect(text_x, y, text_w, 18), font=game.font_tiny, color=ACCENT)
        lines = wrap(description, width=max(1, text_w // game.font_tiny.size('技')[0]))
        if len(lines) * 16 + 18 > rect.h:
            lines = [description]
        for line_index, line in enumerate(lines):
            _text(game, line, pygame.Rect(text_x, y + 18 + line_index * 16, text_w, 15),
                  font=game.font_tiny, color=MUTED)


def draw_shop(game):
    rects = shop_rects(game)
    panel = rects['panel']
    feature = rects['feature']
    game._draw_scrim(231)
    _panel(game, panel, fill=PAPER, radius=12)
    _text(game, '商店', pygame.Rect(panel.x + 12, panel.y + 6, 61, 36), font=game.font_med)
    _art(image_asset('ui/coin.png'), pygame.Rect(panel.x + 78, panel.y + 15, 19, 19))
    _text(game, str(game.player.gold), pygame.Rect(panel.x + 102, panel.y + 6, 72, 36),
          color=config.GOLD_COLOR)
    _button(game, rects['close'], '×')

    for category, heading, keys, assets, definitions in SHOP_SHELVES:
        characters = category == 'character'
        first = rects[f'{category}:{keys[0]}']
        _text(game, heading, pygame.Rect(first.x, first.y - 22, 92, 20))
        for index, key in enumerate(keys):
            tile = rects[f'{category}:{key}']
            status = _shop_status(game, key, characters)
            equipped = status == '已装备'
            _panel(game, tile, selected=equipped, fill=(21, 61, 66) if equipped else SURFACE)
            upgrade = rects.get(f'upgrade:{key}')
            art = pygame.Rect(tile.x + 8, tile.y + 3, tile.w - 16, tile.h - 37)
            if upgrade:
                art.w = upgrade.left - art.x - 3
                if game.desktop_controls:
                    art.x += 14
                    art.w -= 14
            _art(image_asset(assets[key]), art)
            if game.desktop_controls:
                number = index + (5 if characters else 1)
                _text(game, str(number), pygame.Rect(tile.x + 5, tile.y + 3, 18, 16),
                      font=game.font_tiny, color=ACCENT, align='center')
            level = game.player.weapon_upgrades.get(key, 0) if not characters else 0
            name = f'{definitions[key].name} Lv.{level}' if level else definitions[key].name
            _text(game, name, pygame.Rect(tile.x + 4, tile.bottom - 34, tile.w - 8, 16),
                  font=game.font_tiny, align='center')
            if upgrade:
                _panel(game, upgrade, selected=True, fill=(28, 74, 74), radius=4)
                _text(game, f'加强 {game._weapon_upgrade_cost(key)}', upgrade.inflate(-4, -2),
                      font=game.font_tiny, align='center')
            badge = pygame.Rect(tile.centerx - 28, tile.bottom - 17, 56, 15)
            color = config.GOLD_COLOR
            if status in ('已购', '已装备'):
                color = ACCENT if equipped else (169, 215, 255)
                fill = (22, 80, 72) if equipped else (34, 65, 91)
                Draw.rect(config.SCR, fill, badge, border_radius=5)
            _text(game, status, badge, font=game.font_tiny, color=color, align='center')
            if characters:
                _button(game, rects[f'skills:{key}'], '看技能',
                        active=game.shop_category == category and game.shop_character == key)

    characters = game.shop_category == 'character'
    selected = game.shop_character if characters else game.shop_weapon
    definitions = config.CHARACTER_DEFS if characters else config.WEAPON_DEFS
    _panel(game, feature)
    text_x = feature.x + 10
    _text(game, definitions[selected].name, pygame.Rect(text_x, feature.y + 4, feature.w // 2 - 10, 24),
          font=game.font_med)
    _text(game, game.shop_notice or _shop_status(game, selected, characters),
          pygame.Rect(feature.centerx, feature.y + 5, feature.w // 2 - 10, 22),
          font=game.font_tiny, color=config.GOLD_COLOR, align='right')
    if characters:
        _draw_skills(game, selected,
                     pygame.Rect(text_x, feature.y + 29, feature.w - 20, feature.h - 34))
    else:
        path = _WEAPON_ASSETS[selected]
        filename = path.rsplit('/', 1)[1]
        _art(image_asset(f'ui/weapon_showcase/{filename}') or image_asset(path),
             pygame.Rect(feature.centerx, feature.y + 31, feature.w // 2 - 10, feature.h - 36))
        _text(game, WEAPON_DESCRIPTIONS[selected], pygame.Rect(text_x, feature.y + 32, feature.w // 2 - 10, 20),
              font=game.font_tiny, color=MUTED)
