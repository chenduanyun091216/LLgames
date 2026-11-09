"""
游戏全局配置：常量、颜色、武器/角色/敌人数据定义、字体工具。
"""
import os
import math
import sys
import pygame

# ── 屏幕 ─────────────────────────────────────────────────────────────────────
BASE_SCREEN_WIDTH = 960
BASE_SCREEN_HEIGHT = 720
SCREEN_WIDTH = BASE_SCREEN_WIDTH
SCREEN_HEIGHT = BASE_SCREEN_HEIGHT
FPS = 60
BEACH_HEIGHT = 60
GAME_AREA_BOTTOM = SCREEN_HEIGHT - BEACH_HEIGHT
GAME_AREA_LEFT = 0
GAME_AREA_RIGHT = SCREEN_WIDTH
MOBILE_LANDSCAPE_VIEW = False
MOBILE_LANDSCAPE_ENTITY_SCALE = 0.64
MOBILE_LANDSCAPE_BOSS_SCALE = 0.48
MOBILE_PORTRAIT_ENTITY_SCALE = 0.8

# 游戏入口以固定步长推进战斗时钟；单独运行游戏对象时使用实时时钟。
campaign_time_ms = None


def game_ticks():
    return pygame.time.get_ticks() if campaign_time_ms is None else campaign_time_ms


# ── 游戏参数 ─────────────────────────────────────────────────────────────────
GOLD_PER_NORMAL = 1
GOLD_PER_LARGE = 3
WEAPON_SWITCH_COOLDOWN = 200

# ── 颜色 ─────────────────────────────────────────────────────────────────────
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
OCEAN_BLUE = (15, 65, 145)
SAND_COLOR = (220, 200, 150)
SAND_DARK = (180, 160, 110)
UI_BG = (0, 0, 0, 160)
GOLD_COLOR = (255, 215, 0)
HEALTH_GREEN = (50, 220, 50)
HEALTH_RED = (220, 50, 50)
PLAYER_HP_GREEN = (50, 200, 50)
# ── 渐变辅助色 ─────────────────────────────────────────────────────────────────
OCEAN_SURFACE = (25, 130, 200)
OCEAN_MID = (15, 85, 155)
OCEAN_DEEP = (8, 45, 100)
WAVE_COLOR = (40, 150, 220, 60)
LIGHT_RAY = (255, 255, 255, 18)
BUBBLE = (200, 230, 255, 80)
SEAWEED_GREEN = (30, 120, 60)
SEAWEED_LIGHT = (50, 150, 80)
CORAL = (220, 120, 80)
ROCK_GRAY = (60, 70, 85)

# ── 全局屏幕引用 ────────────────────────────────────────────────────────────
SCR = None
VIEW_SCALE = 1.0
VIEW_OFFSET = (0, 0)
VIEW_SIZE = (SCREEN_WIDTH, SCREEN_HEIGHT)


