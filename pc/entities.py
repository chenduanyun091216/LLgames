"""
游戏实体：Player, Enemy, Bullet, Coin, Particle, FireWall, IceFloor, SkillProjectile,
         MagneticStorm, Boss, BossProjectile。
"""
import math
import random
import pygame
from . import config
from .asset_loader import image_asset, image_asset_supersampled, scale_surface_cached
from . import animation

from .config import (
    WEAPON_DEFS, CHARACTER_DEFS,
    HEALTH_RED, HEALTH_GREEN, ENEMY_DEFS,
)

# 角色 → 高清贴图素材映射（呼吸基准按当前角色选择）
_CHAR_ASSETS = {
    'fire': 'player_fire.png',
    'ice': 'player_ice.png',
    'water': 'player_water.png',
    'radiation': 'player_radiation.png',
}
from .sprites import (
    _circle, _rect, _ellipse, _line, _polygon,
    make_player_surface, make_fire_player_surface, make_ice_player_surface,
    make_water_player_surface, make_radiation_player_surface,
    make_enemy_surface, make_bullet_surface, make_coin_surface,
    make_boss_surface,
)


def _breathing_scale(elapsed_ms, growth, period_ms):
    return 1.0 + growth * (1.0 - math.cos(elapsed_ms * math.tau / period_ms)) / 2.0


