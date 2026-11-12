"""共用的屏幕控件，支持触屏和鼠标操作。"""
import math
from functools import lru_cache

import pygame
from . import config
from .asset_loader import image_asset, scale_surface_cached
from .render import Draw, RenderSurface, trim_transparent
from .visuals import panel_surface
from .config import CHARACTER_DEFS, WEAPON_DEFS, _CHAR_KEYS_ORDERED, _WEAPON_KEYS_ORDERED


_CHAR_ASSETS = {
    'fire': 'players/player_fire.png',
    'ice': 'players/player_ice.png',
    'water': 'players/player_water.png',
    'radiation': 'players/player_radiation.png',
}
_CHAR_LETTERS = {'fire': 'F', 'ice': 'I', 'water': 'W', 'radiation': 'R'}


_WEAPON_ASSETS = {
    'pistol': 'weapons/weapon_pistol.png',
    'rifle': 'weapons/weapon_rifle.png',
    'shotgun': 'weapons/weapon_shortgun.png',
    'sniper': 'weapons/weapon_awm.png',
}


# Each path is drawn in a 20px square.
_SKILL_GLYPHS = {
    'fisher_grenade': (((6, 6), (13, 6), (16, 10), (15, 16), (6, 17), (3, 12), (6, 6)),
                       ((8, 6), (8, 2), (13, 2), (15, 4))),
    'fire_wall': (((2, 17), (5, 9), (8, 13), (11, 3), (14, 12), (17, 8), (19, 17), (2, 17)),),
    'fireball': (((3, 12), (9, 5), (14, 3), (18, 7), (17, 12), (11, 17), (8, 15), (3, 17), (6, 12)),),
    'ice_floor': (((2, 15), (6, 8), (9, 12), (13, 4), (18, 15), (2, 15)), ((2, 18), (18, 18))),
    'ice_balls': (((10, 2), (17, 6), (17, 14), (10, 18), (3, 14), (3, 6), (10, 2), (10, 18)),
                  ((3, 6), (17, 14)), ((17, 6), (3, 14))),
    'water_heal': (((7, 4), (13, 4), (13, 8), (17, 8), (17, 13), (13, 13), (13, 17),
                    (7, 17), (7, 13), (3, 13), (3, 8), (7, 8), (7, 4)),),
    'water_boost': (((2, 9), (6, 5), (10, 5), (14, 9), (18, 7)),
                    ((2, 15), (6, 11), (10, 11), (14, 15), (18, 13))),
    'lightning': (((11, 2), (4, 11), (10, 11), (8, 18), (16, 8), (10, 8), (11, 2)),),
    'magnetic_storm': (((17, 5), (13, 2), (6, 3), (2, 8), (3, 14), (8, 18), (15, 16), (18, 11),
                        (15, 7), (10, 7), (7, 10), (10, 13), (13, 11)),),
    'radiation_laser': (((2, 14), (16, 4)), ((5, 17), (18, 8)), ((13, 3), (18, 2), (19, 7))),
    'dart_shield': (((3, 5), (10, 2), (17, 5), (16, 12), (10, 18), (4, 12), (3, 5)),
                    ((7, 11), (13, 7))),
}


