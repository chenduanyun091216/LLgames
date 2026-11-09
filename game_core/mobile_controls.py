"""浏览器版触屏操作层；不改变桌面版输入。"""
import math
from functools import lru_cache

import pygame
from . import config
from .asset_loader import image_asset, scale_surface_cached
from .render import Draw, RenderSurface
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


@lru_cache(maxsize=96)
def _control_art(diameter, corner, color, enabled, active, action, selected, source, icon_size):
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
    tile.blit(panel_surface(diameter, diameter, border, fill, corner, 242 if enabled else 216), rect)
    if source is not None:
        ratio = min(wanted / original for wanted, original in zip(icon_size, source.get_size()))
        icon = scale_surface_cached(source, tuple(max(1, round(value * ratio)) for value in source.get_size()))
        if not enabled:
            icon = icon.copy()
            icon.set_alpha(205)
        tile.blit(icon, icon.get_rect(center=rect.center))
    if source is not None and not enabled:
        lock = pygame.Rect(0, 0, max(8, diameter // 4), max(6, diameter // 6))
        lock.bottomright = (rect.right - 3, rect.bottom - 3)
        metal = (194, 216, 227)
        shackle = lock.inflate(-lock.w // 3, 0).move(0, -lock.h // 2)
        pygame.draw.rect(tile, metal, shackle, width=1, border_radius=3)
        pygame.draw.rect(tile, metal, lock, border_radius=2)
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
        right = width - (42 if compact else 48)
        left = right - gap
        fire_y = height - (72 if compact else 80)
        # Mirror the offsets so both skills sit on the same arc around attack.
        arc_long, arc_short = (88, 32) if compact else (96, 35)
        utility_y = 40 if compact else 48
        utility_radius = 22 if compact else 27
        if compact:
            char_y, char_gap, char_radius = 102, 62, 21
            weapon_y, weapon_x, weapon_radius, weapon_gap = height - 191, (36, 104), 24, 66
        else:
            char_y = 145 if config.MOBILE_LANDSCAPE_VIEW else 222
            char_gap, char_radius = 67, 25
            weapon_y, weapon_x, weapon_radius, weapon_gap = height - 270, (56, 136), 30, 78
        char_positions = ((left, char_y), (right, char_y),
                          (left, char_y + char_gap), (right, char_y + char_gap))
        skill_radius = 24 if compact else 28
        button_rows = [
            ('shop', (left, utility_y), utility_radius, '商店', (85, 190, 230)),
            ('pause', (right, utility_y), utility_radius, 'Ⅱ', (170, 205, 230)),
            ('skill1', (right - arc_long, fire_y - arc_short), skill_radius, 'S1', (115, 205, 255)),
            ('skill2', (right - arc_short, fire_y - arc_long), skill_radius, 'S2', (115, 205, 255)),
            ('attack', (right, fire_y), 34 if compact else 36, '射击', (255, 125, 95)),
            ('auto_fire', (right - 78, fire_y + 36), 24 if compact else 25, '自动', (70, 220, 145)),
        ]
        for index, key in enumerate(_WEAPON_KEYS_ORDERED):
            center = (weapon_x[index % 2], weapon_y - weapon_gap * (1 - index // 2))
            button_rows.append((f'weapon:{key}', center, weapon_radius,
                                WEAPON_DEFS[key].name, WEAPON_DEFS[key].color))
        if game.player.character == 'radiation':
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
                if math.hypot(position[0] - center[0], position[1] - center[1]) <= radius + padding:
                    self.fingers[-1] = action
                    return action
            if (self.joystick_id is None and
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
            self.axis = (0.0, 0.0)

    def reset(self):
        self.fingers.clear()
        self.joystick_id = None
        self.joystick_origin = None
        self.axis = (0.0, 0.0)

    def _update_axis(self, position):
        if self.joystick_origin is None:
            return
        dx = position[0] - self.joystick_origin[0]
        dy = position[1] - self.joystick_origin[1]
        radius = (46 if config.SCREEN_HEIGHT < 500 else 64) - 16
        distance = math.hypot(dx, dy)
        dead_zone = 2
        if distance <= dead_zone:
            self.axis = (0.0, 0.0)
            return
        scale = min(1.0, (distance - dead_zone) / (radius * 0.5 - dead_zone))
        self.axis = (dx / distance * scale, dy / distance * scale)

    def draw(self, surface, game):
        hd = isinstance(surface, RenderSurface)
        scale = surface.scale if hd else 1
        blit = surface.blit_pixels if hd else surface.blit

        def blit_center(image, center):
            blit(image, image.get_rect(center=surface.point(center) if hd else center))

        for action, center, radius, label, color in self._buttons(game):
            active = action in self.fingers.values()
            enabled = action in ('shop', 'pause', 'attack', 'auto_fire', 'skill1', 'laser', 'dart')
            if action == 'auto_fire':
                active = self.auto_fire
            if action == 'skill2':
                enabled = bool(game.player.character)
            source = None
            icon_box = None
            selected = False
            if action.startswith('weapon:'):
                key = action.split(':', 1)[1]
                enabled = key in game.player.owned_weapons and not (game.infinite_mode and key == 'pistol')
                selected = active = key == game.player.current_weapon
                source = image_asset(_WEAPON_ASSETS[key]) or game.weapon_icons[key]
                icon_box = (radius * 2 - 8, radius - 4)
            elif action.startswith('character:'):
                key = action.split(':', 1)[1]
                enabled = key in game.player.owned_characters
                selected = active = key == game.player.character
                source = image_asset(_CHAR_ASSETS[key])
                icon_box = (min(radius * 2 - 6, 38), min(radius * 2 - 6, 40))

            diameter = round(radius * 2 * scale)
            corner = radius if action in ('attack', 'skill1', 'skill2') else 12
            icon_size = tuple(round(value * scale) for value in icon_box) if source is not None else None
            art = _control_art(diameter, round(corner * scale), color, enabled,
                               active, action, selected, source, icon_size)
            blit_center(art, center)
            if source is not None:
                continue
            font = game.font_tiny if action in ('shop', 'auto_fire') else game.font_small
            skill_type = None
            if action in ('skill1', 'skill2'):
                if game.player.character:
                    key = 'K' if action == 'skill1' else 'L'
                    skill_type = next((skill.skill_type for skill in CHARACTER_DEFS[game.player.character].skills
                                       if skill.key_name == key), None)
                elif action == 'skill1':
                    skill_type = 'fisher_grenade'
            elif action in ('laser', 'dart'):
                skill_type = 'radiation_laser' if action == 'laser' else 'dart_shield'
            if skill_type:
                now = config.game_ticks()
                end = game.player.skill_cooldowns.get(skill_type, 0)
                duration = game.player.skill_display_duration.get(skill_type, 0)
                active_end = game.player.skill_active_until.get(skill_type, 0)
                if active_end > now:
                    end = active_end + game.player.skill_active_cd.get(skill_type, 0)
                if action == 'laser':
                    laser = next((item for item in game.radiation_lasers
                                    if item.owner is game.player and not item.is_expired(now)), None)
                    if laser:
                        duration = laser.duration + laser.cooldown_ms
                        end = laser.spawn_time + duration
                if end > now:
                    remaining = end - now
                    label = f'{math.ceil(remaining / 1000)}s'
                    font = game.font_countdown
                    ring = pygame.Rect(0, 0, 2 * radius - 4, 2 * radius - 4)
                    ring.center = center
                    Draw.circle(surface, (47, 81, 99), center, radius - 2, 2)
                    sweep = math.tau * min(1, remaining / max(1, duration))
                    Draw.arc(surface, (125, 225, 241), ring, math.pi / 2, math.pi / 2 + sweep, 3)
            text_color = (231, 243, 255) if enabled else (123, 138, 154)
            if action == 'auto_fire':
                label = '自动开' if active else '自动关'
                center = (center[0], center[1] - 4)
            label_rect = pygame.Rect(0, 0, radius * 2 - 6, 25)
            label_rect.center = center
            if not game.queue_ui_text(label, font, text_color, label_rect, 'center'):
                text = font.render(label, True, text_color)
                surface.blit(text, text.get_rect(center=center))

        short = config.SCREEN_HEIGHT < 500
        center = self.joystick_origin or ((70, config.SCREEN_HEIGHT - 70) if short else
                                         (96, config.SCREEN_HEIGHT - 108))
        radius = 46 if short else 64
        edge = (111, 226, 226) if self.joystick_origin is not None else (106, 172, 192)
        blit_center(_joystick_base(round(radius * scale), edge), center)
        thumb = tuple(round(pos + axis * (radius - 16)) for pos, axis in zip(center, self.axis))
        blit_center(_joystick_grip(round((18 if short else 23) * scale), edge), thumb)
