"""
游戏实体：Player, Enemy, Bullet, Coin, Particle, FireWall, IceFloor, SkillProjectile,
         MagneticStorm, Boss, BossProjectile。
"""
import math
import random
from functools import lru_cache
import pygame
from .render import Draw, RenderSurface, blit_effect, effect_layer
from . import config
from .visuals import blit_label, draw_electric_arc, draw_glow
from .boss_skills import BOSS_COLORS, SIGNATURES, draw_bubble_crab
from .asset_loader import image_asset, image_asset_supersampled, scale_surface_cached
from . import animation

from .config import (
    WEAPON_DEFS, CHARACTER_DEFS,
    HEALTH_RED, HEALTH_GREEN, ENEMY_DEFS,
)

# 角色 → 高清贴图素材映射（呼吸基准按当前角色选择）
_CHAR_ASSETS = {
    'fire': 'players/player_fire.png',
    'ice': 'players/player_ice.png',
    'water': 'players/player_water.png',
    'radiation': 'players/player_radiation.png',
}
from .sprites import (
    _circle, _rect, _ellipse, _line, _polygon,
    make_player_surface, make_fire_player_surface, make_ice_player_surface,
    make_water_player_surface, make_radiation_player_surface,
    make_enemy_surface, make_coin_surface,
    make_boss_surface, blit_lit_sprite,
)