@lru_cache(maxsize=96)
def _control_art(diameter, corner, color, enabled, active, action, selected, source, icon_size, stroke=1):
    padding = max(4, diameter // 7)
    size = diameter + 2 * padding
    tile = pygame.Surface((size, size), pygame.SRCALPHA)
    rect = pygame.Rect(padding, padding, diameter, diameter)
    fill = (10, 24, 38) if enabled else (13, 23, 32)
    border = (112, 172, 193) if enabled else (70, 91, 105)
    if active or action == 'attack':
        fill = tuple(15 + channel // (4 if active else 6) for channel in color)
        border = color
    pygame.draw.rect(tile, (0, 7, 15, 170), rect.move(0, max(2, diameter // 24)), border_radius=corner)
    tile.blit(panel_surface(diameter, diameter, border, fill, corner, 242 if enabled else 216, stroke), rect)
    if source is not None:
        ratio = min(wanted / original for wanted, original in zip(icon_size, source.get_size()))
        icon = scale_surface_cached(source, tuple(max(1, round(value * ratio)) for value in source.get_size()))
        if not enabled:
            icon = icon.copy()
            icon.set_alpha(205)
        tile.blit(icon, icon.get_rect(center=rect.center))
    if source is not None and not enabled:
        lock = pygame.Rect(0, 0, max(8, diameter // 4), max(6, diameter // 6))
        lock.bottomright = (rect.right - 3 * stroke, rect.bottom - 3 * stroke)
        metal = (194, 216, 227)
        shackle = lock.inflate(-lock.w // 3, 0).move(0, -lock.h // 2)
        pygame.draw.rect(tile, metal, shackle, width=stroke, border_radius=3 * stroke)
        pygame.draw.rect(tile, metal, lock, border_radius=2 * stroke)
    if selected:
        gold = (255, 224, 110)
        pygame.draw.rect(tile, gold, rect, max(2, diameter // 20), border_radius=corner)
        radius = max(5, diameter // 8)
        bx, by = rect.right - radius // 2, rect.top + radius // 2
        pygame.draw.circle(tile, gold, (bx, by), radius)
        half = radius // 2
        pygame.draw.lines(tile, (24, 29, 38), False,
                          ((bx - half, by), (bx - 1, by + half // 2), (bx + half, by - half)),
                          max(1, radius // 4))
    if action == 'auto_fire':
        width = max(6, diameter // 4)
        pygame.draw.rect(tile, color if active else (109, 123, 139),
                         (rect.centerx - width // 2, rect.centery + diameter // 5, width, max(2, diameter // 16)),
                         border_radius=2)
    return tile


@lru_cache(maxsize=24)
def _joystick_base(radius, edge):
    size = radius * 2
    image = panel_surface(size, size, edge, (9, 25, 39), radius, 202).copy()
    pygame.draw.circle(image, (100, 172, 191, 140), (radius, radius), round(radius * 0.72), 1)
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        pygame.draw.line(image, (*edge, 175),
                         (radius + dx * round(radius * 0.78), radius + dy * round(radius * 0.78)),
                         (radius + dx * round(radius * 0.89), radius + dy * round(radius * 0.89)), 2)
    return image


@lru_cache(maxsize=24)
def _joystick_grip(radius, edge):
    size = radius * 2
    image = panel_surface(size, size, edge, (26, 59, 79), radius, 255).copy()
    for dy in (-1, 0, 1):
        y = radius + dy * max(2, radius // 5)
        half = max(3, radius // 4)
        pygame.draw.line(image, (*edge, 230), (radius - half, y), (radius + half, y), 2)
    return image


class MobileControls:
    def __init__(self):
        self.fingers = {}
        self.joystick_id = None
        self.joystick_origin = None
        self._joystick_anchor = None
        self.axis = (0.0, 0.0)
        self.auto_fire = True

    def _window_size(self):
        try:
            return pygame.display.get_window_size()
        except pygame.error:
            return config.SCREEN_WIDTH, config.SCREEN_HEIGHT

    def event_position(self, event):
        width, height = self._window_size()
        return config.window_to_game((int(event.x * width), int(event.y * height)))

    def _buttons(self, game):
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        compact = height < 500
        gap = 70 if compact else 76
        inset = width // 50 if not game.desktop_controls else 0
        right = width - (42 if compact else 48) - inset
        left = right - gap
        fire_y = height - (72 if compact else 80)
        auto_x = right if game.desktop_controls else right - 78
        if not config.MOBILE_LANDSCAPE_VIEW:
            auto_x += inset  # Keep clear of the portrait health controls.
        # Mirror the offsets so both skills sit on the same arc around attack.
        arc_long, arc_short = (88, 32) if compact else (96, 35)
        utility_y = 40 if compact else 48
        utility_radius = 22 if compact else 27
        if game.desktop_controls:
            utility_y += 5
            char_radius = weapon_radius = 20
            char_positions = [(right, 104 + index * 48) for index in range(len(_CHAR_KEYS_ORDERED))]
            weapon_y = game.hud_diagnostics_y + 8 + weapon_radius
            weapon_positions = [(36, weapon_y + index * 48) for index in range(len(_WEAPON_KEYS_ORDERED))]
        else:
            if compact:
                char_y, char_gap, char_radius = 102, 62, 21
                weapon_y, weapon_x, weapon_radius, weapon_gap = height - 191, (36, 104), 24, 66
            else:
                char_y = 145 if config.MOBILE_LANDSCAPE_VIEW else 222
                char_gap, char_radius = 67, 25
                weapon_y, weapon_x, weapon_radius, weapon_gap = height - 270, (56, 136), 30, 78
            char_right = right if config.MOBILE_LANDSCAPE_VIEW else right + inset - inset // 3
            char_left = char_right - gap
            char_positions = ((char_left, char_y), (char_right, char_y),
                              (char_left, char_y + char_gap), (char_right, char_y + char_gap))
            weapon_positions = [(x, y) for y in (weapon_y - weapon_gap, weapon_y) for x in weapon_x]
        skill_radius = 24 if compact else 28
        button_rows = [
            ('shop', (left, utility_y), utility_radius, '商店', (85, 190, 230)),
            ('pause', (right, utility_y), utility_radius, 'Ⅱ', (170, 205, 230)),
            ('skill1', (right - arc_long, fire_y - arc_short), skill_radius, 'S1', (115, 205, 255)),
            ('skill2', (right - arc_short, fire_y - arc_long), skill_radius, 'S2', (115, 205, 255)),
            ('attack', (right, fire_y), 34 if compact else 36, '射击', (255, 125, 95)),
            ('auto_fire', (auto_x, fire_y + 36), 24 if compact else 25, '自动', (70, 220, 145)),
        ]
        for key, center in zip(_WEAPON_KEYS_ORDERED, weapon_positions):
            button_rows.append((f'weapon:{key}', center, weapon_radius,
                                WEAPON_DEFS[key].name, WEAPON_DEFS[key].color))
        if game.desktop_controls:
            button_rows = [row for row in button_rows if row[0] not in ('attack', 'skill1', 'skill2')]
        elif game.web and not game.player.character:
            button_rows = [row for row in button_rows if row[0] != 'skill2']
        elif game.player.character == 'radiation':
            special_x = right - 174
            button_rows.extend([
                ('laser', (special_x, fire_y - gap), utility_radius, 'L', (165, 245, 125)),
                ('dart', (special_x, fire_y), utility_radius, 'D', (245, 115, 145)),
            ])
        for key, center in zip(_CHAR_KEYS_ORDERED, char_positions):
            button_rows.append((f'character:{key}', center, char_radius,
                                _CHAR_LETTERS[key], CHARACTER_DEFS[key].color))
        return button_rows

    def is_pressed(self, action):
        return action in self.fingers.values()

    def handle_touch(self, event, game):
        finger_id = event.finger_id
        position = self.event_position(event)
        if event.type == pygame.FINGERDOWN:
            if self.joystick_id == -1:
                self.release(-1)
            for action, center, radius, _label, _color in self._buttons(game):
                padding = 0 if action.startswith('weapon:') else 8
                if math.hypot(position[0] - center[0], position[1] - center[1]) <= radius + padding:
                    self.fingers[finger_id] = action
                    return action
            if (self.joystick_id is None and
                    position[0] <= config.SCREEN_WIDTH * 0.45 and
                    position[1] >= config.SCREEN_HEIGHT * 0.5):
                self.fingers[finger_id] = 'joystick'
                self.joystick_id = finger_id
                self.joystick_origin = position
                self._update_axis(position)
            else:
                self.fingers[finger_id] = 'ignored'
            return None
        if event.type == pygame.FINGERMOTION:
            if self.fingers.get(finger_id) == 'joystick' and finger_id == self.joystick_id:
                self._update_axis(position)
            return None
        if event.type == pygame.FINGERUP:
            self.release(finger_id)
        return None

    def handle_mouse(self, event, game):
        position = config.window_to_game(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for action, center, radius, _label, _color in self._buttons(game):
                padding = 0 if action.startswith('weapon:') else 8
                if game.desktop_controls and action.startswith('character:'):
                    padding = 4
                if math.hypot(position[0] - center[0], position[1] - center[1]) <= radius + padding:
                    self.fingers[-1] = action
                    return action
            if (not game.desktop_controls and self.joystick_id is None and
                    position[0] <= config.SCREEN_WIDTH * 0.45 and
                    position[1] >= config.SCREEN_HEIGHT * 0.5):
                self.fingers[-1] = 'joystick'
                self.joystick_id = -1
                self.joystick_origin = position
                self._update_axis(position)
            return None
        if event.type == pygame.MOUSEMOTION and self.fingers.get(-1) == 'joystick':
            self._update_axis(position)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.release(-1)
        return None

    def release(self, finger_id):
        self.fingers.pop(finger_id, None)
        if finger_id == self.joystick_id:
            self.joystick_id = None
            self.joystick_origin = None
            self._joystick_anchor = None
            self.axis = (0.0, 0.0)

    def release_inactive_touches(self, touch_active):
        # SDL uses the browser's Touch.identifier as the finger ID.
        for finger_id in tuple(self.fingers):
            if finger_id != -1 and not touch_active(finger_id):
                self.release(finger_id)

    def reset(self):
        self.fingers.clear()
        self.joystick_id = None
        self.joystick_origin = None
        self._joystick_anchor = None
        self.axis = (0.0, 0.0)

    def _update_axis(self, position):
        if self.joystick_origin is None:
            return
        anchor_x, anchor_y = self._joystick_anchor or self.joystick_origin
        dx = position[0] - anchor_x
        dy = position[1] - anchor_y
        travel = (46 if config.SCREEN_HEIGHT < 500 else 64) / 2 - 8
        distance = math.hypot(dx, dy)
        dead_zone = 2
        if distance <= dead_zone:
            self.axis = (0.0, 0.0)
            return
        ux, uy = dx / distance, dy / distance
        if distance > travel:
            # Discard movement beyond full tilt so reversing needs only a short drag.
            self._joystick_anchor = (position[0] - ux * travel, position[1] - uy * travel)
        scale = min(1.0, (distance - dead_zone) / (travel - dead_zone))
        self.axis = (ux * scale, uy * scale)

    def _skill_timing(self, game, skill_type, now):
        player = game.player
        end = player.skill_cooldowns.get(skill_type, 0)
        duration = player.skill_display_duration.get(skill_type, 0)
        active_end = player.skill_active_until.get(skill_type, 0)
        if active_end > now:
            end = active_end + player.skill_active_cd.get(skill_type, 0)
        if skill_type == 'radiation_laser':
            laser = next((item for item in game.radiation_lasers
                          if item.owner is player and not item.is_expired(now)), None)
            if laser:
                duration = laser.duration + laser.cooldown_ms
                end = laser.spawn_time + duration
        return end, duration

    def _draw_desktop_skill_status(self, game, character_button):
        _, (cx, cy), radius, _, _ = character_button
        character = CHARACTER_DEFS.get(game.player.character)
        skill_actions = {'K': 'p1_skill1', 'L': 'p1_skill2'}
        skills = [(skill.name, skill.skill_type, skill_actions[skill.key_name])
                  for skill in character.skills] if character else [
            ('手榴弹', 'fisher_grenade', 'p1_skill1')]
        if game.player.character == 'radiation':
            skills.extend([('辐射激光', 'radiation_laser', 'p1_laser'),
                           ('飞镖', 'dart_shield', 'p1_dart')])
        keys = [game._key(action) for _, _, action in skills]
        key_width = max(game._keycap_width(key) for key in keys)
        name_width, status_width = 54, 30
        padding, gap, row_height = 6, 4, 18
        width = padding * 2 + name_width + key_width + status_width + gap * 2
        x, y = cx + radius - width, cy + radius + 8
        key_x = x + padding + name_width + gap
        status_x = key_x + key_width + gap
        game._draw_panel(x, y, width, 8 + row_height * len(skills), r=7)
        now = config.game_ticks()
        for index, ((name, skill_type, _), key) in enumerate(zip(skills, keys)):
            end, _ = self._skill_timing(game, skill_type, now)
            seconds = math.ceil((end - now) / 1000)
            text, color = (f'{seconds}s', (255, 220, 135)) if seconds > 0 else ('就绪', (118, 233, 193))
            row_y = y + 4 + row_height * index
            game._draw_text_fit(name, game.font_skill_status, (231, 243, 255),
                                pygame.Rect(x + padding, row_y, name_width, row_height))
            game._draw_keycap(key, (key_x + key_width // 2, row_y + row_height // 2))
            game._draw_text_fit(text, game.font_skill_status, color,
                                pygame.Rect(status_x, row_y, status_width, row_height), align='right')
        game._draw_gift_hud(now, cx + radius, y + 12 + row_height * len(skills))

    def draw(self, surface, game):
        hd = isinstance(surface, RenderSurface)
        scale = surface.scale if hd else 1
        blit = surface.blit_pixels if hd else surface.blit

        def blit_center(image, center):
            if hd and not game.desktop_controls:
                x, y = surface.point(center)
                art, dx, dy = trim_transparent(image)
                blit(art, (x + dx, y + dy))
            else:
                blit(image, image.get_rect(center=surface.point(center) if hd else center))

        buttons = self._buttons(game)
        for action, center, radius, label, color in buttons:
            active = action in self.fingers.values()
            enabled = action in ('shop', 'pause', 'attack', 'auto_fire', 'skill1', 'laser', 'dart')
            if action == 'auto_fire':
                active = self.auto_fire
            if action == 'skill2':
                enabled = bool(game.player.character)
            source = None
            icon_box = None
            selected = False
            upgrade_level = 0
            if action.startswith('weapon:'):
                key = action.split(':', 1)[1]
                enabled = key in game.player.owned_weapons and not (game.infinite_mode and key == 'pistol')
                selected = active = key == game.player.current_weapon
                source = image_asset(_WEAPON_ASSETS[key]) or game.weapon_icons[key]
                icon_box = (radius * 2 - 8, radius - 4)
                upgrade_level = game.player.weapon_upgrades.get(key, 0) if enabled else 0
            elif action.startswith('character:'):
                key = action.split(':', 1)[1]
                enabled = key in game.player.owned_characters
                selected = active = key == game.player.character
                source = image_asset(_CHAR_ASSETS[key])
                icon_box = (min(radius * 2 - 6, 38), min(radius * 2 - 6, 40))

            if source is not None:
                source = trim_transparent(source)[0]
            diameter = round(radius * 2 * scale)
            corner = radius if action in ('attack', 'skill1', 'skill2') else 12
            icon_size = tuple(round(value * scale) for value in icon_box) if source is not None else None
            art = _control_art(diameter, round(corner * scale), color, enabled,
                               active, action, selected, source, icon_size,
                               max(1, round(scale)) if game.desktop_controls else 1)
            blit_center(art, center)
            if upgrade_level:
                cx, cy = center
                badge = pygame.Rect(cx + radius - 14, cy - radius, 18, 18)
                Draw.circle(surface, (28, 36, 49), badge.center, 9)
                game._draw_text_fit(str(upgrade_level), game.font_tiny, (255, 224, 110),
                                    badge, align='center')
            if game.desktop_controls:
                key = game.desktop_button_key(action)
                cx, cy = center
                offset = radius + 6 + game._keycap_width(key) // 2
                if action.startswith('weapon:'):
                    hint = (cx + offset, cy)
                elif action in ('shop', 'pause'):
                    hint = (cx, cy - radius - 11)
                else:
                    hint = (cx - offset, cy)
                game._draw_keycap(key, hint)
            if source is not None:
                continue
            font = game.font_tiny if action in ('shop', 'auto_fire') else game.font_small
            skill_type = None
            if action in ('skill1', 'skill2'):
                if game.player.character:
                    key = 'K' if action == 'skill1' else 'L'
                    skill = next((skill for skill in CHARACTER_DEFS[game.player.character].skills
                                  if skill.key_name == key), None)
                    if skill:
                        skill_type = skill.skill_type
                        label = skill.name if len(skill.name) <= 3 else '潮汐'
                elif action == 'skill2':
                    label = '—'
                elif action == 'skill1':
                    skill_type = 'fisher_grenade'
                    label = '手榴弹'
            elif action in ('laser', 'dart'):
                skill_type = 'radiation_laser' if action == 'laser' else 'dart_shield'
                label = '激光' if action == 'laser' else '飞镖'
            if skill_type:
                now = config.game_ticks()
                end, duration = self._skill_timing(game, skill_type, now)
                if end > now:
                    remaining = end - now
                    label = f'{math.ceil(remaining / 1000)}s'
                    font = game.font_countdown
                    ring = pygame.Rect(0, 0, 2 * radius - 4, 2 * radius - 4)
                    ring.center = center
                    Draw.circle(surface, (47, 81, 99), center, radius - 2, 2)
                    sweep = math.tau * min(1, remaining / max(1, duration))
                    Draw.arc(surface, (125, 225, 241), ring, math.pi / 2, math.pi / 2 + sweep, 3)
                if game.web or (end <= now and not game.desktop_controls):
                    ink = CHARACTER_DEFS[game.player.character].color if game.player.character else (255, 207, 128)
                    cx, cy = center
                    size = radius * .056 if game.web else 1
                    if end > now:
                        ink = tuple(channel * 3 // 5 for channel in ink)
                    icon_y = cy if game.web else cy - 10
                    for path in _SKILL_GLYPHS[skill_type]:
                        points = [(round(cx + (x - 10) * size), round(icon_y + (y - 10) * size)) for x, y in path]
                        Draw.lines(surface, ink, False, points, max(2, round(size * 2)))
                    if game.web:
                        continue
                    game._draw_text_fit(label, game.font_tiny, (231, 243, 255),
                                        pygame.Rect(cx - radius + 5, cy + 3, radius * 2 - 10, 19),
                                        align='center')
                    continue
            text_color = (231, 243, 255) if enabled else (123, 138, 154)
            if action == 'auto_fire':
                label = '自动开' if active else '自动关'
                center = (center[0], center[1] - 4)
            label_rect = pygame.Rect(0, 0, radius * 2 - 6, 25)
            label_rect.center = center
            if game.desktop_controls:
                game._draw_text_fit(label, font, text_color, label_rect, align='center')
            elif not game.queue_ui_text(label, font, text_color, label_rect, 'center'):
                text = font.render(label, True, text_color)
                surface.blit(text, text.get_rect(center=center))

        if game.desktop_controls:
            self._draw_desktop_skill_status(game, buttons[-1])
            return
        _, (cx, cy), radius, _, _ = buttons[-1]
        game._draw_gift_hud(config.game_ticks(), cx + radius, cy + radius + 3)

        short = config.SCREEN_HEIGHT < 500
        center = self.joystick_origin or ((70 if short else 96) + config.SCREEN_WIDTH // 50,
                                         config.SCREEN_HEIGHT - (70 if short else 108))
        radius = 46 if short else 64
        edge = (111, 226, 226) if self.joystick_origin is not None else (106, 172, 192)
        blit_center(_joystick_base(round(radius * scale), edge), center)
        thumb = tuple(round(pos + axis * (radius - 16)) for pos, axis in zip(center, self.axis))
        blit_center(_joystick_grip(round((18 if short else 23) * scale), edge), thumb)