def update_mobile_view(window_size, layout_size=None):
    global SCREEN_WIDTH, SCREEN_HEIGHT, GAME_AREA_BOTTOM, GAME_AREA_LEFT, GAME_AREA_RIGHT, SCR
    global VIEW_SCALE, VIEW_OFFSET, VIEW_SIZE, MOBILE_LANDSCAPE_VIEW
    ww, wh = max(1, window_size[0]), max(1, window_size[1])
    lw, lh = layout_size or (ww, wh)
    MOBILE_LANDSCAPE_VIEW = lw >= lh
    SCREEN_WIDTH = BASE_SCREEN_WIDTH if MOBILE_LANDSCAPE_VIEW else 480
    SCREEN_HEIGHT = max(1, int(round(SCREEN_WIDTH * lh / lw)))
    VIEW_SCALE = ww / SCREEN_WIDTH
    VIEW_SIZE = (ww, min(wh, max(1, int(round(SCREEN_HEIGHT * VIEW_SCALE)))))
    VIEW_OFFSET = ((ww - VIEW_SIZE[0]) // 2, (wh - VIEW_SIZE[1]) // 2)
    control_space = min(150, max(80, int(SCREEN_HEIGHT * 0.18)))
    GAME_AREA_BOTTOM = SCREEN_HEIGHT - control_space
    if MOBILE_LANDSCAPE_VIEW:
        GAME_AREA_LEFT = SCREEN_WIDTH // 4
        GAME_AREA_RIGHT = SCREEN_WIDTH * 3 // 4
    else:
        GAME_AREA_LEFT = 0
        GAME_AREA_RIGHT = SCREEN_WIDTH
    SCR = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert()


def window_to_game(pos):
    ox, oy = VIEW_OFFSET
    x, y = pos
    if VIEW_SCALE <= 0:
        return pos
    gx = int((x - ox) / VIEW_SCALE)
    gy = int((y - oy) / VIEW_SCALE)
    return gx, gy


def lerp(a, b, t):
    return a + (b - a) * t

def lerp_color(ca, cb, t):
    return tuple(int(lerp(ca[i], cb[i], t)) for i in range(3))

import random

def random_variation(base, delta=10):
    return tuple(max(0, min(255, c + random.randint(-delta, delta))) for c in base)



# ═══════════════════════════════════════════════════════════════════════════════
#  武器 / 敌人 / 角色 数据定义
# ═══════════════════════════════════════════════════════════════════════════════

class WeaponDef:
    __slots__ = ('name', 'cost', 'normal_shots', 'large_shots', 'nick', 'color', 'fire_rate', 'speed')
    def __init__(self, name, cost, normal_shots, large_shots, nick, color, fire_rate, speed):
        self.name = name
        self.cost = cost
        self.normal_shots = normal_shots
        self.large_shots = large_shots
        self.nick = nick
        self.color = color
        self.fire_rate = fire_rate
        self.speed = speed

WEAPON_DEFS = {
    'pistol':  WeaponDef('手枪',  0,  3, 10, '手枪', (255, 220, 80),  300, 10),
    'rifle':   WeaponDef('步枪', 10,  2,  5, '步枪', (100, 180, 255), 200, 14),
    'shotgun': WeaponDef('散弹枪', 15, 2, 5, '散弹', (110, 235, 180), 360, 12),
    'sniper':  WeaponDef('狙击枪', 20,  1,  3, '狙击枪', (255, 100, 100), 480, 20),
}
_WEAPON_KEYS_ORDERED = ['pistol', 'rifle', 'shotgun', 'sniper']


class SkillDef:
    __slots__ = ('name', 'cooldown_ms', 'key_name', 'skill_type')
    def __init__(self, name, cooldown_ms, key_name, skill_type):
        self.name = name
        self.cooldown_ms = cooldown_ms
        self.key_name = key_name
        self.skill_type = skill_type

class CharacterDef:
    __slots__ = ('name', 'cost', 'skills', 'color', 'nick')
    def __init__(self, name, cost, skills, color, nick):
        self.name = name
        self.cost = cost
        self.skills = skills
        self.color = color
        self.nick = nick

CHARACTER_DEFS = {
    'fire': CharacterDef('火人', 40, [
        SkillDef('火墙', 5000, 'K', 'fire_wall'),
        SkillDef('火球', 10000, 'L', 'fireball'),
    ], (255, 120, 40), '火人'),
    'ice': CharacterDef('冰人', 30, [
        SkillDef('冰墙', 5000, 'K', 'ice_floor'),
        SkillDef('冰球', 10000, 'L', 'ice_balls'),
    ], (80, 180, 255), '冰人'),
    'water': CharacterDef('水人', 45, [
        SkillDef('水疗', 8000, 'K', 'water_heal'),
        SkillDef('潮汐强化', 12000, 'L', 'water_boost'),
    ], (70, 210, 230), '水人'),
    'radiation': CharacterDef('辐射工程师', 50, [
        SkillDef('闪电链', 5000, 'K', 'lightning'),
        SkillDef('磁暴', 10000, 'L', 'magnetic_storm'),
    ], (180, 80, 255), '辐射'),
}
_CHAR_KEYS_ORDERED = ['ice', 'water', 'fire', 'radiation']

ENEMY_DEFS = [
    {'key': 'lobster',  'name': '龙虾',   'is_large': False, 'base_speed': 0.4,   'gold': 1},
    {'key': 'crab',     'name': '螃蟹',   'is_large': False, 'base_speed': 0.255, 'gold': 1},
    {'key': 'goldfish', 'name': '小金鱼', 'is_large': False, 'base_speed': 0.7,   'gold': 1},
    {'key': 'crab_red', 'name': '红蟹',   'is_large': False, 'base_speed': 0.255, 'gold': 1},
    {'key': 'jellyfish', 'name': '水母',   'is_large': False, 'base_speed': 0.32,  'gold': 1},
    {'key': 'octopus_pink', 'name': '粉章鱼', 'is_large': False, 'base_speed': 0.3, 'gold': 1},
    {'key': 'seahorse', 'name': '海马',   'is_large': False, 'base_speed': 0.52,  'gold': 1},
    {'key': 'starfish', 'name': '海星',   'is_large': False, 'base_speed': 0.36,  'gold': 1},
    {'key': 'turtle',   'name': '海龟',   'is_large': False, 'base_speed': 0.22,  'gold': 1},
    {'key': 'zongzong', 'name': '小棕棕', 'is_large': False, 'base_speed': 0.28,  'gold': 3,
     'health_mult': 3.0, 'zongzong': True},
    {'key': 'octopus',  'name': '章鱼',   'is_large': True,  'base_speed': 0.25,  'gold': 3},
    {'key': 'shark',    'name': '鲨鱼',   'is_large': True,  'base_speed': 0.35,  'gold': 3},
]

NEW_ENEMY_KEYS = ['crab_red', 'jellyfish', 'octopus_pink', 'seahorse', 'starfish', 'turtle']
SPECIAL_ENEMY_KEYS = ['zongzong']
NORMAL_ENEMIES = [e for e in ENEMY_DEFS if not e['is_large']]
LARGE_ENEMIES  = [e for e in ENEMY_DEFS if e['is_large']]


# ═══════════════════════════════════════════════════════════════════════════════
#  难度系统
# ═══════════════════════════════════════════════════════════════════════════════

class DifficultyConfig:
    __slots__ = ('name', 'spawn_interval_start', 'spawn_interval_min',
                 'spawn_decrease', 'enemy_speed_mult', 'weapon_cost_mult',
                 'character_cost_mult', 'skill_cd_mult', 'bullet_cost_rifle',
                 'bullet_cost_shotgun', 'bullet_cost_sniper', 'boss_hp_mult',
                 'enemy_attack_interval_min', 'enemy_attack_interval_max',
                 'boss_attack_mult', 'boss_homing_mult')
    def __init__(self, name, spawn_interval_start, spawn_interval_min,
                 spawn_decrease, enemy_speed_mult, weapon_cost_mult,
                 character_cost_mult, skill_cd_mult, bullet_cost_rifle,
                 bullet_cost_shotgun, bullet_cost_sniper, boss_hp_mult,
                 enemy_attack_interval_min, enemy_attack_interval_max,
                 boss_attack_mult, boss_homing_mult):
        self.name = name
        self.spawn_interval_start = spawn_interval_start
        self.spawn_interval_min = spawn_interval_min
        self.spawn_decrease = spawn_decrease
        self.enemy_speed_mult = enemy_speed_mult
        self.weapon_cost_mult = weapon_cost_mult
        self.character_cost_mult = character_cost_mult
        self.skill_cd_mult = skill_cd_mult
        self.bullet_cost_rifle = bullet_cost_rifle
        self.bullet_cost_shotgun = bullet_cost_shotgun
        self.bullet_cost_sniper = bullet_cost_sniper
        self.boss_hp_mult = boss_hp_mult
        self.enemy_attack_interval_min = enemy_attack_interval_min
        self.enemy_attack_interval_max = enemy_attack_interval_max
        self.boss_attack_mult = boss_attack_mult
        self.boss_homing_mult = boss_homing_mult

DIFFICULTY_PRESETS = {
    'easy':   DifficultyConfig('简单', 2800, 1450, 2, 0.78, 0.70, 0.95, 0.90, 0, 0, 0, 0.62, 9000, 14000, 1.45, 0.85),
    'medium': DifficultyConfig('中等', 2300, 1000, 3, 0.93, 0.95, 1.00, 0.95, 0, 0, 1, 0.82, 7000, 11000, 1.18, 0.95),
    'hard':   DifficultyConfig('困难', 2100, 850, 3, 1.03, 1.08, 1.00, 1.45, 1, 2, 2, 1.25, 5800, 9500, 0.92, 1.25),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Boss 定义
# ═══════════════════════════════════════════════════════════════════════════════

BOSS_DEFS = [
    {'key': 'boss_lobster',  'name': '巨型龙虾', 'enemy_key': 'lobster',
     'base_hp': 10, 'speed': 0.6,  'attack_interval': 3300, 'projectile_count': 2, 'homing_chance': 0.16},
    {'key': 'boss_crab',     'name': '巨型螃蟹', 'enemy_key': 'crab',
     'base_hp': 15, 'speed': 0.68, 'attack_interval': 3150, 'projectile_count': 3, 'homing_chance': 0.18,
     'laser_chance': 0.012},
    {'key': 'boss_octopus',  'name': '巨型章鱼', 'enemy_key': 'octopus',
     'base_hp': 23, 'speed': 0.5,  'attack_interval': 2950, 'projectile_count': 3, 'homing_chance': 0.20,
     'laser_chance': 0.015},
    {'key': 'boss_shark',    'name': '巨型鲨鱼', 'enemy_key': 'shark',
     'base_hp': 34, 'speed': 0.76, 'attack_interval': 2650, 'projectile_count': 4, 'homing_chance': 0.23,
     'laser_chance': 0.018},
    {'key': 'boss_dragon',   'name': '海龙',     'enemy_key': 'shark',
     'base_hp': 50, 'speed': 0.92, 'attack_interval': 2350, 'projectile_count': 4, 'homing_chance': 0.25,
     'laser_chance': 0.022},
    {'key': 'boss',          'name': '深渊之主', 'enemy_key': 'shark',
     'base_hp': 78, 'speed': 1.08, 'attack_interval': 1900, 'projectile_count': 6,
     'homing_chance': 0.28, 'laser_chance': 0.035, 'final_boss': True, 'size': (180, 160)},
    {'key': 'boss_niu',      'name': '牛魔王', 'enemy_key': 'shark',
     'base_hp': 105, 'fixed_hp': 300, 'speed': 1.65, 'attack_interval': 3000, 'projectile_count': 6,
     'laser_chance': 0.035, 'size': (168, 150)},
    {'key': 'boss_zongzong', 'name': '小粽粽', 'enemy_key': 'zongzong',
     'base_hp': 150, 'fixed_hp': 400, 'speed': 1.18, 'attack_interval': 1900, 'projectile_count': 6,
     'size': (128, 118), 'sprite_asset': 'zongzong.png', 'sprite_key': 'zongzong'},
]


# ═══════════════════════════════════════════════════════════════════════════════
#  关卡配置
# ═══════════════════════════════════════════════════════════════════════════════

LEVEL_CONFIGS = [
    {'level': 1, 'title': '温柔浅滩', 'kills_needed': 14, 'boss_idx': 0, 'gold_reward': 14,
     'enemy_pool': ['lobster', 'crab', 'goldfish'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
    {'level': 2, 'title': '迷失城堡', 'kills_needed': 18, 'boss_idx': 1, 'gold_reward': 24,
     'enemy_pool': ['lobster', 'crab', 'goldfish', 'octopus'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
    {'level': 3, 'title': '海底激战', 'kills_needed': 22, 'boss_idx': 2, 'gold_reward': 36,
     'enemy_pool': ['crab', 'goldfish', 'octopus', 'shark'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
    {'level': 4, 'title': '珊瑚礁岛', 'kills_needed': 26, 'boss_idx': 3, 'gold_reward': 48,
     'enemy_pool': ['lobster', 'octopus', 'shark'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
    {'level': 5, 'title': '沉船迷航', 'kills_needed': 30, 'boss_idx': 4, 'gold_reward': 62,
     'enemy_pool': ['octopus', 'shark'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
    {'level': 6, 'title': '黑暗森林', 'kills_needed': 0, 'boss_idx': 5, 'gold_reward': 0,
     'enemy_pool': ['crab', 'goldfish', 'octopus', 'shark'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS, 'boss_on_start': True},
    {'level': 7, 'title': '死亡火山', 'kills_needed': 36, 'boss_idx': 6, 'gold_reward': 85,
     'enemy_pool': ['crab', 'octopus', 'shark'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
    {'level': 8, 'title': '粽子星球', 'kills_needed': 42, 'boss_idx': 7, 'gold_reward': 110,
     'enemy_pool': ['lobster', 'goldfish', 'octopus', 'shark'] + NEW_ENEMY_KEYS + SPECIAL_ENEMY_KEYS},
]


def get_level_enemy_defs(level_config):
    pool = level_config['enemy_pool']
    return [e for e in ENEMY_DEFS if e['key'] in pool]


# ═══════════════════════════════════════════════════════════════════════════════
#  字体
# ═══════════════════════════════════════════════════════════════════════════════

_CHINESE_FONT = None
_font_candidates = []
if sys.platform == 'emscripten':
    _font_candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'fonts', 'NotoSansCJKsc-Regular.otf'))
_font_candidates.extend([
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/Hiragino Sans GB.ttc',
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
])
for _p in _font_candidates:
    if os.path.exists(_p):
        _CHINESE_FONT = _p
        break

def make_font(size, bold=False):
    if _CHINESE_FONT:
        font = pygame.font.Font(_CHINESE_FONT, size)
        font.set_bold(bold)
        return font
    return pygame.font.SysFont('pingfangsc,hiraginosansgb,stheitimedium', size, bold=bold)

# Web 战役数值。三元组按简单、中等、困难排列。
CAMPAIGN_KILLS = ((12, 14, 15), (15, 17, 18), (17, 20, 21), (19, 22, 24),
                  (21, 24, 26), (0, 0, 0), (23, 27, 29), (25, 30, 32))
CAMPAIGN_SPAWN_MS = ((2600, 2400, 2200), (2500, 2300, 2125), (2400, 2200, 2050),
                     (2320, 2100, 1975), (2250, 2000, 1900), (0, 0, 0),
                     (2150, 1900, 1825), (2050, 1800, 1750))
CAMPAIGN_ENEMY_CAP = ((4, 5, 6), (5, 6, 7), (5, 6, 7), (6, 7, 8),
                      (6, 7, 8), (0, 0, 0), (6, 8, 9), (7, 8, 9))
CAMPAIGN_BOSS_HP = ((18, 24, 28), (30, 40, 46), (45, 60, 69), (62, 82, 94),
                    (80, 106, 122), (99, 132, 152), (118, 156, 180), (131, 174, 200))
CAMPAIGN_BOSS_ATTACK_MS = ((5000, 4400, 3800), (4800, 4100, 3600), (4600, 3900, 3400),
                           (4400, 3700, 3200), (4200, 3500, 3000), (4000, 3400, 2900),
                           (6800, 5800, 5000), (4500, 3700, 3100))
CAMPAIGN_REINFORCEMENT_MS = ((0, 0, 0), (5500, 5000, 4600), (5100, 4600, 4100),
                             (4800, 4300, 3900), (4500, 4000, 3600), (4800, 4200, 3700),
                             (4800, 4300, 3800), (5200, 4600, 4000))
CAMPAIGN_REINFORCEMENT_CAP = ((0, 0, 0), (1, 1, 2), (1, 2, 2), (1, 2, 2),
                              (2, 2, 3), (2, 2, 3), (2, 2, 3), (1, 2, 2))
CAMPAIGN_LARGE_CHANCE = (0, 0.08, 0.12, 0.14, 0.16, 0.16, 0.18, 0.18)
CAMPAIGN_SPEED = (1.00, 1.03, 1.06, 1.09, 1.12, 1.15, 1.18, 1.20)
CAMPAIGN_REWARDS = (8, 12, 16, 20, 24, 24, 30, 0)
CAMPAIGN_WEAPON_PRICES = {'pistol': (0, 0, 0), 'rifle': (8, 10, 12),
                          'shotgun': (12, 14, 16), 'sniper': (16, 18, 20)}
CAMPAIGN_CHARACTER_PRICES = {'ice': (22, 26, 30), 'fire': (26, 30, 34),
                             'water': (28, 32, 36), 'radiation': (30, 34, 38)}
CAMPAIGN_BULLET_DAMAGE = {'pistol': 1.0, 'rifle': 1.35, 'shotgun': 0.85, 'sniper': 3.0}

# 无限模式 Boss 首轮参数，按 BOSS_DEFS 顺序排列。
INFINITE_BOSS_HP = (30, 46, 66, 90, 116, 144, 170, 192)
INFINITE_BOSS_ATTACK_MS = (4400, 4100, 3900, 3700, 3500, 3400, 5800, 3700)