class Player:
    SIZE = (56, 66)
    SPEED = 5

    def __init__(self):
        self.x = config.SCREEN_WIDTH // 2
        self.y = config.GAME_AREA_BOTTOM - 14
        self.owned_weapons = ['pistol']
        self.current_weapon = 'pistol'
        self.gold = 0
        self.last_shot_time = 0
        self.surface = make_player_surface()
        self.sprite_asset = 'player1.png'  # 高清呼吸基准从此 PNG 超采样加载
        self.breath_base = None   # 高分辨率基准，呼吸缩放从它缩小采样，避免放大模糊
        self._breath_src = None
        self.character = None
        self.owned_characters = []
        self.skill_cooldowns = {}
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
        self.breath_start_time = pygame.time.get_ticks()

    def rect(self):
        scale = 1.0
        w, h = (max(1, round(size * scale)) for size in self.SIZE)
        return pygame.Rect(self.x - w // 2, self.y - h // 2, w, h)

    def move(self, dx, dy=0):
        previous = (self.x, self.y)
        width = self.rect().w
        half_width = width // 2
        min_x = max(40, config.GAME_AREA_LEFT + half_width)
        max_x = min(config.SCREEN_WIDTH - 40, config.GAME_AREA_RIGHT - (width + 1) // 2)
        self.x = max(min_x, min(max_x, self.x + dx))
        self.y = max(80, min(config.GAME_AREA_BOTTOM - 14, self.y + dy))
        self.animation_moving = (self.x, self.y) != previous
        if self.animation_moving:
            self.animation_move_at = pygame.time.get_ticks()

    def can_shoot(self, now):
        w = WEAPON_DEFS[self.current_weapon]
        rate = w.fire_rate
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
        return now - self.last_shot_time >= rate

    def shoot(self, now):
        self.last_shot_time = now
        w = WEAPON_DEFS[self.current_weapon]
        if self.current_weapon == 'shotgun':
            return [Bullet(self.x, self.y - 28, w, self.current_weapon, self.character, angle=a) for a in (-18, 0, 18)]
        return [Bullet(self.x, self.y - 28, w, self.current_weapon, self.character)]

    def draw(self, surf):
        now = pygame.time.get_ticks()
        size_scale = 1.0
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
        name = 'player_' + self.character if self.character else self.sprite_asset.removesuffix('.png')
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
        surf.blit(breathing_surface, (self.x - bsw // 2, self.y - bsh // 2))


class Enemy:
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
        self.size_scale = 1.0
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
        self.burning = False
        self.burn_start = 0
        self.burn_duration = 3000
        self.last_burn_tick = 0
        self.burn_hits = 0
        self.burn_damage = False
        self.frozen = False
        self.frozen_until = 0
        self.slowed_until = 0
        self.slow_mult = 1.0
        self.infected = False
        self.infected_weapon = 'pistol'
        self.health_mult = edef.get('health_mult', 1.0)
        self.last_contact_damage_time = -1000
        self.last_attack_time = pygame.time.get_ticks() + random.randint(800, 2200)
        self.attack_interval_min = 3800
        self.attack_interval_max = 7000
        self.attack_interval = random.randint(self.attack_interval_min, self.attack_interval_max)
        self.breath_start_time = pygame.time.get_ticks()
        self.base_surface = make_enemy_surface(edef['key'])
        self.base_surface_size = self.base_surface.get_size()
        self.surface = self.base_surface
        self.sprite_asset = 'zongzong.png' if self.is_zongzong else f'enemy_{edef["key"]}.png'
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

    def update(self):
        now = pygame.time.get_ticks()
        if self.frozen:
            if now >= self.frozen_until:
                self.frozen = False
            else:
                return
        if self.burning:
            if now - self.burn_start >= self.burn_duration:
                self.burning = False
                self.burn_damage = False
            elif self.burn_damage and now - self.last_burn_tick >= 500:
                self.burn_hits += 1
                self.last_burn_tick = now
        move_mult = self.slow_mult if now < self.slowed_until else 1.0
        if move_mult == 1.0:
            self.slow_mult = 1.0
        self.y += self.speed * move_mult

    def hit_by(self, weapon_name, amount=1.0):
        now = pygame.time.get_ticks()
        if self.frozen and now < self.frozen_until:
            amount *= 2.0
        self.hits[weapon_name] = self.hits.get(weapon_name, 0) + amount * getattr(self, 'damage_mult', 1.0)
        if self.is_zongzong:
            self.zong_hits += 1
            target = 0 if self.zong_hits == 1 else max(1, min(3, int(self._damage_progress() * 4)))
            if target > self.zong_expression:
                self.zong_expression_from = self.zong_expression
                self.zong_expression = target
                self.zong_expression_at = now
            self._update_zongzong_size()

    def show_immune(self, now=None):
        self.immune_text_until = (pygame.time.get_ticks() if now is None else now) + 650

    def _damage_progress(self):
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
        self.surface = image_asset('zongzong.png', target_size) or scale_surface_cached(self.base_surface, target_size)
        self.breath_base = None
        self._breath_src = None

    def apply_slow(self, now, duration=4000, mult=0.7):
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
        w = WEAPON_DEFS[weapon_name]
        needed = w.large_shots if self.is_large else w.normal_shots
        needed = max(1, math.ceil(needed * self.health_mult))
        return (self.hits.get(weapon_name, 0) + self.burn_hits) >= needed

    def reached_bottom(self):
        return self.y > config.GAME_AREA_BOTTOM + 20

    def draw(self, surf):
        # 阴影
        shadow_y = int(self.y + self.h - 6)
        _ellipse(surf, (0, 0, 0, 50), (int(self.x - self.w // 2 + 8), shadow_y, self.w - 16, 6))
        now = pygame.time.get_ticks()
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
        if self.is_zongzong:
            sw, sh = self.surface.get_size()
            image = self.surface
            if self.zong_hits:
                elapsed = max(0, now - self.zong_expression_at)
                index = min(self.zong_expression, self.zong_expression_from + elapsed // 120)
                sprite = animation.frame('zongzong_hurt', index)
                if sprite is not None:
                    image = scale_surface_cached(sprite, (sw, sh))
            surf.blit(image, (int(self.x - sw // 2), int(self.y + self.h // 2 - sh // 2)))
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
            surf.blit(breathing_surface, (int(self.x - bsw // 2), int(self.y + self.h // 2 - bsh // 2)))
        # 燃烧效果
        if self.burning:
            overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            overlay.fill((255, 80, 20, 80))
            surf.blit(overlay, (int(self.x - self.w // 2), int(self.y)))
            # 火焰粒子
            now = pygame.time.get_ticks()
            for fi in range(3):
                fx = self.x - self.w // 3 + fi * self.w // 3 + int(math.sin(now * 0.005 + fi) * 4)
                fy = self.y + int(math.sin(now * 0.006 + fi) * 3)
                _circle(surf, (255, 200, 50, 150), (fx, fy + 2), 3)
                _circle(surf, (255, 100, 20, 120), (fx, fy), 2)
        # 冰冻效果
        if self.frozen:
            overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            overlay.fill((100, 180, 255, 120))
            surf.blit(overlay, (int(self.x - self.w // 2), int(self.y)))
            # 冰晶
            _circle(surf, (200, 240, 255, 120), (int(self.x), int(self.y + self.h // 3)), 4)
        if pygame.time.get_ticks() < self.slowed_until:
            _circle(surf, (120, 210, 255, 100), (int(self.x), int(self.y + self.h // 2)),
                    max(round(14 * self.size_scale), self.w // 3), max(1, round(2 * self.size_scale)))
        if self.infected:
            _circle(surf, (160, 255, 80, 90), (int(self.x), int(self.y + self.h // 2)),
                    max(round(12 * self.size_scale), self.w // 4), max(1, round(2 * self.size_scale)))
        if self.is_zongzong and self.label_font:
            label = self.label_font.render('粽', True, (90, 50, 20))
            lx = int(self.x - label.get_width() // 2)
            ly = int(self.y - label.get_height() - 18)
            _circle(surf, (255, 236, 160, 230), (int(self.x), ly + label.get_height() // 2), 15)
            surf.blit(label, (lx, ly))
        if self.is_zongzong and pygame.time.get_ticks() < self.immune_text_until and self.immune_font:
            immune = self.immune_font.render('免疫', True, (255, 245, 210))
            tx = int(self.x - immune.get_width() // 2)
            ty = int(self.y + self.h // 2 - immune.get_height() // 2)
            _rect(surf, (60, 30, 10, 185), (tx - 5, ty - 2, immune.get_width() + 10, immune.get_height() + 4), border_radius=4)
            surf.blit(immune, (tx, ty))
        # HP条
        bar_w = self.w + (round(10 * self.size_scale) if self.is_zongzong else 0)
        bar_h = max(1, round((7 if self.is_zongzong else 4) * self.size_scale))
        bx = int(self.x - bar_w // 2)
        by = int(self.y - 8)
        if self.hits:
            ratio = self._damage_progress()
        else:
            ratio = 0.0
        _rect(surf, (30, 10, 10, 180), (bx - 1, by - 1, bar_w + 2, bar_h + 2), border_radius=2)
        _rect(surf, HEALTH_RED, (bx, by, bar_w, bar_h), border_radius=2)
        _rect(surf, HEALTH_GREEN, (bx, by, int(bar_w * ratio), bar_h), border_radius=2)
        _rect(surf, (150, 255, 100, 80), (bx, by, int(bar_w * ratio), 2), border_radius=1)


class Bullet:
    def __init__(self, x, y, wdef, weapon_key, character=None, angle=0):
        self.x = x
        self.y = y
        self.speed = wdef.speed
        self.angle = angle
        self.weapon_name = weapon_key
        self.character = character
        self.damage = 1.0
        self.gift_kind = None
        self.hit_targets = set()
        self.radius = 10
        if weapon_key == 'sniper':
            self.visual_scale = 1.95
            self.radius = 13
        elif weapon_key == 'shotgun' and angle == 0:
            self.visual_scale = 1.9
            self.radius = 13
        else:
            self.visual_scale = 1.0
        if weapon_key == 'shotgun' and angle == 0:
            self.color = (255, 55, 45)
        elif weapon_key == 'sniper':
            self.color = (190, 95, 255)
        elif weapon_key == 'rifle':
            self.color = (95, 175, 255)
        else:
            self.color = (255, 230, 40)
        self.surface = make_bullet_surface(self.color)
        if self.visual_scale > 1.0:
            sw, sh = self.surface.get_size()
            self.surface = pygame.transform.scale(
                self.surface, (round(sw * self.visual_scale), round(sh * self.visual_scale))
            )
        self.spawn_time = pygame.time.get_ticks()
        self.max_lifetime = 3000

    def rect(self):
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self):
        rad = math.radians(self.angle)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed

    def is_offscreen(self):
        return (pygame.time.get_ticks() - self.spawn_time >= self.max_lifetime or
                self.y < -20 or self.y > config.GAME_AREA_BOTTOM + 20 or
                self.x < -20 or self.x > config.SCREEN_WIDTH + 20)

    def draw(self, surf):
        if self.gift_kind:
            now = pygame.time.get_ticks()
            color = (255, 105, 35) if self.gift_kind == 'fire' else (45, 115, 230)
            core = (255, 235, 150) if self.gift_kind == 'fire' else (135, 210, 255)
            gr = max(3, int(self.radius * 0.7))  # 冰球/火球尺寸缩小 30%
            # 火/冰弹拖尾（沿飞行方向渐隐）
            rad = math.radians(self.angle)
            for ti in range(5, 0, -1):
                tx = self.x - math.sin(rad) * self.speed * ti * 0.7
                ty = self.y + math.cos(rad) * self.speed * ti * 0.7
                t_alpha = max(0, 115 - ti * 20)
                _circle(surf, (*color, t_alpha), (int(tx), int(ty)), max(2, gr + 3 - ti))
            for i in range(4, 0, -1):
                _circle(surf, (*color, 28 + i * 10), (int(self.x), int(self.y)), gr + int(i * 4 * 0.7))
            _circle(surf, (*color, 230), (int(self.x), int(self.y)), gr)
            _circle(surf, (*core, 230), (int(self.x - 3), int(self.y - 4)), max(3, gr // 2))
            if self.gift_kind == 'fire':
                flame = [
                    (self.x - gr * 0.7, self.y + gr),
                    (self.x, self.y + gr * 1.8 + math.sin(now * 0.02) * 2),
                    (self.x + gr * 0.7, self.y + gr),
                ]
                _polygon(surf, (255, 185, 40, 180), flame)
            else:
                for a in range(0, 360, 60):
                    rad = math.radians(a + now * 0.15)
                    _line(surf, (90, 175, 255, 185), (self.x, self.y),
                          (self.x + math.sin(rad) * (gr + 3),
                           self.y + math.cos(rad) * (gr + 3)), 1)
            return
        # 子弹拖尾（步枪拖尾更长更明显）
        trail_len = 6 if self.weapon_name == 'rifle' else 3
        for ti in range(trail_len, 0, -1):
            trail_y = int(self.y + self.speed * ti * 0.8) - self.radius
            trail_alpha = max(0, (120 if self.weapon_name == 'rifle' else 90) - ti * 18)
            _circle(surf, self.color[:3] + (trail_alpha,), (int(self.x), trail_y), max(2, self.radius - ti))
        surf.blit(self.surface, (int(self.x - self.surface.get_width() // 2), int(self.y - self.surface.get_height() // 2)))


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
        surf.blit(self.surface, (int(self.x - self.radius), int(self.y - self.radius)))


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
        self.breath_start_time = pygame.time.get_ticks()
        self.font = config.make_font(18, bold=True)

    def rect(self):
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self):
        self.y += self.speed

    def is_offscreen(self):
        return self.y > config.GAME_AREA_BOTTOM + self.radius

    def draw(self, surf):
        now = pygame.time.get_ticks()
        pulse = 1.0 + 0.08 * math.sin((now - self.breath_start_time) * 0.008)
        r = int(self.radius * pulse)
        x = int(self.x - r)
        y = int(self.y - r)
        _circle(surf, (255, 230, 80, 52), (int(self.x), int(self.y)), r + 9)
        _rect(surf, (190, 45, 55), (x, y, r * 2, r * 2), border_radius=8)
        _rect(surf, (255, 215, 70), (x + r - 4, y, 8, r * 2), border_radius=3)
        _rect(surf, (255, 215, 70), (x, y + r - 4, r * 2, 8), border_radius=3)
        _rect(surf, (255, 245, 165, 120), (x + 4, y + 4, r * 2 - 8, r - 5), border_radius=5, width=1)
        text = self.font.render('?', True, (255, 255, 255))
        surf.blit(text, (int(self.x - text.get_width() // 2), int(self.y - text.get_height() // 2)))


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
    def __init__(self, x, y, color=(255, 180, 60), count=18):
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
        radius = int(10 + 34 * t)
        _circle(surf, (*self.color[:3], alpha // 2), (self.x, self.y), radius, 3)
        _circle(surf, (255, 245, 170, alpha), (self.x, self.y), max(2, int(9 * (1 - t))))
        for s in self.sparks:
            size = max(1, int(s['size'] * (1 - t)))
            _circle(surf, (*self.color[:3], alpha), (s['x'], s['y']), size)


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
        self.spawn_time = pygame.time.get_ticks()
        self.last_damage_time = 0

    def update(self):
        self.y -= self.speed

    def rect(self):
        return pygame.Rect(int(self.x - self.w // 2), int(self.y - self.h), self.w, self.h)

    def is_expired(self):
        return pygame.time.get_ticks() - self.spawn_time >= self.lifetime

    def can_damage(self, now):
        if now - self.last_damage_time >= 500:
            self.last_damage_time = now
            return True
        return False

    def draw(self, surf):
        rx = int(self.x - self.w // 2)
        ry = int(self.y - self.h)
        now = pygame.time.get_ticks()
        # 格挡墙基础层
        glow = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        _rect(glow, (230, 80, 30, 120), (0, 0, self.w, self.h), border_radius=6)
        for y_off in range(0, self.h, 3):
            alpha = max(0, int(190 - y_off * 1.8))
            color = (255, 170 - y_off // 3, 50, alpha)
            _rect(glow, color, (2, y_off, self.w - 4, 2), border_radius=1)
        surf.blit(glow, (rx, ry))
        for i in range(6):
            fx = rx + 18 + i * 32
            _line(surf, (255, 245, 170, 120), (fx, ry + 8), (fx - 10, ry + self.h - 8), 2)
        _rect(surf, (255, 180, 60, 180), (rx, ry, self.w, self.h), border_radius=6, width=2)
        _rect(surf, (255, 240, 120, 100), (rx + 2, ry + 2, self.w - 4, self.h - 4), border_radius=4, width=1)


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
        rx = int(self.x - self.w // 2)
        ry = int(self.y - self.h // 2)
        ice_surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        cx, cy = self.w // 2, self.h - 10
        radius_x = self.w // 2 - 8
        radius_y = self.h - 18
        gap_ranges = [(int(gx - rx - gr), int(gx - rx + gr)) for gx, gr in self.gaps]
        for deg in range(200, 341, 2):
            rad = math.radians(deg)
            px = int(cx + math.cos(rad) * radius_x)
            py = int(cy + math.sin(rad) * radius_y)
            if any(a <= px <= b for a, b in gap_ranges):
                continue
            _circle(ice_surf, (28, 105, 190, 218), (px, py), 20)
            _circle(ice_surf, (65, 165, 235, 205), (px, py), 15)
            _circle(ice_surf, (175, 230, 255, 135), (px, py - 4), 8)
        shield_pts = [
            (cx, 8), (cx + radius_x - 18, cy - 34), (cx + radius_x - 48, cy + 2),
            (cx, self.h - 2), (cx - radius_x + 48, cy + 2), (cx - radius_x + 18, cy - 34),
        ]
        _polygon(ice_surf, (20, 85, 165, 68), shield_pts)
        _polygon(ice_surf, (150, 225, 255, 105), shield_pts, 2)
        for i in range(-2, 3):
            sx = cx + i * max(28, self.w // 11)
            if any(a <= sx <= b for a, b in gap_ranges):
                continue
            _line(ice_surf, (190, 240, 255, 112), (sx, 18), (cx + i * 12, self.h - 14), 2)
        for gx, gr in self.gaps:
            lx = int(gx - rx)
            _circle(ice_surf, (5, 22, 50, 178), (lx, self.h // 2), min(30, gr))
            _circle(ice_surf, (170, 230, 255, 80), (lx, self.h // 2), min(34, gr), 2)
        surf.blit(ice_surf, (rx, ry))
        for i in range(5):
            sx = rx + self.w // 6 + i * self.w // 6
            sy = ry + self.h // 2 + (i % 2) * 9
            _line(surf, (210, 245, 255, 135), (sx - 7, sy), (sx + 7, sy), 1)
            _line(surf, (210, 245, 255, 135), (sx, sy - 7), (sx, sy + 7), 1)


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
        self.r = 28 if ptype == 'fireball' else 12 if ptype == 'grenade' else 18
        self.lifetime = 900 if ptype == 'grenade' else 2500
        self.spawn_time = pygame.time.get_ticks()
        self.alive = True
        self.damage = 1.5 if ptype == 'fireball' else 1.0
        self.hit_targets = set()
        self.owner = owner
        self.skill_type = skill_type

    def update(self):
        rad = math.radians(self.angle)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed
        if pygame.time.get_ticks() - self.spawn_time >= self.lifetime:
            self.alive = False

    def rect(self):
        return pygame.Rect(int(self.x - self.r), int(self.y - self.r), self.r * 2, self.r * 2)

    def is_offscreen(self):
        return (self.y < -30 or self.y > config.GAME_AREA_BOTTOM + 30 or
                self.x < -30 or self.x > config.SCREEN_WIDTH + 30)

    def draw(self, surf):
        if self.ptype == 'fireball':
            # 外圈光晕
            for i in range(4, 0, -1):
                _circle(surf, (255, 100, 20, 25 - i * 5), (int(self.x), int(self.y)), int(self.r) + i)
            _circle(surf, (255, 60, 10, 200), (int(self.x), int(self.y)), int(self.r))
            _circle(surf, (255, 140, 30, 220), (int(self.x), int(self.y)), int(self.r) - 4)
            _circle(surf, (255, 200, 80, 200), (int(self.x), int(self.y)), int(self.r) - 8)
            _circle(surf, (255, 255, 200, 200), (int(self.x) - 3, int(self.y) - 3), int(self.r) // 4)
            # 旋转纹理
            now = pygame.time.get_ticks()
            for a in range(0, 360, 72):
                rad = math.radians(a + now * 0.1)
                ex = self.x + math.sin(rad) * (self.r * 0.6)
                ey = self.y - math.cos(rad) * (self.r * 0.6)
                _circle(surf, (255, 240, 100, 120), (ex, ey), 3)
        elif self.ptype == 'grenade':
            _circle(surf, (40, 90, 50, 230), (int(self.x), int(self.y)), int(self.r))
            _circle(surf, (105, 145, 80, 210), (int(self.x) - 2, int(self.y) - 3), int(self.r) - 4)
            _rect(surf, (30, 45, 35, 230), (int(self.x) - 4, int(self.y) - 15, 8, 5), border_radius=2)
            _line(surf, (230, 210, 120, 180), (self.x + 3, self.y - 14), (self.x + 10, self.y - 20), 2)
        else:
            for i in range(4, 0, -1):
                _circle(surf, (80, 180, 255, 25 - i * 5), (int(self.x), int(self.y)), int(self.r) + i)
            _circle(surf, (40, 140, 255, 200), (int(self.x), int(self.y)), int(self.r))
            _circle(surf, (100, 200, 255, 220), (int(self.x), int(self.y)), int(self.r) - 4)
            _circle(surf, (180, 230, 255, 200), (int(self.x), int(self.y)), int(self.r) - 8)
            _circle(surf, (230, 245, 255, 200), (int(self.x) - 3, int(self.y) - 3), int(self.r) // 4)
            # 冰晶纹
            now = pygame.time.get_ticks()
            for a in range(0, 360, 60):
                rad = math.radians(a + now * 0.08)
                ex = self.x + math.sin(rad) * (self.r * 0.5)
                ey = self.y - math.cos(rad) * (self.r * 0.5)
                _circle(surf, (200, 240, 255, 120), (ex, ey), 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  Lightning — 闪电链特效（瞬时伤害 5 个随机敌人）
# ═══════════════════════════════════════════════════════════════════════════════

class Lightning:
    def __init__(self, src_x, src_y, targets, color=(255, 230, 80)):
        """targets: [(enemy_ref, ex, ey), ...] 最多 5 个目标"""
        self.start_x = src_x
        self.start_y = src_y
        self.targets = targets
        self.color = color
        self.lifetime = 300
        self.spawn_time = pygame.time.get_ticks()

    def is_expired(self):
        return pygame.time.get_ticks() - self.spawn_time >= self.lifetime

    def draw(self, surf):
        now = pygame.time.get_ticks()
        alpha = max(0, int(255 * (1 - (now - self.spawn_time) / self.lifetime)))
        glow_color = (*self.color, alpha // 4)
        bolt_color = (*self.color, alpha)
        # 闪电柱主体
        for t_idx, (_, ex, ey) in enumerate(self.targets):
            # 辉光层
            for thickness in [8, 5]:
                self._draw_bolt(surf, (*glow_color[:3], glow_color[3] // 2), self.start_x, self.start_y, ex, ey, thickness)
            # 主体闪电
            self._draw_bolt(surf, bolt_color, self.start_x, self.start_y, ex, ey, 3)
            # 中心白热线
            self._draw_bolt(surf, (255, 255, 220, alpha), self.start_x, self.start_y, ex, ey, 1)

    def _draw_bolt(self, surf, color, x1, y1, x2, y2, thickness=3):
        segments = 8
        dx = (x2 - x1) / segments
        dy = (y2 - y1) / segments
        pts = [(x1, y1)]
        for i in range(1, segments):
            jitter_x = random.randint(-16, 16)
            jitter_y = random.randint(-16, 16)
            pts.append((x1 + dx * i + jitter_x, y1 + dy * i + jitter_y))
        pts.append((x2, y2))
        for i in range(len(pts) - 1):
            _line(surf, color, pts[i], pts[i + 1], thickness)
            # 分支闪电
            if random.random() < 0.3 and thickness > 1:
                mid_x = (pts[i][0] + pts[i + 1][0]) / 2
                mid_y = (pts[i][1] + pts[i + 1][1]) / 2
                br_x = mid_x + random.randint(-10, 10)
                br_y = mid_y + random.randint(6, 14)
                _line(surf, (*color[:3], color[3] // 2), (mid_x, mid_y), (br_x, br_y), 1)


# ═══════════════════════════════════════════════════════════════════════════════
#  MagneticStorm — 磁暴圈，吸附+持续伤害
# ═══════════════════════════════════════════════════════════════════════════════

class MagneticStorm:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 237
        self.lifetime = 3000
        self.pull_duration = 1500
        self.explode_time = 2000
        self.spawn_time = pygame.time.get_ticks()
        self.last_damage_time = 0
        self.pull_speed = 3.0
        self.exploded = False

    def is_expired(self):
        return pygame.time.get_ticks() - self.spawn_time >= self.lifetime

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
        now = pygame.time.get_ticks()
        alpha = int(120 + 55 * math.sin(now * 0.006))
        pulse = 1 + 0.08 * math.sin(now * 0.008)
        colors = [(255, 35, 35), (40, 255, 80), (170, 70, 255), (245, 245, 255)]
        bg_color = colors[(now // 160) % len(colors)]

        storm_surf = pygame.Surface((int(self.radius * 2 * pulse), int(self.radius * 2 * pulse)), pygame.SRCALPHA)
        cx_center = int(self.radius * pulse)
        cy_center = int(self.radius * pulse)

        # 深色核废水污染区：红绿紫白跳动
        _circle(storm_surf, (*bg_color, 95), (cx_center, cy_center), int(self.radius * 0.92 * pulse))
        _circle(storm_surf, (3, 5, 12, 210), (cx_center, cy_center), int(self.radius * 0.78 * pulse))
        _circle(storm_surf, (*bg_color, 70), (cx_center, cy_center), int(self.radius * 0.62 * pulse))
        for idx, r in enumerate(range(int(self.radius * pulse), int(self.radius * 0.42 * pulse), -18)):
            a = max(0, alpha - (self.radius * pulse - r) * 3)
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
            width = int((22 + 75 * (1 - t)) * pulse)
            twist = now * 0.012 + i * 0.9
            x1 = cx_center + int(math.sin(twist) * width)
            x2 = cx_center - int(math.sin(twist + 0.7) * width * 0.75)
            _line(storm_surf, (235, 255, 235, 120), (x1, y), (x2, y + 10), 3)
            _circle(storm_surf, (120, 255, 150, 70), (x1, y), max(3, 8 - i // 3))

        # 中心核心
        _circle(storm_surf, (180, 255, 70, min(255, alpha * 2)), (cx_center, cy_center), 17)
        _circle(storm_surf, (255, 255, 180, min(255, alpha * 2)), (cx_center, cy_center), 8)

        surf.blit(storm_surf, (int(self.x - cx_center), int(self.y - cy_center)))


class RadiationLaser:
    def __init__(self, owner, duration=5000):
        self.owner = owner
        self.duration = duration
        self.spawn_time = pygame.time.get_ticks()
        self.last_damage_times = {}
        self.swing_power = 0.0
        self.swing_speed = 0.0
        self.last_whip_time = 0

    def is_expired(self, now):
        return now - self.spawn_time >= self.duration

    def rect(self):
        w = int(Player.SIZE[0] * 0.65)
        bottom = int(self.owner.y - Player.SIZE[1] // 2)
        extra = int(abs(self.swing_power) + 18)
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
        if now - self.last_damage_times.get(key, 0) >= 120:
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
        now = pygame.time.get_ticks()
        decay = max(0.0, 1.0 - (now - self.last_whip_time) / 900.0) if self.last_whip_time else 0.0
        swing = self.swing_power * decay
        speed = max(0.01, self.swing_speed)
        colors = [(150, 0, 18), (0, 135, 42), (8, 42, 170), (95, 0, 150)]
        c = colors[(now // 55) % len(colors)]
        beam = pygame.Surface((r.w + 72, r.h), pygame.SRCALPHA)
        cx = beam.get_width() // 2
        last_outer = None
        last_inner = None
        last_core = None
        for y in range(0, r.h, 8):
            t = y / max(1, r.h)
            offset = math.sin(now * speed + t * 8.5) * swing * (0.2 + 0.9 * (1 - t))
            width = int(Player.SIZE[0] * 0.65) + int(18 * (1 - t))
            outer = (cx + int(offset), y)
            inner = (cx + int(offset * 0.72), y)
            core = (cx + int(offset * 0.52), y)
            if last_outer:
                _line(beam, (*c, 125), last_outer, outer, width + 44)
                _line(beam, (20, 8, 28, 218), last_inner, inner, max(8, width + 8))
                _line(beam, (*c, 235), last_inner, inner, max(6, width // 2))
                _line(beam, (255, 245, 230, 220), last_core, core, max(4, width // 5))
            last_outer, last_inner, last_core = outer, inner, core
        for y in range(0, r.h, 15):
            whip_offset = int(math.sin(now * speed + y * 0.11) * swing * 0.75)
            phase = math.sin(now * 0.055 + y * 0.14)
            c2 = colors[(y // 15 + now // 45) % len(colors)]
            _line(beam, (*c2, 220),
                  (cx + whip_offset - int(Player.SIZE[0] * 0.65) // 2 - 18, y),
                  (cx + whip_offset + int(Player.SIZE[0] * 0.65) // 2 + 18, y + int(phase * 16)), 3)
            if y % 45 == 0:
                bx = cx + int(math.sin(now * 0.03 + y) * (r.w * 0.75))
                _circle(beam, (*c2, 180), (bx, y), 12)
                _circle(beam, (255, 255, 255, 160), (bx, y), 4)
        surf.blit(beam, (r.x - 36, r.y))
        head = (int(self.owner.x), int(self.owner.y - Player.SIZE[1] // 2))
        for rr, alpha in ((42, 80), (30, 125), (20, 185)):
            _circle(surf, (*c, alpha), head, rr)
        _circle(surf, (255, 245, 230, 210), head, max(5, r.w // 5))


# ═══════════════════════════════════════════════════════════════════════════════
#  旋转飞镖盾（辐射工程师 R 技能）
# ═══════════════════════════════════════════════════════════════════════════════

class SpinningDarts:
    """8 个带齿纹的飞盘环绕自身旋转：持续伤害触碰的敌人、抵挡敌方子弹；
    持续结束后所有飞盘向外飞出，继续伤害怪物直到飞出屏幕。"""
    DART_COUNT = 8
    RADIUS = 246             # 环绕半径
    ANGULAR_SPEED = 0.0045   # rad/ms，公转速度
    DART_HIT = 42            # 飞盘碰撞半径
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
        self.spawn_time = pygame.time.get_ticks()
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

    def _draw_arc(self, surf, x1, y1, x2, y2, color, alpha, now, seed, thickness=2):
        """两点间的闪电电弧：形状每约 75ms 随机重生成一次，模拟时有时无的放电。"""
        phase = (now + int(seed * 37)) // 75
        state = random.getstate()
        random.seed(int(phase) * 7919 + int(seed))
        segments = 6
        pts = [(x1, y1)]
        for i in range(1, segments):
            t = i / segments
            jitter = 15 * (1 - abs(t - 0.5) * 1.2)
            pts.append((x1 + (x2 - x1) * t + random.uniform(-jitter, jitter),
                        y1 + (y2 - y1) * t + random.uniform(-jitter, jitter)))
        pts.append((x2, y2))
        random.setstate(state)
        # 辉光 + 主体 + 白芯
        for k in range(len(pts) - 1):
            _line(surf, (*color, alpha // 3), pts[k], pts[k + 1], thickness + 3)
        for k in range(len(pts) - 1):
            _line(surf, (*color, alpha), pts[k], pts[k + 1], thickness)
        for k in range(len(pts) - 1):
            _line(surf, (255, 255, 225, min(255, alpha)), pts[k], pts[k + 1], max(1, thickness - 1))

    def _draw_disc(self, surf, dx, dy, spin, dark, light):
        """带齿纹的旋转飞盘（增强版：外发光 + 锐利锯齿）。"""
        glow_pulse = 1 + 0.12 * math.sin(spin * 1.4)
        # 外发光
        _circle(surf, (*light, 42), (dx, dy), int(42 * glow_pulse))
        _circle(surf, (*light, 24), (dx, dy), int(52 * glow_pulse))
        # 齿纹：12 个锐利旋转锯齿
        teeth = 12
        for i in range(teeth):
            a = spin + i * math.tau / teeth
            p1 = (dx + math.cos(a - 0.10) * 24, dy + math.sin(a - 0.10) * 24)
            mid = (dx + math.cos(a) * 27, dy + math.sin(a) * 27)
            tip = (dx + math.cos(a) * 38, dy + math.sin(a) * 38)
            p2 = (dx + math.cos(a + 0.10) * 24, dy + math.sin(a + 0.10) * 24)
            _polygon(surf, dark, [p1, tip, p2])
            if i % 2 == 0:
                _line(surf, (*light, 140), mid, tip, 2)
        # 盘体
        _circle(surf, dark, (dx, dy), 26)
        body = tuple(min(255, int(c * 1.25 + 12)) for c in dark)
        _circle(surf, body, (dx, dy), 21)
        # 轮圈 + 内环
        _circle(surf, light, (dx, dy), 24, 2)
        _circle(surf, (255, 245, 200), (dx, dy), 19, 1)
        _circle(surf, tuple(int(c * 0.6) for c in dark), (dx, dy), 12)
        # 旋辐（体现旋转）
        for i in range(3):
            a = spin + i * math.tau / 3
            _line(surf, light, (dx + math.cos(a) * 6, dy + math.sin(a) * 6),
                  (dx + math.cos(a) * 17, dy + math.sin(a) * 17), 2)
            _line(surf, (255, 235, 190, 150), (dx + math.cos(a + 0.16) * 7, dy + math.sin(a + 0.16) * 7),
                  (dx + math.cos(a + 0.16) * 15, dy + math.sin(a + 0.16) * 15), 1)
        # 轴心
        _circle(surf, (25, 22, 30), (dx, dy), 5)
        _circle(surf, (255, 250, 235), (dx, dy), 3)
        _circle(surf, light, (dx, dy), 2)

    def draw(self, surf):
        now = pygame.time.get_ticks()
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
                if flicker < 0.10:
                    continue  # 该链接此刻完全消失
                alpha = int(35 + 170 * flicker * (0.6 + 0.4 * warn))
                self._draw_arc(surf, x1, y1, x2, y2, (255, 238, 110), alpha, now, i * 13.7 + 5, thickness=2)
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
            _circle(surf, (255, 120, 200, int(70 * (1 - t))), self.center(), int(60 + 170 * t), 3)
            _circle(surf, (255, 200, 120, int(50 * (1 - t))), self.center(), int(90 + 120 * t), 1)

        for idx, ((dx, dy), ang) in enumerate(positions):
            dark, light = self._DART_COLORS[idx % 2]
            if flash:  # 即将飞出：提亮闪烁预警
                dark = tuple(int(a + (255 - a) * 0.4) for a in dark)
                light = tuple(min(255, int(a + (255 - a) * 0.4)) for a in light)
            spin = now * 0.014 + ang * 2
            if self.released and idx < len(self._fly_discs):
                d = self._fly_discs[idx]
                # 飞出尾焰：黄色闪电电弧（非直线）
                tx, ty = dx - d[2] * 34, dy - d[3] * 34
                self._draw_arc(surf, tx, ty, dx, dy, (255, 238, 110), 170, now, idx * 7.3 + 3, thickness=2)
                _circle(surf, (255, 235, 150, 100), (dx, dy), 28, 2)
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
        self.damage = damage
        self.big_fireball = big_fireball
        self.spawn_time = pygame.time.get_ticks()
        self.max_lifetime = 5200 if bomb else 6500

    def update(self, target_x=None, target_y=None):
        if pygame.time.get_ticks() - self.spawn_time >= self.max_lifetime:
            self.alive = False
            return
        self.prev_x = self.x
        self.prev_y = self.y
        age = pygame.time.get_ticks() - self.spawn_time
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
            # 横向缓慢追踪玩家，纵向恒定速度向下
            dx = target_x - self.x
            self.x += dx * 0.04
            self.y += self.speed
        else:
            rad = math.radians(self.angle)
            self.x += math.sin(rad) * self.speed
            self.y += math.cos(rad) * self.speed
        # 到达游戏区域底部或出屏消失
        if self.y > config.GAME_AREA_BOTTOM or self.y < -20 or self.x < -20 or self.x > config.SCREEN_WIDTH + 20:
            self.alive = False
    def rect(self):
        return pygame.Rect(int(self.x - self.r), int(self.y - self.r), self.r * 2, self.r * 2)

    def block_rect(self):
        r = self.r + (10 if self.big_fireball else 0)
        current = pygame.Rect(int(self.x - r), int(self.y - r), r * 2, r * 2)
        previous = pygame.Rect(int(self.prev_x - r), int(self.prev_y - r), r * 2, r * 2)
        return current.union(previous)

    def draw(self, surf):
        if self.bomb:
            now = pygame.time.get_ticks()
            _circle(surf, (255, 210, 80, 55), (int(self.x), int(self.y)), self.r + 10, 2)
            _circle(surf, (22, 20, 28, 235), (int(self.x), int(self.y)), self.r)
            _circle(surf, (70, 68, 82, 235), (int(self.x - 5), int(self.y - 6)), max(4, self.r // 3))
            _line(surf, (35, 30, 25), (self.x + 7, self.y - 12), (self.x + 18, self.y - 23), 3)
            spark = (self.x + 20 + math.sin(now * 0.02) * 3, self.y - 25)
            _circle(surf, (255, 210, 55, 220), spark, 4)
            _circle(surf, (255, 80, 35, 180), spark, 7, 1)
            return
        if self.big_fireball:
            now = pygame.time.get_ticks()
            for i in range(5, 0, -1):
                _circle(surf, (255, 40, 35, 38 - i * 5), (int(self.x), int(self.y)), self.r + i * 2)
            _circle(surf, (255, 35, 25, 230), (int(self.x), int(self.y)), self.r)
            _circle(surf, (190, 55, 255, 230), (int(self.x), int(self.y)), self.r - 5)
            _circle(surf, (95, 20, 165, 235), (int(self.x), int(self.y)), self.r - 10)
            for a in range(0, 360, 90):
                rad = math.radians(a + now * 0.18)
                _circle(surf, (255, 95, 65, 170),
                        (self.x + math.sin(rad) * (self.r * 0.75),
                         self.y - math.cos(rad) * (self.r * 0.75)), 3)
            return
        if self.homing:
            now = pygame.time.get_ticks()
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
        # 外圈光晕
        for i in range(3, 0, -1):
            _circle(surf, (255, 60, 60, 30 - i * 8), (int(self.x), int(self.y)), self.r + i)
        _circle(surf, (255, 50, 50, 220), (int(self.x), int(self.y)), self.r)
        _circle(surf, (255, 120, 80, 220), (int(self.x), int(self.y)), self.r - 2)
        _circle(surf, (255, 200, 150, 220), (int(self.x) - 1, int(self.y) - 1), self.r - 4)
        _circle(surf, (255, 255, 220, 220), (int(self.x) - 2, int(self.y) - 2), max(1, self.r - 6))
        # 旋转纹
        now = pygame.time.get_ticks()
        for a in range(0, 360, 90):
            rad = math.radians(a + now * 0.2)
            ex = self.x + math.sin(rad) * (self.r * 0.4)
            ey = self.y - math.cos(rad) * (self.r * 0.4)
            _circle(surf, (255, 100, 60, 100), (ex, ey), 2)


class Boss:
    def __init__(self, bdef, difficulty):
        self.bdef = bdef
        self.name = bdef['name']
        enemy_def = next(e for e in ENEMY_DEFS if e['key'] == bdef['enemy_key'])
        self.edef = enemy_def
        self.max_hp = bdef.get('fixed_hp', math.ceil(bdef['base_hp'] * difficulty.boss_hp_mult * 2))
        self.hp = self.max_hp
        self.speed = bdef['speed']
        self.attack_interval = int(bdef['attack_interval'] * difficulty.boss_attack_mult)
        self.projectile_count = bdef['projectile_count']
        self.homing_chance = min(0.75, bdef.get('homing_chance', 0.22) * difficulty.boss_homing_mult)
        self.laser_chance = bdef.get('laser_chance', 0)
        self.last_attack_time = 0
        self.base_w, self.base_h = bdef.get('size', (130, 120))
        self.size_scale = 1.0
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
        self.laser_active_until = 0
        self.next_death_laser_time = 0
        self.next_absorb_time = 0
        self.breath_start_time = pygame.time.get_ticks()
        self.sprite_asset = bdef.get('sprite_asset', f'{bdef["key"]}.png')
        surface_size = (round((self.base_w + 20) * self.size_scale),
                        round((self.base_h + 20) * self.size_scale))
        self.surface = make_boss_surface(bdef.get('sprite_key', bdef['key']), surface_size)
        self.breath_base = None   # 高分辨率基准，呼吸缩放从它缩小采样，避免放大模糊
        self._breath_src = None
        self.font_name = config.make_font(18, bold=True)
        self.font_hp = config.make_font(14, bold=True)

    def can_laser(self):
        return self.laser_chance > 0

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
        now = pygame.time.get_ticks()
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
                if self.can_laser():
                    self.next_death_laser_time = now + random.randint(7000, 13000)
            return

        if self.can_laser() and self.laser_warning_start:
            if now - self.laser_warning_start >= 900:
                self.laser_active_until = now + 2000
                self.laser_warning_start = 0
            return

        if self.can_laser() and now < self.laser_active_until:
            self._move(0.5)
            return

        if self.can_laser() and self.next_death_laser_time and now >= self.next_death_laser_time and random.random() < self.laser_chance:
            self.laser_warning_start = now
            self.next_death_laser_time = now + random.randint(9000, 16000)
            return

        self._move(1.0)

    def _move(self, speed_mult):
        now = pygame.time.get_ticks()
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

    def should_attack(self, now):
        if not self.entered or self.laser_warning_start or now < self.laser_active_until:
            return False
        # 随时间推移攻击越来越密集
        if self.fight_start_time > 0:
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
        if random.random() < 0.25:
            for angle in (-24, 0, 24):
                projectiles.append(BossProjectile(self.x, self.y + self.h // 2 + 24, angle, 3.4,
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
        self.hp -= amount * getattr(self, 'damage_mult', 1.0)

    def apply_slow(self, now, duration=4000, mult=0.7):
        self.slowed_until = max(self.slowed_until, now + duration)
        self.slow_mult = min(self.slow_mult, mult)

    def is_killed(self):
        return self.hp <= 0

    def death_laser_rect(self, now=None):
        if not self.can_laser():
            return None
        now = pygame.time.get_ticks() if now is None else now
        if now >= self.laser_active_until:
            return None
        w = max(24, self.w // 2)
        top = int(self.y + self.h * 0.72)
        return pygame.Rect(int(self.x - w // 2), top, w, max(1, config.GAME_AREA_BOTTOM - top))

    def death_laser_xs(self):
        return (self.x,)

    def death_laser_rects(self, now=None):
        if not self.can_laser():
            return ()
        now = pygame.time.get_ticks() if now is None else now
        if now >= self.laser_active_until:
            return ()
        w = max(24, self.w // 2)
        top = int(self.y + self.h * 0.72)
        return tuple(pygame.Rect(int(x - w // 2), top, w,
                                 max(1, config.GAME_AREA_BOTTOM - top))
                     for x in self.death_laser_xs())

    def draw(self, surf):
        now = pygame.time.get_ticks()
        size_scale = self.size_scale
        scale = _breathing_scale(now - self.breath_start_time, 0.30, 2800)
        center_y = self.y + self.h // 2
        # —— 质感光晕 + 悬浮粒子：血量越低越红、越狂暴 ——
        hp_ratio = max(0, self.hp / self.max_hp)
        if self.bdef['key'] == 'boss_niu' and hp_ratio > 0.5:
            aura, glow_c = (255, 85, 30), (255, 205, 80)
        elif hp_ratio > 0.5:
            aura, glow_c = (110, 160, 255), (200, 225, 255)
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
        if sprite is not None:
            breathing_surface = scale_surface_cached(sprite, breathing_surface.get_size())
        bsw, bsh = breathing_surface.get_size()
        surf.blit(breathing_surface, (int(self.x - bsw // 2), int(center_y - bsh // 2)))
        if self.laser_warning_start:
            elapsed = now - self.laser_warning_start
            if (elapsed // 220) % 2 == 0:
                for x in self.death_laser_xs():
                    _circle(surf, (255, 255, 255, 190), (int(x), int(self.y + self.h // 2)), int(self.w * 0.72), 4)
                    _circle(surf, (255, 60, 40, 160), (int(x), int(self.y + self.h * 0.75)), int(self.w * 0.32))
        for lr in self.death_laser_rects(now):
            beam = pygame.Surface((lr.w + 54, lr.h), pygame.SRCALPHA)
            cx = beam.get_width() // 2
            for i in range(8):
                _rect(beam, (180, 0, 25, max(20, 150 - i * 16)),
                      (cx - lr.w // 2 - i * 5, 0, lr.w + i * 10, lr.h), border_radius=8)
            _rect(beam, (255, 45, 25, 235), (cx - lr.w // 2, 0, lr.w, lr.h), border_radius=6)
            _rect(beam, (255, 245, 210, 220), (cx - max(3, lr.w // 8), 0, max(6, lr.w // 4), lr.h), border_radius=4)
            for y in range(0, lr.h, 30):
                _circle(beam, (255, 220, 80, 150), (cx + int(math.sin(now * 0.03 + y) * lr.w * 0.45), y), 10)
            surf.blit(beam, (lr.x - 27, lr.y))
        if pygame.time.get_ticks() < self.slowed_until:
            _circle(surf, (160, 90, 255, 110), (int(self.x), int(self.y + self.h // 2)),
                    round(82 * size_scale), max(1, round(3 * size_scale)))
        # HP bar (黑底)
        bar_w = 420
        bar_h = 18
        bx = config.SCREEN_WIDTH // 2 - bar_w // 2
        by = 8
        _rect(surf, (20, 20, 30, 220), (bx - 2, by - 2, bar_w + 4, bar_h + 4), border_radius=6)
        _rect(surf, (40, 40, 50, 200), (bx, by, bar_w, bar_h), border_radius=4)
        ratio = max(0, self.hp / self.max_hp)
        # HP 渐变
        if ratio > 0.5:
            bar_color = (40, 200, 80)
        elif ratio > 0.25:
            bar_color = (240, 200, 40)
        else:
            bar_color = (240, 60, 50)
        _rect(surf, bar_color, (bx, by, int(bar_w * ratio), bar_h), border_radius=4)
        # 血条高光
        _rect(surf, (255, 255, 255, 40), (bx + 4, by + 2, int(bar_w * ratio) - 8, bar_h // 3), border_radius=2)
        _rect(surf, (255, 255, 255, 60), (bx, by, bar_w, bar_h), border_radius=4, width=1)

        # Boss name
        name_s = self.font_name.render(self.name, True, (255, 255, 255))
        name_bg = pygame.Surface((name_s.get_width() + 16, name_s.get_height() + 8), pygame.SRCALPHA)
        _rect(name_bg, (20, 20, 30, 180), (0, 0, name_s.get_width() + 16, name_s.get_height() + 8), border_radius=6)
        name_bg.blit(name_s, (8, 4))
        surf.blit(name_bg, (bx, by - 26))
        # HP text
        hp_text = f'{int(self.hp)} / {int(self.max_hp)}'
        hp_s = self.font_hp.render(hp_text, True, (255, 255, 255))
        surf.blit(hp_s, (bx + bar_w - hp_s.get_width() - 10, by + 1))