@lru_cache(maxsize=64)
def _laser_flash_sprite(image):
    flash = image.copy()
    flash.fill((90, 90, 90, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return flash


@lru_cache(maxsize=64)
def _niu_slam_sprite(image):
    sprite = image.copy()
    sprite.fill((255, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return sprite


def _breathing_scale(elapsed_ms, growth, period_ms):
    return 1.0 + growth * (1.0 - math.cos(elapsed_ms * math.tau / period_ms)) / 2.0


def _mobile_entity_scale():
    return (config.MOBILE_LANDSCAPE_ENTITY_SCALE if config.MOBILE_LANDSCAPE_VIEW
            else config.MOBILE_PORTRAIT_ENTITY_SCALE)


class Player:
    SIZE = (56, 66)
    SPEED = 4

    def __init__(self):
        self.x = config.SCREEN_WIDTH // 2
        self.y = config.GAME_AREA_BOTTOM - 14
        self.owned_weapons = ['pistol']
        self.current_weapon = 'pistol'
        self.gold = 0
        self.last_shot_time = 0
        self.surface = make_player_surface()
        self.sprite_asset = 'players/player1.png'  # 高清呼吸基准从此 PNG 超采样加载
        self.breath_base = None   # 高分辨率基准，呼吸缩放从它缩小采样，避免放大模糊
        self._breath_src = None
        self.character = None
        self.owned_characters = []
        self.skill_cooldowns = {}
        self.skill_display_duration = {}
        self.skill_active_until = {}
        self.skill_active_cd = {}
        self.water_boost_until = 0
        self.water_haste_until = 0
        self.gift_speed_until = 0
        self.rage_until = 0
        self.snow_slow_until = 0
        self.niu_freeze_until = 0
        self.niu_slow_until = 0
        self.weapon_ammo = {}
        self.animation_moving = False
        self.animation_move_at = None
        self.animation_skill = None
        self.animation_skill_at = None
        self.campaign = False
        self.breath_start_time = config.game_ticks()

    def rect(self):
        scale = _mobile_entity_scale()
        w, h = (max(1, round(size * scale)) for size in self.SIZE)
        return pygame.Rect(self.x - w // 2, self.y - h // 2, w, h)

    def bottom_limit(self):
        return config.SCREEN_HEIGHT - (self.rect().h + 1) // 2 - 8

    def move(self, dx, dy=0):
        previous = (self.x, self.y)
        width = self.rect().w
        half_width = width // 2
        min_x = max(40, config.GAME_AREA_LEFT + half_width)
        max_x = min(config.SCREEN_WIDTH - 40, config.GAME_AREA_RIGHT - (width + 1) // 2)
        self.x = max(min_x, min(max_x, self.x + dx))
        self.y = max(80, min(self.bottom_limit(), self.y + dy))
        self.animation_moving = (self.x, self.y) != previous
        if self.animation_moving:
            self.animation_move_at = config.game_ticks()

    def can_shoot(self, now):
        w = WEAPON_DEFS[self.current_weapon]
        rate = 520 if self.campaign and self.current_weapon == 'sniper' else w.fire_rate
        if self.campaign:
            boost = 1.30 if now < self.water_boost_until else 1.0
            haste = 2.0 if now < self.gift_speed_until else 1.0
            rate = round(rate / max(boost, haste))
            if now < self.rage_until:
                rate = min(rate, 120)
            if now < max(self.snow_slow_until, self.niu_slow_until):
                rate = round(rate / getattr(self, 'hazard_slow', 0.8))
            return now >= self.niu_freeze_until and now - self.last_shot_time >= math.ceil(rate / .70)
        if now < getattr(self, 'water_boost_until', 0):
            rate = int(rate / 2.0)
        if now < getattr(self, 'water_haste_until', 0):
            rate = int(rate * 2 / 3)
        if now < getattr(self, 'gift_speed_until', 0):
            rate = int(rate / 2.0)
        if now < getattr(self, 'rage_until', 0):
            rate = min(rate, 120)  # 终极狂暴：射击速度大幅提升（间隔极限 120ms）
        if now < self.snow_slow_until:
            rate *= 2
        if now < self.niu_slow_until:
            rate *= 2
        if now < self.niu_freeze_until:
            return False
        return now - self.last_shot_time >= math.ceil(rate / .70)

    def shoot(self, now):
        self.last_shot_time = now
        w = WEAPON_DEFS[self.current_weapon]
        if self.current_weapon == 'shotgun':
            return [Bullet(self.x, self.y - 28, w, self.current_weapon, self.character, angle=a) for a in (-18, 0, 18)]
        return [Bullet(self.x, self.y - 28, w, self.current_weapon, self.character)]

    def draw(self, surf):
        now = config.game_ticks()
        size_scale = _mobile_entity_scale()
        speed_active = now < getattr(self, 'gift_speed_until', 0)
        pulse = 1 + 0.12 * math.sin(now * 0.006 + self.x * 0.01)
        glow_r = int(42 * pulse * size_scale)
        if speed_active:
            # 极速 buff：金色能量脉冲光环 + 旋转星点（角色本体始终清晰，不做透明度闪断）
            sp = 1 + 0.15 * math.sin(now * 0.018)
            _circle(surf, (255, 235, 130, 80), (int(self.x), int(self.y)), int((glow_r + 12 * size_scale) * sp), max(1, round(5 * size_scale)))
            _circle(surf, (255, 190, 80, 45), (int(self.x), int(self.y)), int((glow_r + 20 * size_scale) * sp), max(1, round(2 * size_scale)))
            for i in range(8):
                a = now * 0.012 + i * math.tau / 8
                px = self.x + math.cos(a) * (glow_r + 24 * size_scale) * sp
                py = self.y + math.sin(a) * (glow_r + 24 * size_scale) * sp
                _circle(surf, (255, 240, 160, 150), (int(px), int(py)), max(1, round((2 + i % 2) * size_scale)))
        _circle(surf, (255, 230, 120, 42), (int(self.x), int(self.y)), glow_r, max(1, round(4 * size_scale)))
        _circle(surf, (90, 210, 255, 34), (int(self.x), int(self.y - 6 * size_scale)), int(glow_r * 0.78), max(1, round(3 * size_scale)))
        _ellipse(surf, (0, 0, 0, 50), (self.x - 22 * size_scale, self.y + 26 * size_scale,
                                        44 * size_scale, 10 * size_scale))
        if self.breath_base is None or self._breath_src is not self.surface:
            sw, sh = self.surface.get_size()
            asset = _CHAR_ASSETS.get(self.character, self.sprite_asset)
            hi = image_asset_supersampled(asset, (sw, sh), 1.5)
            self.breath_base = hi if hi is not None else scale_surface_cached(
                self.surface, (int(sw * 1.3), int(sh * 1.3)))
            self._breath_src = self.surface
        sw, sh = self.breath_base.get_size()
        # 呼吸缩放始终从高清基准缩小采样，避免放大模糊
        scale = _breathing_scale(now - self.breath_start_time, 0.30, 2000) / 1.3
        breathing_surface = scale_surface_cached(
            self.breath_base, (round(sw * scale * size_scale), round(sh * scale * size_scale))
        )
        name = 'player_' + self.character if self.character else self.sprite_asset.rsplit('/', 1)[-1].removesuffix('.png')
        index = animation.action_frame(self.animation_skill_at, now)
        sprite = None
        if index is not None and self.animation_skill:
            sprite = animation.frame(name + '_' + self.animation_skill, index)
            if sprite is None:
                sprite = animation.frame(name + '_cast', index)
        if sprite is None and self.animation_move_at is not None and 0 <= now - self.animation_move_at < 150:
            sprite = animation.frame(name + '_run', now // 120 % 4)
        if sprite is None:
            sprite = animation.frame(name + '_back', 0)
        if sprite is not None:
            breathing_surface = scale_surface_cached(sprite, breathing_surface.get_size())
        bsw, bsh = breathing_surface.get_size()
        accent = CHARACTER_DEFS[self.character].color if self.character in CHARACTER_DEFS else (117, 221, 255)
        boosted = now < max(self.water_boost_until, self.water_haste_until)
        if boosted:
            draw_glow(surf, (round(self.x), round(self.y)), max(bsw, bsh) // 2 + 18,
                      (82, 249, 255), round(205 + 40 * math.sin(now * 0.012)))
            accent = (112, 255, 249)
        blit_lit_sprite(surf, breathing_surface, (self.x - bsw // 2, self.y - bsh // 2),
                        accent, 245 if boosted else 140,
                        source=sprite or _CHAR_ASSETS.get(self.character, self.sprite_asset))


class Enemy:
    ENTRY_DAMAGE_Y = 8
    ENTRY_END_Y = 10
    def __init__(self, edef):
        self.edef = edef
        self.is_large = edef['is_large']
        self.is_zongzong = edef.get('zongzong', False)
        self.zong_hits = 0
        self.zong_expression = 0
        self.zong_expression_from = 0
        self.zong_expression_at = 0
        self.gold_value = edef['gold']
        self.speed = edef['base_speed'] + random.uniform(-0.15, 0.15)
        size = 110 if self.is_large else 74 if self.is_zongzong else 64
        self.unscaled_base_w = size
        self.unscaled_base_h = size - 14 if self.is_large else size - 8
        self.size_scale = _mobile_entity_scale()
        self.base_w = round(self.unscaled_base_w * self.size_scale)
        self.base_h = round(self.unscaled_base_h * self.size_scale)
        self.w = self.base_w
        self.h = self.base_h
        half_width = self.w // 2
        min_x = max(50, config.GAME_AREA_LEFT + half_width)
        max_x = min(config.SCREEN_WIDTH - 50, config.GAME_AREA_RIGHT - (self.w + 1) // 2)
        self.x = random.uniform(min_x, max_x)
        self.y = -self.h
        self.hits = {}
        self.max_hp = None
        self.damage_taken = 0.0
        self.burning = False
        self.burn_start = 0
        self.burn_duration = 3000
        self.last_burn_tick = 0
        self.burn_hits = 0
        self.burn_damage = False
        self.frozen = False
        self.frozen_until = 0
        self.snowflake_until = 0
        self.water_mark_until = 0
        self.chase_color = None
        self.chase_side = 0
        self.chase_partner = None
        self.slowed_until = 0
        self.slow_mult = 1.0
        self.infected = False
        self.infected_weapon = 'pistol'
        self.health_mult = edef.get('health_mult', 1.0)
        self.last_contact_damage_time = -1000
        self.last_attack_time = config.game_ticks() + random.randint(800, 2200)
        self.attack_interval_min = 3800
        self.attack_interval_max = 7000
        self.attack_interval = random.randint(self.attack_interval_min, self.attack_interval_max)
        self.breath_start_time = config.game_ticks()
        self.base_surface = make_enemy_surface(edef['key'])
        self.base_surface_size = self.base_surface.get_size()
        self.surface = self.base_surface
        self.sprite_asset = 'bosses/zongzong.png' if self.is_zongzong else f'enemies/enemy_{edef["key"]}.png'
        if self.is_zongzong:
            self._update_zongzong_size()
        elif self.size_scale != 1.0:
            target_size = tuple(max(1, round(value * self.size_scale))
                                for value in self.base_surface_size)
            self.surface = scale_surface_cached(self.base_surface, target_size)
        self.breath_base = None   # 高分辨率基准，呼吸缩放从它缩小采样，避免放大模糊
        self._breath_src = None
        self.immune_text_until = 0
        self.label_font = config.make_font(max(1, round(18 * self.size_scale)), bold=True) if self.is_zongzong else None
        self.immune_font = config.make_font(max(1, round(16 * self.size_scale)), bold=True) if self.is_zongzong else None

    def set_size_scale(self, scale):
        if self.size_scale == scale:
            return
        self.size_scale = scale
        self.base_w = round(self.unscaled_base_w * scale)
        self.base_h = round(self.unscaled_base_h * scale)
        if self.is_zongzong:
            self._update_zongzong_size()
        else:
            self.w = self.base_w
            self.h = self.base_h
            target_size = tuple(max(1, round(value * scale))
                                for value in self.base_surface_size)
            self.surface = self.base_surface if scale == 1.0 else scale_surface_cached(
                self.base_surface, target_size
            )
        self.breath_base = None
        self._breath_src = None
        if self.is_zongzong:
            self.label_font = config.make_font(max(1, round(18 * scale)), bold=True)
            self.immune_font = config.make_font(max(1, round(16 * scale)), bold=True)

    def rect(self):
        return pygame.Rect(int(self.x - self.w // 2), int(self.y), self.w, self.h)

    def update(self, target=None):
        now = config.game_ticks()
        if self.frozen:
            if now >= self.frozen_until:
                self.frozen = False
            else:
                return
        if self.burning:
            if now - self.burn_start >= self.burn_duration:
                self.burning = False
                self.burn_damage = False
            elif self.burn_damage and self.y + self.h > 0 and now - self.last_burn_tick >= 500:
                self.burn_hits += 0.5 if self.y < self.ENTRY_END_Y else 1
                self.last_burn_tick = now
        move_mult = self.slow_mult if now < self.slowed_until else 1.0
        if move_mult == 1.0:
            self.slow_mult = 1.0
        if self.chase_color is None:
            step = self.speed * move_mult
            if self.y < self.ENTRY_END_Y:
                step *= 1 + 4 * min(1, (self.ENTRY_END_Y - self.y) / (self.h + self.ENTRY_END_Y))
            self.y += step
        elif target is not None:
            left = config.GAME_AREA_LEFT + self.w / 2
            right = config.GAME_AREA_RIGHT - self.w / 2
            gap = self.w + 8
            center = max(left + gap / 2, min(right - gap / 2, target.x))
            target_x = center + self.chase_side * gap / 2 if self.chase_partner else target.x
            dx, dy = target_x - self.x, target.rect().centery - (self.y + self.h / 2)
            step = min(1, self.speed * move_mult / max(1, math.hypot(dx, dy)))
            if self.chase_partner:
                if self.chase_side < 0:
                    right = min(right, self.chase_partner.x - gap)
                else:
                    left = max(left, self.chase_partner.x + gap)
            self.x = max(left, min(right, self.x + dx * step * .85))
            self.y += dy * step

    def hit_by(self, weapon_name, amount=1.0):
        if self.y + self.h <= 0:
            return
        if self.y < self.ENTRY_END_Y:
            amount *= 0.5
        now = config.game_ticks()
        if self.frozen and now < self.frozen_until:
            amount *= 2.0 if self.max_hp is None else 1.25
        if self.max_hp is None:
            self.hits[weapon_name] = self.hits.get(weapon_name, 0) + amount * getattr(self, 'damage_mult', 1.0)
        else:
            self.damage_taken += amount
        if self.is_zongzong:
            self.zong_hits += 1
            target = 0 if self.zong_hits == 1 else max(1, min(3, int(self._damage_progress() * 4)))
            if target > self.zong_expression:
                self.zong_expression_from = self.zong_expression
                self.zong_expression = target
                self.zong_expression_at = now
            self._update_zongzong_size()

    def show_immune(self, now=None):
        self.immune_text_until = (config.game_ticks() if now is None else now) + 650

    def _damage_progress(self):
        if self.max_hp is not None:
            return min(1.0, (self.damage_taken + self.burn_hits) / self.max_hp)
        if not self.hits:
            return 0.0
        best = 0.0
        for weapon_name, amount in self.hits.items():
            if weapon_name not in WEAPON_DEFS:
                continue
            w = WEAPON_DEFS[weapon_name]
            needed = w.large_shots if self.is_large else w.normal_shots
            needed = max(1, math.ceil(needed * self.health_mult))
            best = max(best, amount / needed)
        return min(1.0, best)

    def _update_zongzong_size(self):
        grow = 1.0 + self._damage_progress() * 0.50
        self.base_w = round(self.unscaled_base_w * self.size_scale)
        self.base_h = round(self.unscaled_base_h * self.size_scale)
        self.w = int(self.base_w * grow)
        self.h = int(self.base_h * grow)
        if config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT < config.SCREEN_WIDTH:
            half_width = self.w // 2
            right_half_width = (self.w + 1) // 2
            self.x = max(config.GAME_AREA_LEFT + half_width,
                         min(config.GAME_AREA_RIGHT - right_half_width, self.x))
        target_size = (
            max(1, int(self.base_surface_size[0] * self.size_scale * grow)),
            max(1, int(self.base_surface_size[1] * self.size_scale * grow)),
        )
        self.surface = image_asset('bosses/zongzong.png', target_size) or scale_surface_cached(self.base_surface, target_size)
        self.breath_base = None
        self._breath_src = None

    def apply_slow(self, now, duration=4000, mult=0.7):
        if self.max_hp is not None and self.is_zongzong:
            duration //= 2
        self.slowed_until = max(self.slowed_until, now + duration)
        self.slow_mult = min(self.slow_mult, mult)

    def projectile_count(self):
        if self.is_zongzong:
            return 3
        if self.is_large:
            return 3
        return 2 if self.edef['key'] == 'crab' else 1

    def should_attack(self, now):
        return now - self.last_attack_time >= self.attack_interval

    def attack(self, now, target_x):
        self.last_attack_time = now
        self.attack_interval = random.randint(self.attack_interval_min, self.attack_interval_max)
        if self.is_zongzong:
            if random.random() > 0.42:
                return []
            return [BossProjectile(self.x, self.y + self.h - 10, a, 3.0,
                                   homing=True, damage=1, bomb=True)
                    for a in (-22, 0, 22)]
        count = self.projectile_count()
        spread = 48
        projectiles = []
        for i in range(count):
            offset = (i - (count - 1) / 2) * spread
            dx = target_x - self.x + offset
            dy = config.GAME_AREA_BOTTOM - self.y
            angle = math.degrees(math.atan2(dx, dy))
            projectiles.append(BossProjectile(self.x, self.y + self.h - 8, angle, 3.2))
        return projectiles

    def is_killed(self, weapon_name):
        if self.max_hp is not None:
            return self.damage_taken + self.burn_hits >= self.max_hp
        w = WEAPON_DEFS[weapon_name]
        needed = w.large_shots if self.is_large else w.normal_shots
        needed = max(1, math.ceil(needed * self.health_mult))
        return (self.hits.get(weapon_name, 0) + self.burn_hits) >= needed

    def reached_bottom(self):
        return self.chase_color is None and self.y > config.GAME_AREA_BOTTOM + 20

    def draw(self, surf):
        # 阴影
        shadow_y = int(self.y + self.h - 6)
        _ellipse(surf, (0, 0, 0, 50), (int(self.x - self.w // 2 + 8), shadow_y, self.w - 16, 6))
        now = config.game_ticks()
        if self.is_zongzong:
            cx, cy = int(self.x), int(self.y + self.h // 2)
            aura_r = max(round(38 * self.size_scale), int(self.w * 0.72))
            for rr, alpha in ((aura_r + 18, 38), (aura_r + 8, 62), (aura_r, 96)):
                _circle(surf, (80, 255, 135, alpha), (cx, cy), rr, 2)
            for i in range(12):
                ang = now * 0.0035 + i * math.tau / 12
                r1 = aura_r - 8 + math.sin(now * 0.006 + i) * 4
                r2 = aura_r + 20
                x1 = cx + math.cos(ang) * r1
                y1 = cy + math.sin(ang) * r1
                x2 = cx + math.cos(ang) * r2
                y2 = cy + math.sin(ang) * r2
                _line(surf, (120, 255, 170, 118), (x1, y1), (x2, y2), 3)
                _circle(surf, (255, 245, 150, 155), (x2, y2), 3)
        # 精灵（非 zongzong：从 1.3x 高分辨率基准缩小采样，消除呼吸放大模糊）
        if self.chase_color is not None:
            draw_bubble_crab(surf, self.x, self.y + self.h * .5, self.w,
                             self.chase_color, now)
        elif self.is_zongzong:
            sw, sh = self.surface.get_size()
            image = self.surface
            sprite = None
            if self.zong_hits:
                elapsed = max(0, now - self.zong_expression_at)
                index = min(self.zong_expression, self.zong_expression_from + elapsed // 120)
                sprite = animation.frame('zongzong_hurt', index)
                if sprite is not None:
                    image = scale_surface_cached(sprite, (sw, sh))
            blit_lit_sprite(surf, image, (self.x - sw // 2, self.y + self.h // 2 - sh // 2),
                            (101, 237, 150), 125, source=sprite or self.sprite_asset)
        else:
            if self.breath_base is None or self._breath_src is not self.surface:
                sw, sh = self.surface.get_size()
                hi = image_asset_supersampled(self.sprite_asset, (sw, sh), 1.5)
                self.breath_base = hi if hi is not None else scale_surface_cached(
                    self.surface, (int(sw * 1.3), int(sh * 1.3)))
                self._breath_src = self.surface
            sw, sh = self.breath_base.get_size()
            scale = _breathing_scale(now - self.breath_start_time, 0.30, 2000) / 1.3
            breathing_surface = scale_surface_cached(
                self.breath_base, (round(sw * scale), round(sh * scale))
            )
            bsw, bsh = breathing_surface.get_size()
            accent = (255, 163, 108) if self.is_large else (144, 217, 235)
            blit_lit_sprite(surf, breathing_surface, (self.x - bsw // 2, self.y + self.h // 2 - bsh // 2),
                            accent, 105, source=self.sprite_asset)
        # 燃烧效果
        if self.burning:
            x, y = self.x, self.y - 7
            tip = math.sin(now * 0.016) * 2
            _polygon(surf, (255, 105, 28),
                     ((x, y + 4), (x - 6, y + 1), (x - 6, y - 4),
                      (x - 3, y - 8), (x + tip, y - 14), (x + 2, y - 6),
                      (x + 5, y - 9), (x + 7, y), (x + 4, y + 3)))
            _polygon(surf, (255, 221, 106),
                     ((x, y + 3), (x - 3, y + 1), (x - 2, y - 3),
                      (x + tip, y - 7), (x + 4, y), (x + 2, y + 2)))
        self._draw_ice_status(surf, now)
        if now < self.slowed_until and now >= self.snowflake_until and not self.frozen:
            _circle(surf, (120, 210, 255, 100), (int(self.x), int(self.y + self.h // 2)),
                    max(round(14 * self.size_scale), self.w // 3), max(1, round(2 * self.size_scale)))
        if now < self.water_mark_until:
            x, y = self.x - 10, self.y - 17
            _polygon(surf, (76, 192, 255), ((x, y - 7), (x - 5, y), (x + 5, y)))
            _circle(surf, (76, 192, 255), (x, y), 5)
            _circle(surf, (224, 251, 255), (x - 2, y - 1), 2)
        if self.infected:
            x, y = self.x + 10, self.y - 17
            _circle(surf, (35, 58, 34), (x, y), 7)
            for i in range(3):
                angle = i * math.tau / 3 - math.pi / 2
                _circle(surf, (177, 249, 99),
                        (x + 4 * math.cos(angle), y + 4 * math.sin(angle)), 2)
            _circle(surf, (210, 255, 136), (x, y), 1)
        if self.is_zongzong and self.label_font:
            height = self.label_font.size('粽')[1]
            center = (int(self.x), int(self.y - height - 18) + height // 2)
            _circle(surf, (255, 236, 160, 230), center, 15)
            blit_label(surf, self.label_font, '粽', (90, 50, 20), center,
                       max(1, round(18 * self.size_scale)), bold=True)
        if self.is_zongzong and config.game_ticks() < self.immune_text_until and self.immune_font:
            width, height = self.immune_font.size('免疫')
            box = pygame.Rect(0, 0, width + 10, height + 4)
            box.center = (int(self.x), int(self.y) + self.h // 2)
            _rect(surf, (60, 30, 10, 185), box, border_radius=4)
            blit_label(surf, self.immune_font, '免疫', (255, 245, 210), box.center,
                       max(1, round(16 * self.size_scale)), bold=True)
        # HP条
        bar_w = self.w + (round(10 * self.size_scale) if self.is_zongzong else 0)
        bar_h = max(1, round((7 if self.is_zongzong else 4) * self.size_scale))
        bx = int(self.x - bar_w // 2)
        by = int(self.y - 8)
        if self.hits or self.damage_taken:
            ratio = self._damage_progress()
        else:
            ratio = 0.0
        _rect(surf, (30, 10, 10, 180), (bx - 1, by - 1, bar_w + 2, bar_h + 2), border_radius=2)
        _rect(surf, HEALTH_RED, (bx, by, bar_w, bar_h), border_radius=2)
        _rect(surf, HEALTH_GREEN, (bx, by, int(bar_w * ratio), bar_h), border_radius=2)
        _rect(surf, (150, 255, 100, 80), (bx, by, int(bar_w * ratio), 2), border_radius=1)

    def _draw_ice_status(self, surf, now):
        if self.frozen or now < self.snowflake_until:
            x, y = self.x, self.y - 12
            for i in range(6):
                angle = i * math.tau / 6
                dx, dy = math.cos(angle), math.sin(angle)
                _line(surf, (225, 250, 255), (x, y), (x + dx * 8, y + dy * 8), 2)
                for side in (-1, 1):
                    _line(surf, (165, 227, 255), (x + dx * 5, y + dy * 5),
                          (x + dx * 3 - side * dy * 3, y + dy * 3 + side * dx * 3))

        x, y = self.x, self.y + self.h * .5
        w, h = self.w * .56, self.h * .58
        if self.frozen:
            layer = effect_layer(surf, (math.ceil(w * 2) + 4, math.ceil(h * 2) + 4))
            position = (round(x - w - 2), round(y - h - 2))
            x, y = w + 2, h + 2
            crown, base = (x + w * .22, y - h), (x - w * .25, y + h)
            left, right = (x - w, y - h * .32), (x + w, y + h * .27)
            shell = (crown, (x + w * .8, y - h * .68), right,
                     (x + w * .54, y + h * .84), base, (x - w, y + h * .4), left)
            _polygon(layer, (100, 202, 249, 82), shell)
            ridge = (x + w * .14, y + h * .20)
            _polygon(layer, (196, 245, 255, 75), (crown, left, ridge))
            _polygon(layer, (61, 161, 230, 75), (crown, right, base, ridge))
            for corner in (crown, left, right, base):
                _line(layer, (205, 246, 255, 145), corner, ridge)
            _polygon(layer, (220, 250, 255, 210), shell, 2)
            blit_effect(surf, layer, position)
        elif self.frozen_until and 0 <= now - self.frozen_until < 420:
            t = (now - self.frozen_until) / 420
            alpha = round(235 * (1 - t))
            for i in range(8):
                angle = i * math.tau / 8
                px = x + math.cos(angle) * (w + 22 * t)
                py = y + math.sin(angle) * (h + 22 * t) + 20 * t * t
                size = 3 + i % 3
                shard = ((px - size, py + size), (px + size, py + size * .45), (px, py - size))
                _polygon(surf, (121, 210, 250, alpha), shard)
                _line(surf, (225, 249, 255, alpha), shard[0], shard[2])


class Bullet:
    def __init__(self, x, y, wdef, weapon_key, character=None, angle=0):
        self.x = x
        self.y = y
        self.speed = wdef.speed * 0.8
        self.angle = angle
        self.weapon_name = weapon_key
        self.character = character
        self.damage = 1.0
        self.gift_kind = None
        self.hit_targets = set()
        self.radius = 10
        if weapon_key == 'sniper' or (weapon_key == 'shotgun' and angle == 0):
            self.radius = 13
        if weapon_key == 'shotgun' and angle == 0:
            self.color = (255, 55, 45)
        elif weapon_key == 'sniper':
            self.color = (190, 95, 255)
        elif weapon_key == 'rifle':
            self.color = (95, 175, 255)
        elif weapon_key == 'shotgun':
            self.color = (255, 166, 52)
        else:
            self.color = (255, 230, 40)
        self.spawn_time = config.game_ticks()
        self.max_lifetime = 3000

    def rect(self):
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self):
        rad = math.radians(self.angle)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed

    def is_offscreen(self):
        return (config.game_ticks() - self.spawn_time >= self.max_lifetime or
                self.y < -20 or self.y > config.SCREEN_HEIGHT + 20 or
                self.x < -20 or self.x > config.SCREEN_WIDTH + 20)

    def draw(self, surf):
        rad = math.radians(self.angle)
        dx, dy = -math.sin(rad), math.cos(rad)
        head = (int(self.x), int(self.y))
        if self.gift_kind:
            now = config.game_ticks()
            color = (255, 105, 35) if self.gift_kind == 'fire' else (65, 155, 255)
            core = (255, 235, 150) if self.gift_kind == 'fire' else (188, 237, 255)
            gr = max(3, self.radius) * 2
            _circle(surf, (*color, 44), head, gr + 4)
            for distance, alpha in ((gr * 3, 65), (gr * 2, 120), (gr, 195)):
                _circle(surf, (*color, alpha), (int(self.x + dx * distance),
                        int(self.y + dy * distance)), gr)
            if self.gift_kind == 'fire':
                flame = [
                    (self.x - gr * 0.7, self.y + gr),
                    (self.x, self.y + gr * 1.8 + math.sin(now * 0.02) * 2),
                    (self.x + gr * 0.7, self.y + gr),
                ]
                _polygon(surf, (255, 185, 40, 220), flame)
            else:
                for a in range(0, 360, 60):
                    rad = math.radians(a + now * 0.15)
                    _line(surf, (150, 222, 255, 210), head,
                          (self.x + math.sin(rad) * (gr + 3),
                           self.y + math.cos(rad) * (gr + 3)), 1)
            _circle(surf, color, head, gr + 2)
            _circle(surf, core, (head[0] - 1, head[1] - 1), max(2, gr // 2))
            return
        core = max(3, round(self.radius * 0.65))
        length = {'rifle': 19, 'sniper': 22}.get(self.weapon_name, 13)
        for fraction, alpha, radius in ((1, 55, core - 3), (0.7, 100, core - 2), (0.4, 160, core - 1)):
            trail = (int(self.x + dx * length * fraction), int(self.y + dy * length * fraction))
            _circle(surf, (*self.color, alpha), trail, radius)
        _circle(surf, self.color, head, core)
        _circle(surf, (255, 248, 232), (head[0] - 2, head[1] - 2), 2)

class Coin:
    def __init__(self, x, y, value):
        self.x = x
        self.y = y
        self.value = value
        self.speed = 2
        self.surface = make_coin_surface()
        self.radius = 12

    def rect(self):
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self):
        self.y += self.speed

    def is_offscreen(self):
        return self.y > config.GAME_AREA_BOTTOM + 20

    def draw(self, surf):
        # 金币辉光
        _circle(surf, (255, 215, 0, 40), (int(self.x), int(self.y)), self.radius + 4)
        _circle(surf, (255, 235, 80, 30), (int(self.x), int(self.y)), self.radius + 2)
        position = (int(self.x - self.radius), int(self.y - self.radius))
        if isinstance(surf, RenderSurface):
            source = image_asset('ui/coin.png') or self.surface
            surf.blit(source, position, logical_size=self.surface.get_size(), static=True)
        else:
            surf.blit(self.surface, position)
        phase = config.game_ticks() % 1400
        if phase < 240:
            glint = (self.x - 7 + phase * 14 / 240, self.y - 6)
            _line(surf, (255, 249, 192, 205), glint, (glint[0] - 2, glint[1] + 5), 2)


class GiftBox:
    SIZE = 54

    def __init__(self, x=None):
        self.radius = self.SIZE // 2
        if x is None:
            min_x = max(50, config.GAME_AREA_LEFT + self.radius)
            max_x = min(config.SCREEN_WIDTH - 50, config.GAME_AREA_RIGHT - self.radius)
            self.x = random.uniform(min_x, max_x)
        else:
            self.x = x
        self.y = -self.SIZE
        self.speed = 1.7
        self.kind = random.choice(('lightning', 'fire', 'ice', 'heal', 'haste'))
        self.breath_start_time = config.game_ticks()
        self.font = config.make_font(18, bold=True)

    def rect(self):
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self):
        self.y += self.speed

    def is_offscreen(self):
        return self.y > config.GAME_AREA_BOTTOM + self.radius

    def draw(self, surf):
        now = config.game_ticks()
        pulse = 1.0 + 0.08 * math.sin((now - self.breath_start_time) * 0.008)
        r = int(self.radius * pulse)
        x = int(self.x - r)
        y = int(self.y - r)
        _circle(surf, (255, 230, 80, 52), (int(self.x), int(self.y)), r + 9)
        _rect(surf, (190, 45, 55), (x, y, r * 2, r * 2), border_radius=8)
        _rect(surf, (255, 215, 70), (x + r - 4, y, 8, r * 2), border_radius=3)
        _rect(surf, (255, 215, 70), (x, y + r - 4, r * 2, 8), border_radius=3)
        _rect(surf, (255, 245, 165, 120), (x + 4, y + 4, r * 2 - 8, r - 5), border_radius=5, width=1)
        blit_label(surf, self.font, '?', (255, 255, 255), (int(self.x), int(self.y)), 18, bold=True)


class Particle:
    def __init__(self, x, y, color, count=8):
        self.particles = []
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(1, 4)
            self.particles.append({
                'x': x, 'y': y,
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed - 2,
                'life': random.uniform(10, 25),
                'max_life': 25,
                'color': color,
                'size': random.uniform(2, 5),
            })

    def update(self):
        for p in self.particles[:]:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += 0.1
            p['life'] -= 1
            if p['life'] <= 0:
                self.particles.remove(p)

    def is_dead(self):
        return len(self.particles) == 0

    def draw(self, surf):
        for p in self.particles:
            alpha = int(255 * (p['life'] / p['max_life']))
            c = (*p['color'][:3], max(0, alpha))
            _circle(surf, c, (p['x'], p['y']), p['size'])


class Explosion:
    def __init__(self, x, y, color=(255, 180, 60), count=18, *, heavy=True, element=None):
        self.heavy = heavy
        self.element = element
        self.x = x
        self.y = y
        self.age = 0
        self.life = 26
        self.color = color
        self.sparks = []
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(2.0, 6.5)
            self.sparks.append({
                'x': x,
                'y': y,
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed,
                'size': random.uniform(2, 5),
            })

    def update(self):
        self.age += 1
        for s in self.sparks:
            s['x'] += s['vx']
            s['y'] += s['vy']
            s['vx'] *= 0.92
            s['vy'] = s['vy'] * 0.92 + 0.04

    def is_dead(self):
        return self.age >= self.life

    def draw(self, surf):
        t = self.age / self.life
        alpha = max(0, int(210 * (1 - t)))
        if self.heavy:
            radius = int(10 + 34 * t)
            draw_glow(surf, (round(self.x), round(self.y)), 38, self.color, alpha)
            _circle(surf, (255, 244, 209, alpha // 3), (self.x, self.y), max(3, radius - 6), 1)
            _circle(surf, (*self.color[:3], alpha // 2), (self.x, self.y), radius, 3)
        core_color = (255, 247, 218, alpha)
        if self.age < 5:
            reach = (16 if self.heavy else 9) + 2 * self.age
            flash = (255, 248, 225, 245 - 42 * self.age)
            _line(surf, flash, (self.x - reach, self.y), (self.x + reach, self.y), 2)
            _line(surf, flash, (self.x, self.y - reach), (self.x, self.y + reach), 2)
            if self.heavy:
                _circle(surf, flash, (self.x, self.y), 7 + 3 * self.age, 2)
        _circle(surf, core_color, (self.x, self.y), max(2, int(9 * (1 - t))))
        if self.element == 'water':
            radius = 8 + round(t * 25)
            for offset in (0, 6):
                _ellipse(surf, (119, 226, 255, alpha), (self.x - radius - offset,
                         self.y - radius / 2 - offset / 2, 2 * (radius + offset), radius + offset), 2)
        elif self.element == 'radiation':
            radius = 10 + round(t * 22)
            for index in range(3):
                start = index * math.tau / 3 + t
                Draw.arc(surf, (193, 255, 103, alpha),
                         pygame.Rect(self.x - radius, self.y - radius, 2 * radius, 2 * radius),
                         start, start + 1.2, 3)
        for s in self.sparks:
            size = max(1, int(s['size'] * (1 - t)))
            x, y = s['x'], s['y']
            if self.element == 'ice':
                _polygon(surf, (170, 233, 255, alpha), ((x, y - size * 2), (x + size, y),
                         (x, y + size * 2), (x - size, y)))
            elif self.element == 'fire':
                _line(surf, (255, 129 + size * 20, 58, alpha), (x, y),
                      (x - s['vx'], y - s['vy'] + size * 2), size)
            else:
                _circle(surf, (*self.color[:3], alpha), (x, y), size)


# ═══════════════════════════════════════════════════════════════════════════════
#  FireWall — 扩大范围，居中放置
# ═══════════════════════════════════════════════════════════════════════════════

class FireWall:
    def __init__(self, x, y, lifetime=5000):
        self.x = x
        self.y = y
        self.w = 200
        self.h = 60
        self.speed = 0
        self.lifetime = lifetime
        self.spawn_time = config.game_ticks()
        self.last_damage_time = 0

    def update(self):
        self.y -= self.speed

    def rect(self):
        return pygame.Rect(int(self.x - self.w // 2), int(self.y - self.h), self.w, self.h)

    def is_expired(self):
        return config.game_ticks() - self.spawn_time >= self.lifetime

    def can_damage(self, now):
        if now - self.last_damage_time >= 500:
            self.last_damage_time = now
            return True
        return False

    def draw(self, surf):
        rx = int(self.x - self.w // 2)
        ry = int(self.y - self.h / 2 - 14)
        now = config.game_ticks()
        _rect(surf, (255, 89, 25, 65), (rx - 3, ry - 5, self.w + 6, 36), border_radius=6)
        _rect(surf, (255, 171, 63), (rx, ry, self.w, 28), border_radius=4)
        for row, offset in enumerate((0, -16)):
            for x in range(offset, self.w, 32):
                left, right = max(0, x), min(self.w, x + 30)
                top = ry + 2 + row * 13
                shade = int(24 * math.sin(now * 0.012 + x))
                _rect(surf, (176 + shade, 49, 26), (rx + left, top, right - left, 11), border_radius=2)
                _line(surf, (255, 128, 47), (rx + left + 1, top), (rx + right - 2, top))
        for i in range(9):
            x = rx + 11 + i * 22
            lift = 6 + 5 * math.sin(now * 0.016 + i * 2.1)
            _polygon(surf, (255, 175, 45, 195), ((x - 5, ry + 1), (x + 2, ry - lift), (x + 5, ry + 1)))


# ═══════════════════════════════════════════════════════════════════════════════
#  IceFloor — 新行为：向上移动的冰墙，碰到敌人后范围冰冻
# ═══════════════════════════════════════════════════════════════════════════════

class IceFloor:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.w = config.SCREEN_WIDTH // 3
        self.h = 92
        self.speed = 4.0
        self.alive = True
        self.freeze_radius = 60  # 碰到敌人后冰冻范围
        self.gaps = []
        self.hits_left = 5

    def update(self):
        self.y -= self.speed

    def rect(self):
        return pygame.Rect(int(self.x - self.w // 2), int(self.y - self.h // 2), self.w, self.h)

    def is_offscreen(self):
        return self.y < -self.h

    def collides(self, entity):
        if not self.alive:
            return False
        er = entity.rect()
        if not self.rect().colliderect(er):
            return False
        hit_x = entity.x
        return not any(abs(hit_x - gx) <= gr for gx, gr in self.gaps)

    def hit(self, x):
        """半月冰刃被怪物咬出缺口，但整体继续存在。"""
        self.gaps.append((x, 34))
        if len(self.gaps) > 8:
            self.gaps.pop(0)
        self.hits_left -= 1
        if self.hits_left <= 0:
            self.alive = False

    def block_projectile(self, projectile):
        if not self.alive:
            return False
        projectile_rect = getattr(projectile, 'block_rect', None)
        projectile_rect = projectile_rect() if projectile_rect else projectile.rect()
        if not self.rect().colliderect(projectile_rect):
            return False
        if not getattr(projectile, 'big_fireball', False) and any(abs(projectile.x - gx) + getattr(projectile, 'r', 0) <= gr for gx, gr in self.gaps):
            return False
        self.hit(projectile.x)
        return True

    def draw(self, surf):
        count = 13
        for i in range(count):
            t = 2 * i / (count - 1) - 1
            x = self.x + t * (self.w / 2 - 13)
            if any(abs(x - gx) <= gr for gx, gr in self.gaps):
                continue
            y = self.y + 36 * t * t
            width = self.w / count * 0.72
            tip = (x + t * 13, y - 34 + (i % 3) * 5)
            base = (x - t * 6, y + 12)
            left, right = (x - width, y - 1), (x + width, y - 9)
            _polygon(surf, (38, 126, 213), (tip, right, base, left))
            _polygon(surf, (133, 222, 255), (tip, left, base, (x, y - 10)))
            _line(surf, (219, 253, 255), tip, left, 2)
            _line(surf, (94, 188, 244), left, base, 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  SkillProjectile — 火球穿透、冰球保持
# ═══════════════════════════════════════════════════════════════════════════════

class SkillProjectile:
    def __init__(self, x, y, angle, speed, ptype, piercing=False, owner=None, skill_type=None):
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = speed
        self.ptype = ptype
        self.piercing = piercing
        self.r = {'fireball': 28, 'grenade': 12, 'fire_rocket': 8}.get(ptype, 18)
        self.lifetime = 900 if ptype == 'grenade' else 2500
        self.spawn_time = config.game_ticks()
        self.alive = True
        self.damage = 1.5 if ptype == 'fireball' else 1.0
        self.hit_targets = set()
        self.owner = owner
        self.skill_type = skill_type

    def update(self):
        rad = math.radians(self.angle)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed
        if config.game_ticks() - self.spawn_time >= self.lifetime:
            self.alive = False

    def rect(self):
        return pygame.Rect(int(self.x - self.r), int(self.y - self.r), self.r * 2, self.r * 2)

    def is_offscreen(self):
        return (self.y < -30 or self.y > config.SCREEN_HEIGHT + 30 or
                self.x < -30 or self.x > config.SCREEN_WIDTH + 30)

    def draw(self, surf):
        if self.ptype == 'fireball':
            radius = 20
            # 外圈光晕
            for i in range(4, 0, -1):
                _circle(surf, (255, 100, 20, 25 - i * 5), (int(self.x), int(self.y)), radius + i)
            _circle(surf, (255, 60, 10), (int(self.x), int(self.y)), radius)
            _circle(surf, (255, 140, 30), (int(self.x), int(self.y)), radius - 3)
            _circle(surf, (255, 200, 80), (int(self.x), int(self.y)), radius - 6)
            _circle(surf, (255, 255, 200), (int(self.x) - 3, int(self.y) - 3), radius // 4)
            # 旋转纹理
            now = config.game_ticks()
            for a in range(0, 360, 72):
                rad = math.radians(a + now * 0.1)
                ex = self.x + math.sin(rad) * (radius * 0.6)
                ey = self.y - math.cos(rad) * (radius * 0.6)
                _circle(surf, (255, 228, 105), (ex, ey), 3)
        elif self.ptype == 'fire_rocket':
            angle = math.radians(self.angle)
            dx, dy = math.sin(angle), -math.cos(angle)
            nx, ny = -dy, dx
            nose = (self.x + dx * 24, self.y + dy * 24)
            left = (self.x - dx * 16 + nx * 7, self.y - dy * 16 + ny * 7)
            right = (self.x - dx * 16 - nx * 7, self.y - dy * 16 - ny * 7)
            tail = (self.x - dx * 43, self.y - dy * 43)
            _polygon(surf, (255, 100, 25, 185), (left, tail, right))
            _polygon(surf, (255, 174, 67), (left, nose, right))
            _line(surf, (255, 245, 176), (self.x, self.y), nose, 3)
        elif self.ptype == 'grenade':
            _circle(surf, (40, 90, 50, 230), (int(self.x), int(self.y)), int(self.r))
            _circle(surf, (105, 145, 80, 210), (int(self.x) - 2, int(self.y) - 3), int(self.r) - 4)
            _rect(surf, (30, 45, 35, 230), (int(self.x) - 4, int(self.y) - 15, 8, 5), border_radius=2)
            _line(surf, (230, 210, 120, 180), (self.x + 3, self.y - 14), (self.x + 10, self.y - 20), 2)
        else:
            for i in range(4, 0, -1):
                _circle(surf, (80, 180, 255, 25 - i * 5), (int(self.x), int(self.y)), int(self.r) + i)
            _circle(surf, (40, 140, 255), (int(self.x), int(self.y)), int(self.r))
            _circle(surf, (100, 200, 255), (int(self.x), int(self.y)), int(self.r) - 4)
            _circle(surf, (180, 230, 255), (int(self.x), int(self.y)), int(self.r) - 8)
            _circle(surf, (230, 245, 255), (int(self.x) - 3, int(self.y) - 3), int(self.r) // 4)
            # 冰晶纹
            now = config.game_ticks()
            for a in range(0, 360, 60):
                rad = math.radians(a + now * 0.08)
                ex = self.x + math.sin(rad) * (self.r * 0.5)
                ey = self.y - math.cos(rad) * (self.r * 0.5)
                _circle(surf, (236, 250, 255), (ex, ey), 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  Lightning — 闪电链特效（瞬时伤害 5 个随机敌人）
# ═══════════════════════════════════════════════════════════════════════════════

class Lightning:
    TRAVEL_MS = 55

    def __init__(self, src_x, src_y, targets, damage, *, gift=False):
        self.start_x = src_x
        self.start_y = src_y
        self.targets = targets
        self.damage = damage
        self.gift = gift
        self.lifetime = 430
        self.spawn_time = config.game_ticks()

    def is_expired(self):
        return config.game_ticks() - self.spawn_time >= self.lifetime

    def draw(self, surf):
        now = config.game_ticks()
        age = now - self.spawn_time
        travel = min(1, max(0, age / self.TRAVEL_MS))
        alpha = round(255 * max(0, 1 - max(0, age - self.TRAVEL_MS) / (self.lifetime - self.TRAVEL_MS)))
        for index, target in enumerate(self.targets):
            start = (self.start_x, self.start_y)
            target_point = getattr(target, 'lightning_target', None)
            tx, ty = target_point(*start) if target_point else (target.x, target.y + target.h // 2)
            end = (self.start_x + (tx - self.start_x) * travel,
                   self.start_y + (ty - self.start_y) * travel)
            draw_electric_arc(surf, start, end, (255, 202, 58), alpha, now, index, 3)


# ═══════════════════════════════════════════════════════════════════════════════
#  MagneticStorm — 磁暴圈，吸附+持续伤害
# ═══════════════════════════════════════════════════════════════════════════════

class MagneticStorm:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 140
        self.lifetime = 3000
        self.pull_duration = 1500
        self.explode_time = 2000
        self.spawn_time = config.game_ticks()
        self.last_damage_time = 0
        self.pull_speed = 3.0
        self.exploded = False

    def is_expired(self):
        return config.game_ticks() - self.spawn_time >= self.lifetime

    def can_pull(self, now):
        return now - self.spawn_time <= self.pull_duration

    def should_explode(self, now):
        return (not self.exploded) and now - self.spawn_time >= self.explode_time

    def can_damage(self, now):
        if now - self.last_damage_time >= 300:
            self.last_damage_time = now
            return True
        return False

    def pull(self, entity):
        """将实体向中心吸附。"""
        dx = self.x - entity.x
        dy = self.y - (entity.y + entity.h // 2)
        dist = math.hypot(dx, dy)
        if dist < 1:
            return
        force = self.pull_speed * min(1, self.radius / max(1, dist))
        entity.x += dx / dist * force
        entity.y += dy / dist * force

    def contains(self, entity):
        ex = entity.x
        ey = entity.y + entity.h // 2
        return math.hypot(self.x - ex, self.y - ey) < self.radius

    def contains_point(self, x, y):
        return math.hypot(self.x - x, self.y - y) < self.radius

    def contains_projectile(self, projectile):
        return math.hypot(self.x - projectile.x, self.y - projectile.y) < self.radius + getattr(projectile, 'r', 0)

    def pull_projectile(self, projectile):
        dx = self.x - projectile.x
        dy = self.y - projectile.y
        dist = math.hypot(dx, dy)
        if dist < 1:
            return
        force = self.pull_speed * 1.8 * min(1, self.radius / max(1, dist))
        projectile.x += dx / dist * force
        projectile.y += dy / dist * force

    def draw(self, surf):
        now = config.game_ticks()
        alpha = int(120 + 55 * math.sin(now * 0.006))
        pulse = 1 + 0.08 * math.sin(now * 0.008)
        colors = [(255, 35, 35), (40, 255, 80), (170, 70, 255), (245, 245, 255)]
        bg_color = colors[(now // 160) % len(colors)]

        storm_surf = effect_layer(surf, (int(self.radius * 2 * pulse), int(self.radius * 2 * pulse)))
        cx_center = int(self.radius * pulse)
        cy_center = int(self.radius * pulse)

        # 深色核废水污染区：红绿紫白跳动
        _circle(storm_surf, (*bg_color, 95), (cx_center, cy_center), int(self.radius * 0.92 * pulse))
        _circle(storm_surf, (3, 5, 12, 210), (cx_center, cy_center), int(self.radius * 0.78 * pulse))
        _circle(storm_surf, (*bg_color, 70), (cx_center, cy_center), int(self.radius * 0.62 * pulse))
        for idx, r in enumerate(range(int(self.radius * pulse), int(self.radius * 0.42 * pulse), -11)):
            a = max(0, alpha - (self.radius * pulse - r) * 5)
            c = colors[(idx + now // 140) % len(colors)]
            _circle(storm_surf, (*c, a), (cx_center, cy_center), r, 3)

        for i in range(28):
            phase = now * 0.004 + i * 1.7
            rr = (self.radius * 0.18 + (i * 19 + now * 0.03) % (self.radius * 0.7)) * pulse
            bx = cx_center + math.cos(phase) * rr
            by = cy_center + math.sin(phase * 0.8) * rr * 0.65
            bubble_r = 3 + int(3 * (0.5 + 0.5 * math.sin(phase * 2.3)))
            _circle(storm_surf, (180, 255, 160, 90), (bx, by), bubble_r, 1)

        # 中心龙卷风
        for i in range(14):
            t = i / 13
            y = cy_center + int((t - 0.5) * self.radius * 0.95)
            width = int((13 + 45 * (1 - t)) * pulse)
            twist = now * 0.012 + i * 0.9
            x1 = cx_center + int(math.sin(twist) * width)
            x2 = cx_center - int(math.sin(twist + 0.7) * width * 0.75)
            _line(storm_surf, (235, 255, 235, 120), (x1, y), (x2, y + 10), 3)
            _circle(storm_surf, (120, 255, 150, 70), (x1, y), max(3, 8 - i // 3))

        # 边缘涡柱和内部脉冲都按时间驱动，独立于战斗随机数。
        for i in range(5):
            angle = now * 0.0016 + i * math.tau / 5
            distance = self.radius * pulse * 0.71
            x = cx_center + math.cos(angle) * distance
            y = cy_center + math.sin(angle) * distance
            for ring in range(5):
                width = 8 + ring * 5
                swirl = x + math.sin(now * 0.018 + ring) * 5
                _ellipse(storm_surf, (169, 255, 179, 130),
                         (swirl - width / 2, y - ring * 6, width, 8), 2)
        for i in range(4):
            burst = (now + i * 115) // 460
            phase = ((now + i * 115) % 460) / 460
            angle = i * 2.4 + burst * 1.9
            x = cx_center + math.cos(angle) * self.radius * 0.46
            y = cy_center + math.sin(angle) * self.radius * 0.46
            _circle(storm_surf, (255, 234, 151, int(205 * (1 - phase))), (x, y), 4 + int(24 * phase), 2)
            _circle(storm_surf, (255, 255, 225, int(230 * (1 - phase))), (x, y), max(2, int(8 * (1 - phase))))

        # 中心核心
        _circle(storm_surf, (180, 255, 70, min(255, alpha * 2)), (cx_center, cy_center), 17)
        _circle(storm_surf, (255, 255, 180, min(255, alpha * 2)), (cx_center, cy_center), 8)

        blit_effect(surf, storm_surf, (int(self.x - cx_center), int(self.y - cy_center)))


class RadiationLaser:
    def __init__(self, owner, duration=5000):
        self.owner = owner
        self.duration = duration
        self.spawn_time = config.game_ticks()
        self.last_damage_times = {}
        self.swing_power = 0.0
        self.swing_speed = 0.0
        self.last_whip_time = 0

    def is_expired(self, now):
        return now - self.spawn_time >= self.duration

    def beam_width(self):
        return int(Player.SIZE[0] * 0.40)

    def rect(self):
        w = self.beam_width()
        bottom = int(self.owner.y - Player.SIZE[1] // 2)
        extra = int(abs(self.swing_power) + 10)
        return pygame.Rect(int(self.owner.x - w // 2 - extra), 0, w + extra * 2, max(1, bottom))

    def whip(self, now):
        interval = max(40, now - self.last_whip_time) if self.last_whip_time else 260
        impulse = max(10, min(72, int(9500 / interval)))
        # 持续按住空格（快速连续触发）：冲量减半且甩动上限降为 50%
        holding = bool(self.last_whip_time) and interval < 400
        if holding:
            impulse = max(5, int(impulse * 0.5))
        cap_power = 60 if holding else 120
        cap_speed = 0.0225 if holding else 0.045
        self.swing_power = min(cap_power, self.swing_power * 0.65 + impulse)
        self.swing_speed = min(cap_speed, self.swing_speed * 0.7 + impulse * 0.00045)
        self.last_whip_time = now

    def can_damage(self, target, now):
        key = id(target)
        if now - self.last_damage_times.get(key, 0) >= getattr(self, 'damage_interval', 120):
            self.last_damage_times[key] = now
            return True
        return False

    def push(self, target):
        dx = target.x - self.owner.x
        if abs(dx) < 1:
            dx = random.choice((-1, 1))
        half_width = target.w // 2
        min_x = max(30, config.GAME_AREA_LEFT + half_width)
        max_x = min(config.SCREEN_WIDTH - 30, config.GAME_AREA_RIGHT - (target.w + 1) // 2)
        target.x = max(min_x, min(max_x, target.x + (1 if dx > 0 else -1) * 8))
        target.y = max(-target.h, target.y - 14)

    def draw(self, surf):
        r = self.rect()
        now = config.game_ticks()
        decay = max(0.0, 1.0 - (now - self.last_whip_time) / 900.0) if self.last_whip_time else 0.0
        swing = self.swing_power * decay
        speed = max(0.01, self.swing_speed)
        colors = [(150, 0, 18), (0, 135, 42), (8, 42, 170), (95, 0, 150)]
        c = colors[(now // 55) % len(colors)]
        beam = effect_layer(surf, (r.w + 72, r.h))
        cx = beam.get_size()[0] // 2
        last_outer = None
        last_inner = None
        last_core = None
        base_width = self.beam_width()
        for y in range(0, r.h, 8):
            t = y / max(1, r.h)
            offset = math.sin(now * speed + t * 8.5) * swing * (0.2 + 0.9 * (1 - t))
            width = base_width + int(10 * (1 - t))
            outer = (cx + int(offset), y)
            inner = (cx + int(offset * 0.72), y)
            core = (cx + int(offset * 0.52), y)
            if last_outer:
                _line(beam, (*c, 125), last_outer, outer, width + 26)
                _line(beam, (20, 8, 28, 218), last_inner, inner, max(6, width + 6))
                _line(beam, (*c, 235), last_inner, inner, max(6, width // 2))
                _line(beam, (255, 245, 230, 220), last_core, core, max(4, width // 5))
            last_outer, last_inner, last_core = outer, inner, core
        for y in range(0, r.h, 15):
            whip_offset = int(math.sin(now * speed + y * 0.11) * swing * 0.75)
            phase = math.sin(now * 0.055 + y * 0.14)
            c2 = colors[(y // 15 + now // 45) % len(colors)]
            _line(beam, (*c2, 220),
                  (cx + whip_offset - base_width // 2 - 10, y),
                  (cx + whip_offset + base_width // 2 + 10, y + int(phase * 16)), 3)
            if y % 45 == 0:
                bx = cx + int(math.sin(now * 0.03 + y) * (r.w * 0.75))
                _circle(beam, (*c2, 180), (bx, y), 10)
                _circle(beam, (255, 255, 255, 160), (bx, y), 3)
        blit_effect(surf, beam, (r.x - 36, r.y))
        head = (int(self.owner.x), int(self.owner.y - Player.SIZE[1] // 2))
        for rr, alpha in ((34, 80), (24, 125), (16, 185)):
            _circle(surf, (*c, alpha), head, rr)
        _circle(surf, (255, 245, 230, 210), head, max(5, r.w // 5))


# ═══════════════════════════════════════════════════════════════════════════════
#  旋转飞镖盾（辐射工程师 R 技能）
# ═══════════════════════════════════════════════════════════════════════════════

class SpinningDarts:
    """8 个带齿纹的飞盘环绕自身旋转：持续伤害触碰的敌人、抵挡敌方子弹；
    持续结束后所有飞盘向外飞出，继续伤害怪物直到飞出屏幕。"""
    DART_COUNT = 8
    RADIUS = 145             # 环绕半径
    ANGULAR_SPEED = 0.0045   # rad/ms，公转速度
    DART_HIT = 26            # 飞盘碰撞半径
    DAMAGE_INTERVAL = 180    # 对同一目标的持续伤害间隔
    FLY_SPEED = 9.0          # 飞出速度 px/帧
    # 深红 / 深紫 交替配色：(暗色, 亮色)
    _DART_COLORS = [
        ((125, 20, 30), (205, 60, 70)),   # 深红
        ((72, 16, 115), (155, 60, 205)),  # 深紫
    ]

    def __init__(self, owner, duration=5000):
        self.owner = owner
        self.duration = duration
        self.spawn_time = config.game_ticks()
        self.last_damage_times = {}
        self.skill_type = 'dart_shield'
        self.released = False          # 是否已结束环绕、向外飞出
        self.release_time = 0
        self._fly_discs = []           # 飞出阶段: [[x, y, vx, vy], ...]

    def is_expired(self, now):
        return now - self.spawn_time >= self.duration

    def is_gone(self, now):
        """技能彻底结束（所有飞盘已离屏）。"""
        return self.released and not self._fly_discs

    def release(self, now):
        """环绕结束：所有飞盘沿当前轨道方向向外飞出。"""
        if self.released:
            return
        self.release_time = now
        cx, cy = self.center()
        positions = list(self.dart_positions(now))  # 先取环绕位置，再置 released
        self.released = True
        for (dx, dy), _ang in positions:
            vx, vy = dx - cx, dy - cy
            dist = max(1, math.hypot(vx, vy))
            self._fly_discs.append([float(dx), float(dy),
                                    vx / dist * self.FLY_SPEED, vy / dist * self.FLY_SPEED])

    def update(self):
        """飞出阶段：移动飞盘并移除出屏的。"""
        if not self.released:
            return
        for d in self._fly_discs[:]:
            d[0] += d[2]
            d[1] += d[3]
            if (d[0] < -70 or d[0] > config.SCREEN_WIDTH + 70
                    or d[1] < -70 or d[1] > config.SCREEN_HEIGHT + 70):
                self._fly_discs.remove(d)

    def center(self):
        return int(self.owner.x), int(self.owner.y - Player.SIZE[1] // 2 + 12)

    def dart_positions(self, now):
        if self.released:
            for i, d in enumerate(self._fly_discs):
                ang = now * 0.012 + i * math.tau / self.DART_COUNT
                yield (int(d[0]), int(d[1])), ang
            return
        cx, cy = self.center()
        base = now * self.ANGULAR_SPEED
        for i in range(self.DART_COUNT):
            ang = base + i * math.tau / self.DART_COUNT
            yield (cx + int(math.cos(ang) * self.RADIUS),
                   cy + int(math.sin(ang) * self.RADIUS * 0.70)), ang

    def hits(self, rect, now):
        r = self.DART_HIT
        for (dx, dy), _ang in self.dart_positions(now):
            if pygame.Rect(dx - r, dy - r, r * 2, r * 2).colliderect(rect):
                return True
        return False

    def can_damage(self, target, now):
        tid = id(target)
        last = self.last_damage_times.get(tid, 0)
        if now - last >= self.DAMAGE_INTERVAL:
            self.last_damage_times[tid] = now
            return True
        return False

    def _draw_disc(self, surf, dx, dy, spin, dark, light):
        """带齿纹的旋转飞盘（增强版：外发光 + 锐利锯齿）。"""
        glow_pulse = 1 + 0.12 * math.sin(spin * 1.4)
        # 外发光
        _circle(surf, (*light, 42), (dx, dy), int(26 * glow_pulse))
        _circle(surf, (*light, 24), (dx, dy), int(32 * glow_pulse))
        # 齿纹：12 个锐利旋转锯齿
        teeth = 12
        for i in range(teeth):
            a = spin + i * math.tau / teeth
            p1 = (dx + math.cos(a - 0.10) * 15, dy + math.sin(a - 0.10) * 15)
            mid = (dx + math.cos(a) * 17, dy + math.sin(a) * 17)
            tip = (dx + math.cos(a) * 24, dy + math.sin(a) * 24)
            p2 = (dx + math.cos(a + 0.10) * 15, dy + math.sin(a + 0.10) * 15)
            _polygon(surf, dark, [p1, tip, p2])
            if i % 2 == 0:
                _line(surf, (*light, 140), mid, tip, 2)
        # 盘体
        _circle(surf, dark, (dx, dy), 16)
        body = tuple(min(255, int(c * 1.25 + 12)) for c in dark)
        _circle(surf, body, (dx, dy), 13)
        # 轮圈 + 内环
        _circle(surf, light, (dx, dy), 15, 2)
        _circle(surf, (255, 245, 200), (dx, dy), 12, 1)
        _circle(surf, tuple(int(c * 0.6) for c in dark), (dx, dy), 8)
        # 旋辐（体现旋转）
        for i in range(3):
            a = spin + i * math.tau / 3
            _line(surf, light, (dx + math.cos(a) * 4, dy + math.sin(a) * 4),
                  (dx + math.cos(a) * 11, dy + math.sin(a) * 11), 2)
            _line(surf, (255, 235, 190, 150), (dx + math.cos(a + 0.16) * 5, dy + math.sin(a + 0.16) * 5),
                  (dx + math.cos(a + 0.16) * 9, dy + math.sin(a + 0.16) * 9), 1)
        # 轴心
        _circle(surf, (25, 22, 30), (dx, dy), 3)
        _circle(surf, (255, 250, 235), (dx, dy), 2)
        _circle(surf, light, (dx, dy), 1)

    def draw(self, surf):
        now = config.game_ticks()
        remaining = max(0.0, 1.0 - (now - self.spawn_time) / self.duration)
        flash = not self.released and remaining < 0.25 and (now // 120) % 2 == 0
        positions = list(self.dart_positions(now))

        if not self.released:
            cx, cy = self.center()
            pulse = 0.5 + 0.5 * math.sin(now * 0.012)
            warn = max(0.0, min(1.0, (0.28 - remaining) / 0.28))
            # 环绕轨道微光
            track = (cx - self.RADIUS, int(cy - self.RADIUS * 0.70), self.RADIUS * 2, int(self.RADIUS * 1.4))
            # —— 多层能量轨道 ——
            _ellipse(surf, (205, 45, 90, int(30 + 40 * warn)), track, 4)
            _ellipse(surf, (120, 60, 230, int(24 + 30 * pulse)), track, 2)
            _ellipse(surf, (255, 210, 90, int(20 + 80 * warn)), (track[0] + 12, track[1] + 8, track[2] - 24, track[3] - 16), 1)
            # 流动粒子环：沿轨道高速飞行的能量光点 + 拖尾
            n_orb = 18
            for i in range(n_orb):
                a = now * 0.0042 + i * math.tau / n_orb
                px = cx + int(math.cos(a) * (self.RADIUS - 6))
                py = cy + int(math.sin(a) * (self.RADIUS * 0.70 - 4))
                fade = (math.sin(now * 0.009 + i * 1.7) + 1) * 0.5
                _circle(surf, (255, 220, 130, int(45 + 130 * fade)), (px, py), 3)
                _circle(surf, (235, 90, 200, int(60 * fade)), (px - int(math.cos(a) * 11), py - int(math.sin(a) * 11)), 2)
            # 旋转虚线内环（红紫交替）
            for i in range(14):
                a = now * 0.003 + i * math.tau / 14
                px = cx + int(math.cos(a) * (self.RADIUS - 30))
                py = cy + int(math.sin(a) * (self.RADIUS * 0.70 - 22))
                _circle(surf, (*self._DART_COLORS[i % 2][1], 70), (px, py), 2)
            # 飞盘间：时有时无的黄色闪电链接
            for i in range(len(positions)):
                (x1, y1), _a1 = positions[i]
                (x2, y2), _a2 = positions[(i + 1) % len(positions)]
                flicker = (math.sin(now * 0.021 + i * 2.4) + 1) * 0.5  # 每个链接独立相位
                alpha = int(100 + 130 * flicker * (0.6 + 0.4 * warn))
                draw_electric_arc(surf, (x1, y1), (x2, y2), (255, 222, 115), alpha, now, i)
            # —— 中心辐射能量印记 ——
            ring = 30 + int(14 * pulse) + int(12 * warn)
            _circle(surf, (170, 80, 255, 46), (cx, cy), ring, 2)
            _circle(surf, (255, 120, 60, int(70 * warn)), (cx, cy), ring + 5, 1)
            # 旋转三叉能量符
            for i in range(3):
                a = now * 0.004 + i * math.tau / 3
                tip = (cx + int(math.cos(a) * ring), cy + int(math.sin(a) * ring))
                _line(surf, (255, 235, 150, 110), (cx, cy), tip, 2)
                _circle(surf, (255, 235, 150, 130), tip, 4)
            if warn > 0:
                _circle(surf, (255, 190, 80, int(90 * warn)), (cx, cy), int(34 + 34 * pulse), 2)
        else:
            # 释放阶段：中心能量爆发快速扩散淡出
            t = min(1.0, (now - self.release_time) / 900.0)
            _circle(surf, (255, 120, 200, int(70 * (1 - t))), self.center(), int(36 + 102 * t), 3)
            _circle(surf, (255, 200, 120, int(50 * (1 - t))), self.center(), int(54 + 72 * t), 1)

        for idx, ((dx, dy), ang) in enumerate(positions):
            dark, light = self._DART_COLORS[idx % 2]
            if flash:  # 即将飞出：提亮闪烁预警
                dark = tuple(int(a + (255 - a) * 0.4) for a in dark)
                light = tuple(min(255, int(a + (255 - a) * 0.4)) for a in light)
            spin = now * 0.014 + ang * 2
            if self.released and idx < len(self._fly_discs):
                d = self._fly_discs[idx]
                # 飞出尾焰：黄色闪电电弧（非直线）
                tx, ty = dx - d[2] * 20, dy - d[3] * 20
                origin = self.center() if t < 0.35 else (tx, ty)
                draw_electric_arc(surf, origin, (dx, dy), (255, 225, 135), 195, now, idx)
                _circle(surf, (255, 235, 150, 100), (dx, dy), 18, 2)
            self._draw_disc(surf, dx, dy, spin, dark, light)


# ═══════════════════════════════════════════════════════════════════════════════
#  Boss & BossProjectile
# ═══════════════════════════════════════════════════════════════════════════════

class BossProjectile:
    def __init__(self, x, y, angle, speed, homing=False, damage=1, big_fireball=False,
                 bomb=False, explode_radius=72):
        self.x = x
        self.y = y
        self.prev_x = x
        self.prev_y = y
        self.speed = speed
        self.angle = angle
        self.bomb = bomb
        self.explode_radius = explode_radius
        self.r = 16 if bomb else 18 if big_fireball else 8
        self.alive = True
        self.homing = homing
        self.homing_duration = None
        self.damage = damage
        self.tint = None
        self.big_fireball = big_fireball
        self.spawn_time = config.game_ticks()
        self.max_lifetime = 5200 if bomb else 6500

    def update(self, target_x=None, target_y=None):
        if config.game_ticks() - self.spawn_time >= self.max_lifetime:
            self.alive = False
            return
        self.prev_x = self.x
        self.prev_y = self.y
        age = config.game_ticks() - self.spawn_time
        if self.bomb and age < 350:
            rad = math.radians(self.angle)
            self.x += math.sin(rad) * self.speed
            self.y += math.cos(rad) * self.speed
        elif self.bomb and target_x is not None and target_y is not None:
            dx = target_x - self.x
            dy = target_y - self.y
            dist = max(1, math.hypot(dx, dy))
            self.x += dx / dist * self.speed
            self.y += max(0.4, dy / dist * self.speed)
            if dist <= self.explode_radius * 0.55:
                self.alive = False
        elif self.homing and target_x is not None:
            if self.homing_duration is not None and age >= self.homing_duration:
                self.homing = False
                self.y += self.speed
                return
            # 横向缓慢追踪玩家，纵向恒定速度向下
            dx = target_x - self.x
            self.x += dx * 0.04
            self.y += self.speed
            if self.homing_duration is not None:
                self.angle = math.degrees(math.atan2(dx * 0.04, self.speed))
        else:
            rad = math.radians(self.angle)
            self.x += math.sin(rad) * self.speed
            self.y += math.cos(rad) * self.speed
        # 到达游戏区域底部或出屏消失
        if self.y > config.SCREEN_HEIGHT + self.r or self.y < -20 or self.x < -20 or self.x > config.SCREEN_WIDTH + 20:
            self.alive = False
    def rect(self):
        return pygame.Rect(int(self.x - self.r), int(self.y - self.r), self.r * 2, self.r * 2)

    def block_rect(self):
        r = self.r + (10 if self.big_fireball else 0)
        current = pygame.Rect(int(self.x - r), int(self.y - r), r * 2, r * 2)
        previous = pygame.Rect(int(self.prev_x - r), int(self.prev_y - r), r * 2, r * 2)
        return current.union(previous)

    def draw(self, surf):
        if self.tint and not self.big_fireball:
            now = config.game_ticks()
            center = (round(self.x), round(self.y))
            radius = self.r + 4
            bounds = pygame.Rect(center[0] - radius, center[1] - radius, 2 * radius, 2 * radius)
            phase = (now * .013 + self.angle) % math.tau
            Draw.arc(surf, (*self.tint, 150), bounds, phase, phase + math.pi * 1.15, 2)
        if self.bomb:
            now = config.game_ticks()
            _circle(surf, (255, 210, 80, 55), (int(self.x), int(self.y)), self.r + 10, 2)
            _circle(surf, (22, 20, 28, 235), (int(self.x), int(self.y)), self.r)
            _circle(surf, (70, 68, 82, 235), (int(self.x - 5), int(self.y - 6)), max(4, self.r // 3))
            _line(surf, (35, 30, 25), (self.x + 7, self.y - 12), (self.x + 18, self.y - 23), 3)
            spark = (self.x + 20 + math.sin(now * 0.02) * 3, self.y - 25)
            _circle(surf, (255, 210, 55, 220), spark, 4)
            _circle(surf, (255, 80, 35, 180), spark, 7, 1)
            return
        if self.big_fireball:
            center = (round(self.x), round(self.y))
            _circle(surf, (255, 117, 48, 55), center, self.r + 5)
            _circle(surf, (116, 30, 69), center, self.r + 1)
            _circle(surf, (222, 54, 54), center, self.r)
            _circle(surf, (255, 130, 47), center, self.r - 4)
            _circle(surf, (255, 197, 81), (self.x - 2, self.y - 2), self.r - 9)
            _circle(surf, (255, 242, 190), (self.x - 5, self.y - 6), 3)
            return
        if self.homing:
            now = config.game_ticks()
            body = (155, 70, 255)
            flame = (255, 120, 255)
            pts = [
                (self.x, self.y + 12),
                (self.x - 7, self.y - 4),
                (self.x, self.y - 13),
                (self.x + 7, self.y - 4),
            ]
            _polygon(surf, body, pts)
            _circle(surf, (230, 210, 255, 220), (int(self.x), int(self.y - 5)), 3)
            _polygon(surf, flame, [
                (self.x - 5, self.y + 9),
                (self.x, self.y + 18 + math.sin(now * 0.02) * 3),
                (self.x + 5, self.y + 9),
            ])
            _circle(surf, (170, 80, 255, 70), (int(self.x), int(self.y)), 15, 2)
            return
        # A rounded head and tapered wake form a drop facing its actual movement.
        center = (int(self.x), int(self.y))
        dx, dy = self.x - self.prev_x, self.y - self.prev_y
        distance = math.hypot(dx, dy)
        if distance:
            dx, dy = dx / distance, dy / distance
        else:
            angle = math.radians(self.angle)
            dx, dy = math.sin(angle), math.cos(angle)
        px, py = -dy, dx
        color = self.tint or (255, 85, 65)
        _polygon(surf, (*color, 120), [
            (self.x + px * self.r * 0.9, self.y + py * self.r * 0.9),
            (self.x - dx * self.r * 1.3 + px * self.r * 0.55,
             self.y - dy * self.r * 1.3 + py * self.r * 0.55),
            (self.x - dx * self.r * 2.8, self.y - dy * self.r * 2.8),
            (self.x - dx * self.r * 1.3 - px * self.r * 0.55,
             self.y - dy * self.r * 1.3 - py * self.r * 0.55),
            (self.x - px * self.r * 0.9, self.y - py * self.r * 0.9),
        ])
        _circle(surf, (*color, 85), center, self.r + 2)
        _circle(surf, (63, 18, 34), center, self.r + 1)
        _circle(surf, (*color, 245), center, self.r)
        _circle(surf, (115, 24, 64, 255), center, max(1, self.r - 2))
        _circle(surf, (255, 225, 180, 255), (self.x - 1, self.y - 1), max(2, self.r // 3))



class DragonFireball(BossProjectile):
    def __init__(self, x, y, damage):
        super().__init__(x, y, 0, 5.5, damage=damage, bomb=True, explode_radius=55)
        self.blast_reason = '被火龙追踪火球击败！'

    def update(self, target_x=None, target_y=None):
        super().update()
        if (not self.alive or target_x is None or target_y is None
                or config.game_ticks() - self.spawn_time < 350):
            return
        self.x += max(-2.5, min(2.5, (target_x - self.x) * .035))
        if math.hypot(target_x - self.x, target_y - self.y) <= self.explode_radius * .55:
            self.alive = False

    def draw(self, surf):
        x, y = self.x, self.y
        drift = math.sin(config.game_ticks() * .025) * 5
        _polygon(surf, (255, 84, 25, 210),
                 ((x - 14, y), (x - 12, y - 18), (x + drift - 8, y - 35),
                  (x + 3, y - 22), (x + drift + 10, y - 31), (x + 15, y - 8), (x + 9, y + 11)))
        _circle(surf, (255, 99, 24), (x, y), self.r)
        _circle(surf, (255, 178, 52), (x, y), self.r - 4)
        _circle(surf, (255, 238, 144), (x - 3, y + 2), self.r - 9)


class Boss:
    def __init__(self, bdef, difficulty):
        self.bdef = bdef
        self.name = bdef['name']
        enemy_def = next(e for e in ENEMY_DEFS if e['key'] == bdef['enemy_key'])
        self.edef = enemy_def
        self.max_hp = bdef.get('fixed_hp', math.ceil(bdef['base_hp'] * difficulty.boss_hp_mult * 2))
        self.hp = self.max_hp
        self.speed = bdef['speed']
        tier = bdef.get('campaign_tier')
        self.attack_interval = (bdef['attack_interval'] if tier is not None
                                else int(bdef['attack_interval'] * difficulty.boss_attack_mult))
        self.projectile_count = bdef['projectile_count']
        if bdef.get('campaign_level') == 3:
            self.projectile_count = (3, 4, 5)[tier]
        homing_mult = difficulty.boss_homing_mult if tier is None else 1
        self.homing_chance = min(0.75, bdef.get('homing_chance', 0.22) * homing_mult)
        self.laser_chance = bdef.get('laser_chance', 0)
        self.signature = None
        self.next_signature_time = 0
        self.signature_opening_pending = bdef['key'] in SIGNATURES
        self.last_attack_time = 0
        self.base_w, self.base_h = bdef.get('size', (130, 120))
        self.size_scale = (config.MOBILE_LANDSCAPE_BOSS_SCALE if config.MOBILE_LANDSCAPE_VIEW
                           else config.MOBILE_PORTRAIT_ENTITY_SCALE)
        self.w = max(1, round(self.base_w * self.size_scale))
        self.h = max(1, round(self.base_h * self.size_scale))
        self.x = config.SCREEN_WIDTH // 2
        self.y = -self.h
        self.movement_timer = 0
        self.entered = False
        self.fight_start_time = 0
        self.slowed_until = 0
        self.slow_mult = 1.0
        self.laser_warning_start = 0
        self.laser_warning_ms = 1500
        self.laser_active_until = 0
        self.next_death_laser_time = 0
        self.last_laser_hit_until = 0
        self.next_absorb_time = 0
        self.absorb_target = None
        self.absorb_count = 0
        self.breath_start_time = config.game_ticks()
        self.sprite_asset = bdef.get('sprite_asset', f'bosses/{bdef["key"]}.png')
        surface_size = (round((self.base_w + 20) * self.size_scale),
                        round((self.base_h + 20) * self.size_scale))
        self.surface = make_boss_surface(bdef.get('sprite_key', bdef['key']), surface_size)
        self.breath_base = None   # 高分辨率基准，呼吸缩放从它缩小采样，避免放大模糊
        self._breath_src = None
        self.font_hp = config.make_font(14, bold=True)

    def can_laser(self):
        return self.laser_chance > 0

    def _laser_mouth_pose(self):
        if 1 <= self.bdef.get('campaign_level', 0) <= 6:
            return animation.DOWNWARD_LASER_POSES.get(self.bdef['key'])
        return None

    def rect(self):
        return pygame.Rect(int(self.x - self.w // 2), int(self.y), self.w, self.h)

    def set_size_scale(self, scale):
        if self.size_scale == scale:
            return
        self.size_scale = scale
        self.w = max(1, round(self.base_w * scale))
        self.h = max(1, round(self.base_h * scale))
        if not self.entered:
            self.y = max(-self.h, min(60, self.y))
        surface_size = (round((self.base_w + 20) * scale),
                        round((self.base_h + 20) * scale))
        self.surface = make_boss_surface(self.bdef.get('sprite_key', self.bdef['key']), surface_size)
        self.breath_base = None
        self._breath_src = None

    def collides(self, rect):
        return rect.colliderect(self.rect())

    def hitboxes(self):
        return (self.rect(),)

    def update(self):
        now = config.game_ticks()
        if not self.can_laser():
            self.laser_warning_start = 0
            self.laser_active_until = 0
            self.next_death_laser_time = 0
        if not self.entered:
            self.y += 1.5
            if self.y >= 60:
                self.y = 60
                self.entered = True
                self.fight_start_time = now
                tier = self.bdef.get('campaign_tier')
                if tier is not None:
                    self.last_attack_time = now - self.attack_interval + (2000, 1600, 1200)[tier]
                if self.can_laser():
                    self.next_death_laser_time = now + random.randint(7000 if tier is None else 8000, 13000) * self.bdef.get('laser_interval_mult', 1)
            return

        if self.can_laser() and self.laser_warning_start:
            self._move(0.5, laser=True)
            if now - self.laser_warning_start >= self.laser_warning_ms:
                self.laser_active_until = now + 2000
                self.laser_warning_start = 0
            return

        if self.can_laser() and now < self.laser_active_until:
            self._move(0.5, laser=True)
            return

        if self.can_laser() and self.next_death_laser_time and now >= self.next_death_laser_time and random.random() < self.laser_chance:
            self._keep_laser_inside()
            self.laser_warning_start = now
            self.laser_warning_ms = 1500
            self.next_death_laser_time = now + random.randint(9000, 16000) * self.bdef.get('laser_interval_mult', 1)
            return

        self._move(1.0)

    def _move(self, speed_mult, laser=False):
        now = config.game_ticks()
        move_mult = self.slow_mult if now < self.slowed_until else 1.0
        if move_mult == 1.0:
            self.slow_mult = 1.0
        self.movement_timer += self.speed * move_mult * speed_mult
        patrol_half_width = 250 + max(0, config.SCREEN_WIDTH - config.BASE_SCREEN_WIDTH) / 2
        if config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT < config.SCREEN_WIDTH:
            center = (config.GAME_AREA_LEFT + config.GAME_AREA_RIGHT) / 2
            patrol_width = self.w + (220 * self.size_scale if self.bdef['key'] == 'boss_zongzong' else 0)
            patrol_half_width = min(patrol_half_width,
                                    (config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT - patrol_width) / 2)
        else:
            center = config.SCREEN_WIDTH // 2
        self.x = center + math.sin(self.movement_timer * 0.02) * patrol_half_width
        if laser:
            previous_x = self.x
            self._keep_laser_inside()
            if self.x != previous_x and patrol_half_width > 0:
                angle = math.asin(max(-1, min(1, (self.x - center) / patrol_half_width)))
                if self.x < previous_x:
                    angle = math.pi - angle
                self.movement_timer = angle / 0.02

    def should_attack(self, now):
        if not self.entered or self.laser_warning_start or now < self.laser_active_until:
            return False
        # 随时间推移攻击越来越密集
        tier = self.bdef.get('campaign_tier')
        if tier is not None:
            effective_interval = self.attack_interval
            if self.bdef['campaign_level'] >= 3 and now - self.fight_start_time >= 30000:
                effective_interval *= (1, 0.90, 0.85)[tier]
        elif self.fight_start_time > 0:
            elapsed = (now - self.fight_start_time) / 1000.0
            effective_interval = max(900, self.attack_interval / (1 + elapsed * 0.035))
        else:
            effective_interval = self.attack_interval
        if now < self.slowed_until:
            effective_interval /= self.slow_mult
        return now - self.last_attack_time >= effective_interval
    def attack(self, now, player_x):
        self.last_attack_time = now
        projectiles = []
        if self.bdef.get('campaign_level', 3) >= 3 and random.random() < 0.25:
            for index, angle in enumerate((-24, 0, 24)):
                projectiles.append(BossProjectile(self.x + (index - 1) * 40, self.y + self.h // 2 + 24, angle, 3.4,
                                                  damage=3, big_fireball=True))
            return projectiles
        if self.bdef.get('final_boss'):
            pattern = random.choice(('homing', 'wide', 'cross'))
            if pattern == 'homing':
                for ox, angle in ((-35, 5), (0, 0), (35, -5)):
                    projectiles.append(BossProjectile(self.x + ox, self.y + self.h // 2 + 30, angle, 3.0, homing=True))
                return projectiles
            if pattern == 'cross':
                for angle in (-50, -28, -10, 10, 28, 50):
                    projectiles.append(BossProjectile(self.x, self.y + self.h // 2 + 24, angle, 3.5))
                for ox in (-70, 70):
                    projectiles.append(BossProjectile(self.x + ox, self.y + self.h // 2 + 10, 0, 4.0))
                return projectiles
            for i in range(self.projectile_count + 3):
                angle = -62 + i * (124 / max(1, self.projectile_count + 2))
                projectiles.append(BossProjectile(self.x + random.randint(-34, 34), self.y + self.h // 2 + 24, angle, 3.6))
            return projectiles
        if random.random() < self.homing_chance:
            p1 = BossProjectile(self.x - 15, self.y + self.h // 2 + 20, 5, 2.6, homing=True)
            p2 = BossProjectile(self.x + 15, self.y + self.h // 2 + 20, -5, 2.6, homing=True)
            projectiles.extend([p1, p2])
            return projectiles
        # Normal spread attack (downward)
        spread = 40
        n = self.projectile_count
        base_angle = 0  # downward (cos(0)=1, y increases)
        for i in range(n):
            angle_offset = (i - (n - 1) / 2) * (spread / max(1, n - 1))
            p = BossProjectile(
                self.x + random.randint(-20, 20),
                self.y + self.h // 2 + 20,
                base_angle + angle_offset,
                3.0
            )
            projectiles.append(p)
        return projectiles
    def hit_by(self, weapon_name, amount=1.0, source='skill', hit_rect=None):
        if self.y < Enemy.ENTRY_DAMAGE_Y:
            return
        self.hp -= amount * getattr(self, 'damage_mult', 1.0)

    def apply_slow(self, now, duration=4000, mult=0.7):
        self.slowed_until = max(self.slowed_until, now + duration)
        self.slow_mult = min(self.slow_mult, max(0.8, mult) if 'campaign_tier' in self.bdef else mult)

    def is_killed(self):
        return self.hp <= 0

    def death_laser_rect(self, now=None):
        if not self.can_laser():
            return None
        now = config.game_ticks() if now is None else now
        if now >= self.laser_active_until:
            return None
        if self._laser_mouth_pose():
            return self.death_laser_zones()[0]
        w = max(24, self.w // 2)
        top = int(self.y + self.h * 0.72)
        return pygame.Rect(int(self.x - w // 2), top, w, max(1, config.SCREEN_HEIGHT - top))

    def death_laser_xs(self):
        pose = self._laser_mouth_pose()
        if pose:
            return (self.x + self.surface.get_width() * (pose[1] - .5),)
        return (self.x,)

    def _safe_laser_x(self, x):
        player_width = round(Player.SIZE[0] * _mobile_entity_scale())
        clearance = max(math.ceil(player_width * 1.5), 41 + (player_width + 1) // 2)
        beam_width = max(24, self.w // 2)
        left = config.GAME_AREA_LEFT + clearance + beam_width // 2
        right = config.GAME_AREA_RIGHT - clearance - (beam_width + 1) // 2
        return max(left, min(right, x))

    def _keep_laser_inside(self):
        # Move the Boss with the beam so a mouth-fired laser stays aligned.
        x = self.death_laser_xs()[0]
        self.x += self._safe_laser_x(x) - x

    def death_laser_rects(self, now=None):
        if not self.can_laser():
            return ()
        now = config.game_ticks() if now is None else now
        if now >= self.laser_active_until:
            return ()
        return self.death_laser_zones()

    def death_laser_zones(self):
        w = max(24, self.w // 2)
        pose = self._laser_mouth_pose()
        top = (round(self.y + self.h // 2 + self.surface.get_height() * (pose[2] - .5))
               if pose else int(self.y + self.h * 0.72))
        return tuple(pygame.Rect((round(x) if pose else int(x)) - w // 2, top, w,
                                 max(1, config.SCREEN_HEIGHT - top))
                     for x in self.death_laser_xs())

    def draw(self, surf):
        now = config.game_ticks()
        size_scale = self.size_scale
        scale = _breathing_scale(now - self.breath_start_time, 0.30, 2800)
        mouth_laser = now < self.laser_active_until and self._laser_mouth_pose()
        center_y = self.y + self.h // 2
        # —— 质感光晕 + 悬浮粒子：血量越低越红、越狂暴 ——
        hp_ratio = max(0, self.hp / self.max_hp)
        skill_color = BOSS_COLORS.get(self.bdef['key'], (110, 160, 255))
        if hp_ratio > 0.5:
            aura = skill_color
            glow_c = tuple((value + 255) // 2 for value in aura)
        elif hp_ratio > 0.25:
            aura, glow_c = (255, 150, 60), (255, 220, 140)
        else:
            aura, glow_c = (255, 60, 50), (255, 130, 95)
        pulse = 1 + 0.10 * math.sin(now * 0.008)
        ex, ey = int(self.x), int(center_y)
        rx, ry = int(self.w * 0.68 * scale), int(self.h * 0.60 * scale)
        # 1) 多层脉动光晕包住 Boss 轮廓
        _ellipse(surf, (*aura, 24), (ex - rx - 16 * size_scale, ey - ry - 16 * size_scale,
                                     (rx + 16 * size_scale) * 2, (ry + 16 * size_scale) * 2),
                 max(1, round(7 * size_scale)))
        _ellipse(surf, (*aura, 40), (ex - rx, ey - ry, rx * 2, ry * 2), 4)
        _ellipse(surf, (*glow_c, 30), (ex - int(rx * 0.82 * pulse), ey - int(ry * 0.82 * pulse),
                                       int(rx * 1.64 * pulse), int(ry * 1.64 * pulse)), 2)
        # 2) 绕 Boss 外轮廓旋转的发光能量粒子（双层，外圈）
        for i in range(14):
            angle = now * 0.0018 + i * math.tau / 14
            depth = (math.sin(angle * 2 + i) + 1.0) / 2.0
            px = ex + math.cos(angle) * rx * (1.24 + 0.06 * math.sin(now * 0.005 + i))
            py = ey + math.sin(angle) * ry * 1.30 * (1 + 0.05 * math.sin(now * 0.006 + i * 2.3))
            r = 3 + round(depth * 3)
            _circle(surf, (*aura, 30), (int(px), int(py)), round((r + 6) * size_scale))
            _circle(surf, (*glow_c, 90 + round(depth * 110)), (int(px), int(py)), max(1, round(r * size_scale)))
        # 3) 从 Boss 边缘不断上浮的能量微尘
        for i in range(12):
            ph = (now * 0.02 + i * 0.83) % 1.0
            ang = i * 2.399
            px = ex + math.cos(ang) * rx * (0.75 + 0.35 * ph)
            py = ey + math.sin(ang) * ry * 0.7 - ph * 26 * size_scale
            alpha = int(130 * (1 - ph))
            _circle(surf, (*glow_c, alpha), (int(px), int(py)), max(1, round((2 + 2 * (1 - ph)) * size_scale)))
        # 4) 缓慢漂移的漂浮能量碎片
        for i in range(6):
            ang = now * 0.0009 + i * math.tau / 6
            dr = 1.18 + 0.10 * math.sin(now * 0.003 + i * 1.9)
            px = ex + math.cos(ang) * rx * dr
            py = ey + math.sin(ang) * ry * dr * 0.9 + math.sin(now * 0.004 + i) * 8 * size_scale
            _circle(surf, (255, 240, 180, 90), (int(px), int(py)), max(1, round((3 + i % 3) * size_scale)), 1)
        for i in range(10):
            angle = now * 0.0012 + i * math.tau / 10
            depth = (math.sin(angle) + 1.0) / 2.0
            px = self.x + math.cos(angle) * self.w * 0.62 * scale
            py = center_y + math.sin(angle) * self.h * 0.46 * scale
            radius = 5 + round(depth * 3)
            if self.bdef['key'] == 'boss_niu':
                _circle(surf, (255, 75, 25, 45), (px, py), radius + 5)
                _circle(surf, (255, 205, 75, 120 + round(depth * 80)), (px, py), radius)
            else:
                _circle(surf, (90, 220, 255, 45), (px, py), radius + 5)
                _circle(surf, (180, 110, 255, 120 + round(depth * 80)), (px, py), radius)
        if self.bdef.get('final_boss'):
            pulse = 1 + 0.08 * math.sin(now * 0.009)
            for r, alpha in ((130, 34), (105, 46), (78, 60)):
                _circle(surf, (130, 40, 220, alpha), (int(self.x), int(self.y + self.h // 2)),
                        max(1, int(r * pulse * size_scale)), max(1, round(3 * size_scale)))
            for a in range(0, 360, 45):
                rad = math.radians(a + now * 0.05)
                _circle(surf, (80, 220, 255, 130),
                        (self.x + math.cos(rad) * 86 * size_scale,
                         self.y + self.h // 2 + math.sin(rad) * 50 * size_scale),
                        max(1, round(4 * size_scale)))
        if self.breath_base is None or self._breath_src is not self.surface:
            sw, sh = self.surface.get_size()
            hi = image_asset_supersampled(self.sprite_asset, (sw, sh), 1.5)
            self.breath_base = hi if hi is not None else scale_surface_cached(
                self.surface, (int(sw * 1.3), int(sh * 1.3)))
            self._breath_src = self.surface
        sw, sh = self.breath_base.get_size()
        # 呼吸缩放从 1.3x 基准缩小采样，视觉尺寸不变但更清晰
        breathing_surface = scale_surface_cached(
            self.breath_base, (round(sw * scale / 1.3), round(sh * scale / 1.3))
        )
        sprite = animation.boss_frame(self, now)
        sprite_x, sprite_y = self.x, center_y
        if sprite is not None:
            size = self.surface.get_size() if mouth_laser else breathing_surface.get_size()
            action_size = animation.boss_action_size(sprite, self.surface, size)
            if mouth_laser:
                # Keep the mouth at the existing beam origin when the frame grows.
                sprite_x += (size[0] - action_size[0]) * (mouth_laser[1] - .5)
                sprite_y += (size[1] - action_size[1]) * (mouth_laser[2] - .5)
            breathing_surface = scale_surface_cached(sprite, action_size)
        elif self.bdef['key'] == 'boss':
            breathing_surface = scale_surface_cached(
                breathing_surface, tuple(round(value * .85) for value in breathing_surface.get_size()))
        slam_start = getattr(self, 'axe_slam_start', None)
        slam_active = slam_start is not None and 0 <= now - slam_start < self.axe_slam_duration
        if slam_active:
            breathing_surface = _niu_slam_sprite(scale_surface_cached(
                breathing_surface, tuple(round(value * 1.35) for value in breathing_surface.get_size())))
        bsw, bsh = breathing_surface.get_size()
        source = breathing_surface if slam_active else sprite or self.sprite_asset
        if self.laser_warning_start and (now - self.laser_warning_start) // 150 % 2 == 0:
            breathing_surface = _laser_flash_sprite(breathing_surface)
            source = breathing_surface
        blit_lit_sprite(surf, breathing_surface, (sprite_x - bsw // 2, sprite_y - bsh // 2), glow_c, 185, source=source)
        if self.laser_warning_start:
            elapsed = now - self.laser_warning_start
            if (elapsed // 220) % 2 == 0:
                for x in self.death_laser_xs():
                    _circle(surf, (255, 255, 255, 190), (int(x), int(self.y + self.h // 2)), int(self.w * 0.72), 4)
                    _circle(surf, (255, 60, 40, 160), (int(x), int(self.y + self.h * 0.75)), int(self.w * 0.32))
        for lr in self.death_laser_rects(now):
            if self.bdef['key'] == 'boss_niu':
                continue
            if mouth_laser:
                x, y = lr.centerx, lr.top
                half = lr.w / 2
                neck = min(28, lr.h)
                _polygon(surf, (*skill_color, 140),
                         ((x - 6, y), (x + 6, y), (x + half + 6, y + neck),
                          (x + half + 6, lr.bottom), (x - half - 6, lr.bottom),
                          (x - half - 6, y + neck)))
                _polygon(surf, (*skill_color, 245),
                         ((x - 3, y), (x + 3, y), (lr.right, y + neck),
                          (lr.right, lr.bottom), (lr.left, lr.bottom), (lr.left, y + neck)))
                _line(surf, (255, 247, 220), (x, y), (x, lr.bottom), max(3, lr.w // 5))
                _circle(surf, (*skill_color, 225), (x, y), 8)
                _circle(surf, (255, 247, 220), (x, y), 4)
                continue
            beam = effect_layer(surf, (lr.w + 54, lr.h))
            cx = beam.get_size()[0] // 2
            for i in range(8):
                _rect(beam, (*skill_color, max(20, 150 - i * 16)),
                      (cx - lr.w // 2 - i * 5, 0, lr.w + i * 10, lr.h), border_radius=8)
            _rect(beam, (*skill_color, 235), (cx - lr.w // 2, 0, lr.w, lr.h), border_radius=6)
            _rect(beam, (255, 245, 210, 220), (cx - max(3, lr.w // 8), 0, max(6, lr.w // 4), lr.h), border_radius=4)
            for y in range(0, lr.h, 30):
                _circle(beam, (255, 220, 80, 150), (cx + int(math.sin(now * 0.03 + y) * lr.w * 0.45), y), 10)
            draw_electric_arc(beam, (cx, 2), (cx, lr.h - 2), skill_color, 215, now,
                              seed=lr.x, thickness=3)
            blit_effect(surf, beam, (lr.x - 27, lr.y))
        if config.game_ticks() < self.slowed_until:
            _circle(surf, (160, 90, 255, 110), (int(self.x), int(self.y + self.h // 2)),
                    round(82 * size_scale), max(1, round(3 * size_scale)))
