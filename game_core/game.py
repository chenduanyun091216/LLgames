"""
游戏主逻辑：GameState, Game 类——难度选择、关卡系统、Boss战、商店、UI。
P1: WASD移动 J射击 K/L技能 1-4切换角色 Q/E切换武器
P2: 方向键移动 小键盘1射击 小键盘2/3技能 小键盘Enter激光 小键盘+飞镖 小键盘7/8/9/4切换角色 小键盘5/6切换武器
"""
import math, random, pygame
from copy import deepcopy
from . import config
from .render import Draw, RenderSurface, blit_effect, effect_layer
from .asset_loader import image_asset, scale_surface_cached
from .background import scrolling_background_art
from .config import (
    WEAPON_SWITCH_COOLDOWN,
    WHITE, GOLD_COLOR, OCEAN_BLUE, SAND_COLOR, PLAYER_HP_GREEN, HEALTH_RED, HEALTH_GREEN,
    make_font, WEAPON_DEFS, CHARACTER_DEFS, _WEAPON_KEYS_ORDERED, _CHAR_KEYS_ORDERED,
    NORMAL_ENEMIES, LARGE_ENEMIES, ENEMY_DEFS,
    DIFFICULTY_PRESETS, BOSS_DEFS, LEVEL_CONFIGS,
    get_level_enemy_defs,
)
from .sprites import (
    _circle, _rect, _ellipse, _line, _polygon, _aaline,
    make_player_surface, make_fire_player_surface, make_ice_player_surface,
    make_water_player_surface, make_radiation_player_surface,
    make_weapon_icon, make_coin_surface,
)
from .mobile_controls import MobileControls, _CHAR_ASSETS, _WEAPON_ASSETS
from .visuals import blit_label, draw_electric_arc, draw_glow, draw_water_drift, panel_surface, small_desktop_label
from .sounds import play_sound, start_music
from .entities import (
    Player, Enemy, Bullet, Coin, GiftBox, Particle, Explosion,
    FireWall, IceFloor, SkillProjectile,
    MagneticStorm, RadiationLaser, Lightning, Boss, BossProjectile,
    SpinningDarts, DragonFireball,
)
from .boss_skills import BOSS_COLORS, CRAB_BUBBLE_BURST_MS, CRAB_BUBBLE_COLORS, BossSignature, SIGNATURES, circle_hits_rect
from .orochi import OrochiBoss
from .abyss_bosses import AbyssProjectile, MechaLizardBoss, AncientWhaleBoss
from .special_bosses import CrescentWave, NiuBoss, NiuShieldShard, ReturningAxe, ZongBomb, ZongBoss, ZongReflectBullet

class GameState:
    DIFFICULTY_SELECT = 0; MENU = 1; PLAYING = 2; SHOP = 3
    BOSS_FIGHT = 4; LEVEL_TRANSITION = 5; GAME_OVER = 6; VICTORY = 7
    PAUSED = 8; CUSTOM_DIFFICULTY = 9; INFINITE_CONTINUE = 11
    INFINITE_COUNTDOWN = 12; KEY_SETTINGS = 13; PAID_REVIVE = 14


TEMPLE_WORM = {'key': 'ancient_worm', 'name': '远古虫', 'is_large': False,
               'gold': 0, 'base_speed': 2.5, 'size': (42, 42),
               'sprite_asset': 'enemies/enemy_ancient_worm.png'}
TEMPLE_RIFT = {'key': 'ancient_rift', 'name': '裂隙之眼', 'is_large': False,
               'gold': 0, 'base_speed': 0, 'size': (378, 126),
               'sprite_asset': 'enemies/enemy_ancient_rift.png'}

CONTACT_DAMAGE_COOLDOWN = 1000
REVIVE_INVINCIBILITY_MS = 1500
TITLE_CROP_RATIO = 390 / 1057
TITLE_MAX_SCALE = 1.30
FISHER_GRENADE_COOLDOWN = 3000
FISHER_GRENADE_RADIUS = 90
FISHER_GRENADE_DAMAGE = 3.0
FAST_ENEMY_CHANCE = 0.12
ENEMY_ATTACK_INTERVAL_MULT = 0.75
ZONGZONG_SPAWN_CHANCE = 0.05
INFINITE_LARGE_ENEMY_CHANCE = 0.16
GIFT_DROP_MIN_MS = 15000
GIFT_DROP_MAX_MS = 15000
GIFT_BUFF_MS = 10000
GIFT_LIGHTNING_DAMAGE = 5.0
BG_FADE_MS = 900
BACKGROUND_SCROLL_TICKS = 40 * config.FPS
INFINITE_BOSS_CYCLE_HP_GROWTH = 0.10
INFINITE_BOSS_STEP_HP_GROWTH = 0.02
CONTROL_DEFS = [
    ('p1_left', 'P1 左移', pygame.K_a), ('p1_right', 'P1 右移', pygame.K_d),
    ('p1_up', 'P1 上移', pygame.K_w), ('p1_down', 'P1 下移', pygame.K_s),
    ('p1_shoot', 'P1 射击', pygame.K_j), ('p1_skill1', 'P1 技能1', pygame.K_k),
    ('p1_skill2', 'P1 技能2', pygame.K_l), ('p1_laser', 'P1 辐射激光', pygame.K_SPACE),
    ('p1_dart', 'P1 飞镖', pygame.K_r), ('p1_weapon_prev', 'P1 上个武器', pygame.K_q),
    ('p1_weapon_next', 'P1 下个武器', pygame.K_e), ('p1_char_ice', 'P1 冰人', pygame.K_1),
    ('p1_char_water', 'P1 水人', pygame.K_2), ('p1_char_fire', 'P1 火人', pygame.K_3),
    ('p1_char_radiation', 'P1 辐射工程师', pygame.K_4),
]
DEFAULT_CONTROLS = {key: default for key, _, default in CONTROL_DEFS}
KEY_LABELS = {
    pygame.K_0: '数字0', pygame.K_1: '数字1', pygame.K_2: '数字2', pygame.K_3: '数字3',
    pygame.K_4: '数字4', pygame.K_5: '数字5', pygame.K_6: '数字6', pygame.K_7: '数字7',
    pygame.K_8: '数字8', pygame.K_9: '数字9', pygame.K_KP0: '小键盘0', pygame.K_KP1: '小键盘1',
    pygame.K_KP2: '小键盘2', pygame.K_KP3: '小键盘3', pygame.K_KP4: '小键盘4',
    pygame.K_KP5: '小键盘5', pygame.K_KP6: '小键盘6', pygame.K_KP7: '小键盘7',
    pygame.K_KP8: '小键盘8', pygame.K_KP9: '小键盘9', pygame.K_SPACE: '空格',
    pygame.K_KP_ENTER: '小键盘Enter', pygame.K_KP_PLUS: '小键盘+',
    pygame.K_LEFT: '左箭头', pygame.K_RIGHT: '右箭头', pygame.K_UP: '上箭头', pygame.K_DOWN: '下箭头',
    pygame.K_RETURN: '回车', pygame.K_ESCAPE: 'Esc',
}

DESKTOP_WEAPON_KEYS = dict(zip(_WEAPON_KEYS_ORDERED, (
    pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4,
)))
DESKTOP_BATTLE_KEYS = {'shop': pygame.K_b, 'pause': pygame.K_h, 'auto_fire': pygame.K_t}
DESKTOP_HUD_KEYS = (pygame.K_LEFTBRACKET, pygame.K_p, pygame.K_RIGHTBRACKET)


class Game:
    def __init__(self, *, desktop_controls=False, scroll_campaign_backgrounds=False):
        self.scroll_campaign_backgrounds = scroll_campaign_backgrounds
        self.desktop_controls = desktop_controls
        self.exit_confirmation = False
        self.clock = pygame.time.Clock()
        self.font_large = make_font(48, bold=True)
        self.font_med = make_font(28, bold=True)
        self.font_small = make_font(20)
        self.font_tiny = make_font(16)
        self.font_countdown = make_font(16, bold=True)
        self._ui_labels = None
        self._desktop_fonts = {}
        self._ui_font_styles = {
            self.font_large: (48, True), self.font_med: (28, True),
            self.font_small: (20, False), self.font_tiny: (16, False),
            self.font_countdown: (16, True),
        }
        if self.desktop_controls:
            self.font_keycap = make_font(11, bold=True)
            self.font_skill_status = make_font(13)
            self._ui_font_styles[self.font_keycap] = (11, True)
            self._ui_font_styles[self.font_skill_status] = (13, False)
        self.title_image = image_asset('ui/title.png')
        self.custom_fields = [
            ('spawn_interval_start', '初始刷怪间隔', 200, 4000, 100),
            ('spawn_interval_min', '最小刷怪间隔', 100, 2000, 50),
            ('spawn_decrease', '每次击杀加速', 0, 30, 1),
            ('enemy_speed_mult', '敌人速度倍率', 0.50, 3.00, 0.05),
            ('weapon_cost_mult', '武器价格倍率', 0.20, 3.00, 0.05),
            ('character_cost_mult', '角色价格倍率', 0.20, 3.00, 0.05),
            ('skill_cd_mult', '技能冷却倍率', 0.20, 3.00, 0.05),
            ('bullet_cost_rifle', '步枪每发金币', 0, 5, 1),
            ('bullet_cost_shotgun', '散弹枪每次射击金币', 0, 8, 1),
            ('bullet_cost_sniper', '狙击每发金币', 0, 8, 1),
            ('boss_hp_mult', 'Boss 血量倍率', 0.30, 4.00, 0.05),
            ('enemy_attack_interval_min', '小怪最短开火间隔', 1000, 10000, 250),
            ('enemy_attack_interval_max', '小怪最长开火间隔', 1500, 14000, 250),
            ('boss_attack_mult', 'Boss 攻击间隔倍率', 0.50, 2.50, 0.05),
            ('boss_homing_mult', 'Boss追击倍率', 0.50, 3.00, 0.05),
        ]
        self.controls = DEFAULT_CONTROLS.copy()
        self.setting_key_action = None
        self.mobile_controls = MobileControls()
        self._last_touch_event = -9999
        self.reset()

    def reset(self):
        self.state = GameState.DIFFICULTY_SELECT
        self.background_scroll_ticks = 0
        self.mobile_controls.reset()
        self.mobile_controls.auto_fire = not self.desktop_controls
        self.difficulty = None
        self.infinite_mode = False
        self.selecting_infinite_mode = False
        self.infinite_boss_index = 0
        self.infinite_start_time = 0
        self.infinite_deaths = 0
        self.infinite_music_variant = 0
        self.infinite_background_level = 1
        self.temple_rifts_at = 0
        self.player_invincible_until = 0
        self.infinite_countdown_end = 0
        self.infinite_resume_state = GameState.PLAYING
        self.player = Player()
        self.player.x = config.SCREEN_WIDTH // 2 - 80
        self.player.surface = make_player_surface('players/player1.png')
        self.player.sprite_asset = 'players/player1.png'
        self.enemies = []; self.bullets = []; self.coins = []; self.particles = []
        self.gift_boxes = []
        self.gift_messages = []
        self.explosions = []
        self.fire_walls = []; self.ice_floors = []; self.skill_projectiles = []
        self.magnetic_storms = []; self.radiation_lasers = []; self.lightnings = []
        self.dart_shields = []
        self.laser_impacts = []; self.last_laser_hit_sound = -220; self.last_skill_hit_sound = -80
        self.water_heal_effects = []
        self.muzzle_flashes = []
        self.skill_flash = None
        self.boss = None; self.boss_projectiles = []
        self.warned_boss_shots = []
        self.warned_boss_shots_at = 0
        self.enemy_projectiles = []
        self.current_level = 1; self.level_kills = 0; self.kill_count = 0; self.score = 0
        self.chapter = 1
        self.lives = 3
        self.revive_count = 0
        self.spawn_interval = 2000; self.min_spawn_interval = 800; self.spawn_decrease = 5
        self.last_spawn_time = 0; self.last_switch_time = -9999
        self.game_over_reason = ''
        self.level_checkpoint = None
        self.pause_prev_state = GameState.PLAYING
        self.shop_prev_state = GameState.PLAYING
        self.cursor_pos = (config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)
        self.player_hp = 5; self.max_player_hp = 5
        self.player_hit_impact = None
        self.player_defeat_visual_at = None
        self.water_temp_hp_until = 0; self.water_passive_kills = 0
        self.leak_count = 0
        self.last_attack_gift = None
        self.level_spawn_count = 0
        self.large_enemy_slots = set()
        self.last_spawn_was_elite = False
        self.enemy_volley_times = []
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0; self.next_gift_time = 0
        self.level_transition_end = 0
        self.victory_end = 0
        self.level_title_until = 0
        self.bg_transition_until = 0
        self.bg_transition_prev = None
        self.custom_values = self._difficulty_to_values(DIFFICULTY_PRESETS['medium'])
        self.custom_row = 0
        self.key_settings_row = 0
        self.bg = self._load_bg()
        self.weapon_icons = {k: make_weapon_icon(k) for k in WEAPON_DEFS}
        self.coin_surface = make_coin_surface()
        self.button_images = {}
        self.ui_panel_image = None
        self.difficulty_card_images = {}
        self.level_enemy_defs = ENEMY_DEFS

    def _load_bg(self):
        from .background import make_background
        level = self.infinite_background_level if self.infinite_mode else getattr(self, 'current_level', 1)
        return make_background(level)

    def _boss_starts_immediately(self):
        level = self.infinite_background_level if self.infinite_mode else self.current_level
        return LEVEL_CONFIGS[level - 1].get('boss_on_start', False)

    def _scrolls_background(self):
        return self.scroll_campaign_backgrounds and self.difficulty

    def scrolling_background(self, size):
        if self._scrolls_background():
            level = self.infinite_background_level if self.infinite_mode else self.current_level
            return scrolling_background_art(
                level, size, self.background_scroll_ticks / BACKGROUND_SCROLL_TICKS)
        return None

    def resize_view(self, previous_area=None):
        self._desktop_fonts.clear()
        if previous_area and not self.infinite_mode:
            old_left, old_right, old_bottom = previous_area
            horizontal_scale = (config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT) / (old_right - old_left)
            vertical_scale = max(1, config.GAME_AREA_BOTTOM) / max(1, old_bottom)
            for entities in (self.players, self.enemies, self.bullets,
                             self.enemy_projectiles, self.boss_projectiles, self.gift_boxes):
                for entity in entities:
                    entity.x = config.GAME_AREA_LEFT + (entity.x - old_left) * horizontal_scale
                    entity.y *= vertical_scale
                    if isinstance(entity, Enemy):
                        entity.speed *= vertical_scale
                    elif isinstance(entity, Player):
                        entity.geyser_lift_y *= vertical_scale

        self.bg_transition_prev = None
        self.bg_transition_until = 0
        self.bg = self._load_bg()
        size_scale = (config.MOBILE_LANDSCAPE_ENTITY_SCALE
                      if config.MOBILE_LANDSCAPE_VIEW else
                      config.MOBILE_PORTRAIT_ENTITY_SCALE)
        for player in self.players:
            player_width = player.rect().w
            half_width = player_width // 2
            min_x = max(40, config.GAME_AREA_LEFT + half_width)
            max_x = min(config.SCREEN_WIDTH - 40,
                        config.GAME_AREA_RIGHT - (player_width + 1) // 2)
            player.x = max(min_x, min(max_x, player.x))
            player.y = max(80, min(player.bottom_limit(), player.y))
        for enemy in self.enemies:
            if enemy.temple_kind == 'rift':
                self._size_temple_rift(enemy)
                low, high = self._temple_rift_y_range(enemy, enemy.temple_side or -1)
                enemy.y = max(low, min(high, enemy.y))
            else:
                enemy.set_size_scale(size_scale)
            half_width = enemy.w // 2
            right_half_width = (enemy.w + 1) // 2
            enemy.x = max(config.GAME_AREA_LEFT + half_width,
                          min(config.GAME_AREA_RIGHT - right_half_width, enemy.x))
        if self.boss:
            if (previous_area and previous_area != (config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT,
                                                    config.GAME_AREA_BOTTOM)
                    and isinstance(self.boss, (MechaLizardBoss, AncientWhaleBoss))):
                # A telegraph belongs to the arena in which it was announced.
                # On solo rotation, cancel only these new attacks and give a
                # full recovery interval instead of stretching a live hitbox
                # onto the player. Online rooms never change layout mid-match.
                self.boss_projectiles[:] = [shot for shot in self.boss_projectiles
                                            if not isinstance(shot, AbyssProjectile)]
                self.warned_boss_shots[:] = [shot for shot in self.warned_boss_shots
                                             if not isinstance(shot, AbyssProjectile)]
                self.boss.last_attack_time = config.game_ticks()
                self.boss.current_skill = ''
            boss_scale = config.MOBILE_LANDSCAPE_BOSS_SCALE if config.MOBILE_LANDSCAPE_VIEW else size_scale
            if self.boss.signature:
                self.boss.signature.stop(self.boss)
                self.boss.signature = None
            self.boss.set_size_scale(boss_scale)
            boss_rect = self.boss.rect()
            left_extent = max(0, int(self.boss.x) - boss_rect.left)
            right_extent = max(0, boss_rect.right - int(self.boss.x))
            self.boss.x = max(config.GAME_AREA_LEFT + left_extent,
                              min(config.GAME_AREA_RIGHT - right_extent, self.boss.x))

    @property
    def players(self):
        return (self.player,)

    def _key(self, action):
        return self.controls.get(action, DEFAULT_CONTROLS[action])

    def _key_name(self, key):
        if key in KEY_LABELS:
            return KEY_LABELS[key]
        name = pygame.key.name(key)
        return name.upper() if len(name) == 1 else name

    def _control_name(self, action):
        return self._key_name(self._key(action))

    def _keycap_text(self, key):
        return {pygame.K_RETURN: 'Enter', pygame.K_ESCAPE: 'Esc',
                pygame.K_LEFT: '←', pygame.K_RIGHT: '→',
                pygame.K_UP: '↑', pygame.K_DOWN: '↓'}.get(key, pygame.key.name(key).upper())

    def desktop_button_key(self, action):
        group, _, item = action.partition(':')
        if group == 'weapon':
            return DESKTOP_WEAPON_KEYS[item]
        if group == 'character':
            return self._key(f'p1_char_{item}')
        return DESKTOP_BATTLE_KEYS[action]

    def _key_pressed(self, keys, action):
        key = self._key(action)
        return self._pressed_key(keys, key)

    def _pressed_key(self, keys, key):
        try:
            return keys[key]
        except (IndexError, KeyError):
            return False

    # ═══ Events ═══════════════════════════════════════════════════════════════
    def handle_events(self, events=None):
        for event in pygame.event.get() if events is None else events:
            if event.type == pygame.QUIT: return False
            if event.type in (
                    getattr(pygame, 'WINDOWFOCUSLOST', -1),
                    getattr(pygame, 'WINDOWHIDDEN', -2),
                    getattr(pygame, 'WINDOWMINIMIZED', -3)):
                self.mobile_controls.reset()
                continue
            if self.exit_confirmation:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    self.exit_confirmation = False
                    if event.key == pygame.K_RETURN and not self._handle_escape():
                        return False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    cancel, confirm = self._choice_rects()
                    position = config.window_to_game(event.pos)
                    if cancel.collidepoint(position):
                        self.exit_confirmation = False
                    elif confirm.collidepoint(position):
                        self.exit_confirmation = False
                        if not self._handle_escape():
                            return False
                continue
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.mobile_controls.release(-1)
            if not self.desktop_controls and event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
                self._last_touch_event = config.game_ticks()
                if self.state in (GameState.PLAYING, GameState.BOSS_FIGHT):
                    if event.type == pygame.FINGERDOWN and self._handle_hud_click(self.mobile_controls.event_position(event)):
                        continue
                    action = self.mobile_controls.handle_touch(event, self)
                    if action:
                        self._handle_mobile_action(action)
                elif event.type == pygame.FINGERUP:
                    self.mobile_controls.release(event.finger_id)
                elif event.type == pygame.FINGERDOWN:
                    self._handle_click(self.mobile_controls.event_position(event))
                continue
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                if getattr(event, 'touch', False) or config.game_ticks() - self._last_touch_event < 120:
                    continue
                if self.state in (GameState.PLAYING, GameState.BOSS_FIGHT):
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self._handle_hud_click(config.window_to_game(event.pos)):
                        continue
                    action = self.mobile_controls.handle_mouse(event, self)
                    if action:
                        self._handle_mobile_action(action)
                    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                        continue
            if event.type == pygame.KEYDOWN:
                infinite = self.infinite_mode or self.selecting_infinite_mode
                level = (event.key - pygame.K_0 if pygame.K_1 <= event.key <= pygame.K_9
                         else {pygame.K_0: 11 if infinite else 10,
                               pygame.K_MINUS: 10 if infinite else 11}.get(event.key, 0))
                jump_limit = len(config.INFINITE_BOSS_HP) if infinite else len(LEVEL_CONFIGS)
                if 1 <= level <= jump_limit and event.mod & pygame.KMOD_SHIFT:
                    self._jump_to_level(level)
                    continue
                if self.setting_key_action:
                    if event.key != pygame.K_ESCAPE:
                        if self.desktop_controls and (
                                event.key in DESKTOP_BATTLE_KEYS.values() or
                                event.key in DESKTOP_WEAPON_KEYS.values() or
                                event.key in DESKTOP_HUD_KEYS or
                                any(event.key == self._key(action) for action in DEFAULT_CONTROLS
                                    if action != self.setting_key_action)):
                            continue
                        self.controls[self.setting_key_action] = event.key
                    self.setting_key_action = None
                    continue
                if event.key == pygame.K_ESCAPE:
                    if self.desktop_controls and (
                            self.state in (GameState.PLAYING, GameState.BOSS_FIGHT, GameState.LEVEL_TRANSITION)
                            or (self.state == GameState.SHOP and self.infinite_mode)):
                        self.exit_confirmation = True
                        continue
                    if not self._handle_escape():
                        return False
                    continue
                self._handle_keydown(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(config.window_to_game(event.pos))
            if event.type == pygame.MOUSEMOTION:
                self.cursor_pos = config.window_to_game(event.pos)
        return True

    def _hud_controls(self):
        width = 170 if config.MOBILE_LANDSCAPE_VIEW else 108
        health = pygame.Rect(0, config.SCREEN_HEIGHT - 43, width, 28)
        health.centerx = config.SCREEN_WIDTH // 2 - (0 if config.MOBILE_LANDSCAPE_VIEW else 8)
        return (pygame.Rect(health.left - 36, health.y, 32, health.h),
                health,
                pygame.Rect(health.right + 4, health.y, 32, health.h))

    def _handle_hud_click(self, position):
        left, health, right = self._hud_controls()
        if health.collidepoint(position):
            self._activate_rage()
            return True
        if not (left.collidepoint(position) or right.collidepoint(position)):
            return False
        delta = -1 if left.collidepoint(position) else 1
        current = self.chapter if self.infinite_mode else self.current_level
        target = max(1, current + delta) if self.infinite_mode else max(1, min(len(LEVEL_CONFIGS), current + delta))
        if target != current:
            if self.infinite_mode:
                now = config.game_ticks()
                self.chapter = target
                self.infinite_boss_index = target - 1
                self._set_infinite_background((target - 1) % len(config.INFINITE_BOSS_HP) + 1, now)
                self.boss = None
                self.boss_projectiles.clear(); self.enemy_projectiles.clear()
                self.enemies.clear(); self.bullets.clear()
                self.spawn_interval = max(800, 1300 - 50 * (self.infinite_boss_index // 2))
                self.last_spawn_time = now + 1200 - self.spawn_interval
                self._start_infinite_chapter(now)
            else:
                self.state = GameState.PLAYING
                self._start_level(target)
        return True

    def _activate_rage(self):
        if not self.infinite_mode and self.difficulty is DIFFICULTY_PRESETS['medium']:
            return
        now = config.game_ticks()
        for p in self.players:
            p.rage_until = now + 20000
        self.rage_banner_until = now + 3000
        play_sound('level_up')

    def _handle_mobile_action(self, action):
        if self._whale_is_swallowing() and action != 'pause':
            return
        if action == 'shop':
            self._open_shop()
        elif action == 'pause':
            if self.state == GameState.PAUSED:
                self.state = self.pause_prev_state
            else:
                self.pause_prev_state = self.state
                self.state = GameState.PAUSED
        elif action.startswith('weapon:'):
            self.try_switch_weapon(action.split(':', 1)[1])
        elif action == 'auto_fire':
            self.mobile_controls.auto_fire = not self.mobile_controls.auto_fire
        elif action == 'skill1':
            self._handle_skill_key(self.player, self._key('p1_skill1'), self._key('p1_skill1'), self._key('p1_skill2'))
        elif action == 'skill2':
            self._handle_skill_key(self.player, self._key('p1_skill2'), self._key('p1_skill1'), self._key('p1_skill2'))
        elif action == 'laser':
            self._activate_radiation_laser(self.player)
        elif action == 'dart':
            self._activate_dart_shield(self.player)
        elif action.startswith('character:'):
            self.try_switch_character(action.split(':', 1)[1], self.player)

    def _handle_escape(self):
        if self.state == GameState.DIFFICULTY_SELECT:
            return False
        if self.state == GameState.PAUSED:
            self.state = self.pause_prev_state
        elif self.state == GameState.PAID_REVIVE:
            self.state = GameState.GAME_OVER
        elif self.state == GameState.KEY_SETTINGS:
            self.setting_key_action = None
            self.state = GameState.MENU
        elif self.state == GameState.CUSTOM_DIFFICULTY:
            self.state = GameState.DIFFICULTY_SELECT
        elif self.state == GameState.SHOP and not self.infinite_mode:
            self._close_shop()
        elif self.state in (GameState.PLAYING, GameState.SHOP, GameState.BOSS_FIGHT, GameState.LEVEL_TRANSITION):
            self.state = GameState.MENU
            self.boss = None
            self.boss_projectiles.clear()
        elif self.state == GameState.MENU:
            self.reset()
        elif self.state in (GameState.GAME_OVER, GameState.VICTORY,
                            GameState.INFINITE_CONTINUE, GameState.INFINITE_COUNTDOWN):
            self.reset()
        return True

    def _handle_keydown(self, event):
        s, k = self.state, event.key
        # 作弊键：Ctrl+P 终极狂暴（射击速度与移动达到极限，持续 20s）
        if k == DESKTOP_HUD_KEYS[1] and (event.mod | pygame.key.get_mods()) & pygame.KMOD_CTRL:
            self._activate_rage()
            return
        if k == DESKTOP_BATTLE_KEYS['pause'] and s in (GameState.PLAYING, GameState.BOSS_FIGHT, GameState.PAUSED):
            self._handle_mobile_action('pause')
            return
        if self.desktop_controls and s == GameState.PAUSED:
            if k == pygame.K_RETURN: self._handle_mobile_action('pause')
            elif k == pygame.K_n: self.reset()
            return
        if self.desktop_controls and s in (GameState.PLAYING, GameState.BOSS_FIGHT):
            for index, key in enumerate(DESKTOP_HUD_KEYS):
                if k == key:
                    self._handle_hud_click(self._hud_controls()[index].center)
                    return
            if k == DESKTOP_BATTLE_KEYS['auto_fire']:
                self._handle_mobile_action('auto_fire')
                return
            for weapon, key in DESKTOP_WEAPON_KEYS.items():
                if k == key:
                    self._handle_mobile_action(f'weapon:{weapon}')
                    return
        if s == GameState.DIFFICULTY_SELECT:
            if k == pygame.K_1: self._start_game('easy')
            elif k == pygame.K_2: self._start_game('medium')
            elif k == pygame.K_3: self._start_game('hard')
            elif k == pygame.K_4: self._start_infinite_game()
            elif k == pygame.K_c: self.state = GameState.CUSTOM_DIFFICULTY
        elif s == GameState.CUSTOM_DIFFICULTY:
            if k in (pygame.K_RETURN, pygame.K_SPACE): self._start_custom_game()
            elif self.desktop_controls:
                if k in (pygame.K_UP, pygame.K_DOWN):
                    self.custom_row = (self.custom_row + (1 if k == pygame.K_DOWN else -1)) % len(self.custom_fields)
                elif k in (pygame.K_LEFT, pygame.K_RIGHT):
                    self._change_custom_value(self.custom_fields[self.custom_row][0], -1 if k == pygame.K_LEFT else 1)
                elif k == pygame.K_r:
                    self.custom_values = self._difficulty_to_values(DIFFICULTY_PRESETS['medium'])
        elif s == GameState.MENU:
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = GameState.PLAYING; self.last_spawn_time = config.game_ticks()
            elif k == pygame.K_b: self._open_shop()
            elif k == pygame.K_c: self.state = GameState.KEY_SETTINGS
        elif s == GameState.KEY_SETTINGS:
            if k == pygame.K_r: self.controls = DEFAULT_CONTROLS.copy()
            elif self.desktop_controls:
                if k in (pygame.K_UP, pygame.K_DOWN):
                    self.key_settings_row = (self.key_settings_row + (1 if k == pygame.K_DOWN else -1)) % len(CONTROL_DEFS)
                elif k == pygame.K_RETURN:
                    self.setting_key_action = CONTROL_DEFS[self.key_settings_row][0]
        elif s == GameState.GAME_OVER:
            if k in (pygame.K_RETURN, pygame.K_SPACE): self._retry_level()
            elif k == pygame.K_n: self.reset()
        elif s == GameState.PAID_REVIVE:
            if k in (pygame.K_y, pygame.K_RETURN): self._paid_revive()
            elif k == pygame.K_n: self.state = GameState.GAME_OVER
        elif s == GameState.INFINITE_CONTINUE:
            if k in (pygame.K_y, pygame.K_RETURN, pygame.K_SPACE): self._continue_infinite()
            elif k in (pygame.K_n, pygame.K_ESCAPE): self.reset()
        elif s in (GameState.PLAYING, GameState.BOSS_FIGHT):
            if self._whale_is_swallowing():
                return
            if k == self._key('p1_weapon_prev'): self.cycle_weapon(self.player, -1)
            elif k == self._key('p1_weapon_next'): self.cycle_weapon(self.player, 1)
            elif k == self._key('p1_char_ice'): self.try_switch_character('ice', self.player)
            elif k == self._key('p1_char_water'): self.try_switch_character('water', self.player)
            elif k == self._key('p1_char_fire'): self.try_switch_character('fire', self.player)
            elif k == self._key('p1_char_radiation'): self.try_switch_character('radiation', self.player)
            elif k == self._key('p1_laser'): self._activate_radiation_laser(self.player)
            elif k == self._key('p1_dart'): self._activate_dart_shield(self.player)
            elif k == pygame.K_b: self._open_shop()
            self._handle_skill_key(self.player, k, self._key('p1_skill1'), self._key('p1_skill2'))
        elif s == GameState.SHOP:
            if k == pygame.K_b: self._close_shop()
            elif pygame.K_1 <= k <= pygame.K_4:
                self._buy_or_equip_weapon(_WEAPON_KEYS_ORDERED[k - pygame.K_1])
            elif pygame.K_5 <= k <= pygame.K_8:
                self._buy_or_equip_character(_CHAR_KEYS_ORDERED[k - pygame.K_5])

    def _handle_click(self, pos):
        mx, my = pos; s = self.state
        if s == GameState.DIFFICULTY_SELECT: self._click_difficulty(mx, my)
        elif s == GameState.CUSTOM_DIFFICULTY: self._click_custom_difficulty(mx, my)
        elif s == GameState.MENU:
            if self._mobile_menu_rects()['start'].collidepoint(mx, my):
                self.state = GameState.PLAYING; self.last_spawn_time = config.game_ticks()
            elif self._mobile_menu_rects()['shop'].collidepoint(mx, my):
                self._open_shop()
            elif self.desktop_controls and self._mobile_menu_rects()['keys'].collidepoint(mx, my):
                self.state = GameState.KEY_SETTINGS
        elif s == GameState.PLAYING: self.cursor_pos = (mx, my)
        elif s == GameState.SHOP: self._handle_shop_click(mx, my)
        elif s == GameState.PAUSED:
            resume, exit_run = self._choice_rects()
            if resume.collidepoint(pos): self.state = self.pause_prev_state
            elif exit_run.collidepoint(pos): self.reset()
        elif s == GameState.PAID_REVIVE:
            revive, end_run = self._choice_rects()
            if revive.collidepoint(pos): self._paid_revive()
            elif end_run.collidepoint(pos): self.state = GameState.GAME_OVER
        elif s == GameState.KEY_SETTINGS: self._handle_key_settings_click(mx, my)
        elif s == GameState.INFINITE_CONTINUE:
            if self._hit(mx, my, config.SCREEN_WIDTH//2-170, config.SCREEN_HEIGHT//2+70, 150, 46): self._continue_infinite()
            elif self._hit(mx, my, config.SCREEN_WIDTH//2+20, config.SCREEN_HEIGHT//2+70, 150, 46): self.reset()
        elif s == GameState.GAME_OVER:
            retry, home = self._game_over_choice_rects()
            if retry.collidepoint(pos): self._retry_level()
            elif home.collidepoint(pos): self.reset()

    def _click_difficulty(self, mx, my):
        if self._mobile_custom_button().collidepoint(mx, my):
            self.state = GameState.CUSTOM_DIFFICULTY
            return
        for key, rect in self._mobile_difficulty_rects():
            if rect.collidepoint(mx, my):
                if key == 'infinite':
                    self._start_infinite_game()
                else:
                    self._start_game(key)
                return

    def _hit(self, mx, my, rx, ry, rw, rh):
        return rx <= mx <= rx+rw and ry <= my <= ry+rh

    # ═══ Game Flow ════════════════════════════════════════════════════════════
    def _start_game(self, diff_key):
        self.selecting_infinite_mode = False
        self.difficulty = DIFFICULTY_PRESETS[diff_key]
        self._begin_selected_run()

    def _start_custom_game(self):
        v = self.custom_values
        self.difficulty = config.DifficultyConfig(
            '自定义',
            int(v['spawn_interval_start']),
            int(v['spawn_interval_min']),
            int(v['spawn_decrease']),
            float(v['enemy_speed_mult']),
            float(v['weapon_cost_mult']),
            float(v['character_cost_mult']),
            float(v['skill_cd_mult']),
            int(v['bullet_cost_rifle']),
            int(v['bullet_cost_shotgun']),
            int(v['bullet_cost_sniper']),
            float(v['boss_hp_mult']),
            int(v['enemy_attack_interval_min']),
            int(v['enemy_attack_interval_max']),
            float(v['boss_attack_mult']),
            float(v['boss_homing_mult']),
        )
        self.selecting_infinite_mode = False
        self._begin_selected_run()

    def _start_infinite_game(self):
        self.selecting_infinite_mode = True
        self.difficulty = DIFFICULTY_PRESETS['hard']
        self._begin_selected_run()

    def _begin_selected_run(self):
        if self.selecting_infinite_mode:
            self._begin_infinite_run()
        else:
            self._begin_run()

    def _jump_to_level(self, level):
        self.setting_key_action = None
        if self.infinite_mode or self.selecting_infinite_mode:
            self._begin_infinite_run(level)
            return
        if self.difficulty is None:
            self.difficulty = DIFFICULTY_PRESETS['medium']
        self._begin_run(level)

    def _begin_run(self, start_level=1):
        self.player_hit_impact = None
        self.selecting_infinite_mode = False
        self.player.x = config.SCREEN_WIDTH // 2
        self.player.y = config.GAME_AREA_BOTTOM - 14
        self.player.current_weapon = 'pistol'
        self.player.character = None
        self.player.surface = make_player_surface('players/player1.png')
        self.player.sprite_asset = 'players/player1.png'
        self.player.skill_cooldowns = {}
        self.player.skill_display_duration.clear()
        self.player.skill_active_until = {}
        self.player.skill_active_cd = {}
        self.player.water_boost_until = 0
        self.player.water_haste_until = 0
        self.player.gift_speed_until = 0
        self.player.rage_until = 0
        self.player.weapon_ammo = {}
        self.infinite_mode = False
        self.player.campaign = True
        self.player.hazard_slow = (0.85, 0.80, 0.75)[self._campaign_tier()]
        self.lives = 3
        self.revive_count = 0
        self._apply_difficulty(start_level)
    
    def _begin_infinite_run(self, start_chapter=1):
        self.player_hit_impact = None
        self.selecting_infinite_mode = False
        self.infinite_mode = True
        self.player.campaign = False
        self.difficulty = DIFFICULTY_PRESETS['hard']
        self.player.x = config.SCREEN_WIDTH // 2
        self.player.y = config.GAME_AREA_BOTTOM - 14
        self.player.owned_weapons = list(_WEAPON_KEYS_ORDERED)
        self.player.owned_characters = list(_CHAR_KEYS_ORDERED)
        self.player.current_weapon = 'pistol'
        self.player.character = None
        self.player.surface = make_player_surface('players/player1.png')
        self.player.sprite_asset = 'players/player1.png'
        self.player.skill_cooldowns = {}
        self.player.skill_display_duration.clear()
        self.player.skill_active_until = {}
        self.player.skill_active_cd = {}
        self.player.water_boost_until = 0
        self.player.water_haste_until = 0
        self.player.gift_speed_until = 0
        self.player.rage_until = 0
        self.player.weapon_ammo = {}
        self.player.gold = 0
        self.current_level = 1; self.level_kills = 0; self.kill_count = 0; self.score = 0
        self.chapter = start_chapter
        self.lives = 3
        self.revive_count = 0
        self.infinite_background_level = start_chapter
        self.infinite_deaths = 0
        self.background_scroll_ticks = 0
        self.max_player_hp = 5; self.player_hp = self.max_player_hp
        self.spawn_interval = 1300; self.min_spawn_interval = 800; self.spawn_decrease = 0
        self.boss = None; self.boss_projectiles.clear(); self.enemy_projectiles.clear()
        self.enemies.clear(); self.bullets.clear(); self.coins.clear(); self.gift_boxes.clear(); self.gift_messages.clear(); self.explosions.clear()
        self.factory_link_attempts = set()
        self.temple_rifts_at = 0
        self.enemy_volley_times = []
        self.leak_count = 0
        self.fire_walls.clear(); self.ice_floors.clear(); self.skill_projectiles.clear()
        self.magnetic_storms.clear(); self.radiation_lasers.clear(); self.lightnings.clear()
        self.dart_shields.clear(); self.laser_impacts.clear()
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0
        self.bg = self._load_bg()
        now = config.game_ticks()
        self.last_spawn_time = now - 100
        self._schedule_next_gift(now)
        self.infinite_start_time = now
        self.infinite_music_variant = 0
        self.player_invincible_until = 0
        self.infinite_boss_index = start_chapter - 1
        # 第 9、10 轮使用各自的小怪池，其余轮次沿用原刷怪组成。
        self.level_enemy_defs = get_level_enemy_defs(LEVEL_CONFIGS[7])
        self.bg_transition_until = 0
        self.bg_transition_prev = None
        self._start_infinite_chapter(now)

    def _start_infinite_chapter(self, now):
        self.level_title_until = now + 2200
        if self._boss_starts_immediately():
            self._trigger_infinite_boss()
        else:
            self.state = GameState.PLAYING
            start_music(self.infinite_background_level, infinite=True, variant=self.infinite_music_variant)

    def _apply_difficulty(self, start_level=1):
        self.spawn_interval = self.difficulty.spawn_interval_start
        self.min_spawn_interval = self.difficulty.spawn_interval_min
        self.spawn_decrease = self.difficulty.spawn_decrease
        self.current_level = 1; self.level_kills = 0; self.kill_count = 0
        self.chapter = start_level
        self.max_player_hp = (6, 5, 4)[self._campaign_tier()]
        self.player_hp = self.max_player_hp
        self.boss = None; self.boss_projectiles.clear()
        self.enemy_projectiles.clear()
        self.gift_boxes.clear()
        self.gift_messages.clear()
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0
        self.state = GameState.PLAYING
        self._start_level(start_level)

    def _difficulty_to_values(self, diff):
        values = {name: getattr(diff, name) for name, _, _, _, _ in self.custom_fields}
        if diff is DIFFICULTY_PRESETS['medium']:
            values.update(spawn_interval_start=2400, spawn_interval_min=1800, spawn_decrease=0,
                          enemy_speed_mult=1.0, weapon_cost_mult=1.0, skill_cd_mult=1.0,
                          bullet_cost_sniper=0, boss_hp_mult=1.0, boss_attack_mult=1.0,
                          boss_homing_mult=1.0, enemy_attack_interval_min=8000,
                          enemy_attack_interval_max=12000)
        return values

    def _change_custom_value(self, key, delta):
        _label, min_v, max_v, step = next(item[1:] for item in self.custom_fields if item[0] == key)
        value = max(min_v, min(max_v, self.custom_values[key] + delta * step))
        self.custom_values[key] = int(value) if isinstance(min_v, int) and isinstance(step, int) else value

    def _click_custom_difficulty(self, mx, my):
        for index, (key, row, minus, plus) in enumerate(self._mobile_custom_rows()):
            if row.collidepoint(mx, my):
                self.custom_row = index
            if minus.collidepoint(mx, my):
                self._change_custom_value(key, -1)
                return
            if plus.collidepoint(mx, my):
                self._change_custom_value(key, 1)
                return
        actions = self._mobile_custom_action_rects()
        if actions['reset'].collidepoint(mx, my):
            self.custom_values = self._difficulty_to_values(DIFFICULTY_PRESETS['medium'])
        elif actions['back'].collidepoint(mx, my):
            self.state = GameState.DIFFICULTY_SELECT
        elif actions['start'].collidepoint(mx, my):
            self._start_custom_game()

    def _key_settings_rects(self):
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        columns = 3 if config.MOBILE_LANDSCAPE_VIEW else 2
        rows = (len(CONTROL_DEFS) + columns - 1) // columns
        row_w = min(250, (width - (columns + 1) * 12) // columns)
        row_h = min(36, max(24, (height - 160) // rows - 6))
        left = (width - columns * row_w - (columns - 1) * 12) // 2
        return [
            (action, label, pygame.Rect(left + i // rows * (row_w + 12),
                                        86 + i % rows * (row_h + 6), row_w, row_h))
            for i, (action, label, _) in enumerate(CONTROL_DEFS)
        ]

    def _key_settings_buttons(self):
        center, y = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 62
        return pygame.Rect(center - 156, y, 150, 42), pygame.Rect(center + 6, y, 150, 42)

    def _handle_key_settings_click(self, mx, my):
        for action, _, rect in self._key_settings_rects():
            if rect.collidepoint(mx, my):
                self.setting_key_action = action
                return
        reset, back = self._key_settings_buttons()
        if reset.collidepoint(mx, my):
            self.controls = DEFAULT_CONTROLS.copy()
            self.setting_key_action = None
        elif back.collidepoint(mx, my):
            self.setting_key_action = None
            self.state = GameState.MENU

    def _campaign_tier(self):
        name = self.difficulty.name if self.difficulty else '中等'
        return {'简单': 0, '困难': 2}.get(name, 1)

    def _enemy_speed_multiplier(self):
        return 1.30 if self.infinite_mode else (1.20, 1.25, 1.30)[self._campaign_tier()]

    def _campaign_value(self, table):
        return table[self.current_level - 1][self._campaign_tier()]

    def _start_level(self, n, *, checkpoint=True):
        for player in self.players:
            player.geyser_lift_until = 0
        self.current_level = n; self.level_kills = 0
        self.background_scroll_ticks = 0
        self.bg = self._load_bg()
        self.level_title_until = config.game_ticks() + 2200
        self.boss = None; self.boss_projectiles.clear()
        self.fire_walls.clear(); self.ice_floors.clear()
        self.skill_projectiles.clear(); self.magnetic_storms.clear(); self.radiation_lasers.clear(); self.lightnings.clear()
        self.dart_shields.clear(); self.laser_impacts.clear()
        self.enemies.clear(); self.bullets.clear(); self.gift_boxes.clear(); self.gift_messages.clear(); self.explosions.clear(); self.muzzle_flashes.clear()
        self.enemy_projectiles.clear()
        self.factory_link_attempts = set()
        self.temple_rifts_at = 0
        self.skill_flash = None
        self.level_enemy_defs = get_level_enemy_defs(LEVEL_CONFIGS[n-1])
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0
        now = config.game_ticks()
        self.spawn_interval = self._campaign_value(config.CAMPAIGN_SPAWN_MS)
        self.spawn_decrease = 0
        if self.difficulty and self.difficulty.name == '自定义':
            self.spawn_interval = round(self.spawn_interval * self.difficulty.spawn_interval_start / 2400)
            self.min_spawn_interval = min(self.spawn_interval, self.difficulty.spawn_interval_min)
            self.spawn_decrease = self.difficulty.spawn_decrease
        self.last_spawn_time = now + 1200 - self.spawn_interval
        self.leak_count = 0
        self.last_attack_gift = None
        self.level_spawn_count = 0
        self.large_enemy_slots = self._campaign_large_enemy_slots()
        self.last_spawn_was_elite = False
        self.enemy_volley_times = []
        self.water_passive_kills = 0
        self.next_gift_time = now + 18000
        start_music(n)
        if LEVEL_CONFIGS[n-1].get('boss_on_start'):
            self._trigger_boss()
        if checkpoint and not self.infinite_mode:
            self._save_level_checkpoint(now)

    def _save_level_checkpoint(self, now):
        player = {}
        for key, value in vars(self.player).items():
            if key in ('surface', 'breath_base', '_breath_src'):
                continue
            if key in ('last_shot_time', 'animation_move_at', 'animation_skill_at', 'animation_hit_at') and value is not None:
                value -= now
            elif key.endswith('_until') and isinstance(value, (int, float)):
                value = max(0, value - now)
            elif key in ('skill_cooldowns', 'skill_active_until'):
                value = {name: max(0, deadline - now) for name, deadline in value.items()}
            player[key] = deepcopy(value)
        fields = ('player_hp', 'max_player_hp', 'kill_count', 'score',
                  'chapter', 'water_passive_kills', 'leak_count')
        timers = ('player_invincible_until', 'water_temp_hp_until')
        self.level_checkpoint = {
            'level': self.current_level, 'player': player, 'surface': self.player.surface,
            'fields': {key: getattr(self, key) for key in fields},
            'timers': {key: max(0, getattr(self, key) - now) for key in timers},
        }

    def _retry_level(self):
        checkpoint = self.level_checkpoint
        if self.infinite_mode or checkpoint is None:
            self.reset()
            return
        now = config.game_ticks()
        for key, value in checkpoint['fields'].items():
            setattr(self, key, value)
        self.lives = 3
        self.revive_count = 0
        for key, value in checkpoint['player'].items():
            value = deepcopy(value)
            if key in ('last_shot_time', 'animation_move_at', 'animation_skill_at', 'animation_hit_at') and value is not None:
                value += now
            elif key.endswith('_until') and isinstance(value, (int, float)):
                value = now + value if value else 0
            elif key in ('skill_cooldowns', 'skill_active_until'):
                value = {name: now + remaining for name, remaining in value.items() if remaining > 0}
            setattr(self.player, key, value)
        self.player.surface = checkpoint['surface']
        self.player.breath_base = None
        self.player._breath_src = None
        for key, remaining in checkpoint['timers'].items():
            setattr(self, key, now + remaining if remaining else 0)
        self.coins.clear()
        self.particles.clear()
        self.water_heal_effects.clear()
        self.warned_boss_shots.clear()
        self.game_over_reason = ''
        self.state = GameState.PLAYING
        self._start_level(checkpoint['level'], checkpoint=False)

    def _trigger_boss(self):
        if self.boss:
            self._settle_boss_if_killed()
            return
        lcfg = LEVEL_CONFIGS[self.current_level-1]; bdef = BOSS_DEFS[lcfg['boss_idx']]
        tier = self._campaign_tier()
        custom = self.difficulty.name == '自定义'
        attack_mult = self.difficulty.boss_attack_mult if custom else 1
        homing_mult = self.difficulty.boss_homing_mult if custom else 1
        bdef = {
            **bdef,
            'fixed_hp': self._campaign_boss_hp(),
            'attack_interval': round(self._campaign_value(config.CAMPAIGN_BOSS_ATTACK_MS) * attack_mult),
            'campaign_tier': tier,
            'campaign_level': self.current_level,
            'homing_chance': (0.10, 0.16, 0.22)[tier] * homing_mult if self.current_level >= 4 else 0,
            'damage_cap': (1, 2, 2)[tier],
        }
        if bdef['key'] == 'boss_niu':
            bdef.update(shield_thresholds=((0.5,), (0.65, 0.30), (0.75, 0.5, 0.25))[tier])
        elif bdef['key'] == 'boss_zongzong':
            bdef['easy_campaign'] = tier < 2
        self.boss = self._make_boss(bdef)
        self.warned_boss_shots.clear()
        self.boss_projectiles.clear(); self.enemy_projectiles.clear(); self.bullets.clear()
        self.last_spawn_time = config.game_ticks()
        start_music(self.current_level, boss=True)
        play_sound('boss_appear'); self.state = GameState.BOSS_FIGHT

    def _campaign_boss_hp(self):
        multiplier = self.difficulty.boss_hp_mult if self.difficulty.name == '自定义' else 1
        return math.ceil(self._campaign_value(config.CAMPAIGN_BOSS_HP) * multiplier)

    def _infinite_boss_hp(self, index, cycle):
        health_percent = 100 + 20 * min(cycle, 6)
        return (config.INFINITE_BOSS_HP[index] * health_percent + 99) // 100

    def _trigger_infinite_boss(self):
        boss_number = self.infinite_boss_index
        cycle, index = divmod(boss_number, len(config.INFINITE_BOSS_HP))
        bdef = BOSS_DEFS[index]
        interval_percent = max(70, 100 - 5 * cycle)
        bdef = {**bdef,
                'fixed_hp': self._infinite_boss_hp(index, cycle),
                'attack_interval': round(config.INFINITE_BOSS_ATTACK_MS[index] * interval_percent / 100),
                'campaign_tier': 1, 'campaign_level': index + 1, 'damage_cap': 2}
        if bdef['key'] == 'boss_niu':
            bdef.update(shield_thresholds=(0.65, 0.30))
        elif bdef['key'] == 'boss_zongzong':
            bdef['easy_campaign'] = False
        self.boss = self._make_boss(bdef)
        self.enemies.clear()
        self.boss_projectiles.clear(); self.enemy_projectiles.clear(); self.bullets.clear()
        self.last_spawn_time = config.game_ticks()
        start_music(self.infinite_background_level, boss=True, infinite=True)
        play_sound('boss_appear'); self.state = GameState.BOSS_FIGHT

    def _make_boss(self, bdef):
        cls = {'boss_niu': NiuBoss, 'boss_zongzong': ZongBoss,
               'boss_orochi': OrochiBoss, 'boss_mecha_lizard': MechaLizardBoss,
               'boss_ancient_whale': AncientWhaleBoss}.get(bdef['key'], Boss)
        boss = cls(bdef, self.difficulty)
        boss.intro_until = config.game_ticks() + 950
        return boss

    def _player_defeated(self, reason):
        self.player_defeat_visual_at = pygame.time.get_ticks()
        self.game_over_reason = reason
        if self.infinite_mode:
            self.infinite_deaths += 1
            self.state = GameState.INFINITE_CONTINUE
        else:
            self.lives -= 1
            if self.lives > 0:
                self._resume_after_defeat()
                return
            self.state = (GameState.PAID_REVIVE if self._can_buy_revive()
                          else GameState.GAME_OVER)
        play_sound('game_over')

    def _revive_cost(self):
        return (50, 75, 100)[self._campaign_tier()]

    def _paid_revives_remaining(self):
        revive_limit = (5, 4, 3)[self._campaign_tier()]
        return max(0, revive_limit - self.revive_count)

    def _can_buy_revive(self):
        return self._paid_revives_remaining() > 0 and self.player.gold >= self._revive_cost()

    def _paid_revive(self):
        if self.state != GameState.PAID_REVIVE or not self._can_buy_revive():
            return
        self.player.gold -= self._revive_cost()
        self.revive_count += 1
        self.lives = 1
        self._resume_after_defeat()

    def _clear_invaded_enemies(self):
        self.enemies = [e for e in self.enemies if not e.reached_bottom()]

    def _continue_infinite(self):
        self.score = 0
        self.revive_count += 1
        self._resume_after_defeat()

    @staticmethod
    def _place_revived_player(player):
        player.geyser_lift_until = 0
        player.animation_hit_at = None
        player.animation_skill_at = None
        player.x, player.y = config.SCREEN_WIDTH // 2, config.GAME_AREA_BOTTOM - 14

    def _resume_after_defeat(self):
        self._place_revived_player(self.player)
        now = config.game_ticks()
        self._clear_invaded_enemies()
        if self.boss and self.boss.signature:
            signature = self.boss.signature
            # A lethal bite must not cancel the rest of the dive.
            if not (signature.key == 'boss' and signature.origin is not None):
                signature.stop(self.boss)
                self.boss.signature = None
        self.player_hp = self.max_player_hp
        self.infinite_countdown_end = pygame.time.get_ticks() + 3000
        if not self.infinite_mode:
            for projectiles in (self.enemy_projectiles, self.boss_projectiles):
                projectiles[:] = [p for p in projectiles if math.hypot(
                    p.x - self.player.x, p.y - self.player.y) > 150]
        self.infinite_resume_state = GameState.BOSS_FIGHT if self.boss else GameState.PLAYING
        self.last_spawn_time = now
        self.state = GameState.INFINITE_COUNTDOWN

    def _level_complete(self):
        self.explosions.clear()
        self._burst_remaining_enemies()
        self.bullets.clear()
        self.enemy_projectiles.clear()
        self.boss_projectiles.clear()
        self.warned_boss_shots.clear()
        self.player.gold += config.CAMPAIGN_REWARDS[self.current_level - 1]
        play_sound('level_up')
        if self.current_level >= len(LEVEL_CONFIGS):
            self.state = GameState.VICTORY
            self.victory_end = config.game_ticks() + 4000
        else:
            self.state = GameState.LEVEL_TRANSITION
            self.level_transition_end = config.game_ticks() + 2000

    # ═══ Weapons & Skills ═════════════════════════════════════════════════════
    def _equipped_by_other(self, player, attr, key):
        if attr == 'current_weapon' and key == 'pistol':
            return False
        return any(other is not player and getattr(other, attr) == key for other in self.players)

    def _handle_skill_key(self, player, key, skill1_key, skill2_key):
        if config.game_ticks() < player.geyser_lift_until:
            return
        if not player.character:
            if key == skill1_key:
                self._activate_fisher_grenade(player)
            return
        cdef = CHARACTER_DEFS.get(player.character)
        if not cdef:
            return
        for sk in cdef.skills:
            if (sk.key_name == 'K' and key == skill1_key) or (sk.key_name == 'L' and key == skill2_key):
                self._activate_skill(sk, player)

    def _activate_fisher_grenade(self, player):
        now = config.game_ticks()
        skill_type = 'fisher_grenade'
        if not self._skill_ready(player, skill_type, now):
            return
        if self.infinite_mode:
            self._start_skill_effect(player, skill_type, FISHER_GRENADE_COOLDOWN, 900, now)
        else:
            self._start_skill_effect(player, skill_type, self._skill_cooldown(4000, FISHER_GRENADE_COOLDOWN), 0, now)
        self.skill_projectiles.append(SkillProjectile(player.x, player.y - 28, 0, 6, 'grenade', owner=player, skill_type=skill_type))
        play_sound('grenade')

    def _skill_ready(self, player, skill_type, now):
        return (now >= player.skill_cooldowns.get(skill_type, 0) and
                now >= getattr(player, 'skill_active_until', {}).get(skill_type, 0))

    def _start_skill_effect(self, player, skill_type, cd_ms, active_ms, now=None):
        now = config.game_ticks() if now is None else now
        player.animation_skill = skill_type
        player.animation_skill_at = now
        player.skill_display_duration[skill_type] = cd_ms + max(0, active_ms)
        if active_ms <= 0:
            player.skill_cooldowns[skill_type] = now + cd_ms
            return
        self._flash_skill(player, now)
        player.skill_active_until[skill_type] = now + active_ms
        player.skill_active_cd[skill_type] = cd_ms

    def _finish_skill_effect(self, player, skill_type, now=None):
        if not player or skill_type not in getattr(player, 'skill_active_until', {}):
            return
        now = config.game_ticks() if now is None else now
        cd_ms = player.skill_active_cd.pop(skill_type, 0)
        player.skill_active_until.pop(skill_type, None)
        player.skill_display_duration[skill_type] = cd_ms
        player.skill_cooldowns[skill_type] = now + cd_ms

    def _finish_projectile_skill_if_gone(self, sp, now=None):
        owner = getattr(sp, 'owner', None)
        skill_type = getattr(sp, 'skill_type', None)
        if not owner or not skill_type:
            return
        for other in self.skill_projectiles:
            if other is not sp and getattr(other, 'owner', None) is owner and getattr(other, 'skill_type', None) == skill_type:
                return
        self._finish_skill_effect(owner, skill_type, now)

    def _skill_has_active_artifact(self, player, skill_type):
        for group in (self.skill_projectiles, self.fire_walls, self.ice_floors, self.magnetic_storms, self.dart_shields):
            for obj in group:
                if getattr(obj, 'owner', None) is player and getattr(obj, 'skill_type', None) == skill_type:
                    return True
        return False

    def _remove_skill_projectile(self, sp, now=None):
        if sp in self.skill_projectiles:
            self._finish_projectile_skill_if_gone(sp, now)
            self.skill_projectiles.remove(sp)

    def _expire_active_skills(self, now):
        for player in self.players:
            for skill_type, active_until in list(getattr(player, 'skill_active_until', {}).items()):
                if now >= active_until and not self._skill_has_active_artifact(player, skill_type):
                    self._finish_skill_effect(player, skill_type, now)

    def try_switch_weapon(self, key, player=None):
        player = player or self.player
        now = config.game_ticks()
        if now - self.last_switch_time < WEAPON_SWITCH_COOLDOWN: return False
        if self.infinite_mode and key == 'pistol':
            return False  # 无限模式手枪置灰，不可切换
        if key in player.owned_weapons and not self._equipped_by_other(player, 'current_weapon', key):
            player.current_weapon = key; self.last_switch_time = now
            return True
        return False

    def cycle_weapon(self, player=None, direction=1):
        if isinstance(player, int):
            direction = player
            player = self.player
        player = player or self.player
        pool = player.owned_weapons
        if self.infinite_mode:
            # 无限模式手枪置灰：Q/E 只在步枪/散弹枪/狙击枪之间切换
            pool = [key for key in pool if key != 'pistol']
        owned = [key for key in pool if not self._equipped_by_other(player, 'current_weapon', key)]
        if not owned: return
        if player.current_weapon not in owned:
            self.try_switch_weapon(owned[0], player)
            return
        if len(owned) <= 1: return
        try: idx = owned.index(player.current_weapon)
        except ValueError: idx = 0
        self.try_switch_weapon(owned[(idx+direction) % len(owned)], player)

    def _cycle_character(self, player=None):
        player = player or self.player
        owned = [key for key in player.owned_characters if not self._equipped_by_other(player, 'character', key)]
        if not owned: return
        if player.character is None: next_key = owned[0]
        else:
            try: idx = owned.index(player.character)
            except ValueError: idx = -1
            next_key = owned[(idx+1) % len(owned)]
        self.try_switch_character(next_key, player)

    def try_switch_character(self, key, player=None):
        player = player or self.player
        now = config.game_ticks()
        # 辐射激光持续期间禁止切换角色
        if any(laser.owner is player and not laser.is_expired(now) for laser in self.radiation_lasers):
            play_sound('error')
            return False
        if key not in player.owned_characters or self._equipped_by_other(player, 'character', key):
            return False
        sm = {'fire': make_fire_player_surface, 'ice': make_ice_player_surface, 'water': make_water_player_surface, 'radiation': make_radiation_player_surface}
        player.surface = sm[key](); player.character = key
        return True

    def _bullet_cost(self, wkey):
        if self.infinite_mode or not self.difficulty or self.difficulty.name != '自定义':
            return 0
        return getattr(self.difficulty, f'bullet_cost_{wkey}', 0)

    def _weapon_cost(self, key):
        price = config.CAMPAIGN_WEAPON_PRICES[key][self._campaign_tier()]
        if self.difficulty and self.difficulty.name == '自定义':
            price *= self.difficulty.weapon_cost_mult
        return math.ceil(price)

    def _player_speed(self, player, now):
        speed = Player.SPEED
        if now < player.water_boost_until:
            speed *= 1.6 if self.infinite_mode else 1.25
        if now < getattr(player, 'rage_until', 0):
            speed = max(speed, Player.SPEED * 1.6)
        if isinstance(self.boss, NiuBoss) and any(
                rect.colliderect(player.rect()) for rect in self.boss.lightning_rects(now)):
            speed *= 0.6
        if now < player.niu_slow_until:
            speed *= 0.5 if self.infinite_mode else (0.85, 0.80, 0.75)[self._campaign_tier()]
        if now < player.snow_slow_until:
            speed *= 0.5 if self.infinite_mode else (0.85, 0.80, 0.75)[self._campaign_tier()]
        return speed * 1.3 / self._player_fire_interval_multiplier(now)

    def _player_fire_interval_multiplier(self, now):
        if isinstance(self.boss, AncientWhaleBoss) and self.boss.suction_active(now):
            return 2
        return 1

    def _heal_player(self, amount, increase_max=False, temporary_ms=0):
        if increase_max:
            self.max_player_hp = min(5, self.max_player_hp + amount)
        if temporary_ms > 0:
            self.player_hp = min(self.max_player_hp + amount, self.player_hp + amount)
        else:
            self.player_hp = min(self.max_player_hp, self.player_hp + amount)
        if temporary_ms > 0:
            self.water_temp_hp_until = max(self.water_temp_hp_until, config.game_ticks() + temporary_ms)

    def _expire_water_temp_hp(self, now):
        if self.water_temp_hp_until and now >= self.water_temp_hp_until:
            self.player_hp = min(self.player_hp, self.max_player_hp)
            self.water_temp_hp_until = 0

    def _schedule_next_gift(self, now):
        self.next_gift_time = now + random.randint(GIFT_DROP_MIN_MS, GIFT_DROP_MAX_MS)

    def _maybe_spawn_gift(self, now):
        if not self.next_gift_time:
            self._schedule_next_gift(now)
        if now < self.next_gift_time:
            return
        if self.infinite_mode:
            self.gift_boxes.append(GiftBox())
            self._schedule_next_gift(now)
        else:
            self.next_gift_time = now + 22000
            if not self.gift_boxes:
                weights = {'fire': 25, 'ice': 25, 'heal': 20, 'haste': 15, 'lightning': 15}
                weights.pop(self.last_attack_gift, None)
                box = GiftBox()
                box.kind = random.choices(list(weights), weights=list(weights.values()))[0]
                self.last_attack_gift = box.kind if box.kind in ('fire', 'ice', 'lightning') else None
                self.gift_boxes.append(box)

    def _is_zongzong(self, e):
        return getattr(e, 'is_zongzong', False)

    def _show_immune(self, e, now=None):
        if (e.y + e.h <= 0 if isinstance(e, Enemy) else e.y < Enemy.ENTRY_DAMAGE_Y):
            return True
        if self.infinite_mode and self._is_zongzong(e):
            now = config.game_ticks() if now is None else now
            if now < getattr(e, 'immune_text_until', 0):
                return True
            e.show_immune(now)
            self._spawn_hit_effect(e.x, e.y + e.h // 2, (255, 230, 150), False)
            self._play_skill_hit_sound(now)
            return True
        return False

    def _handle_bullet_gift_hit(self, b, now):
        br = b.rect()
        for box in self.gift_boxes[:]:
            if br.colliderect(box.rect()):
                self.gift_boxes.remove(box)
                self._open_gift_box(box, now)
                if b in self.bullets:
                    self.bullets.remove(b)
                return True
        return False

    def _open_gift_box(self, box, now):
        self.explosions.append(Explosion(box.x, box.y, (255, 215, 80), 26))
        self.particles.append(Particle(box.x, box.y, (255, 235, 130), 22))
        labels = {
            'lightning': ('闪电礼包', (255, 60, 45)),
            'fire': ('火弹礼包', (255, 120, 45)),
            'ice': ('冰弹礼包', (70, 150, 245)),
            'heal': ('血包礼包', (120, 255, 135)),
            'haste': ('极速礼包', (255, 215, 90)),
        }
        label, color = labels.get(box.kind, ('大礼包', (255, 235, 150)))
        self.gift_messages.append((f'礼包：{label}', color, now + 3000, now))
        if box.kind == 'lightning':
            self.gift_lightning_remaining = 3 if self.infinite_mode else 2
            self.gift_lightning_next = now
            self.gift_lightning_icon_until = now + self.gift_lightning_remaining * 3000
            play_sound('lightning')
        elif box.kind == 'fire':
            self.gift_fire_until = now + (GIFT_BUFF_MS if self.infinite_mode else 7000)
            self.gift_ice_until = 0
            play_sound('fire_cast')
        elif box.kind == 'ice':
            self.gift_ice_until = now + GIFT_BUFF_MS
            self.gift_fire_until = 0
            play_sound('ice_cast')
        elif box.kind == 'heal':
            self._heal_player(1)
            play_sound('coin')
        elif box.kind == 'haste':
            for p in self.players:
                p.gift_speed_until = now + GIFT_BUFF_MS
            play_sound('level_up')

    def _nearby_lightning_targets(self, x, y):
        targets = self.enemies[:]
        if self.boss and self.boss.entered:
            targets.append(self.boss)
        reach = min(280, config.SCREEN_HEIGHT * .55)
        def point(target):
            if isinstance(target, OrochiBoss):
                return target.lightning_target(x, y)
            return target.x, target.y + target.h // 2
        targets = [e for e in targets if e.y + e.h > 0 and math.dist(point(e), (x, y)) <= reach
                   and (not isinstance(e, OrochiBoss) or e.hitboxes())]
        return sorted(targets, key=lambda e: math.dist(point(e), (x, y)))

    def _maybe_fire_gift_lightning(self, now):
        if (self.gift_lightning_remaining <= 0 or now < self.gift_lightning_next
                or now >= self.gift_lightning_icon_until):
            return
        x, y = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2
        targets = self._nearby_lightning_targets(x, y)[:5 if self.infinite_mode else 3]
        if not targets:
            return
        self.gift_lightning_remaining -= 1
        self.gift_lightning_next = now + 3000
        damage = GIFT_LIGHTNING_DAMAGE * self._gift_damage_mult(now) if self.infinite_mode else 3
        self.lightnings.append(Lightning(x, y, targets, damage, gift=True))
        if not self.gift_lightning_remaining:
            self.gift_lightning_icon_until = now + self.lightnings[-1].lifetime
        play_sound('lightning')

    def _update_lightnings(self, now):
        self.lightnings[:] = [bolt for bolt in self.lightnings if not bolt.is_expired()]
        for bolt in self.lightnings[:]:
            if not bolt.damage or now < bolt.spawn_time + bolt.TRAVEL_MS:
                continue
            damage, bolt.damage = bolt.damage, 0
            for target in bolt.targets:
                boss = target is self.boss
                if not boss and target not in self.enemies:
                    continue
                if self._show_immune(target, now):
                    continue
                amount = 2 if boss and bolt.gift and not self.infinite_mode else damage
                if isinstance(target, OrochiBoss):
                    hitbox = target.lightning_hitbox(bolt.start_x, bolt.start_y)
                    if hitbox is None:
                        continue
                    target.hit_by('sniper', amount, hit_rect=hitbox)
                    x, y = hitbox.center
                else:
                    target.hit_by('sniper', amount)
                    x, y = target.x, target.y + target.h // 2
                self._spawn_hit_effect(x, y, (255, 95, 45), boss or target.is_large)
                self._play_skill_hit_sound(now)
                if boss:
                    if self._settle_boss_if_killed():
                        return
                elif target.is_killed('sniper'):
                    self._kill_enemy(target)
                    if self.state not in (GameState.PLAYING, GameState.BOSS_FIGHT):
                        return

    def _explode_enemy_bomb(self, p, now):
        self.explosions.append(Explosion(p.x, p.y, (255, 95, 35), 34))
        self.particles.append(Particle(p.x, p.y, (255, 210, 80), 26))
        radius = getattr(p, 'explode_radius', 72)
        hit_player = None
        for player in self.players:
            pr = player.rect()
            closest_x = max(pr.left, min(p.x, pr.right))
            closest_y = max(pr.top, min(p.y, pr.bottom))
            if math.hypot(p.x - closest_x, p.y - closest_y) <= radius:
                hit_player = player
                break
        if hit_player and not self._player_is_invincible(now):
            self._apply_niu_ice_axe_effect(p, hit_player, now)
            return self._damage_player(now, getattr(p, 'damage', 1),
                                       getattr(p, 'blast_reason', '被小粽粽炸弹击败！'), hit_feedback=True)
        return False

    def _apply_niu_ice_axe_effect(self, projectile, player, now):
        if (isinstance(self.boss, NiuBoss) and isinstance(projectile, ReturningAxe)
                and not projectile.red and not self._player_is_invincible(now)):
            freeze = 1000 if self.infinite_mode else (0, 300, 500)[self._campaign_tier()]
            player.niu_freeze_until = max(player.niu_freeze_until, now + freeze)
            player.niu_slow_until = max(player.niu_slow_until, now + (3000 if self.infinite_mode else 1500))

    def _gift_damage_mult(self, now):
        if now >= self.gift_fire_until:
            return 1.0
        return 2.0 if self.infinite_mode else 1.25

    def _blocked_by_fire_wall(self, rect, wall_rects=None):
        wall_rects = wall_rects if wall_rects is not None else [fw.rect() for fw in self.fire_walls]
        return any(rect.colliderect(fr) for fr in wall_rects)

    def _block_enemy_with_fire_walls(self, e, wall_rects=None):
        if e.temple_kind == 'rift':
            return
        er = e.rect()
        wall_rects = wall_rects if wall_rects is not None else [fw.rect() for fw in self.fire_walls]
        for fr in wall_rects:
            if er.colliderect(fr):
                e.y = fr.top - e.h
                return

    def _pull_projectiles_to_storms(self, projectiles):
        now = config.game_ticks()
        for p in projectiles[:]:
            if getattr(p, 'unblockable', False) or getattr(p, 'detonate_at', 0):
                continue
            for ms in self.magnetic_storms:
                if not ms.can_pull(now):
                    continue
                if ms.contains_projectile(p):
                    ms.pull_projectile(p)
                    if math.hypot(ms.x - p.x, ms.y - p.y) < 18:
                        projectiles.remove(p)
                    break

    def _blocked_by_ice_floor(self, projectile):
        now = config.game_ticks()
        for ice in self.ice_floors[:]:
            if ice.block_projectile(projectile):
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
                return True
        return False

    def _shatter_ice_floor(self, ice, now):
        if ice in self.ice_floors:
            self.ice_floors.remove(ice)
        self._finish_skill_effect(getattr(ice, 'owner', None), getattr(ice, 'skill_type', None), now)
        sx, sy = ice.x, ice.y
        slow_radius = ice.freeze_radius + 50
        for e in self.enemies[:]:
            if math.hypot(e.x - sx, e.y + e.h // 2 - sy) <= slow_radius:
                if self._show_immune(e, now):
                    continue
                e.apply_slow(now, 3000, 0.5)
        self.particles.append(Particle(sx, sy, (120, 205, 255), 22))
        self.explosions.append(Explosion(sx, sy, (105, 195, 255), 20))

    def _explode_magnetic_storm(self, ms, include_boss=False):
        color = (165, 255, 90)
        explosion = Explosion(ms.x, ms.y, color, 34)
        explosion.shockwave_radius = ms.radius
        self.explosions.append(explosion)
        self.particles.append(Particle(ms.x, ms.y, color, 30))
        for e in self.enemies[:]:
            ex, ey = e.x, e.y + e.h // 2
            dist = math.hypot(ex - ms.x, ey - ms.y)
            if dist >= ms.radius:
                continue
            if self._show_immune(e):
                continue
            e.hit_by('pistol', (1.0 if self.infinite_mode else 3.0) * self._gift_damage_mult(config.game_ticks()))
            if e.temple_kind != 'rift':
                if dist < 1:
                    dx, dy = 0, -1
                else:
                    dx, dy = (ex - ms.x) / dist, (ey - ms.y) / dist
                force = int(92 * (1 - dist / ms.radius)) + 28
                half_width = e.w // 2
                min_x = max(30, config.GAME_AREA_LEFT + half_width)
                max_x = min(config.SCREEN_WIDTH - 30, config.GAME_AREA_RIGHT - (e.w + 1) // 2)
                e.x = max(min_x, min(max_x, e.x + dx * force))
                e.y = max(-e.h, min(config.GAME_AREA_BOTTOM - e.h, e.y + dy * force))
                e.apply_slow(config.game_ticks(), 900, 0.45)
            self._spawn_hit_effect(ex, ey, color, e.is_large, element='radiation')
            if e.is_killed('pistol'):
                self._kill_enemy(e)
        hitbox = self._boss_hitbox_in_radius(ms.x, ms.y, ms.radius) if include_boss and self.boss else None
        play_sound('storm')
        if hitbox:
            self.boss.hit_by('pistol', (1.0 if self.infinite_mode else 3.0) * self._gift_damage_mult(config.game_ticks()),
                             hit_rect=hitbox)
            self._spawn_hit_effect(*hitbox.center, color, True, element='radiation')
            self._settle_boss_if_killed()

    def _update_magnetic_storms(self, now, include_boss=False):
        for ms in self.magnetic_storms[:]:
            if ms.should_explode(now):
                ms.exploded = True
                self._explode_magnetic_storm(ms, include_boss)
                if ms in self.magnetic_storms:
                    self.magnetic_storms.remove(ms)
                    self._finish_skill_effect(getattr(ms, 'owner', None), getattr(ms, 'skill_type', None), now)
                continue
            if ms.is_expired():
                self.magnetic_storms.remove(ms)
                self._finish_skill_effect(getattr(ms, 'owner', None), getattr(ms, 'skill_type', None), now)
                continue
            damage_now = ms.can_damage(now)
            hitbox = self._boss_hitbox_in_radius(ms.x, ms.y, ms.radius) if include_boss and damage_now and self.boss else None
            if hitbox:
                self.boss.hit_by('pistol', 0.75 * self._gift_damage_mult(now), hit_rect=hitbox)
                self._spawn_hit_effect(*hitbox.center, (165, 255, 90), True, element='radiation')
                self._play_skill_hit_sound(now)
                if self._settle_boss_if_killed():
                    return
            for e in self.enemies[:]:
                if ms.contains(e):
                    if self._show_immune(e, now):
                        continue
                    if e.temple_kind != 'rift' and ms.can_pull(now):
                        ms.pull(e)
                    if damage_now:
                        e.hit_by('pistol', 0.5 * self._gift_damage_mult(now))
                        self._spawn_hit_effect(*e.rect().center, (165, 255, 90), e.is_large, element='radiation')
                        self._play_skill_hit_sound(now)
                        if e.is_killed('pistol'):
                            self._kill_enemy(e)

    def _boss_hitbox_in_radius(self, x, y, radius):
        if not self.boss:
            return None
        for br in self.boss.hitboxes():
            closest_x = max(br.left, min(x, br.right))
            closest_y = max(br.top, min(y, br.bottom))
            if math.hypot(x - closest_x, y - closest_y) <= radius:
                return br
        return None

    def _skill_cooldown(self, campaign_ms, legacy_ms):
        if self.infinite_mode:
            return legacy_ms // 2
        factor = (0.90, 1.00, 1.15)[self._campaign_tier()]
        if self.difficulty and self.difficulty.name == '自定义':
            factor = self.difficulty.skill_cd_mult
        return round(campaign_ms * factor)

    def _activate_skill(self, sk, player=None):
        player = player or self.player
        now = config.game_ticks()
        base_cooldowns = {'fire_wall': 7000, 'fireball': 9000, 'ice_floor': 6000, 'ice_balls': 9000,
                          'lightning': 7000, 'magnetic_storm': 12000, 'water_heal': 12000,
                          'water_boost': 12000}
        cd_ms = self._skill_cooldown(base_cooldowns[sk.skill_type], sk.cooldown_ms)
        if not self._skill_ready(player, sk.skill_type, now): return
        px, py = player.x, player.y - 28
        st = sk.skill_type
        if st == 'fire_wall':
            lifetime = 2500 if self.infinite_mode else 4000
            fw = FireWall(px, max(100, py - 40), lifetime)
            fw.owner = player; fw.skill_type = st
            self._start_skill_effect(player, st, cd_ms, lifetime, now)
            self.fire_walls.append(fw)
            play_sound('fire_cast')
        elif st == 'fireball':
            self._start_skill_effect(player, st, cd_ms, 2500, now)
            cast_damage = {} if not self.infinite_mode else None
            shot_speed = 7
            for angle in (-32, 0, 32):
                shot = SkillProjectile(px, py, angle, shot_speed, 'fireball', piercing=True, owner=player, skill_type=st)
                shot.cast_damage = cast_damage
                self.skill_projectiles.append(shot)
            for angle in (-16, 16):
                self.skill_projectiles.append(SkillProjectile(
                    px, py, angle, shot_speed, 'fire_rocket', owner=player, skill_type=st))
            play_sound('fire_cast')
        elif st == 'ice_floor':
            ice = IceFloor(px, py)
            ice.owner = player; ice.skill_type = st
            self._start_skill_effect(player, st, cd_ms, 8000 if self.infinite_mode else 5000, now)
            self.ice_floors.append(ice)
            play_sound('ice_cast')
        elif st == 'ice_balls':
            self._start_skill_effect(player, st, cd_ms, 2500, now)
            cast_damage = {} if not self.infinite_mode else None
            for angle in (-56, -40, -24, -8, 8, 24, 40, 56):
                shot = SkillProjectile(px, py, angle, 6, 'ice_ball', owner=player, skill_type=st)
                shot.cast_damage = cast_damage
                self.skill_projectiles.append(shot)
            play_sound('ice_cast')
        elif st == 'lightning':
            targets = self._nearby_lightning_targets(px, py)[:5 if self.infinite_mode else 4]
            if targets:
                bolt = Lightning(px, py, targets, 2.0 * self._gift_damage_mult(now))
                self._start_skill_effect(player, st, cd_ms, bolt.lifetime, now)
                self.lightnings.append(bolt)
                play_sound('lightning')
        elif st == 'magnetic_storm':
            ms = MagneticStorm(px, max(120, player.y - 170))
            ms.owner = player; ms.skill_type = st
            self._start_skill_effect(player, st, cd_ms, 3000, now)
            self.magnetic_storms.append(ms)
            play_sound('storm')
        elif st == 'water_heal':
            self._start_skill_effect(player, st, cd_ms, 5000 if self.infinite_mode else 0, now)
            if self.player_hp >= self.max_player_hp:
                self._heal_player(1, temporary_ms=15000 if self.infinite_mode else 8000)
            else:
                self._heal_player(1)
            if self.infinite_mode:
                player.water_haste_until = now + 5000
            self.player_invincible_until = max(self.player_invincible_until, now + (2000 if self.infinite_mode else 800))
            self.water_heal_effects.append((player, now))
            play_sound('water_cast')
        elif st == 'water_boost':
            duration = 10000 if self.infinite_mode else 6000
            self._start_skill_effect(player, st, cd_ms, duration, now)
            for target in self.players:
                target.water_boost_until = now + duration
            play_sound('level_up')

    def _activate_radiation_laser(self, player=None):
        now = config.game_ticks()
        cd_mult = self.difficulty.skill_cd_mult if self.difficulty else 1.0
        self._expire_radiation_lasers(now, cd_mult)
        candidates = (player,) if player else self.players
        for player in candidates:
            if player.character != 'radiation' or now < player.geyser_lift_until:
                continue
            active = next((laser for laser in self.radiation_lasers if laser.owner is player and not laser.is_expired(now)), None)
            if active:
                active.whip(now)
                play_sound('laser')
                return
            skill_type = 'radiation_laser'
            cd_ms = self._skill_cooldown(14000, 12000)
            if now < player.skill_cooldowns.get(skill_type, 0):
                return
            player.animation_skill = 'radiation_laser'
            player.animation_skill_at = now
            laser = RadiationLaser(player, 5000 if self.infinite_mode else 4000)
            laser.muzzle_effect = random.randrange(len(laser.MUZZLE_COLORS))
            if not self.infinite_mode:
                laser.damage_interval = 500
            laser.cooldown_ms = cd_ms
            self.radiation_lasers.append(laser)
            self._flash_skill(player, now)
            play_sound('laser')
            return

    def _activate_dart_shield(self, player):
        """辐射工程师 R 技能：8 个齿纹飞盘环绕自身 5 秒，结束后向外飞出。"""
        if not player or player.character != 'radiation':
            return
        now = config.game_ticks()
        skill_type = 'dart_shield'
        if now < player.geyser_lift_until or not self._skill_ready(player, skill_type, now):
            return
        if any(s.owner is player and not s.is_gone(now) for s in self.dart_shields):
            return
        cd_ms = self._skill_cooldown(14000, 20000)
        duration = 5000 if self.infinite_mode else 3000
        self._start_skill_effect(player, skill_type, cd_ms, duration, now)
        self.dart_shields.append(SpinningDarts(player, duration))
        play_sound('dart_cast')

    # ═══ Update ═══════════════════════════════════════════════════════════════
    def update(self):
        now = config.game_ticks()
        if self.state == GameState.VICTORY:
            self._update_combat_effects()
            if now >= self.victory_end:
                self.reset()
                start_music()
            return
        if self.state == GameState.INFINITE_COUNTDOWN:
            if pygame.time.get_ticks() >= self.infinite_countdown_end:
                self.player_invincible_until = now + REVIVE_INVINCIBILITY_MS
                self.state = self.infinite_resume_state
            return
        if self.state in (GameState.PLAYING, GameState.BOSS_FIGHT) and not self._whale_is_swallowing():
            for player in self.players:
                player.update_geyser_lift(now)
        if self.infinite_mode or self.state in (GameState.PLAYING, GameState.BOSS_FIGHT):
            self._expire_active_skills(now)
            self._maybe_fire_gift_lightning(now)
            self._update_lightnings(now)
        if self.state == GameState.LEVEL_TRANSITION:
            self._update_combat_effects()
            if now >= self.level_transition_end:
                background = self.scrolling_background(self.bg.get_size())
                self.bg_transition_prev = (background if background is not None else self.bg).copy()
                self.bg_transition_until = now + BG_FADE_MS
                self._start_level(self.current_level+1)
                if self.state != GameState.BOSS_FIGHT:
                    self.state = GameState.PLAYING
            return
        if self.state == GameState.PLAYING and self.difficulty and not self._boss_starts_immediately():
            self.background_scroll_ticks += 1
            if self.background_scroll_ticks >= BACKGROUND_SCROLL_TICKS:
                if self.infinite_mode:
                    self._trigger_infinite_boss()
                else:
                    self._trigger_boss()
                return
        elif (self.state == GameState.BOSS_FIGHT and self._scrolls_background()
              and self._boss_starts_immediately() and self.background_scroll_ticks < BACKGROUND_SCROLL_TICKS):
            self.background_scroll_ticks += 1
        if self.state == GameState.PLAYING: self._update_playing(now)
        elif self.state == GameState.BOSS_FIGHT: self._update_boss_fight(now)

    def _nearest_player(self, x, y=None):
        if y is None:
            return min(self.players, key=lambda player: abs(player.x - x))
        return min(self.players, key=lambda player: math.hypot(player.x - x, player.y - y))

    def _hit_player(self, rect):
        for player in self.players:
            if rect.colliderect(player.rect()):
                return player
        return None

    def _hit_by_projectile(self, projectile):
        """Use the same precise telegraph/ring/beam collision in every runtime."""
        hits_rect = getattr(projectile, 'hits_rect', None)
        if hits_rect is None:
            return self._hit_player(projectile.rect())
        hit_players = getattr(projectile, '_hit_players', ())
        return next((player for player in self.players
                     if player not in hit_players and hits_rect(player.rect())), None)

    def _player_is_invincible(self, now):
        return now < self.player_invincible_until

    def _damage_player(self, now, amount, reason, *, hit_feedback=False):
        if self._player_is_invincible(now):
            return False
        self.player_hp -= amount
        if amount > 0:
            self.player.animation_hit_at = now
        if hit_feedback and amount > 0:
            self.player_hit_impact = (pygame.time.get_ticks(), self.player.rect().center)
            play_sound('player_hit')
        self.player_invincible_until = now + (650 if self.infinite_mode else (850, 650, 550)[self._campaign_tier()])
        if self.player_hp <= 0:
            self._player_defeated(reason)
            return True
        return False

    def _resolve_leak(self, enemy, now):
        reason = f'{enemy.edef["name"]} 入侵成功！'
        self.enemies.remove(enemy)
        self.leak_count += 1
        damage = 1 if self.infinite_mode else (1, 1, 2)[self._campaign_tier()]
        return self._damage_player(now, damage, reason)

    def _enemy_contact_damage(self, e):
        if not e.is_large:
            return 1
        return 2 if self.infinite_mode else (1, 2, 2)[self._campaign_tier()]

    def _play_contact_impact(self, player, contact, *, heavy=False):
        x, y = player.rect().clip(contact).center
        self._spawn_hit_effect(x, y, (255, 100, 55), heavy)
        play_sound('player_hit')

    def _damage_player_on_contacts(self, now):
        for e in self.enemies[:]:
            if e.temple_kind == 'rift':
                continue
            if now - e.last_contact_damage_time < CONTACT_DAMAGE_COOLDOWN:
                continue
            contact = e.rect()
            if not self._player_is_invincible(now) and self._hit_player(contact):
                e.last_contact_damage_time = now
                amount = self._enemy_contact_damage(e)
                self._play_contact_impact(self.player, contact, heavy=e.is_large)
                if self._damage_player(now, amount, f'被{e.edef["name"]}撞击击败！'):
                    return True
        if (self.boss and not (self.boss.signature and self.boss.signature.origin is not None)
                and not (isinstance(self.boss, OrochiBoss) and self.boss.skill in ('split', 'storm', 'laser'))
                and any(self._hit_player(br) for br in self.boss.hitboxes())
                and not self._player_is_invincible(now)):
            contact = next(rect for rect in self.boss.hitboxes() if self._hit_player(rect))
            self._play_contact_impact(self.player, contact, heavy=True)
            self.player.move(0, contact.bottom - self.player.rect().top + 2)
            return self._damage_player(now, 2, f'被{self.boss.name}撞击击败！')
        return False

    def _skill_projectile_damage(self, projectile, target, now):
        damage = projectile.damage * self._gift_damage_mult(now)
        ledger = getattr(projectile, 'cast_damage', None)
        if ledger is None:
            return damage
        cap = 4 if projectile.ptype == 'fireball' else 2
        dealt = ledger.get(target, 0)
        damage = min(damage, cap - dealt)
        ledger[target] = dealt + damage
        return damage

    def _hit_enemy_with_fireball(self, sp, e, now):
        if id(e) in sp.hit_targets:
            return
        if self._show_immune(e, now):
            sp.hit_targets.add(id(e))
            return
        e.hit_by('sniper', self._skill_projectile_damage(sp, e, now))
        sp.hit_targets.add(id(e))
        sp.damage *= 0.7
        if not e.burning:
            e.burning = True; e.burn_start = now; e.last_burn_tick = now
        e.burn_damage = self.infinite_mode
        self._spawn_hit_effect(sp.x, sp.y, (255, 130, 35), e.is_large, element='fire')
        self._play_skill_hit_sound(now)
        if e.is_killed('sniper'):
            self._kill_enemy(e)

    def _hit_boss_with_fireball(self, sp):
        if not self.boss or id(self.boss) in sp.hit_targets:
            return
        self.boss.hit_by('sniper', self._skill_projectile_damage(sp, self.boss, config.game_ticks()), hit_rect=sp.rect())
        sp.hit_targets.add(id(self.boss))
        sp.damage *= 0.7
        self._spawn_hit_effect(sp.x, sp.y, (255, 150, 60), True, element='fire')
        self._play_skill_hit_sound(config.game_ticks())
        self._settle_boss_if_killed()

    def _explode_fire_rocket(self, sp, now, include_boss=False):
        radius = 44
        damage = sp.damage * self._gift_damage_mult(now)
        self.explosions.append(Explosion(sp.x, sp.y, (255, 123, 36), 16, element='fire'))
        for enemy in self.enemies[:]:
            rect = enemy.rect()
            x = max(rect.left, min(sp.x, rect.right))
            y = max(rect.top, min(sp.y, rect.bottom))
            if math.hypot(x - sp.x, y - sp.y) <= radius and not self._show_immune(enemy, now):
                enemy.hit_by('sniper', damage)
                self._spawn_hit_effect(x, y, (255, 123, 36), enemy.is_large, element='fire')
                if enemy.is_killed('sniper'):
                    self._kill_enemy(enemy)
        if include_boss and self.boss:
            hitbox = self._boss_hitbox_in_radius(sp.x, sp.y, radius)
            if hitbox:
                self.boss.hit_by('sniper', damage, hit_rect=hitbox)
                self._spawn_hit_effect(*hitbox.center, (255, 123, 36), True, element='fire')
                self._settle_boss_if_killed()
        play_sound('hit')

    def _explode_grenade(self, sp, include_boss=False):
        self.explosions.append(Explosion(sp.x, sp.y, (120, 145, 80), 26))
        self.particles.append(Particle(sp.x, sp.y, (225, 210, 130), 18))
        for e in self.enemies[:]:
            if math.hypot(e.x - sp.x, e.y + e.h // 2 - sp.y) <= FISHER_GRENADE_RADIUS:
                if self._show_immune(e):
                    continue
                e.hit_by('pistol', FISHER_GRENADE_DAMAGE * self._gift_damage_mult(config.game_ticks()))
                self._spawn_hit_effect(e.x, e.y + e.h // 2, (225, 210, 130), e.is_large)
                if e.is_killed('pistol'):
                    self._kill_enemy(e)
        if include_boss and self.boss:
            boss_hitbox = self._boss_hitbox_in_radius(sp.x, sp.y, FISHER_GRENADE_RADIUS)
            if boss_hitbox:
                self.boss.hit_by('pistol', (FISHER_GRENADE_DAMAGE if self.infinite_mode else 2) * self._gift_damage_mult(config.game_ticks()),
                                 hit_rect=boss_hitbox)
                self._spawn_hit_effect(sp.x, sp.y, (225, 210, 130), True)
                self._settle_boss_if_killed()
        play_sound('hit')

    def _move_player_from_controls(self, player, keys, now):
        if now < max(player.niu_freeze_until, player.geyser_lift_until):
            return
        dx, dy = self.mobile_controls.axis
        if self.desktop_controls:
            key_dx = self._key_pressed(keys, 'p1_right') - self._key_pressed(keys, 'p1_left')
            key_dy = self._key_pressed(keys, 'p1_down') - self._key_pressed(keys, 'p1_up')
            if key_dx or key_dy:
                dx, dy = key_dx, key_dy
        speed = self._player_speed(player, now)
        player.move(dx * speed, dy * speed)

    def _mobile_fire_active(self):
        return self.mobile_controls.auto_fire or self.mobile_controls.is_pressed('attack')

    def _infinite_density(self, now):
        if not self.infinite_mode:
            return 1
        limit = 7 if self.infinite_background_level in (9, 10) else 12
        return min(limit, 4 + self.infinite_boss_index // 3)

    def _infinite_health_mult(self, now):
        return 1.0 + 0.2 * min(self.infinite_boss_index // len(config.INFINITE_BOSS_HP), 6)

    def _infinite_damage_mult(self):
        return 1.0

    def _expire_radiation_lasers(self, now, cd_mult=None):
        if cd_mult is None:
            cd_mult = self.difficulty.skill_cd_mult if self.difficulty else 1.0
        for laser in self.radiation_lasers[:]:
            if not laser.is_expired(now):
                continue
            cd_ms = getattr(laser, 'cooldown_ms', int(12000 * (0.5 if self.infinite_mode else cd_mult)))
            laser.owner.skill_display_duration['radiation_laser'] = cd_ms
            laser.owner.skill_cooldowns['radiation_laser'] = now + cd_ms
            self.radiation_lasers.remove(laser)

    def _update_dart_shields(self, now):
        """飞盘环绕：持续伤害触碰的敌人；5秒结束后向外飞出继续伤害，全部离屏后进入CD。"""
        for shield in self.dart_shields[:]:
            shield.update()
            if shield.is_gone(now):
                self.dart_shields.remove(shield)
                self._finish_skill_effect(shield.owner, 'dart_shield', now)
                continue
            if not shield.released and shield.is_expired(now):
                shield.release(now)
                play_sound('dart_burst')
                continue
            for e in self.enemies[:]:
                if shield.hits(e.rect(), now) and shield.can_damage(e, now):
                    if self._show_immune(e, now):
                        continue
                    e.hit_by('sniper', 0.45 * self._gift_damage_mult(now))
                    self._spawn_hit_effect(e.x, e.y + e.h // 2, (180, 60, 80), e.is_large, element='radiation')
                    self._play_skill_hit_sound(now)
                    if e.is_killed('sniper'):
                        self._kill_enemy(e)
                        if self.state not in (GameState.PLAYING, GameState.BOSS_FIGHT):
                            break
            boss_hitbox = next((br for br in self.boss.hitboxes() if shield.hits(br, now)), None) if self.boss else None
            if boss_hitbox and shield.can_damage(self.boss, now):
                previous_hp = self.boss.hp
                self.boss.hit_by('sniper', 0.45 * self._gift_damage_mult(now), hit_rect=boss_hitbox)
                if self.boss.hp < previous_hp:
                    self.boss.apply_slow(now, 300, 0.9)
                self._spawn_hit_effect(*boss_hitbox.center, (180, 60, 80), True, element='radiation')
                self._play_skill_hit_sound(now)
                if self._settle_boss_if_killed():
                    return

    def _blocked_by_dart_shield(self, rect, now):
        """敌方子弹被旋转飞镖抵挡。"""
        for shield in self.dart_shields:
            if shield.hits(rect, now):
                return shield
        return None

    def _update_radiation_lasers(self, now):
        self._expire_radiation_lasers(now)
        for laser in self.radiation_lasers[:]:
            lr = laser.rect()
            for e in self.enemies[:]:
                if lr.colliderect(e.rect()) and laser.can_damage(e, now):
                    if self._show_immune(e, now):
                        continue
                    e.hit_by('sniper', (0.45 if self.infinite_mode else 1.0) * self._gift_damage_mult(now))
                    laser.push(e)
                    self._spawn_hit_effect(e.x, e.y + e.h // 2, (120, 255, 120), e.is_large, element='radiation')
                    self._play_laser_hit_sound(now)
                    if e.is_killed('sniper'):
                        self._kill_enemy(e)
                        if self.state not in (GameState.PLAYING, GameState.BOSS_FIGHT):
                            return
            if self.boss and self.boss.collides(lr) and laser.can_damage(self.boss, now):
                previous_hp = self.boss.hp
                self.boss.hit_by('sniper', (0.35 if self.infinite_mode else 1.0) * self._gift_damage_mult(now), hit_rect=lr)
                if self.boss.hp < previous_hp:
                    self.boss.apply_slow(now, 600, 0.85)
                self._spawn_hit_effect(self.boss.x, self.boss.y + self.boss.h // 2, (190, 70, 255), True, element='radiation')
                # 激光命中 Boss：灼烧冲击特效 + 音效（节流）
                impact_x = self.boss.x + random.randint(-24, 24)
                impact_y = self.boss.y + self.boss.h // 2 + random.randint(-14, 22)
                self.laser_impacts.append((impact_x, impact_y, now))
                self._play_laser_hit_sound(now)
                if self._settle_boss_if_killed():
                    return

    def _shoot(self, now, player=None):
        player = player or self.player
        if not player.current_weapon:
            return False
        wkey = player.current_weapon; cost = self._bullet_cost(wkey)
        if cost > self.player.gold:
            player.current_weapon = 'pistol'
            self.gift_messages.append(('金币不足，已切回手枪', GOLD_COLOR, now + 2200, now))
            return False
        self.player.gold -= cost
        shots = player.shoot(now)
        for b in shots:
            b.source_player = player
            if not self.infinite_mode:
                b.damage = config.CAMPAIGN_BULLET_DAMAGE[wkey]
            elif wkey == 'rifle':
                b.damage = 1.3
            if now < self.gift_fire_until:
                b.gift_kind = 'fire'
                b.radius = 6
            elif now < self.gift_ice_until:
                b.gift_kind = 'ice'
                b.radius = 6
                if self.infinite_mode:
                    b.damage = 2.2
        self.bullets.extend(shots)
        self.muzzle_flashes.append((player, now, wkey))
        play_sound(f'shoot_{wkey}')
        return True

    def _apply_bullet_passive(self, e, b, now):
        damage = b.damage
        if self.infinite_mode and b.weapon_name == 'shotgun':
            damage *= 0.5
        if b.character == 'fire':
            damage *= 1.5 if self.infinite_mode else 1.2
            if not e.burning:
                e.burning = True; e.burn_start = now; e.last_burn_tick = now
                e.burn_damage = False
        elif b.character == 'ice':
            duration, multiplier = (4000, 0.7) if self.infinite_mode else (2500, 0.75)
            e.apply_slow(now, duration, multiplier)
            e.snowflake_until = now + 900
        elif b.character == 'water':
            e.water_mark_until = now + 900
        elif b.character == 'radiation':
            e.infected = True
            e.infected_weapon = b.weapon_name
        if getattr(b, 'gift_kind', None) == 'ice' and self.infinite_mode:
            e.frozen = True
            e.frozen_until = now + 2000
        shooter = getattr(b, 'source_player', self.player)
        if self.infinite_mode and now < shooter.water_boost_until:
            damage *= 1.5
        damage *= self._gift_damage_mult(now)
        e.hit_by(b.weapon_name, damage)
        if not self.infinite_mode and getattr(b, 'gift_kind', None) == 'ice':
            e.apply_slow(now, 2500, 0.75)
            if not e.is_large and not e.is_zongzong and not e.frozen:
                e.frozen = True
                e.frozen_until = now + 800

    def _bullet_hit_color(self, b):
        if getattr(b, 'gift_kind', None) == 'fire':
            return (255, 105, 35)
        if getattr(b, 'gift_kind', None) == 'ice':
            return (45, 115, 230)
        return WEAPON_DEFS[b.weapon_name].color

    def _character_cost(self, cdef):
        key = next(key for key, item in CHARACTER_DEFS.items() if item is cdef)
        price = config.CAMPAIGN_CHARACTER_PRICES[key][self._campaign_tier()]
        if self.difficulty and self.difficulty.name == '自定义':
            price *= self.difficulty.character_cost_mult
        return math.ceil(price)

    def _update_playing(self, now):
        if self.desktop_controls:
            # Refresh held keys during catch-up updates without draining queued events.
            pygame.event.pump()
        keys = pygame.key.get_pressed()
        self._move_player_from_controls(self.player, keys, now)
        self._expire_water_temp_hp(now)
        if (self._mobile_fire_active() or self._key_pressed(keys, 'p1_shoot')) and self.player.can_shoot(now):
            self._shoot(now, self.player)
        if now - self.last_spawn_time >= self.spawn_interval:
            if self.infinite_mode:
                if sum(not enemy.temple_kind for enemy in self.enemies) < self._infinite_density(now):
                    self.spawn_enemy()
                self.last_spawn_time = now
            elif sum(not e.temple_kind for e in self.enemies) < self._campaign_value(config.CAMPAIGN_ENEMY_CAP):
                self.spawn_enemy()
                self.last_spawn_time = now
        self._maybe_spawn_gift(now)
        factory = self._is_factory_stage()
        if factory:
            self._settle_factory_link(now)
            self._start_factory_link(now)
        fire_wall_rects = [fw.rect() for fw in self.fire_walls]
        for b in self.bullets[:]:
            b.update()
            if b.is_offscreen(): self.bullets.remove(b)
        self._update_temple_enemies(now)
        speed_multiplier = self._enemy_speed_multiplier()
        for e in self.enemies[:]:
            target = self._nearest_player(e.x, e.y) if e.chase_color is not None or e.temple_kind == 'worm' else None
            previous_burn_hits = e.burn_hits
            e.update(target, speed_multiplier=speed_multiplier)
            if e.burn_hits > previous_burn_hits:
                self._spawn_hit_effect(*e.rect().center, (255, 130, 35), e.is_large, element='fire')
                self._play_skill_hit_sound(now)
            self._block_enemy_with_fire_walls(e, fire_wall_rects)
            if self._enemy_can_attack(e, now):
                self.enemy_projectiles.extend(self._enemy_shots(e, now))
            if e.reached_bottom() and self._resolve_leak(e, now):
                return
        if self._damage_player_on_contacts(now):
            return
        self._pull_projectiles_to_storms(self.enemy_projectiles)
        for ep in self.enemy_projectiles[:]:
            target = self._nearest_player(ep.x, ep.y)
            ep.update(target_x=target.x, target_y=target.y)
            if not ep.alive:
                if getattr(ep, 'bomb', False) and self._explode_enemy_bomb(ep, now):
                    return
                self.enemy_projectiles.remove(ep)
            elif not getattr(ep, 'unblockable', False) and self._blocked_by_fire_wall(ep.rect(), fire_wall_rects):
                self.enemy_projectiles.remove(ep)
            elif not getattr(ep, 'unblockable', False) and self._blocked_by_ice_floor(ep):
                self.enemy_projectiles.remove(ep)
            elif not getattr(ep, 'unblockable', False) and self._blocked_by_dart_shield(ep.block_rect(), now):
                self._spawn_hit_effect(ep.x, ep.y, (140, 255, 150), False)
                self.enemy_projectiles.remove(ep)
            elif getattr(ep, 'bomb', False) and self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._explode_enemy_bomb(ep, now): return
            elif self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._damage_player(now, 1, '被怪物子弹击败！', hit_feedback=True): return
        for b in self.bullets[:]:
            br = b.rect()
            if self._handle_bullet_gift_hit(b, now):
                continue
            for e in self.enemies[:]:
                if (e.y + e.h <= 0 or br.right < e.x - e.w // 2 or br.left > e.x + e.w // 2 or
                        br.bottom < e.y or br.top > e.y + e.h):
                    continue
                if id(e) not in b.hit_targets and br.colliderect(e.rect()):
                    self._apply_bullet_passive(e, b, now); b.hit_targets.add(id(e)); play_sound('hit')
                    self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), e.is_large, element=b.gift_kind or b.character)
                    if e.is_killed(b.weapon_name):
                        self._kill_enemy(e)
                        if self.state != GameState.PLAYING:
                            break
                    if b.weapon_name == 'sniper':
                        b.damage *= 0.7 if self.infinite_mode else 0.65
                    else:
                        if b in self.bullets: self.bullets.remove(b)
                        break
            if self.state != GameState.PLAYING:
                return
        for sp in self.skill_projectiles[:]:
            sp.update()
            if not sp.alive or sp.is_offscreen():
                if sp.ptype == 'grenade':
                    self._explode_grenade(sp)
                    self._remove_skill_projectile(sp, now)
                    continue
                if sp.ptype == 'fireball' and sp.piercing and not sp.is_offscreen():
                    for e in self.enemies[:]:
                        if math.hypot(e.x-sp.x, e.y+e.h//2-sp.y) < 80:
                            self._hit_enemy_with_fireball(sp, e, now)
                    self.particles.append(Particle(sp.x, sp.y, (255, 160, 40), 15))
                self._remove_skill_projectile(sp, now); continue
            sr = sp.rect()
            for e in self.enemies[:]:
                if (e.y + e.h <= 0 or sr.right < e.x - e.w // 2 or sr.left > e.x + e.w // 2 or
                        sr.bottom < e.y or sr.top > e.y + e.h):
                    continue
                if sr.colliderect(e.rect()):
                    if sp.ptype == 'grenade':
                        self._explode_grenade(sp)
                        self._remove_skill_projectile(sp, now); break
                    elif sp.ptype == 'fire_rocket':
                        self._remove_skill_projectile(sp, now)
                        self._explode_fire_rocket(sp, now)
                        break
                    elif sp.ptype == 'fireball':
                        self._hit_enemy_with_fireball(sp, e, now)
                        if not sp.piercing: self._remove_skill_projectile(sp, now); break
                    elif sp.ptype == 'ice_ball':
                        if self._show_immune(e, now):
                            self._remove_skill_projectile(sp, now); break
                        e.hit_by('pistol', self._skill_projectile_damage(sp, e, now))
                        if self.infinite_mode or not e.is_zongzong:
                            e.frozen = True
                            e.frozen_until = now + 4000
                        else:
                            e.apply_slow(now, 2500, 0.75)
                        self._spawn_hit_effect(sp.x, sp.y, (150, 220, 255), e.is_large, element='ice')
                        self._play_skill_hit_sound(now)
                        if e.is_killed('pistol'): self._kill_enemy(e)
                        self._remove_skill_projectile(sp, now); break
        for fw in self.fire_walls[:]:
            if not self.infinite_mode and not fw.is_expired() and fw.can_damage(now):
                contact = fw.rect().inflate(0, 4)
                for enemy in self.enemies[:]:
                    if contact.colliderect(enemy.rect()):
                        enemy.hit_by('pistol', 0.75)
                        self._spawn_hit_effect(*contact.clip(enemy.rect()).center, (255, 105, 35), enemy.is_large, element='fire')
                        self._play_skill_hit_sound(now)
                        if enemy.is_killed('pistol'):
                            self._kill_enemy(enemy)
                hitbox = next((box for box in self.boss.hitboxes() if box.colliderect(contact)), None) if self.boss else None
                if hitbox:
                    self.boss.hit_by('pistol', 0.75, hit_rect=contact)
                    self._spawn_hit_effect(*contact.clip(hitbox).center, (255, 105, 35), True, element='fire')
                    self._play_skill_hit_sound(now)
                    if self._settle_boss_if_killed():
                        return
            if fw.is_expired():
                self.fire_walls.remove(fw)
                self._finish_skill_effect(getattr(fw, 'owner', None), getattr(fw, 'skill_type', None), now)
        for ice in self.ice_floors[:]:
            if not self.infinite_mode and getattr(ice, 'owner', None) and now >= ice.owner.skill_active_until.get('ice_floor', now):
                self.ice_floors.remove(ice)
                self._finish_skill_effect(ice.owner, ice.skill_type, now)
                continue
            ice.update()
            if ice.is_offscreen() or not ice.alive:
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
                else:
                    self.ice_floors.remove(ice)
                    self._finish_skill_effect(getattr(ice, 'owner', None), getattr(ice, 'skill_type', None), now)
                continue
            hit = None
            for e in self.enemies[:]:
                if ice.collides(e): hit = e; break
            if hit:
                hx, hy = hit.x, hit.y + hit.h//2
                if self._show_immune(hit, now):
                    ice.hit(hx)
                    continue
                hit.hit_by('pistol', 0.5 * self._gift_damage_mult(now))
                self._spawn_hit_effect(hx, hy, (150, 220, 255), hit.is_large, element='ice')
                self._play_skill_hit_sound(now)
                for e in self.enemies[:]:
                    if math.hypot(e.x-hx, e.y+e.h//2-hy) < ice.freeze_radius:
                        if self._is_zongzong(e):
                            self._show_immune(e, now)
                            continue
                        e.frozen = True; e.frozen_until = now + 4000
                ice.hit(hx)
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
        self._update_magnetic_storms(now)
        self._pull_projectiles_to_storms(self.enemy_projectiles)
        self._update_radiation_lasers(now)
        self._update_dart_shields(now)
        if self.state != GameState.PLAYING:
            return
        for e in self.enemies[:]:
            w = self.player.current_weapon
            if w and e.is_killed(w): self._kill_enemy(e)
        if factory:
            self._settle_factory_link(now)
        for c in self.coins[:]:
            c.update()
            if self._hit_player(c.rect()):
                self.player.gold += c.value
                play_sound('coin'); self.coins.remove(c)
            elif c.is_offscreen(): self.coins.remove(c)
        for box in self.gift_boxes[:]:
            box.update()
            if box.is_offscreen():
                self.gift_boxes.remove(box)
        self._update_combat_effects()

    def _update_combat_effects(self):
        for p in self.particles[:]:
            p.update()
            if p.is_dead(): self.particles.remove(p)
        for ex in self.explosions[:]:
            ex.update()
            if ex.is_dead(): self.explosions.remove(ex)

    def _update_special_boss_hazards(self, now):
        boss = self.boss
        if isinstance(boss, OrochiBoss):
            self.boss_projectiles.extend(boss.shots)
            boss.shots.clear()
            if boss.impacts:
                play_sound('hit')
                boss.impacts.clear()
            if boss.skill in ('slam', 'split', 'laser', 'storm'):
                age = boss.age(now)
                hit = boss.hazard_strike(age)
                if (boss.hazard_hit != hit and not self._player_is_invincible(now)
                        and any(boss.hazard_hits(player.rect(), age) for player in self.players)):
                    boss.hazard_hit = hit
                    return self._damage_player(now, 2, f'被{boss.name}击败！', hit_feedback=True)
            return False
        if not isinstance(boss, NiuBoss):
            return False
        if boss.shield_break_at is not None and boss.shield_break_at != boss.shield_shards_launched_at:
            self._add_boss_projectiles(boss.launch_shield_shards())
        slam = boss.axe_slam_rect(now)
        strike = (now - boss.axe_slam_start) // boss.AXE_SLAM_CYCLE_MS if slam is not None else -1
        if slam is not None:
            cycle_start = boss.axe_slam_start + strike * boss.AXE_SLAM_CYCLE_MS
            if (now >= cycle_start + boss.AXE_SLAM_LAND_MS
                    and (boss.axe_slam_impact is None or boss.axe_slam_impact[2] < cycle_start)):
                boss.axe_slam_impact = (slam.centerx, slam.bottom, now)
                play_sound('niu_axe_impact')
        if (slam is not None and strike != boss.axe_slam_hit and not self._player_is_invincible(now)
                and self._hit_player(slam)):
            boss.axe_slam_hit = strike
            if self._damage_player(now, 1, '被牛魔王的巨斧击败！', hit_feedback=True):
                return True
        if now >= boss.lightning_warning_until and now >= boss.lightning_next_tick and boss.lightning_rects(now):
            boss.lightning_next_tick = now + 650
            if any(self._hit_player(rect) for rect in boss.lightning_rects(now)):
                if self._damage_player(now, min(2, boss.bdef.get('damage_cap', 2)),
                                       '被牛魔王的雷电击败！', hit_feedback=True):
                    return True
        return False

    def _hazard_warning_ms(self, zones, now, minimum=None):
        """Find a clear lane on either axis, including the player's collision box."""
        tier = self._campaign_tier()
        if minimum is None:
            minimum = (1200, 1000, 850)[tier]
        player = self.player
        body = player.rect()
        if not body.collidelistall(zones):
            return minimum
        left = max(40, config.GAME_AREA_LEFT + body.w // 2)
        right = min(config.SCREEN_WIDTH - 40, config.GAME_AREA_RIGHT - (body.w + 1) // 2)
        bottom = max(80, player.bottom_limit())
        distances = []
        for position, low, high, half_size, blocked in (
            (player.x, left, right, body.w / 2,
             [(zone.left, zone.right) for zone in zones if zone.top < body.bottom and zone.bottom > body.top]),
            (player.y, 80, bottom, body.h / 2,
             [(zone.top, zone.bottom) for zone in zones if zone.left < body.right and zone.right > body.left]),
        ):
            cursor = low
            for start, end in sorted(blocked) + [(high + half_size, high + half_size)]:
                if end + half_size < cursor:
                    continue
                lane_end = min(high, start - half_size)
                if lane_end - cursor >= body.w / 2:
                    # Leave a pixel between the player's collision box and the hazard.
                    destination = max(cursor + 1, min(lane_end - 1, position))
                    distances.append(abs(destination - position))
                cursor = max(cursor, end + half_size)
        if not distances:
            return None
        # A temporary movement buff may expire before the player clears the warning.
        speed = min(self._player_speed(player, now), player.SPEED * 1.3) * config.FPS
        freeze_ms = max(0, player.niu_freeze_until - now)
        reaction_ms = (350, 300, 250)[tier]
        return max(minimum, math.ceil(min(distances) / speed * 1000) + freeze_ms + reaction_ms)

    def _extend_ground_warning(self, boss, now):
        if boss.lightning_warning_until > now:
            fields = ('lightning_warning_until', 'lightning_until', 'lightning_next_tick')
            zones = list(boss.lightning_rects(now))
        else:
            return
        warning = self._hazard_warning_ms(zones, now)
        if warning is None:
            for field in fields:
                setattr(boss, field, now)
            boss.next_hazard_time = now
            return
        extra = max(0, now + warning - getattr(boss, fields[0]))
        for field in (*fields, 'next_hazard_time', 'next_death_laser_time'):
            setattr(boss, field, getattr(boss, field) + extra)

    def _shot_warning_zone(self, shot):
        if isinstance(shot, ReturningAxe):
            radius = shot.explode_radius
            return pygame.Rect(round(shot.target_x - radius), shot.landing_y - radius,
                               radius * 2, radius * 2)
        # Project the shot across the current player's row, including its hit radius.
        body = self.player.rect()
        top = max(shot.y, body.top - shot.r)
        bottom = max(top, body.bottom + shot.r)
        slope = math.tan(math.radians(shot.angle))
        xs = (shot.x + (top - shot.y) * slope, shot.x + (bottom - shot.y) * slope)
        radius = shot.r
        return pygame.Rect(math.floor(min(xs) - radius), 0,
                           math.ceil(abs(xs[0] - xs[1]) + 2 * radius), config.SCREEN_HEIGHT)

    def _queue_boss_shots(self, shots, now):
        if self.infinite_mode or not any(shot.big_fireball or isinstance(shot, (CrescentWave, ReturningAxe))
                                         for shot in shots):
            self._add_boss_projectiles(shots)
            return
        warning = self._hazard_warning_ms([self._shot_warning_zone(shot) for shot in shots], now)
        if warning is None:
            return
        self.warned_boss_shots = shots
        for shot in shots:
            if shot.big_fireball:
                shot.launch_offset = (shot.x - self.boss.x, shot.y - self.boss.y)
        self.warned_boss_shots_at = now + warning
        if self.boss.can_laser():
            self.boss.next_death_laser_time = max(self.boss.next_death_laser_time,
                                                 self.warned_boss_shots_at + 1400)

    def _try_boss_signature(self, now, *, opening=False):
        boss = self.boss
        key = boss.bdef.get('key')
        if key not in SIGNATURES or boss.signature is not None:
            return False
        if (key == 'boss'
                and (boss.laser_warning_start or now < boss.laser_active_until)):
            return False
        if not opening and now < boss.next_signature_time:
            return False
        boss.signature = BossSignature(boss, self.player, now, 0, campaign=True)
        if key != 'boss':
            boss.next_signature_time = now + 10000
        boss.animation_attack_at = now
        boss.signature_opening_pending = False
        return True

    def _update_boss_signature(self, now):
        boss = self.boss
        signature = boss.signature
        if signature is None or now < signature.impact_at:
            return False
        if signature.key == 'boss_crab' and now >= signature.impact_at + CRAB_BUBBLE_BURST_MS:
            for index in range(2):
                self._release_crab_bubble(index, now)
        if now >= signature.end_at:
            signature.stop(boss)
            boss.signature = None
            if signature.key == 'boss':
                boss.next_signature_time = now + 10000
            return False
        if signature.key == 'boss_dragon' and now >= signature.next_fireball_at:
            signature.next_fireball_at = now + 400
            boss.animation_attack_at = now - 300
            self._add_boss_projectiles([
                DragonFireball(boss.x, boss.y + boss.h * .65, signature.damage)
            ])
        signature.move(boss, now, self.player)
        if not self._player_is_invincible(now) and signature.hit(boss, self.player.rect(), now):
            damage = (self.player_hp if signature.key == 'boss' else
                      min(signature.damage, boss.bdef.get('damage_cap', 2)))
            return self._damage_player(now, damage, f'被{signature.name}击败！', hit_feedback=True)
        return False

    def _release_crab_bubble(self, index, now):
        signature = self.boss.signature
        if signature.bubble_released[index]:
            return
        signature.bubble_released[index] = True
        x, y, _ = signature._bubbles(now - signature.impact_at)[index]
        self._spawn_hit_effect(x, y, CRAB_BUBBLE_COLORS[index], False)
        definition = next(edef for edef in ENEMY_DEFS if edef['key'] == 'crab')
        crab = Enemy(definition)
        crab.chase_color = CRAB_BUBBLE_COLORS[index]
        crab.chase_side = (-1, 1)[index]
        crab.max_hp = self.boss.max_hp * (.15, .20, .25)[self._campaign_tier()]
        crab.speed = 1.9
        crab.x = x
        crab.y = max(Enemy.ENTRY_DAMAGE_Y, y - crab.h / 2)
        crab.last_contact_damage_time = now - CONTACT_DAMAGE_COOLDOWN + 450
        partner = signature.bubble_crabs[1 - index]
        if partner in self.enemies:
            crab.chase_partner = partner
            partner.chase_partner = crab
        signature.bubble_crabs[index] = crab
        self.enemies.append(crab)

    def _hit_crab_bubble(self, rect, now):
        signature = self.boss.signature if self.boss else None
        if not signature or signature.key != 'boss_crab' or not signature.impact_at <= now < signature.impact_at + CRAB_BUBBLE_BURST_MS:
            return False
        for index, (x, y, radius) in enumerate(signature._bubbles(now - signature.impact_at)):
            if not signature.bubble_released[index] and circle_hits_rect(rect, x, y, radius):
                self._release_crab_bubble(index, now)
                return True
        return False

    def _add_boss_projectiles(self, projectiles):
        color = BOSS_COLORS.get(self.boss.bdef.get('key'))
        if color:
            for projectile in projectiles:
                projectile.tint = color
        cap = self.boss.bdef.get('damage_cap')
        if cap is not None:
            for projectile in projectiles:
                projectile.damage = min(projectile.damage, cap)
        if not self.infinite_mode:
            for projectile in projectiles:
                if projectile.homing and not projectile.bomb:
                    projectile.homing_duration = (550, 650, 750)[self._campaign_tier()]
        self.boss_projectiles.extend(projectiles)

    def _defeat_players_by_suction(self, now):
        self.player_hp = 0
        self._player_defeated('被远古巨鲸吸入！')
        if self.state == GameState.INFINITE_COUNTDOWN:
            self.player.x, self.player.y = self.boss.swallow_origins[0][1]

    def _whale_is_swallowing(self):
        return isinstance(self.boss, AncientWhaleBoss) and self.boss.swallowing

    def _update_whale_suction(self, now):
        boss = self.boss
        if not isinstance(boss, AncientWhaleBoss):
            return False
        if boss.swallowing:
            progress = boss.swallow_progress(now)
            travel = progress * progress
            for player, (x, y) in boss.swallow_origins:
                player.x = x + (boss.x - x) * travel
                player.y = y + (boss.y + boss.h * .81 - y) * travel
            if progress >= 1:
                boss.current_skill = ''
                boss.last_attack_time = now
                self._defeat_players_by_suction(now)
                boss.swallow_origins.clear()
            return True
        if boss.current_skill != 'whale_suction':
            return False
        if boss.suction_interrupted():
            boss.current_skill = ''
            boss.last_attack_time = now
            return False
        age = now - boss.skill_started_at
        if age >= boss.SUCTION_MS:
            boss.current_skill = 'whale_swallow'
            boss.skill_started_at = now
            boss.swallow_origins = [(player, (player.x, player.y)) for player in self.players]
            return True
        mouth_y = boss.y + boss.h * .81
        pull = .012 + .014 * age / boss.SUCTION_MS
        for player in self.players:
            dx, dy = boss.x - player.x, mouth_y - player.y
            distance = math.hypot(dx, dy)
            # Keep the player outside the mouth until the final gulp.
            if distance > boss.h * .4:
                strength = min(pull, 1 - boss.h * .4 / distance)
                player.move(dx * strength, dy * strength)
        for enemy in self.enemies:
            if enemy.temple_kind == 'rift':
                continue
            enemy.x += (boss.x - enemy.x) * pull
            enemy.y += (mouth_y - enemy.h / 2 - enemy.y) * pull
        return False

    def _update_boss_fight(self, now):
        if not self.boss: return
        if self._settle_boss_if_killed():
            return
        if isinstance(self.boss, OrochiBoss) and self.boss.death_at is not None:
            self.boss_projectiles.clear()
            return
        if self.desktop_controls:
            pygame.event.pump()
        keys = pygame.key.get_pressed()
        if self._update_whale_suction(now):
            return
        self._move_player_from_controls(self.player, keys, now)
        self._expire_water_temp_hp(now)
        signature = self.boss.signature
        if not (signature and signature.key == 'boss' and now >= signature.impact_at):
            if isinstance(self.boss, (ZongBoss, OrochiBoss)):
                target = self._nearest_player(self.boss.x, self.boss.y)
                self.boss.update(target.x, target.y)
            else:
                self.boss.update()
        if not self.infinite_mode and now and getattr(self.boss, 'laser_warning_start', 0) == now:
            zones = self.boss.death_laser_zones()
            warning = self._hazard_warning_ms(list(zones), now)
            if warning is None:
                self.boss.laser_warning_start = 0
        if isinstance(self.boss, ZongBoss) and now < self.boss.snow_until:
            for player in self.players:
                player.snow_slow_until = max(player.snow_slow_until, self.boss.snow_until)
        if isinstance(self.boss, ZongBoss) and self.boss.crescent_projectiles:
            self._add_boss_projectiles(self.boss.crescent_projectiles[:])
            self.boss.crescent_projectiles.clear()
        if isinstance(self.boss, ZongBoss) and self.boss.pending_projectiles:
            if not self.warned_boss_shots or self.infinite_mode:
                self._queue_boss_shots(self.boss.pending_projectiles[:], now)
            self.boss.pending_projectiles.clear()
        if self._damage_player_on_contacts(now):
            return
        death_lasers = self.boss.death_laser_rects(now)
        if self.boss.last_laser_hit_until != self.boss.laser_active_until:
            laser_hit = any(self._hit_player(rect) for rect in death_lasers)
            if laser_hit and not self._player_is_invincible(now):
                self.boss.last_laser_hit_until = self.boss.laser_active_until
                if self._damage_player(now, 1, f'被{self.boss.name}毁灭激光击败！', hit_feedback=True): return
        if self.infinite_mode:
            cycle, index = divmod(self.infinite_boss_index, len(config.INFINITE_BOSS_HP))
            interval = config.INFINITE_REINFORCEMENT_MS[index] * max(75, 100 - 5 * cycle) // 100
            cap = config.INFINITE_REINFORCEMENT_CAP[index] + min(2, cycle)
        else:
            interval = self._campaign_value(config.CAMPAIGN_REINFORCEMENT_MS)
            cap = self._campaign_value(config.CAMPAIGN_REINFORCEMENT_CAP)
        if (interval and (not self.infinite_mode or self.boss.entered) and now - self.last_spawn_time >= interval
                and not self.warned_boss_shots and not self.boss.laser_warning_start
                and now >= self.boss.laser_active_until
                and sum(not e.temple_kind for e in self.enemies) < cap):
            self.spawn_enemy()
            self.last_spawn_time = now
        self._maybe_spawn_gift(now)
        factory = self._is_factory_stage()
        if factory:
            self._settle_factory_link(now)
            self._start_factory_link(now)
        fire_wall_rects = [fw.rect() for fw in self.fire_walls]
        self._update_temple_enemies(now)
        speed_multiplier = self._enemy_speed_multiplier()
        for e in self.enemies[:]:
            target = self._nearest_player(e.x, e.y) if e.chase_color is not None or e.temple_kind == 'worm' else None
            previous_burn_hits = e.burn_hits
            e.update(target, speed_multiplier=speed_multiplier)
            if e.burn_hits > previous_burn_hits:
                self._spawn_hit_effect(*e.rect().center, (255, 130, 35), e.is_large, element='fire')
                self._play_skill_hit_sound(now)
            self._block_enemy_with_fire_walls(e, fire_wall_rects)
            if self._enemy_can_attack(e, now):
                self.enemy_projectiles.extend(self._enemy_shots(e, now))
            if e.reached_bottom() and self._resolve_leak(e, now):
                return
        if self._update_boss_signature(now) or self._update_special_boss_hazards(now):
            return
        if self._damage_player_on_contacts(now):
            return
        self._try_boss_absorb_minions(now)
        self._pull_projectiles_to_storms(self.enemy_projectiles)
        for ep in self.enemy_projectiles[:]:
            target = self._nearest_player(ep.x, ep.y)
            ep.update(target_x=target.x, target_y=target.y)
            if not ep.alive:
                if getattr(ep, 'bomb', False) and self._explode_enemy_bomb(ep, now):
                    return
                self.enemy_projectiles.remove(ep)
            elif not getattr(ep, 'unblockable', False) and self._blocked_by_fire_wall(ep.rect(), fire_wall_rects):
                self.enemy_projectiles.remove(ep)
            elif not getattr(ep, 'unblockable', False) and self._blocked_by_ice_floor(ep):
                self.enemy_projectiles.remove(ep)
            elif not getattr(ep, 'unblockable', False) and self._blocked_by_dart_shield(ep.block_rect(), now):
                self._spawn_hit_effect(ep.x, ep.y, (140, 255, 150), False)
                self.enemy_projectiles.remove(ep)
            elif getattr(ep, 'bomb', False) and self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._explode_enemy_bomb(ep, now): return
            elif self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._damage_player(now, 1, '被怪物子弹击败！', hit_feedback=True): return
        opening_delay_elapsed = now - self.boss.fight_start_time >= config.BOSS_OPENING_DELAY_MS
        if self.boss.entered and opening_delay_elapsed:
            self._try_boss_signature(now, opening=self.boss.signature_opening_pending)
        if self.warned_boss_shots:
            if now >= self.warned_boss_shots_at:
                for shot in self.warned_boss_shots:
                    shot.spawn_time = now
                    if shot.big_fireball:
                        shot.x = shot.prev_x = self.boss.x + shot.launch_offset[0]
                        shot.y = shot.prev_y = self.boss.y + shot.launch_offset[1]
                self._add_boss_projectiles(self.warned_boss_shots)
                self.warned_boss_shots.clear()
                self.boss.last_attack_time = now
                self.boss.animation_attack_at = now
        elif (isinstance(self.boss, NiuBoss) and self.boss.entered
              and self.boss.opening_skill_pending and opening_delay_elapsed):
            self.boss.opening_skill_pending = False
            self.boss.animation_attack_at = now
            shots = self.boss.attack(now, self._nearest_player(self.boss.x, self.boss.y).x, opening=True)
            self._add_boss_projectiles(shots)
        elif opening_delay_elapsed and self.boss.should_attack(now):
            self.boss.animation_attack_at = now
            target = self._nearest_player(self.boss.x, self.boss.y)
            if isinstance(self.boss, (ZongBoss, MechaLizardBoss, AncientWhaleBoss)):
                shots = self.boss.attack(now, target.x, target.y)
            else:
                shots = self.boss.attack(now, target.x)
            if not self.infinite_mode and isinstance(self.boss, NiuBoss):
                self._extend_ground_warning(self.boss, now)
            self._queue_boss_shots(shots, now)
        self._pull_projectiles_to_storms(self.boss_projectiles)
        for bp in self.boss_projectiles[:]:
            if isinstance(self.boss, MechaLizardBoss) and isinstance(bp, AbyssProjectile):
                self.boss.sync_weapon_mount(bp, now)
            if isinstance(bp, NiuShieldShard):
                bp.follow_shield(self.boss)
            target = self._nearest_player(bp.x, bp.y)
            was_armed = getattr(bp, 'detonate_at', 0)
            target_x, target_y = target.rect().center if isinstance(bp, ZongBomb) else (target.x, target.y)
            bp.update(target_x=target_x, target_y=target_y)
            if not self.infinite_mode and not was_armed and getattr(bp, 'detonate_at', 0):
                zones = []
                for armed in self.boss_projectiles:
                    if getattr(armed, 'detonate_at', 0) > now:
                        radius = armed.explode_radius
                        zones.append(pygame.Rect(round(armed.x - radius), round(armed.y - radius),
                                                 2 * radius, 2 * radius))
                warning = self._hazard_warning_ms(zones, now, bp.warning_ms)
                if warning is None:
                    self.boss_projectiles.remove(bp)
                    continue
                bp.detonate_at = now + warning
            if getattr(bp, 'impact_pending', False):
                bp.impact_pending = False
                if self._explode_enemy_bomb(bp, now): return
            if not bp.alive:
                self.boss_projectiles.remove(bp)
                if isinstance(bp, AbyssProjectile) and bp.pearl_burst_at and now >= bp.pearl_burst_at:
                    self.explosions.append(Explosion(bp.x, bp.y, (255, 220, 145), 36))
                    self._add_boss_projectiles(bp.pearl_fragments())
                if (getattr(bp, 'bomb', False) and (not isinstance(bp, ZongBomb) or bp.proximity_detonated)
                        and self._explode_enemy_bomb(bp, now)): return
            elif not getattr(bp, 'unblockable', False) and self._blocked_by_fire_wall(bp.block_rect(), fire_wall_rects):
                self.boss_projectiles.remove(bp)
            elif not getattr(bp, 'unblockable', False) and self._blocked_by_ice_floor(bp):
                self.boss_projectiles.remove(bp)
            elif not getattr(bp, 'unblockable', False) and self._blocked_by_dart_shield(bp.block_rect(), now):
                self._spawn_hit_effect(bp.x, bp.y, (140, 255, 150), False)
                self.boss_projectiles.remove(bp)
            elif getattr(bp, 'bomb', False) and self._hit_player(bp.rect()):
                self.boss_projectiles.remove(bp)
                if self._explode_enemy_bomb(bp, now): return
            elif (hit_player := self._hit_by_projectile(bp)):
                if not hasattr(bp, 'impact_pending') and not getattr(bp, 'persistent', False):
                    self.boss_projectiles.remove(bp)
                if (not self._player_is_invincible(now)
                        and (getattr(bp, 'persistent', False)
                             or now - getattr(bp, 'last_player_hit', -9999) >= 800)):
                    bp.last_player_hit = now
                    if getattr(bp, 'persistent', False):
                        bp._hit_players.add(hit_player)
                    if isinstance(bp, ReturningAxe) and not bp.red:
                        self._apply_niu_ice_axe_effect(bp, hit_player, now)
                    if isinstance(bp, AbyssProjectile) and bp.skill == 'rune_geyser':
                        hit_player.start_geyser_lift(now)
                    if self._damage_player(now, bp.damage, f'被{self.boss.name}击败！', hit_feedback=True): return
        if ((self._mobile_fire_active() or self._key_pressed(keys, 'p1_shoot'))
                and self.player.can_shoot(now, self._player_fire_interval_multiplier(now))):
            self._shoot(now, self.player)
        for b in self.bullets[:]:
            b.update()
            if b.is_offscreen(): self.bullets.remove(b)
            else:
                if self._handle_bullet_gift_hit(b, now):
                    continue
                br = b.rect()
                if self._hit_crab_bubble(br, now):
                    play_sound('hit')
                    self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), False, element=b.gift_kind or b.character)
                    self.bullets.remove(b)
                    continue
                hit_enemy = False
                for e in self.enemies[:]:
                    if (e.y + e.h <= 0 or br.right < e.x - e.w // 2 or br.left > e.x + e.w // 2 or
                            br.bottom < e.y or br.top > e.y + e.h):
                        continue
                    if id(e) not in b.hit_targets and br.colliderect(e.rect()):
                        hit_enemy = True
                        self._apply_bullet_passive(e, b, now); b.hit_targets.add(id(e)); play_sound('hit')
                        self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), e.is_large, element=b.gift_kind or b.character)
                        if e.is_killed(b.weapon_name):
                            self._kill_enemy(e)
                        if b.weapon_name == 'sniper':
                            b.damage *= 0.7 if self.infinite_mode else 0.65
                        else:
                            if b in self.bullets: self.bullets.remove(b)
                            break
                if (not hit_enemy) and self.boss and b in self.bullets and self.boss.collides(br):
                    damage = b.damage
                    if b.character == 'fire':
                        damage *= 1.5 if self.infinite_mode else 1.2
                    if self.infinite_mode and b.weapon_name == 'shotgun':
                        damage *= 0.5
                    shooter = getattr(b, 'source_player', self.player)
                    if self.infinite_mode and now < shooter.water_boost_until:
                        damage *= 1.5
                    damage *= self._gift_damage_mult(now)
                    reflected = isinstance(self.boss, ZongBoss) and self.boss.reflects_bullet()
                    if reflected:
                        self._add_boss_projectiles([ZongReflectBullet(b.x, b.y)])
                    shielded = isinstance(self.boss, NiuBoss) and now < self.boss.shield_until
                    previous_hp = self.boss.hp
                    self.boss.hit_by(b.weapon_name, damage, source='bullet', hit_rect=br)
                    self.bullets.remove(b)
                    if self.boss.hp < previous_hp:
                        if b.character == 'ice' or getattr(b, 'gift_kind', None) == 'ice':
                            self.boss.apply_slow(now, 4000, 0.7)
                    if not shielded and (reflected or self.boss.hp < previous_hp):
                        play_sound('hit')
                        self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), True, element=b.gift_kind or b.character)
                    if self._settle_boss_if_killed():
                        return
        for sp in self.skill_projectiles[:]:
            sp.update()
            if not sp.alive or sp.is_offscreen():
                if sp.ptype == 'grenade':
                    self._explode_grenade(sp, include_boss=True)
                    if self.state != GameState.BOSS_FIGHT:
                        self._remove_skill_projectile(sp, now)
                        return
                self._remove_skill_projectile(sp, now); continue
            sr = sp.rect()
            for e in self.enemies[:]:
                if (e.y + e.h <= 0 or sr.right < e.x - e.w // 2 or sr.left > e.x + e.w // 2 or
                        sr.bottom < e.y or sr.top > e.y + e.h):
                    continue
                if sr.colliderect(e.rect()):
                    if sp.ptype == 'grenade':
                        self._explode_grenade(sp, include_boss=True)
                        self._remove_skill_projectile(sp, now)
                        if self.state != GameState.BOSS_FIGHT:
                            return
                        break
                    elif sp.ptype == 'fire_rocket':
                        self._remove_skill_projectile(sp, now)
                        self._explode_fire_rocket(sp, now, include_boss=True)
                        if self.state != GameState.BOSS_FIGHT:
                            return
                        break
                    elif sp.ptype == 'fireball':
                        self._hit_enemy_with_fireball(sp, e, now)
                        if not sp.piercing: self._remove_skill_projectile(sp, now); break
                    elif sp.ptype == 'ice_ball':
                        if self._show_immune(e, now):
                            self._remove_skill_projectile(sp, now); break
                        e.hit_by('pistol', self._skill_projectile_damage(sp, e, now))
                        if self.infinite_mode or not e.is_zongzong:
                            e.frozen = True
                            e.frozen_until = now + 4000
                        else:
                            e.apply_slow(now, 2500, 0.75)
                        self._spawn_hit_effect(sp.x, sp.y, (150, 220, 255), e.is_large, element='ice')
                        self._play_skill_hit_sound(now)
                        if e.is_killed('pistol'): self._kill_enemy(e)
                        self._remove_skill_projectile(sp, now); break
            if sp not in self.skill_projectiles:
                continue
            if self.boss and self.boss.collides(sr):
                previous_hp = self.boss.hp
                if sp.ptype == 'grenade':
                    self._explode_grenade(sp, include_boss=True)
                    if self.state != GameState.BOSS_FIGHT:
                        self._remove_skill_projectile(sp, now)
                        return
                elif sp.ptype == 'fire_rocket':
                    self._remove_skill_projectile(sp, now)
                    self._explode_fire_rocket(sp, now, include_boss=True)
                    if self.state != GameState.BOSS_FIGHT:
                        return
                    continue
                elif sp.ptype == 'fireball':
                    self._hit_boss_with_fireball(sp)
                else:
                    self.boss.hit_by('sniper', self._skill_projectile_damage(sp, self.boss, now), hit_rect=sr)
                if sp.ptype == 'ice_ball' and self.boss:
                    if self.boss.hp < previous_hp:
                        self.boss.apply_slow(now, 4000, 0.7)
                    self._spawn_hit_effect(sp.x, sp.y, (150, 220, 255), True, element='ice')
                    self._play_skill_hit_sound(now)
                if not (sp.ptype == 'fireball' and sp.piercing): self._remove_skill_projectile(sp, now)
                if self._settle_boss_if_killed():
                    return
        for fw in self.fire_walls[:]:
            if not self.infinite_mode and not fw.is_expired() and fw.can_damage(now):
                contact = fw.rect().inflate(0, 4)
                for enemy in self.enemies[:]:
                    if contact.colliderect(enemy.rect()):
                        enemy.hit_by('pistol', 0.75)
                        self._spawn_hit_effect(*contact.clip(enemy.rect()).center, (255, 105, 35), enemy.is_large, element='fire')
                        self._play_skill_hit_sound(now)
                        if enemy.is_killed('pistol'):
                            self._kill_enemy(enemy)
                hitbox = next((box for box in self.boss.hitboxes() if box.colliderect(contact)), None) if self.boss else None
                if hitbox:
                    self.boss.hit_by('pistol', 0.75, hit_rect=contact)
                    self._spawn_hit_effect(*contact.clip(hitbox).center, (255, 105, 35), True, element='fire')
                    self._play_skill_hit_sound(now)
                    if self._settle_boss_if_killed():
                        return
            if fw.is_expired():
                self.fire_walls.remove(fw)
                self._finish_skill_effect(getattr(fw, 'owner', None), getattr(fw, 'skill_type', None), now)
        self._update_magnetic_storms(now, include_boss=True)
        if self.state != GameState.BOSS_FIGHT:
            return
        self._pull_projectiles_to_storms(self.boss_projectiles)
        self._pull_projectiles_to_storms(self.enemy_projectiles)
        for ice in self.ice_floors[:]:
            if not self.infinite_mode and getattr(ice, 'owner', None) and now >= ice.owner.skill_active_until.get('ice_floor', now):
                self.ice_floors.remove(ice)
                self._finish_skill_effect(ice.owner, ice.skill_type, now)
                continue
            ice.update()
            if ice.is_offscreen() or not ice.alive:
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
                else:
                    self.ice_floors.remove(ice)
                    self._finish_skill_effect(getattr(ice, 'owner', None), getattr(ice, 'skill_type', None), now)
                continue
            hit = None
            for e in self.enemies[:]:
                if ice.collides(e): hit = e; break
            if hit:
                hx, hy = hit.x, hit.y + hit.h//2
                if self._show_immune(hit, now):
                    ice.hit(hx)
                    continue
                hit.hit_by('pistol', 0.5 * self._gift_damage_mult(now))
                self._spawn_hit_effect(hx, hy, (150, 220, 255), hit.is_large, element='ice')
                self._play_skill_hit_sound(now)
                for e in self.enemies[:]:
                    if math.hypot(e.x-hx, e.y+e.h//2-hy) < ice.freeze_radius:
                        if self._is_zongzong(e):
                            self._show_immune(e, now)
                            continue
                        e.frozen = True; e.frozen_until = now + 4000
                ice.hit(hx)
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
                continue
            if self.boss and self.boss.collides(ice.rect()):
                previous_hp = self.boss.hp
                self.boss.hit_by('pistol', 0.5 * self._gift_damage_mult(now), hit_rect=ice.rect())
                if self.boss.hp < previous_hp:
                    self.boss.apply_slow(now, 4000, 0.7)
                self._spawn_hit_effect(ice.x, ice.y, (150, 220, 255), True, element='ice')
                self._play_skill_hit_sound(now)
                ice.hit(self.boss.x)
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
                if self._settle_boss_if_killed():
                    return
        self._update_radiation_lasers(now)
        self._update_dart_shields(now)
        if self.state != GameState.BOSS_FIGHT:
            return
        for e in self.enemies[:]:
            w = self.player.current_weapon
            if w and e.is_killed(w): self._kill_enemy(e)
        if factory:
            self._settle_factory_link(now)
        for c in self.coins[:]:
            c.update()
            if self._hit_player(c.rect()):
                self.player.gold += c.value
                play_sound('coin'); self.coins.remove(c)
            elif c.is_offscreen(): self.coins.remove(c)
        for box in self.gift_boxes[:]:
            box.update()
            if box.is_offscreen():
                self.gift_boxes.remove(box)
        self._update_combat_effects()

    def _settle_boss_if_killed(self):
        if self.boss and self.boss.is_killed():
            self._kill_boss()
            return True
        return False

    def _advance_infinite_background(self, now):
        self._set_infinite_background(self.infinite_background_level % len(config.INFINITE_BOSS_HP) + 1, now)

    def _set_infinite_background(self, level, now):
        background = self.scrolling_background(self.bg.get_size())
        self.bg_transition_prev = (background if background is not None else self.bg).copy()
        self.infinite_background_level = level
        self.background_scroll_ticks = 0
        self.temple_rifts_at = 0
        self.bg = self._load_bg()
        self.bg_transition_until = now + BG_FADE_MS

    def _burst_remaining_enemies(self):
        for enemy in self.enemies:
            x, y = enemy.rect().center
            self.particles.append(Particle(x, y, (255, 185, 95), 16))
        self.enemies.clear()

    def _kill_boss(self):
        if not self.boss:
            return
        self.chapter += 1
        b = self.boss
        if not isinstance(b, OrochiBoss):
            self.particles.append(Particle(b.x, b.y+b.h//2, (255, 200, 50), 30))
            self.explosions.append(Explosion(b.x, b.y+b.h//2, (255, 130, 70), 28))
        self.boss_projectiles.clear()
        if self.infinite_mode:
            self.score += 100
            self.kill_count += 1
            self.infinite_boss_index += 1
            self.boss = None
            now = config.game_ticks()
            self.spawn_interval = max(800, 1300 - 50 * (self.infinite_boss_index // 2))
            self.last_spawn_time = now + 1200 - self.spawn_interval
            self._burst_remaining_enemies()
            self.enemy_projectiles.clear()
            self.bullets.clear()
            self._heal_player(1)
            self.infinite_music_variant += 1
            self._advance_infinite_background(now)
            play_sound('kill')
            self._start_infinite_chapter(now)
            return
        self._heal_player((2, 2, 1)[self._campaign_tier()])
        play_sound('kill'); self.boss = None; self._level_complete()

    def _try_boss_absorb_minions(self, now):
        if self.infinite_mode or self.current_level != 6 or not self.boss.entered:
            return
        boss = self.boss
        tier = self._campaign_tier()
        if boss.absorb_count >= 2:
            return
        if not boss.next_absorb_time:
            boss.next_absorb_time = boss.fight_start_time + 14000
        if now < boss.next_absorb_time:
            return
        target = boss.absorb_target
        if target is None:
            targets = [e for e in self.enemies if not e.is_large]
            if targets:
                boss.absorb_target = min(targets, key=lambda e: math.hypot(e.x - boss.x, e.y - boss.y))
                boss.next_absorb_time = now + (1600, 1300, 1100)[tier]
            return
        boss.absorb_target = None
        boss.next_absorb_time = now + (15000, 13000, 11000)[tier]
        if target not in self.enemies:
            return
        self.enemies.remove(target)
        amount = min(boss.max_hp - boss.hp, boss.max_hp * (0.04, 0.06, 0.08)[tier])
        boss.hp += amount
        boss.absorb_count += 1
        boss.last_attack_time = now
        boss.next_death_laser_time = max(boss.next_death_laser_time, now + 2000)
        self.gift_messages.append((f'{boss.name}恢复 {amount:.1f} HP', HEALTH_RED, now + 2000, now))
        self.explosions.append(Explosion(target.x, target.y + target.h // 2, (145, 45, 220), 16))
        play_sound('coin')

    def _campaign_large_enemy_slots(self):
        level = self.current_level
        wave_size = self._campaign_value(config.CAMPAIGN_KILLS)
        expected = wave_size * config.CAMPAIGN_LARGE_CHANCE[level - 1]
        if not expected:
            return set()
        count = math.floor(expected)
        if random.random() < expected - count:
            count += 1
        slots = {3} if level == 2 else set()
        count = max(0, count - len(slots))
        first_slot = 5 if slots else 1
        # Sample from compressed positions, then leave one normal spawn between slots.
        positions = sorted(random.sample(range(first_slot, wave_size - count + 1), count))
        return slots.union(position + index for index, position in enumerate(positions))

    def _spawn_campaign_enemy(self):
        level = self.current_level
        tier = self._campaign_tier()
        count = self.level_spawn_count
        ordinary = [e for e in self.level_enemy_defs if not e['is_large'] and not e.get('zongzong')]
        large = [e for e in self.level_enemy_defs if e['is_large']]
        rare = next((e for e in self.level_enemy_defs if e.get('zongzong')), None)
        elite_chance = config.CAMPAIGN_LARGE_CHANCE[level - 1]
        rare_chance = 0 if level < 4 else 0.05 if level == 8 else 0.03
        wave = self.state == GameState.PLAYING
        scheduled_wave = wave and count < self._campaign_value(config.CAMPAIGN_KILLS)
        if wave and level == 1 and count < 2:
            key = ('lobster', 'crab')[count]
            definition = next(e for e in ordinary if e['key'] == key)
        elif wave and level == 2 and count == 3:
            definition = next(e for e in large if e['key'] == 'octopus')
        elif (not self.last_spawn_was_elite and large and
              (count in self.large_enemy_slots if scheduled_wave else random.random() < elite_chance)):
            definition = random.choice(large)
        elif (not self.last_spawn_was_elite and rare and random.random() < rare_chance
              and not (scheduled_wave and count + 1 in self.large_enemy_slots)
              and not any(e.is_zongzong for e in self.enemies)):
            definition = rare
        else:
            if wave and level == 1 and count < 6:
                ordinary = [e for e in ordinary if e['key'] != 'goldfish']
            definition = random.choice(ordinary)

        enemy = Enemy(definition)
        if level == 9 and definition['key'] in config.FACTORY_ENEMY_KEYS:
            enemy.factory_kind = 'original'
        self.last_spawn_was_elite = enemy.is_large or enemy.is_zongzong
        self.level_spawn_count += 1
        enemy.max_hp = definition.get('campaign_hp', 9 if enemy.is_large else 8 if enemy.is_zongzong else 3)
        enemy.speed = definition['base_speed'] * random.uniform(0.88, 1.12)
        enemy.speed *= config.CAMPAIGN_SPEED[level - 1]
        enemy.speed *= (0.88, 1, 1.08)[tier]
        if self.difficulty and self.difficulty.name == '自定义':
            enemy.speed *= self.difficulty.enemy_speed_mult
        if (not self.last_spawn_was_elite and level >= (2, 1, 1)[tier]
                and (level != 1 or count >= 6) and random.random() < (0.05, 0.08, 0.12)[tier]):
            enemy.speed *= (1.35, 1.50, 1.60)[tier]
            enemy.fast_variant = True
        distance = config.GAME_AREA_BOTTOM + 20 + enemy.h
        reference_height = round(enemy.unscaled_base_h * config.MOBILE_LANDSCAPE_ENTITY_SCALE)
        enemy.speed *= distance / (384 + reference_height)
        enemy.speed = min(enemy.speed, (config.GAME_AREA_BOTTOM + 20) / (60 * (5, 4.5, 4)[tier]))
        minimum, maximum = ((10000, 14000), (8000, 12000), (6500, 10000))[tier]
        if self.difficulty and self.difficulty.name == '自定义':
            minimum, maximum = sorted((self.difficulty.enemy_attack_interval_min,
                                       self.difficulty.enemy_attack_interval_max))
        enemy.attack_interval_min = minimum
        enemy.attack_interval_max = maximum
        enemy.attack_interval = (4500, 3800, 3200)[tier] + math.ceil(enemy.h / enemy.speed * 1000 / 60)
        enemy.last_attack_time = config.game_ticks()
        self.enemies.append(enemy)

    def _spawn_temple_worm(self, parent, hp, offset, speed):
        worm = Enemy(TEMPLE_WORM)
        worm.temple_kind = 'worm'
        worm.max_hp = hp
        worm.speed = speed
        worm.x = max(config.GAME_AREA_LEFT + worm.w / 2,
                     min(config.GAME_AREA_RIGHT - worm.w / 2, parent.x + offset))
        worm.y = min(config.GAME_AREA_BOTTOM - worm.h, parent.y + parent.h * .65)
        self.enemies.append(worm)

    def _size_temple_rift(self, rift):
        width = config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT
        base_width, base_height = TEMPLE_RIFT['size']
        height = config.SCREEN_HEIGHT * .215 - 8
        rift.set_size_scale(min(1, (width - 24) / base_width, height / base_height))

    def _temple_rift_y_range(self, rift, side):
        top = config.SCREEN_HEIGHT * .07
        middle = config.SCREEN_HEIGHT * .285
        bottom = config.SCREEN_HEIGHT / 2
        if side < 0:
            return top, middle - rift.h - 8
        return middle + 8, bottom - rift.h

    def _spawn_temple_rift(self, now, side):
        rift = Enemy(TEMPLE_RIFT)
        rift.temple_kind = 'rift'
        rift.temple_side = side
        rift.max_hp = 16
        self._open_temple_rift(rift, now, side or -1)
        self.enemies.append(rift)

    def _open_temple_rift(self, rift, now, side):
        self._size_temple_rift(rift)
        width = config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT
        center = config.GAME_AREA_LEFT + width / 2
        outer = (config.GAME_AREA_LEFT + rift.w / 2 + 8 if side < 0
                 else config.GAME_AREA_RIGHT - rift.w / 2 - 8)
        inner = center + side * rift.w / 2
        rift.x = random.uniform(outer, inner) if side * (outer - inner) >= 0 else outer
        rift.y = random.uniform(*self._temple_rift_y_range(rift, side))
        rift.breath_start_time = now
        tier = 1 if self.infinite_mode else self._campaign_tier()
        rift.temple_spawn_at = now + (800, 650, 480)[tier] + (650 if side > 0 else 0)
        rift.temple_worms_left = (3, 4, 6)[tier]

    def _update_temple_enemies(self, now):
        level = self.infinite_background_level if self.infinite_mode else self.current_level
        if level != 10:
            return
        if not (self.infinite_mode and self.boss):
            if not self.temple_rifts_at:
                self.temple_rifts_at = now + 8500
            elif now >= self.temple_rifts_at and self.temple_rifts_at != math.inf:
                self.temple_rifts_at = math.inf
                self._spawn_temple_rift(now, 0)
        tier = 1 if self.infinite_mode else self._campaign_tier()
        worm_cap = (6, 8, 10)[tier]
        worms = sum(e.temple_kind == 'worm' for e in self.enemies)
        for enemy in self.enemies[:]:
            if enemy.temple_kind == 'rift':
                if now < enemy.temple_spawn_at:
                    continue
                if enemy.temple_worms_left:
                    if worms >= worm_cap:
                        continue
                    offset = (enemy.temple_worms_left - ((3, 4, 6)[tier] + 1) / 2) * enemy.w / 7
                    self._spawn_temple_worm(enemy, 2.4, offset, (2.8, 3.1, 3.4)[tier])
                    worms += 1
                    enemy.temple_worms_left -= 1
                    enemy.temple_spawn_at = now + ((420, 350, 280)[tier] if enemy.temple_worms_left
                                                   else (10000, 8500, 7000)[tier])
                else:
                    # Only the original eye can open the second rift.
                    if enemy.temple_side == 0:
                        enemy.temple_side = -1
                        self._spawn_temple_rift(now, 1)
                    self._open_temple_rift(enemy, now, enemy.temple_side)
            elif (enemy.edef['key'] in config.TEMPLE_ENEMY_KEYS and enemy.temple_spawn_at == 0
                  and enemy.y >= 70 and not enemy.frozen):
                enemy.temple_spawn_at = now or 1
                if worms < worm_cap and random.random() < (.18, .24, .28)[tier]:
                    hp = enemy.max_hp
                    if hp is None:
                        pistol = config.WEAPON_DEFS['pistol']
                        hits = pistol.large_shots if enemy.is_large else pistol.normal_shots
                        hp = math.ceil(hits * enemy.health_mult)
                    count = min(random.randint(1, (2, 2, 3)[tier]), worm_cap - worms)
                    for index in range(count):
                        offset = (index - (count - 1) / 2) * enemy.w / 3
                        self._spawn_temple_worm(enemy, hp * .3, offset, 2.5)
                    worms += count

    def _is_factory_stage(self):
        return (self.infinite_background_level if self.infinite_mode else self.current_level) == 9

    def _start_factory_link(self, now):
        if any(e.factory_link_until or e.factory_kind == 'mini_boss' for e in self.enemies):
            return
        candidates = [e for e in self.enemies if e.factory_kind == 'original'
                      and e.y + e.h > 0 and e.y < config.GAME_AREA_BOTTOM]
        visible = set(candidates)
        self.factory_link_attempts = {trio for trio in self.factory_link_attempts if trio <= visible}
        if len(candidates) < 3:
            return
        trio = frozenset(candidates[-3:])
        if trio in self.factory_link_attempts:
            return
        self.factory_link_attempts.add(trio)
        if random.random() < .5:
            for enemy in trio:
                enemy.factory_link_until = now + 2000
                enemy._clamp_factory_health()

    def _settle_factory_link(self, now):
        linked = [e for e in self.enemies if e.factory_link_until]
        if not linked:
            return
        if all(e._damage_progress() >= .99 - 1e-9 for e in linked):
            for enemy in linked:
                self._kill_enemy(enemy, linked=True)
        elif now >= linked[0].factory_link_until:
            x = sum(e.x for e in linked) / len(linked)
            y = sum(e.rect().centery for e in linked) / len(linked)
            for enemy in linked:
                self.enemies.remove(enemy)
            definition = dict(key='mecha_crab', name='机械蜥蜴·熔芯（小型）', is_large=True,
                              base_speed=1.6, size=(86, 75), gold=sum(e.gold_value for e in linked),
                              sprite_asset='bosses/boss_mecha_lizard.png')
            mini = Enemy(definition)
            mini.factory_kind = 'mini_boss'
            if self.infinite_mode:
                cycle, index = divmod(self.infinite_boss_index, len(config.INFINITE_BOSS_HP))
                mini.max_hp = self._infinite_boss_hp(index, cycle) * .16
            else:
                mini.max_hp = self._campaign_boss_hp() * (.12, .16, .20)[self._campaign_tier()]
            mini.factory_patrol_direction = 1
            mini.x = max(config.GAME_AREA_LEFT + mini.w / 2,
                         min(config.GAME_AREA_RIGHT - mini.w / 2, x))
            mini.y = max(Enemy.ENTRY_END_Y, min(config.GAME_AREA_BOTTOM * .46, y - mini.h / 2))
            mini.last_attack_time, mini.attack_interval = now, 1000
            self.enemies.append(mini)
            self._spawn_hit_effect(mini.x, mini.rect().centery, (120, 220, 255), True)

    def _split_factory_enemy(self, parent, now):
        count = random.randint(1, 3)
        for index in range(count):
            child = Enemy(parent.edef)
            child.factory_kind = 'fragment'
            child.unscaled_base_w = round(parent.unscaled_base_w * .74)
            child.unscaled_base_h = round(parent.unscaled_base_h * .74)
            child.base_w = child.w = round(child.unscaled_base_w * child.size_scale)
            child.base_h = child.h = round(child.unscaled_base_h * child.size_scale)
            child.max_hp = parent.max_hp * .25
            child.gold_value = 0
            child.speed = parent.speed
            left = config.GAME_AREA_LEFT + child.w / 2
            right = config.GAME_AREA_RIGHT - child.w / 2
            step = min(child.w * 1.65, (right - left) / max(1, count - 1))
            half_spread = step * (count - 1) / 2
            center = max(left + half_spread, min(right - half_spread, parent.x))
            offset = index - (count - 1) / 2
            child.x = center + offset * step
            lift = max(0, 1 - abs(offset)) * child.h / 2
            child.y = max(0, min(config.GAME_AREA_BOTTOM - child.h, parent.y - lift))
            child.last_attack_time, child.attack_interval = now, parent.attack_interval
            self.enemies.append(child)

    def _enemy_shots(self, enemy, now):
        if not enemy.factory_kind:
            target = self._nearest_player(enemy.x, enemy.y)
            return enemy.attack(now, target.x)
        mini = enemy.factory_kind == 'mini_boss'
        enemy.last_attack_time = now
        enemy.attack_interval = 3000 if mini else random.randint(enemy.attack_interval_min, enemy.attack_interval_max)
        shots = []
        for angle in (-24, 0, 24) if mini else (0,):
            missile = AbyssProjectile('guided_missile', enemy.x + angle * enemy.size_scale,
                                      enemy.y + enemy.h, angle=angle, speed=3.6 if mini else 3,
                                      warning_ms=180, active_ms=9000,
                                      scale=enemy.size_scale * (.68 if mini else .46))
            missile.missile_pass = 2
            missile.missile_turn_rate = 125 if mini else 42
            missile.unblockable = mini
            missile.persistent = False
            shots.append(missile)
        return shots

    def _enemy_can_attack(self, enemy, now):
        if enemy.temple_kind or enemy.chase_color is not None or not enemy.should_attack(now):
            return False
        self.enemy_volley_times[:] = [t for t in self.enemy_volley_times if now - t < 1000]
        cap = 1 if self.boss else 2 if self.infinite_mode else (1, 2, 2)[self._campaign_tier()]
        if len(self.enemy_volley_times) >= cap:
            enemy.last_attack_time += 180
            return False
        self.enemy_volley_times.append(now)
        return True

    def spawn_enemy(self):
        if not self.infinite_mode:
            self._spawn_campaign_enemy()
            return
        level = self.infinite_background_level
        pool = get_level_enemy_defs(LEVEL_CONFIGS[level - 1]) if level in (9, 10) else self.level_enemy_defs
        large_pool = [e for e in pool if e['is_large']]
        zong_pool = [e for e in pool if e['key'] == 'zongzong']
        normal_pool = [e for e in pool if not e['is_large'] and e['key'] != 'zongzong']
        zong_chance = ZONGZONG_SPAWN_CHANCE * (2 if self.infinite_background_level == 8 else 1)
        if zong_pool and random.random() < zong_chance:
            edef = random.choice(zong_pool)
        elif large_pool and random.random() < INFINITE_LARGE_ENEMY_CHANCE:
            edef = random.choice(large_pool)
        else: edef = random.choice(normal_pool or pool)
        e = Enemy(edef)
        if self.difficulty:
            e.speed *= self.difficulty.enemy_speed_mult
            amin = int(self.difficulty.enemy_attack_interval_min)
            amax = int(self.difficulty.enemy_attack_interval_max)
            e.attack_interval_min = min(amin, amax)
            e.attack_interval_max = max(amin, amax)
            e.attack_interval = random.randint(e.attack_interval_min, e.attack_interval_max)
        now = config.game_ticks()
        e.health_mult *= self._infinite_health_mult(now)
        if level in (9, 10):
            e.max_hp = edef['campaign_hp'] * e.health_mult
            if level == 9:
                e.factory_kind = 'original'
        e.speed *= 0.82
        e.damage_mult = self._infinite_damage_mult()
        if not e.is_large and random.random() < FAST_ENEMY_CHANCE:
            e.speed *= 2
            e.fast_variant = True
        e.attack_interval_min = max(500, int(e.attack_interval_min * ENEMY_ATTACK_INTERVAL_MULT))
        e.attack_interval_max = max(e.attack_interval_min, int(e.attack_interval_max * ENEMY_ATTACK_INTERVAL_MULT))
        e.attack_interval = random.randint(e.attack_interval_min, e.attack_interval_max)
        self.enemies.append(e)

    def _kill_enemy(self, e, *, linked=False):
        if e not in self.enemies or (e.factory_link_until and not linked): return
        if e.chase_partner:
            e.chase_partner.chase_partner = None
            e.chase_partner = None
        credit = 0 if e.temple_kind or e.factory_kind == 'fragment' else 3 if e.factory_kind == 'mini_boss' else 1
        self.enemies.remove(e); self.kill_count += credit; self.level_kills += credit
        if credit and any(player.character == 'water' for player in self.players):
            self.water_passive_kills += 1
            if self.infinite_mode and self.water_passive_kills % 10 == 0:
                self._heal_player(1, increase_max=True)
            elif not self.infinite_mode and self.water_passive_kills in (14, 28):
                self._heal_player(1)
        self.score += e.gold_value * (10 if self.infinite_mode else 1)
        if self.spawn_decrease:
            self.spawn_interval = max(self.min_spawn_interval, self.spawn_interval - self.spawn_decrease)
        play_sound('kill')
        cx, cy = e.x, e.y+e.h//2
        if not self.infinite_mode:
            for _ in range(e.gold_value): self.coins.append(Coin(cx+random.randint(-10,10), cy+random.randint(-5,5), 1))
        if e.frozen:
            self.explosions.append(Explosion(cx, cy, (137, 220, 255), 28 if e.is_large else 18, element='ice'))
        else:
            self.explosions.append(Explosion(cx, cy, (255, 185, 70), 28 if e.is_large else 18))
            self.particles.append(Particle(e.x, e.y+e.h//2, (255,200,50) if e.is_large else (255,255,100), 22 if e.is_large else 14))
            # 副爆层：白闪核心 + 橙红飞散 + 残余火光，让死亡更有冲击力
            self.explosions.append(Explosion(cx, cy, (255, 245, 170), 14 if e.is_large else 9))
            self.particles.append(Particle(cx, cy, (255, 90, 40) if e.is_large else (255, 130, 50), 12 if e.is_large else 8))
            self.particles.append(Particle(cx + random.randint(-6, 6), cy + random.randint(-6, 6), (255, 255, 255), 7 if e.is_large else 4))
        if self._is_zongzong(e):
            for color, count in (
                ((255, 90, 35), 48),
                ((255, 225, 80), 38),
                ((80, 255, 130), 34),
                ((255, 255, 245), 26),
            ):
                self.explosions.append(Explosion(cx + random.randint(-8, 8), cy + random.randint(-8, 8), color, count))
            for _ in range(5):
                ox = random.randint(-38, 38)
                oy = random.randint(-28, 28)
                self.explosions.append(Explosion(cx + ox, cy + oy, (255, 150, 45), 24))
            self.particles.append(Particle(cx, cy, (255, 230, 80), 48))
            self.particles.append(Particle(cx, cy, (90, 255, 150), 38))
        if e.is_large and self.difficulty and self.difficulty.name == '简单' and random.random() < 0.25:
            self._heal_player(1)
            self.particles.append(Particle(cx, cy, (100, 255, 120), 18))
        if e.infected:
            blast_weapon = e.infected_weapon
            self.explosions.append(Explosion(cx, cy, (120, 255, 80), 32))
            self.explosions.append(Explosion(cx, cy, (190, 80, 255), 24))
            self.particles.append(Particle(cx, cy, (120, 255, 80), 28))
            self.particles.append(Particle(cx, cy, (190, 80, 255), 18))
            for other in self.enemies[:]:
                if math.hypot(other.x-cx, other.y+other.h//2-cy) < (130 if self.infinite_mode else 100):
                    if self._show_immune(other):
                        continue
                    other.hit_by(blast_weapon, (2.0 if self.infinite_mode else 1.5) * self._gift_damage_mult(config.game_ticks()))
                    self._spawn_hit_effect(other.x, other.y+other.h//2, (120, 255, 80), other.is_large)
                    self._play_skill_hit_sound(config.game_ticks())
                    if other.is_killed(blast_weapon):
                        self._kill_enemy(other)
        if e.factory_kind == 'original' and not linked:
            self._split_factory_enemy(e, config.game_ticks())

    def _play_skill_hit_sound(self, now):
        if now - self.last_skill_hit_sound >= 80:
            play_sound('hit')
            self.last_skill_hit_sound = now

    def _play_laser_hit_sound(self, now):
        if now - self.last_laser_hit_sound >= 220:
            play_sound('laser_hit')
            self.last_laser_hit_sound = now

    def _spawn_hit_effect(self, x, y, color, heavy=False, *, element=None):
        # 冲击波 + 火花 + 白色闪光，打击感更强
        self.explosions.append(Explosion(x, y, color, 14 if heavy else 10, heavy=heavy, element=element))
        self.particles.append(Particle(x, y, color, 18 if heavy else 12))
        self.particles.append(Particle(x, y, (255, 255, 255), 6 if heavy else 4))

    # ═══ Shop ═════════════════════════════════════════════════════════════════
    def _buy_or_equip_weapon(self, key):
        if key not in self.player.owned_weapons:
            cost = self._weapon_cost(key)
            if self.player.gold >= cost:
                self.player.gold -= cost
                self.player.owned_weapons.append(key)
                self.try_switch_weapon(key, self.player)
                play_sound('buy')
                if not self.infinite_mode:
                    self._close_shop()
            else:
                play_sound('error')
        else:
            if self.try_switch_weapon(key, self.player):
                self._close_shop()
            else:
                play_sound('error')

    def _buy_or_equip_character(self, key):
        cdef = CHARACTER_DEFS[key]
        if key in self.player.owned_characters:
            if self.try_switch_character(key, self.player):
                self._close_shop()
            else:
                play_sound('error')
            return
        cost = self._character_cost(cdef)
        if self.player.gold >= cost:
            self.player.gold -= cost
            self.player.owned_characters.append(key)
            self.try_switch_character(key, self.player)
            play_sound('buy')
            self._close_shop()
        else:
            play_sound('error')

    def _open_shop(self):
        self.shop_prev_state = self.state
        self.state = GameState.SHOP

    def _close_shop(self):
        self.state = GameState.PLAYING if self.infinite_mode else self.shop_prev_state

    def _handle_shop_click(self, mx, my):
        rects = self._mobile_shop_rects()
        if rects['close'].collidepoint(mx, my):
            self._close_shop()
            return
        for key in _WEAPON_KEYS_ORDERED:
            if rects[f'weapon:{key}'].collidepoint(mx, my):
                self._buy_or_equip_weapon(key)
                return
        for key in _CHAR_KEYS_ORDERED:
            if rects[f'character:{key}'].collidepoint(mx, my):
                self._buy_or_equip_character(key)
                return

    # ═══ Draw ═════════════════════════════════════════════════════════════════
    def draw(self, ui_labels=None, draw_background=True):
        self._ui_labels = ui_labels
        if draw_background:
            background = self.scrolling_background(self.bg.get_size())
            config.SCR.blit(background if background is not None else self.bg, (0, 0))
        if self.bg_transition_prev:
            now = config.game_ticks()
            if now < self.bg_transition_until:
                remaining = (self.bg_transition_until - now) / BG_FADE_MS
                alpha = round(255 * remaining * remaining * (3 - 2 * remaining))
                prev = self.bg_transition_prev
                prev.set_alpha(alpha)
                config.SCR.blit(prev, (0, 0))
            else:
                self.bg_transition_prev = None
        s = self.state
        if s == GameState.DIFFICULTY_SELECT: self._draw_difficulty_select()
        elif s == GameState.CUSTOM_DIFFICULTY: self._draw_custom_difficulty()
        elif s == GameState.MENU: self._draw_menu()
        elif s == GameState.KEY_SETTINGS: self._draw_key_settings()
        elif s in (GameState.PLAYING, GameState.BOSS_FIGHT): self._draw_game()
        elif s == GameState.SHOP: self._draw_game(); self._draw_shop_overlay()
        elif s == GameState.LEVEL_TRANSITION: self._draw_game(); self._draw_level_transition()
        elif s == GameState.GAME_OVER: self._draw_game(); self._draw_game_over()
        elif s == GameState.INFINITE_CONTINUE: self._draw_game(); self._draw_infinite_continue()
        elif s == GameState.INFINITE_COUNTDOWN: self._draw_game(); self._draw_infinite_countdown()
        elif s == GameState.VICTORY: self._draw_game(); self._draw_victory()
        elif s == GameState.PAUSED: self._draw_game(); self._draw_pause_overlay()
        elif s == GameState.PAID_REVIVE: self._draw_game(); self._draw_pause_overlay()
        if self.player_hit_impact is not None:
            self._draw_player_hit_impact()
        if self.exit_confirmation:
            self._draw_pause_overlay()
        self._ui_labels = None

    def _draw_player_hit_impact(self):
        started, (x, y) = self.player_hit_impact
        progress = (pygame.time.get_ticks() - started) / 380
        if progress >= 1:
            self.player_hit_impact = None
            return

        fade = 1 - progress
        radius = round(25 + 68 * progress)
        extent = radius + 24
        impact = effect_layer(config.SCR, (2 * extent + 1, 2 * extent + 1))
        center = (extent, extent)
        if progress < 0.25:
            _circle(impact, (255, 240, 210, round(170 * (1 - 4 * progress))), center, 27)
        _circle(impact, (255, 65, 35, round(240 * fade)), center, radius, max(1, round(7 * fade)))
        for index in range(8):
            angle = (index + 0.5) * math.tau / 8
            dx, dy = math.cos(angle), math.sin(angle)
            inner = radius * 0.75
            outer = radius + 22 * fade
            _line(impact, (255, 205, 130, round(255 * fade)),
                  (extent + dx * inner, extent + dy * inner),
                  (extent + dx * outer, extent + dy * outer), 3)
        blit_effect(config.SCR, impact, (x - extent, y - extent))

    def _draw_difficulty_select(self):
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        self._draw_scrim(195)
        top = 48 if config.MOBILE_LANDSCAPE_VIEW else max(30, height // 12)
        self._draw_text_fit('海洋生物入侵  /  OCEAN INVADERS', self.font_tiny, (126, 224, 221),
                            pygame.Rect(14, top, width - 28, 24), align='center')
        self._draw_title_text('选择难度', pygame.Rect(14, top + 26, width - 28, 54))
        modes = (
            ('简单', '轻松防守', '子弹免费', (105, 235, 192)),
            ('中等', '标准挑战', '标准战役 · 子弹免费', (118, 199, 255)),
            ('困难', '高压防线', '敌人更快、血量更高', (255, 155, 122)),
            ('无限', '生存挑战', '全角色武器 · 技能冷却缩短', (200, 171, 255)),
        )
        silhouettes = ('enemies/enemy_starfish.png', 'enemies/enemy_seahorse.png',
                       'enemies/enemy_crab.png', 'enemies/enemy_turtle.png')
        for i, ((_, rect), (name, tagline, detail, accent)) in enumerate(zip(self._mobile_difficulty_rects(), modes), 1):
            selected = rect.collidepoint(self.cursor_pos)
            self._draw_panel(*rect, accent=accent, fill=(12, 39, 55) if selected else (7, 26, 41), r=13, alpha=245)
            x, y, w, h = rect
            self._draw_text_fit(f'0{i}  /  {tagline}', self.font_tiny, accent,
                                pygame.Rect(x + 16, y + 12, w - 32, 22))
            self._draw_text_fit(name, self.font_med, WHITE, pygame.Rect(x + 16, y + 37, w - 32, 34))
            if self.desktop_controls:
                self._draw_keycap(pygame.K_0 + i, (rect.right - 24, y + 23))
            if h >= 120:
                position = (rect.right - 55, y + 42)
                if self.desktop_controls and isinstance(config.SCR, RenderSurface):
                    icon = image_asset(silhouettes[i - 1])
                    if icon:
                        config.SCR.blit(icon, position, logical_size=(42, 42), static=True)
                else:
                    icon = image_asset(silhouettes[i - 1], (42, 42))
                    if icon:
                        config.SCR.blit(icon, position)
                for step in range(4):
                    bar = pygame.Rect(x + 16 + step * 18, y + 82, 14, 4)
                    Draw.rect(config.SCR, accent if step < i else (44, 65, 81),
                                     bar, border_radius=2)
            self._draw_text_fit(detail, self.font_tiny, (194, 222, 231),
                                pygame.Rect(x + 16, y + h - 31, w - 32, 22))
        self._draw_button('自定义难度', *self._mobile_custom_button(), (62, 184, 170), key=pygame.K_c)

    def _mobile_difficulty_rects(self):
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        columns = 4 if config.MOBILE_LANDSCAPE_VIEW else 2
        rows = 4 // columns
        margin, gap = (width // 16 if columns == 4 else 18), 12
        card_w = (width - margin * 2 - gap * (columns - 1)) // columns
        start_y = max(132, height // 3 if columns == 4 else height // 4)
        button_y = self._mobile_custom_button().y
        card_h = min(148, max(82, (button_y - start_y - 18 - gap * (rows - 1)) // rows))
        return [
            (key, pygame.Rect(margin + (i % columns) * (card_w + gap),
                              start_y + (i // columns) * (card_h + gap), card_w, card_h))
            for i, key in enumerate(('easy', 'medium', 'hard', 'infinite'))
        ]

    def _mobile_custom_button(self):
        return pygame.Rect(config.SCREEN_WIDTH // 2 - 125, config.SCREEN_HEIGHT - 72, 250, 48)

    def _mobile_custom_rows(self):
        width = config.SCREEN_WIDTH
        columns = 3 if width >= 640 and config.SCREEN_HEIGHT < 460 else 2
        column_width = (width - (columns + 1) * 16) // columns
        row_step = 66 if width < 640 else 36
        row_height = 58 if width < 640 else 30
        start_y = 98 if width < 640 else 82
        rows_per_column = (len(self.custom_fields) + columns - 1) // columns
        result = []
        for index, (key, _label, _min_v, _max_v, _step) in enumerate(self.custom_fields):
            col, row = divmod(index, rows_per_column)
            x, y = 16 + col * (column_width + 16), start_y + row * row_step
            panel = pygame.Rect(x, y, column_width, row_height)
            if width < 640:
                minus = pygame.Rect(x + 8, y + 26, 32, 28)
                plus = pygame.Rect(x + column_width - 40, y + 26, 32, 28)
            else:
                minus = pygame.Rect(x + column_width - 82, y, 34, 30)
                plus = pygame.Rect(x + column_width - 42, y, 34, 30)
            result.append((key, panel, minus, plus))
        return result

    def _mobile_custom_action_rects(self):
        y = config.SCREEN_HEIGHT - 66
        width = min(132, (config.SCREEN_WIDTH - 48) // 3)
        return {
            'reset': pygame.Rect(16, y, width, 48),
            'back': pygame.Rect(config.SCREEN_WIDTH // 2 - width // 2, y, width, 48),
            'start': pygame.Rect(config.SCREEN_WIDTH - width - 16, y, width, 48),
        }

    def _mobile_menu_rects(self):
        height = config.SCREEN_HEIGHT
        start_y = height - (112 if height < 500 else 154)
        shop_y = height - (56 if height < 500 else 82)
        buttons = {
            'start': pygame.Rect(config.SCREEN_WIDTH // 2 - 140, start_y, 280, 52 if height < 500 else 58),
            'shop': pygame.Rect(config.SCREEN_WIDTH // 2 - 140, shop_y, 280, 48 if height < 500 else 52),
        }
        if self.desktop_controls:
            shop = buttons['shop']
            shop.w = 135
            buttons['keys'] = shop.move(145, 0)
        return buttons

    def _mobile_shop_rects(self):
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        columns = 2 if width < 640 else 4
        margin, gap, card_h = 14, 10, 62 if width < 640 else 64
        card_w = (width - margin * 2 - gap * (columns - 1)) // columns
        top = max(12, (height - 430) // 2) if width < 640 else 12
        weapon_y = top + (108 if width < 640 else 94)
        character_y = weapon_y + (card_h + 10) * (4 // columns) + (32 if width < 640 else 44)
        rects = {'close': pygame.Rect(width - 56, top, 42, 42)}
        for index, key in enumerate(_WEAPON_KEYS_ORDERED):
            x = margin + (index % columns) * (card_w + gap)
            y = weapon_y + (index // columns) * (card_h + 10)
            rects[f'weapon:{key}'] = pygame.Rect(x, y, card_w, card_h)
        for index, key in enumerate(_CHAR_KEYS_ORDERED):
            x = margin + (index % columns) * (card_w + gap)
            y = character_y + (index // columns) * (card_h + 10)
            rects[f'character:{key}'] = pygame.Rect(x, y, card_w, card_h)
        return rects

    def _draw_custom_difficulty(self):
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((3, 12, 28, 185))
        config.SCR.blit(ov, (0, 0))
        self._draw_title_text('自定义难度', pygame.Rect(16, 18, config.SCREEN_WIDTH - 32, 48), accent=(110, 210, 255))
        if self.desktop_controls:
            self._draw_text_fit('↑ ↓ 选择项目', self.font_tiny, (190, 225, 245),
                                pygame.Rect(16, 66, config.SCREEN_WIDTH - 32, 20), align='center')
        for index, (key, row, minus, plus) in enumerate(self._mobile_custom_rows()):
            focused = self.desktop_controls and index == self.custom_row
            self._draw_panel(*row, accent=(130, 218, 237) if focused else (76, 139, 160),
                             fill=(16, 47, 64) if focused else (7, 21, 34), r=7)
            label = next(item[1] for item in self.custom_fields if item[0] == key)
            value = self.custom_values[key]
            value_text = f'{value:.2f}' if isinstance(value, float) else str(value)
            if config.SCREEN_WIDTH < 640:
                self._draw_text_fit(label, self.font_tiny, (225, 240, 255), pygame.Rect(row.x + 6, row.y + 2, row.w - 12, 22))
                value_rect = pygame.Rect(minus.right + 4, minus.y, plus.x - minus.right - 8, 28)
                self._draw_text_fit(value_text, self.font_tiny, GOLD_COLOR, value_rect, align='center')
                self._draw_step_button('←' if focused else '-', minus.x, minus.y, minus.size)
                self._draw_step_button('→' if focused else '+', plus.x, plus.y, plus.size)
            else:
                label_w = min(168, row.w - 160)
                self._draw_text_fit(label, self.font_tiny, (225, 240, 255), pygame.Rect(row.x + 8, row.y + 4, label_w, row.h - 8))
                value_rect = pygame.Rect(row.x + label_w + 10, row.y + 4, row.w - label_w - 108, row.h - 8)
                self._draw_text_fit(value_text, self.font_tiny, GOLD_COLOR, value_rect, align='right')
                self._draw_step_button('←' if focused else '-', minus.x, minus.y)
                self._draw_step_button('→' if focused else '+', plus.x, plus.y)
        actions = self._mobile_custom_action_rects()
        self._draw_button('重置', actions['reset'].x, actions['reset'].y, actions['reset'].w, actions['reset'].h, (40, 120, 60), key=pygame.K_r)
        self._draw_button('返回', actions['back'].x, actions['back'].y, actions['back'].w, actions['back'].h, key=pygame.K_ESCAPE)
        self._draw_button('开始', actions['start'].x, actions['start'].y, actions['start'].w, actions['start'].h, (40, 120, 60), key=pygame.K_RETURN)

    def _draw_step_button(self, text, x, y, size=(34, 30)):
        w, h = size
        self._draw_button(text, x, y, w, h)

    def _draw_menu(self):
        width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        self._draw_scrim(156)
        title_y = 10 if height < 500 else max(28, int(height * 0.08))
        title_w = min(360 if height < 500 else 460, width - 32)
        buttons = self._mobile_menu_rects()
        columns = 2 if width < 640 else 4
        card_h = 62 if width < 640 else 48 if height < 500 else 58
        if height < 500:
            subtitle_y = int(height * 0.42)
            weapon_y = int(height * 0.54)
        else:
            subtitle_y = int(height * 0.28)
            weapon_y = int(height * 0.38)
        if self.desktop_controls:
            weapon_y = buttons['start'].top - (card_h + 8) * (4 // columns) - 4
            subtitle_y = weapon_y - 62
            title_space = subtitle_y - title_y - 8
            title_ratio = (self.title_image.get_height() / self.title_image.get_width()
                           if self.title_image else TITLE_CROP_RATIO)
            title_w = max(1, min(title_w, int(title_space / (title_ratio * TITLE_MAX_SCALE))))
        self._draw_title_image(title_y, title_w)
        self._draw_text_fit('消灭入侵的海洋生物！', self.font_med, (200, 230, 255),
                            pygame.Rect(10, subtitle_y, width - 20, 34), align='center')
        if self.difficulty:
            self._draw_text_fit(f'当前难度: {self.difficulty.name}', self.font_tiny, GOLD_COLOR,
                                pygame.Rect(10, subtitle_y + 32, width - 20, 22), align='center')
        margin, gap = 14, 10
        card_w = (width - margin * 2 - gap * (columns - 1)) // columns
        for index, (key, wdef) in enumerate(WEAPON_DEFS.items()):
            x = margin + (index % columns) * (card_w + gap)
            y = weapon_y + (index // columns) * (card_h + 8)
            self._draw_panel(x, y, card_w, card_h, accent=(85, 185, 245), fill=(12, 36, 68), r=10, alpha=205)
            icon = self.weapon_icons[key]
            position = icon.get_rect(center=(x + 34, y + card_h // 2))
            if self.desktop_controls and isinstance(config.SCR, RenderSurface):
                source = image_asset(_WEAPON_ASSETS[key]) or icon
                config.SCR.blit(source, position, logical_size=icon.get_size(), static=True)
            else:
                config.SCR.blit(icon, position)
            self._draw_text_fit(wdef.name, self.font_small, WHITE, pygame.Rect(x + 64, y + 7, card_w - 72, 22))
            cost = self._weapon_cost(key)
            self._draw_text_fit('免费' if cost == 0 else f'{cost}金币', self.font_tiny, GOLD_COLOR,
                                pygame.Rect(x + 64, y + card_h - 21, card_w - 72, 18))
        self._draw_button('开 始 游 戏', buttons['start'].x, buttons['start'].y,
                          buttons['start'].w, buttons['start'].h, key=pygame.K_RETURN)
        self._draw_button('商    店', buttons['shop'].x, buttons['shop'].y,
                          buttons['shop'].w, buttons['shop'].h, (40, 120, 60), key=pygame.K_b)
        if self.desktop_controls:
            self._draw_button('按键设置', *buttons['keys'], key=pygame.K_c)

    def _draw_key_settings(self):
        self._draw_scrim(212)
        width = config.SCREEN_WIDTH
        self._draw_title_text('按键设置', pygame.Rect(16, 16, width - 32, 46), font=self.font_med)
        hint = '点击一项后按新键，Esc 取消或返回'
        if self.desktop_controls:
            hint = ('按未占用的新键 · Esc 取消' if self.setting_key_action else
                    '↑ ↓ 选择 · Enter 修改 · Esc 返回')
        self._draw_text_fit(hint, self.font_tiny, (190, 225, 245),
                            pygame.Rect(16, 60, width - 32, 20), align='center')
        for index, (action, label, rect) in enumerate(self._key_settings_rects()):
            x, y, w, h = rect
            active = action == self.setting_key_action
            fill = (41, 67, 47) if active else (9, 24, 44)
            focused = self.desktop_controls and index == self.key_settings_row
            accent = (255, 230, 120) if active or focused else (70, 155, 210)
            self._draw_panel(*rect, accent=accent, fill=fill, r=7, alpha=220)
            self._draw_text_fit(label.removeprefix('P1 '), self.font_tiny, (225, 240, 255),
                                pygame.Rect(x + 10, y, w // 2, h))
            self._draw_text_fit('按新键…' if active else self._control_name(action), self.font_tiny, accent,
                                pygame.Rect(x + w // 2 + 10, y, w // 2 - 20, h), align='right')
        reset, back = self._key_settings_buttons()
        self._draw_button('恢复默认', *reset, (40, 120, 60), key=pygame.K_r)
        self._draw_button('返回', *back, key=pygame.K_ESCAPE)

    def _player_downed_age(self, player, now):
        if self.player_defeat_visual_at is not None and self.state in (
                GameState.GAME_OVER, GameState.PAID_REVIVE,
                GameState.INFINITE_CONTINUE, GameState.INFINITE_COUNTDOWN):
            return pygame.time.get_ticks() - self.player_defeat_visual_at
        return None

    def _players_to_draw(self):
        return self.players

    def _draw_game(self):
        ui_labels = self._ui_labels
        active = self.state in (GameState.PLAYING, GameState.BOSS_FIGHT)
        if not active:
            self._ui_labels = None  # Keep all labels behind the modal, like the scene itself.
        if isinstance(self.boss, OrochiBoss) and self.boss.skill == 'storm':
            now = config.game_ticks()
            self.boss.draw_storm_lightning(config.SCR, now)
        draw_water_drift(config.SCR, config.game_ticks())
        if self.boss and self.boss.signature:
            self.boss.signature.draw(config.SCR, self.boss, config.game_ticks())
        for ms in self.magnetic_storms: ms.draw(config.SCR)
        linked = [e.rect().center for e in self.enemies if getattr(e, 'factory_link_until', 0)]
        for index, start in enumerate(linked):
            for end in linked[index + 1:]:
                draw_electric_arc(config.SCR, start, end, (110, 230, 255), 235, config.game_ticks(), index)
        for e in self.enemies:
            e.draw(config.SCR)
            if not self.infinite_mode:
                if self.boss and self.boss.absorb_target is e:
                    Draw.rect(config.SCR, (190, 85, 255), e.rect().inflate(12, 12), 2)
                warning_seconds = (1.4, 1.2, 1.0)[self._campaign_tier()]
                if (not getattr(e, 'factory_link_until', 0)
                        and getattr(e, 'factory_kind', '') != 'mini_boss'
                        and config.GAME_AREA_BOTTOM + 20 - e.y <= e.speed * 60 * warning_seconds):
                    Draw.line(config.SCR, (255, 100, 80), (e.rect().left, config.GAME_AREA_BOTTOM - 3),
                                     (e.rect().right, config.GAME_AREA_BOTTOM - 3), 3)
        for c in self.coins: c.draw(config.SCR)
        for box in self.gift_boxes: box.draw(config.SCR)
        for b in self.bullets: b.draw(config.SCR)
        for ep in self.enemy_projectiles: ep.draw(config.SCR)
        for p in self.particles: p.draw(config.SCR)
        for ex in self.explosions: ex.draw(config.SCR)
        for fw in self.fire_walls: fw.draw(config.SCR)
        for ice in self.ice_floors: ice.draw(config.SCR)
        ice_casts = {}
        for sp in self.skill_projectiles:
            if sp.ptype == 'ice_ball':
                ice_casts.setdefault((sp.owner, sp.spawn_time), []).append(sp)
        now = config.game_ticks()
        for shots in ice_casts.values():
            for left, right in zip(shots, shots[1:]):
                draw_electric_arc(config.SCR, (left.x, left.y), (right.x, right.y),
                                  (88, 199, 255), 220, now, left.angle)
        for sp in self.skill_projectiles: sp.draw(config.SCR)
        for laser in self.radiation_lasers: laser.draw(config.SCR)
        for shield in self.dart_shields: shield.draw(config.SCR)
        self._draw_laser_impacts()
        for lt in self.lightnings:
            if not lt.is_expired(): lt.draw(config.SCR)
        for bp in self.boss_projectiles:
            previous = getattr(bp, 'lightning_previous', None)
            if previous in self.boss_projectiles:
                draw_electric_arc(config.SCR, (previous.x, previous.y), (bp.x, bp.y),
                                  (255, 190, 75), 230, now, bp.angle)
        for bp in self.boss_projectiles: bp.draw(config.SCR)
        if self.boss:
            signature = self.boss.signature
            if not signature or not signature.draw_bite(config.SCR, self.boss):
                self.boss.draw(config.SCR)
            if not self.infinite_mode:
                now = config.game_ticks()
                for shot in self.warned_boss_shots:
                    if shot.big_fireball or isinstance(shot, ReturningAxe):
                        continue
                    if isinstance(shot, CrescentWave):
                        zone = self._shot_warning_zone(shot)
                        _rect(config.SCR, (255, 112, 53, 44), zone)
                        Draw.rect(config.SCR, (255, 174, 83), zone, 2)
                        continue
                    angle = math.radians(shot.angle)
                    distance = max(0, config.SCREEN_HEIGHT - shot.y)
                    Draw.line(config.SCR, (255, 150, 65), (int(shot.x), int(shot.y)),
                                     (int(shot.x + math.tan(angle) * distance), config.SCREEN_HEIGHT), 3)
                if isinstance(self.boss, ZongBoss):
                    message = None
                    if self.boss.fusion_warning_mode:
                        message = '反射预警 · 停火' if self.boss.fusion_warning_mode == 'shield' else '融合预警 · 躲避火弹'
                    elif 0 < self.boss.next_revive_check - now <= 2000 and not self.boss.campaign_revived:
                        message = '分身即将复活'
                    if message:
                        self._draw_text_fit(message, self.font_small, GOLD_COLOR,
                                            pygame.Rect(0, 50, config.SCREEN_WIDTH, 30), align='center')
        self._draw_muzzle_flashes()
        self._draw_skill_flash()
        self._draw_hud()
        for i, player in enumerate(self._players_to_draw(), 1):
            downed_age = self._player_downed_age(player, now)
            if downed_age is not None and player.character in CHARACTER_DEFS:
                player.draw(config.SCR, downed_age=downed_age)
                continue
            if self._whale_is_swallowing():
                progress = self.boss.swallow_progress(now)
                if progress < .96:
                    player.draw(config.SCR, visual_scale=max(.08, 1 - progress ** 2))
                continue
            player.draw(config.SCR)
            self._draw_invincible_shield(player)
            self._draw_niu_freeze(player)
            self._draw_player_label(player, f'P{i}')
            self._draw_water_boost_status(player)
        self._draw_water_heal_effects()
        slow_until = max(player.snow_slow_until for player in self.players)
        ZongBoss.draw_snow(config.SCR, slow_until, self.font_small,
                           50 if self.infinite_mode else (15, 20, 25)[self._campaign_tier()])
        self._draw_level_title()
        self._draw_gift_lightning_icon()
        self._draw_rage_banner()
        if active:
            self.mobile_controls.draw(config.SCR, self)
            if self.desktop_controls:
                fps = round(self.clock.get_fps())
                self._draw_text_fit(f'FPS {fps or "--"}', self.font_tiny, (180, 220, 232),
                                    self.hud_fps_rect, align='right')
        if self.boss:
            self._draw_boss_hud()
        self._ui_labels = ui_labels

    def _draw_boss_hud(self):
        boss = self.boss
        width = 420 if config.MOBILE_LANDSCAPE_VIEW else 144
        x = (config.SCREEN_WIDTH - width) // 2 if config.MOBILE_LANDSCAPE_VIEW else 178
        y = 8
        now = config.game_ticks()
        entering = now < boss.intro_until
        accent = (255, 184, 112) if entering else (100, 176, 192)
        self._draw_panel(x, y, width, 39, accent=accent, fill=(19, 28, 41), r=7, alpha=242)
        name = boss.name
        if isinstance(boss, ZongBoss):
            name = '小粽粽 × 2'
            if boss.fusion_mode:
                name += ' · 护盾' if boss.fusion_mode == 'shield' else ' · 狂暴'
        self._draw_text_fit(name, self.font_tiny, WHITE, pygame.Rect(x + 6, y + 2, width - 12, 16),
                            align='center')
        bar = pygame.Rect(x + 5, y + 20, width - 10, 15)
        ratio = max(0, min(1, boss.hp / boss.max_hp))
        color = (40, 200, 80) if ratio > 0.5 else (240, 200, 40) if ratio > 0.25 else (240, 60, 50)
        Draw.rect(config.SCR, (45, 49, 62), bar, border_radius=4)
        if ratio:
            Draw.rect(config.SCR, color, (bar.x, bar.y, round(bar.w * ratio), bar.h), border_radius=4)
        hp = f'{int(boss.hp)} / {int(boss.max_hp)}'
        self._draw_text_fit(hp, self.font_tiny, WHITE, bar, align='center')
        remaining = self.warned_boss_shots_at - now if self.warned_boss_shots else 0
        if boss.signature:
            countdown = max(0, boss.signature.impact_at - now)
            label = f'{boss.signature.name} · {countdown / 1000:.1f}s' if countdown else boss.signature.name
            self._draw_text_fit(label, self.font_tiny, (255, 229, 181),
                                pygame.Rect(x, y + 40, width, 18), align='center')
        elif isinstance(boss, OrochiBoss) and (boss.skill == 'storm' or now < boss.invincible_until):
            if boss.skill == 'storm':
                heads = sum(hp > 0 for hp in boss.head_hp)
                seconds = max(0, boss.STORM_DURATION - boss.age(now)) / 1000
                label = f'击碎蛇头 · {heads} · {seconds:.1f}s'
            else:
                label = f'再生护盾 · {(boss.invincible_until - now) / 1000:.1f}s'
            self._draw_text_fit(label, self.font_tiny, (180, 215, 255),
                                pygame.Rect(x, y + 40, width, 18), align='center')
        elif remaining > 0:
            self._draw_text_fit(f'危险 · {remaining / 1000:.1f}s', self.font_tiny, (255, 205, 139),
                                pygame.Rect(x, y + 40, width, 18), align='center')
        elif entering:
            self._draw_text_fit('首领来袭', self.font_tiny, accent,
                                pygame.Rect(x, y + 40, width, 18), align='center')

    def _draw_rage_banner(self):
        """终极狂暴提示：屏幕中间红金大字，持续约 3s。"""
        now = config.game_ticks()
        if now >= self.rage_banner_until:
            return
        rem = self.rage_banner_until - now
        alpha = min(235, int(rem / 3000 * 235))
        pulse = 1 + 0.06 * math.sin(now * 0.012)
        if self.desktop_controls and isinstance(config.SCR, RenderSurface):
            text = '终极狂暴！'
            center = (config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)
            panel = pygame.Rect(0, 0, *self.font_large.size(text)).inflate(60, 28)
            panel.center = center
            Draw.rect(config.SCR, (70, 10, 12, min(210, alpha)), panel, border_radius=14)
            Draw.rect(config.SCR, (255, 180, 40, min(220, alpha)), panel.inflate(-6, -6), 4, 12)
            blit_label(config.SCR, self.font_large, text, (255, 60, 40), center,
                       round(48 * pulse), bold=True, alpha=max(0, alpha - 60))
            blit_label(config.SCR, self.font_large, text, (255, 220, 80), center, 48, bold=True, alpha=alpha)
            return
        surf = self.font_large.render('终极狂暴！', True, (255, 60, 40))
        surf2 = self.font_large.render('终极狂暴！', True, (255, 220, 80))
        pad_x, pad_y = 30, 14
        w = surf.get_width() + pad_x * 2
        h = surf.get_height() + pad_y * 2
        x = config.SCREEN_WIDTH // 2 - w // 2
        y = config.SCREEN_HEIGHT // 2 - h // 2
        # 背景 + 红金描边
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        _rect(bg, (70, 10, 12, min(210, alpha)), (0, 0, w, h), border_radius=14)
        _rect(bg, (255, 180, 40, min(220, alpha)), (3, 3, w - 6, h - 6), width=4, border_radius=12)
        config.SCR.blit(bg, (x, y))
        # 双层描字（红底金字 + 脉动缩放）
        sx = config.SCREEN_WIDTH // 2
        sy = config.SCREEN_HEIGHT // 2
        tw, th = surf.get_width(), surf.get_height()
        tx, ty = sx - tw // 2, sy - th // 2
        glow = pygame.transform.smoothscale(surf, (int(tw * pulse), int(th * pulse)))
        gw, gh = glow.get_size()
        glow.set_alpha(max(0, alpha - 60))
        config.SCR.blit(glow, (sx - gw // 2, sy - gh // 2))
        surf2.set_alpha(alpha)
        config.SCR.blit(surf2, (tx, ty))

    def _draw_gift_lightning_icon(self):
        """闪电礼包激活期间在屏幕正中心显示脉动反应堆。"""
        now = config.game_ticks()
        if now >= self.gift_lightning_icon_until:
            return
        cx, cy = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2
        s = 1 + 0.10 * math.sin(now * 0.009)
        # 光晕
        _circle(config.SCR, (255, 220, 90, 40), (cx, cy), int(46 * s), 3)
        _circle(config.SCR, (255, 235, 160, 30), (cx, cy), int(56 * s), 1)
        width, height = round(96 * s), round(64 * s)
        size = (width, height)
        position = (cx - width // 2, cy - height // 2)
        reactor = image_asset('effects/lightning_reactor.png')
        if reactor is not None:
            if isinstance(config.SCR, RenderSurface):
                config.SCR.blit(reactor, position, logical_size=size, static=True)
            else:
                config.SCR.blit(scale_surface_cached(reactor, size), position)
        else:
            _circle(config.SCR, (113, 30, 24), (cx, cy), round(29 * s))
            _circle(config.SCR, (255, 163, 48), (cx, cy), round(24 * s), 4)
            _circle(config.SCR, (255, 227, 115), (cx, cy), round(12 * s))
        # 环绕星点
        for i in range(6):
            a = now * 0.008 + i * math.tau / 6
            px = cx + math.cos(a) * 42 * s
            py = cy + math.sin(a) * 42 * s
            _circle(config.SCR, (255, 240, 160, 150), (int(px), int(py)), 2)

    def _draw_gift_messages(self):
        now = config.game_ticks()
        for msg in self.gift_messages[:]:
            text, color, end, start = msg
            if now >= end:
                self.gift_messages.remove(msg)
                continue
            life = max(1, end - start)
            t = (now - start) / life
            alpha = max(0, min(230, int(230 * (1.0 - max(0, t - 0.55) / 0.45))))
            y = 118 - int(18 * t)
            if self.desktop_controls and isinstance(config.SCR, RenderSurface):
                tw, th = self.font_large.size(text)
                center = (config.SCREEN_WIDTH // 2, y + th // 2)
                panel = pygame.Rect(0, 0, tw + 52, th + 24)
                panel.center = center
                Draw.rect(config.SCR, (10, 20, 35, min(205, alpha)), panel, border_radius=10)
                Draw.rect(config.SCR, (*color[:3], min(200, alpha)), panel.inflate(-4, -4), 3, 9)
                blit_label(config.SCR, self.font_large, text, tuple(color[:3]), center, 48, bold=True, alpha=alpha)
                continue
            surf = self.font_large.render(text, True, color)
            pad_x, pad_y = 26, 12
            x = config.SCREEN_WIDTH // 2 - surf.get_width() // 2
            bg = pygame.Surface((surf.get_width() + pad_x * 2, surf.get_height() + pad_y * 2), pygame.SRCALPHA)
            _rect(bg, (10, 20, 35, min(205, alpha)), (0, 0, bg.get_width(), bg.get_height()), border_radius=10)
            _rect(bg, (*color[:3], min(200, alpha)), (2, 2, bg.get_width() - 4, bg.get_height() - 4), width=3, border_radius=9)
            config.SCR.blit(bg, (x - pad_x, y - pad_y))
            text_surf = surf.copy()
            text_surf.set_alpha(alpha)
            config.SCR.blit(text_surf, (x, y))
        self._draw_level_title()

    def _draw_invincible_shield(self, player):
        now = config.game_ticks()
        if not self._player_is_invincible(now):
            return
        rem = self.player_invincible_until - now
        pulse = 1 + 0.12 * math.sin(now * 0.02)
        alpha = min(170, 70 + rem // 18)
        _circle(config.SCR, (190, 235, 255, alpha), (int(player.x), int(player.y)), int(48 * pulse), 3)
        _circle(config.SCR, (255, 255, 255, alpha // 2), (int(player.x), int(player.y)), int(36 * pulse), 2)

    def _draw_niu_freeze(self, player):
        now = config.game_ticks()
        if now >= player.niu_freeze_until:
            return
        cx, cy = int(player.x), int(player.y)
        _circle(config.SCR, (105, 215, 255, 210), (cx, cy), 39, 3)
        for angle in (0, 60, 120):
            rad = math.radians(angle)
            dx, dy = math.cos(rad) * 29, math.sin(rad) * 29
            _line(config.SCR, (205, 250, 255), (cx - dx, cy - dy), (cx + dx, cy + dy), 3)

    def _draw_level_title(self):
        now = config.game_ticks()
        if now >= self.level_title_until:
            return
        level = self.infinite_background_level if self.infinite_mode else self.current_level
        lcfg = LEVEL_CONFIGS[level - 1]
        label = f'第{self.chapter}章' if self.infinite_mode else f'第{level}关'
        width = 200 if config.MOBILE_LANDSCAPE_VIEW else 166
        if level == 9:
            width = 270
        plaque = pygame.Rect(0, 102, width, 64)
        plaque.centerx = config.SCREEN_WIDTH // 2
        self._draw_panel(*plaque, accent=(106, 214, 218), fill=(5, 29, 45), r=10, alpha=220)
        self._draw_text_fit(label, self.font_tiny, GOLD_COLOR,
                            pygame.Rect(plaque.x + 8, plaque.y + 5, width - 16, 19), align='center')
        self._draw_title_text(lcfg['title'], pygame.Rect(plaque.x + 8, plaque.y + 25, width - 16, 32),
                              font=self.font_med)

    def _draw_laser_impacts(self):
        """激光命中 Boss 的灼烧冲击动画：扩散双环 + 放射火花 + 灼烧亮点。"""
        now = config.game_ticks()
        for impact in self.laser_impacts[:]:
            ix, iy, t0 = impact
            age = now - t0
            if age > 300:
                self.laser_impacts.remove(impact)
                continue
            p = age / 300
            fade = 1.0 - p
            draw_glow(config.SCR, (ix, iy), 30, (120, 255, 140), int(255 * fade))
            ring_r = int(12 + p * 52)
            _circle(config.SCR, (120, 255, 140, int(200 * fade)), (ix, iy), ring_r, 3)
            _circle(config.SCR, (200, 90, 255, int(120 * fade)), (ix, iy), int(ring_r * 0.65), 2)
            for si in range(6):
                a = si * math.tau / 6 + t0 * 0.02
                d = 10 + p * 40
                _circle(config.SCR, (210, 255, 170, int(220 * fade)),
                        (ix + int(math.cos(a) * d), iy + int(math.sin(a) * d)), 3)
            _circle(config.SCR, (255, 255, 220, int(230 * fade)), (ix, iy), int(9 * fade) + 2)

    def _draw_water_heal_effects(self):
        now = config.game_ticks()
        for player, start in self.water_heal_effects[:]:
            age = now - start
            if age >= 800:
                self.water_heal_effects.remove((player, start))
                continue
            x, y = player.x, player.y - 8
            for i in range(8):
                progress = min(1, (age + i * 34) / 800)
                radius = 6 + 52 * (1 - progress)
                angle = i * math.tau / 8 + progress * 3
                px, py = x + math.cos(angle) * radius, y + math.sin(angle) * radius
                alpha = int(230 * (1 - progress))
                _line(config.SCR, (95, 237, 255, alpha), (px, py),
                      (px + math.cos(angle) * 9, py + math.sin(angle) * 9), 3)
                _circle(config.SCR, (216, 255, 249, alpha), (px, py), 3)
            draw_glow(config.SCR, (round(x), round(y)), 23, (105, 255, 231),
                      int(230 * math.sin(math.pi * age / 800)))

    def _flash_skill(self, player, now):
        if player.character in CHARACTER_DEFS:
            self.skill_flash = (player.x, player.y - 22, now, CHARACTER_DEFS[player.character].color)

    def _draw_skill_flash(self):
        if self.skill_flash is None:
            return
        x, y, start, color = self.skill_flash
        progress = max(0, config.game_ticks() - start) / 340
        if progress >= 1:
            self.skill_flash = None
            return
        radius = round(16 + 42 * progress)
        alpha = round(205 * (1 - progress))
        center = (round(x), round(y))
        draw_glow(config.SCR, center, 38, color, alpha)
        _circle(config.SCR, (*color, alpha // 2), center, radius + 4, 3)
        _circle(config.SCR, (*color, alpha), center, radius, 2)
        for ray in range(6):
            angle = ray * math.tau / 6 + progress * 0.5
            dx, dy = math.cos(angle), math.sin(angle)
            _line(config.SCR, (235, 248, 255, alpha), (x + dx * radius, y + dy * radius),
                  (x + dx * (radius + 9), y + dy * (radius + 9)), 2)

    def _draw_muzzle_flashes(self):
        now = config.game_ticks()
        for player, start, weapon in self.muzzle_flashes[:]:
            progress = max(0, now - start) / 90
            if progress >= 1:
                self.muzzle_flashes.remove((player, start, weapon))
                continue
            strength = 1 - progress
            alpha = round(245 * strength)
            x, y = player.x, player.y - 34
            width, height = {'pistol': (11, 24), 'rifle': (9, 30),
                             'shotgun': (22, 24), 'sniper': (12, 44)}[weapon]
            width, height = round(width * strength) + 4, round(height * strength) + 6
            color = WEAPON_DEFS[weapon].color
            draw_glow(config.SCR, (round(x), round(y - height / 3)), 28, color, alpha)
            _polygon(config.SCR, (*color, alpha),
                     [(x, y - height), (x - width, y + 3), (x, y + 7), (x + width, y + 3)])
            _polygon(config.SCR, (255, 245, 190, alpha),
                     [(x, y - height * 0.68), (x - width * 0.42, y + 2), (x + width * 0.42, y + 2)])
            for side in (-1, 1):
                _line(config.SCR, (*color, alpha * 2 // 3), (x + side * width, y - 4),
                      (x + side * (width + 7), y - height * 0.62), 2)

    def _draw_player_label(self, player, label):
        bounds = player.rect()
        badge = pygame.Rect(0, 0, 28, 16)
        badge.bottomright = (bounds.left - 4, bounds.bottom + 8)
        badge.clamp_ip(pygame.Rect(0, 0, config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        _rect(config.SCR, (5, 18, 34, 185), badge, border_radius=5)
        color = (255, 230, 160) if label == 'P1' else (170, 230, 255)
        self._draw_text_fit(label, self.font_tiny, color, badge, align='center')

    def _draw_water_status_badge(self, cx, ty, label, bg, border, text_color):
        tw, th = 86, 22
        tx = max(8, min(config.SCREEN_WIDTH - tw - 8, cx - tw // 2))
        ty = max(56, ty)
        _rect(config.SCR, (*bg, 210), (tx, ty, tw, th), border_radius=6)
        _rect(config.SCR, (*border, 160), (tx, ty, tw, th), border_radius=6, width=1)
        self._draw_text_fit(label, self.font_tiny, text_color, pygame.Rect(tx + 6, ty + 2, tw - 12, th - 4), align='center')

    def _draw_water_boost_status(self, player):
        now = config.game_ticks()
        rem = player.water_boost_until - now
        haste_rem = getattr(player, 'water_haste_until', 0) - now
        if rem <= 0 and haste_rem <= 0:
            return
        pulse = 1 + 0.12 * math.sin(now * 0.014)
        cx, cy = int(player.x), int(player.y - 4)
        label_y = cy - 72
        if rem > 0:
            _circle(config.SCR, (255, 35, 35, 70), (cx, cy), int(38 * pulse), 4)
            _circle(config.SCR, (255, 80, 60, 45), (cx, cy), int(48 * pulse), 2)
            for a in range(0, 360, 60):
                rad = math.radians(a + now * 0.08)
                _circle(config.SCR, (255, 50, 35, 150), (cx + math.cos(rad) * 34, cy + math.sin(rad) * 24), 4)
            self._draw_water_status_badge(cx, label_y, f'水增益 {rem/1000:.1f}s', (90, 12, 18), (255, 95, 80), (255, 235, 220))
            label_y -= 24
        if haste_rem > 0:
            _circle(config.SCR, (80, 235, 255, 70), (cx, cy), int(36 * pulse), 4)
            _circle(config.SCR, (120, 255, 220, 50), (cx, cy), int(46 * pulse), 2)
            self._draw_water_status_badge(cx, label_y, f'水急速 {haste_rem/1000:.1f}s', (10, 50, 60), (90, 230, 255), (220, 245, 255))

    @property
    def hud_fps_rect(self):
        return pygame.Rect(111, 88 if self.infinite_mode else 66, 49, 21)

    @property
    def hud_diagnostics_y(self):
        return 119 if self.infinite_mode else 97

    def _draw_gift_hud(self, now, right, y):
        effects = (
            ('火弹', self.gift_fire_until, (255, 153, 92)),
            ('冰弹', self.gift_ice_until, (122, 198, 255)),
            ('极速', max(p.gift_speed_until for p in self.players), (134, 244, 181)),
            ('闪电', self.gift_lightning_icon_until, (255, 219, 116)),
        )
        for name, end, color in reversed(effects):
            if end <= now:
                continue
            x = right - 70
            self._draw_panel(x, y, 70, 18, accent=color, fill=(6, 23, 37), r=6, alpha=219)
            seconds = (end - now + 999) // 1000
            self._draw_text_fit(f'{name} {seconds}s', self.font_tiny, color,
                                pygame.Rect(x + 4, y + 1, 62, 16), align='center')
            right = x - 4

    def _draw_hud(self):
        now = config.game_ticks()
        self._draw_panel(8, 8, 162, self.hud_diagnostics_y - 9, accent=(89, 188, 206), fill=(6, 23, 37), r=10, alpha=219)
        if self.desktop_controls and isinstance(config.SCR, RenderSurface):
            source = image_asset('ui/coin.png') or self.coin_surface
            config.SCR.blit(source, (16, 13), logical_size=self.coin_surface.get_size(), static=True)
        else:
            config.SCR.blit(self.coin_surface, (16, 13))
        self._draw_text_fit(str(self.player.gold), self.font_small, GOLD_COLOR, pygame.Rect(42, 10, 46, 26))
        if self.player.current_weapon:
            self._draw_text_fit(WEAPON_DEFS[self.player.current_weapon].name, self.font_tiny,
                                (166, 213, 228), pygame.Rect(77, 11, 83, 24), align='right')
        Draw.line(config.SCR, (55, 102, 121), (17, 38), (160, 38))
        self._draw_text_fit(f'第 {self.chapter} 章  ·  击杀 {self.kill_count}', self.font_tiny, WHITE,
                            pygame.Rect(17, 43, 143, 21))
        if self.infinite_mode:
            self._draw_text_fit(f'积分 {self.score}', self.font_tiny, (180, 220, 232),
                                pygame.Rect(17, 66, 68, 21))
            self._draw_text_fit(f'死亡次数 {self.infinite_deaths}', self.font_tiny, (180, 220, 232),
                                pygame.Rect(87, 66, 73, 21), align='right')
            minutes, seconds = divmod((now - self.infinite_start_time) // 1000, 60)
            self._draw_text_fit(f'用时 {minutes:02d}:{seconds:02d}', self.font_tiny,
                                (180, 220, 232), pygame.Rect(17, 88, 90, 21))
        else:
            self._draw_text_fit(f'第 {self.current_level} 关  ·  生命 {self.lives}', self.font_tiny,
                                (180, 220, 232), pygame.Rect(17, 66, 90, 21))
        left, health, right = self._hud_controls()
        labels = self._ui_labels
        # Keep the bottom controls and their text behind the player on every frame.
        self._ui_labels = None
        self._draw_button('-', *left, (50, 105, 125))
        self._draw_button('+', *right, (50, 105, 125))
        if self.desktop_controls:
            for rect, key in zip((left, health, right), DESKTOP_HUD_KEYS):
                self._draw_keycap(key, (rect.centerx, rect.top - 11))
        width = health.w - 12
        x, y = health.x + 6, health.y + 2
        self._draw_panel(*health, accent=(89, 188, 206), fill=(6, 23, 37), r=8, alpha=225)
        bar = pygame.Rect(x, y + 16, width, 7)
        Draw.rect(config.SCR, (66, 41, 57), bar, border_radius=4)
        Draw.rect(config.SCR, (128, 94, 108), bar, width=1, border_radius=4)
        fill = bar.inflate(-2, -2)
        fill.w = max(0, min(fill.w, int(fill.w * self.player_hp / self.max_player_hp)))
        if fill.w > 0:
            Draw.rect(config.SCR, (78, 216, 166), fill, border_radius=3)
            if fill.w > 5:
                Draw.line(config.SCR, (166, 255, 216),
                                 (fill.left + 2, fill.top + 1), (fill.right - 3, fill.top + 1))
        self._draw_text_fit(f'HP {self.player_hp}/{self.max_player_hp}', self.font_tiny, WHITE,
                            pygame.Rect(x, y, width, 16), align='center')
        self._ui_labels = labels

    def _draw_shop_overlay(self):
        self._draw_scrim(226)
        rects = self._mobile_shop_rects()
        close = rects['close']
        width, top = config.SCREEN_WIDTH, close.top
        bottom = max(rect.bottom for rect in rects.values())
        self._draw_panel(6, max(0, top - 8), width - 12, bottom - top + 20,
                         accent=(88, 154, 178), fill=(8, 25, 41), r=14, alpha=174)
        self._draw_title_text('商店', pygame.Rect(60, top, width - 120, 42), font=self.font_med)
        self._draw_text_fit(f'金币: {self.player.gold}', self.font_small, GOLD_COLOR,
                            pygame.Rect(16, top + 42, width - 32, 26), align='center')
        self._draw_button('×', *close, (110, 55, 65), key=pygame.K_b)
        weapon_y = min(rect.y for key, rect in rects.items() if key.startswith('weapon:'))
        character_y = min(rect.y for key, rect in rects.items() if key.startswith('character:'))
        self._draw_text_fit('武器', self.font_small, WHITE,
                            pygame.Rect(12, weapon_y - 24, config.SCREEN_WIDTH - 24, 22), align='center')
        for index, key in enumerate(_WEAPON_KEYS_ORDERED):
            rect = rects[f'weapon:{key}']
            wdef = WEAPON_DEFS[key]
            owned = key in self.player.owned_weapons
            active = key == self.player.current_weapon
            icon = image_asset(_WEAPON_ASSETS[key]) or self.weapon_icons[key]
            self._draw_shop_card(rect, wdef.name, self._weapon_cost(key), owned, active, icon, (90, 180, 225), pygame.K_1 + index)
        self._draw_text_fit('角色', self.font_small, WHITE,
                            pygame.Rect(12, character_y - 24, config.SCREEN_WIDTH - 24, 22), align='center')
        for index, key in enumerate(_CHAR_KEYS_ORDERED):
            rect = rects[f'character:{key}']
            cdef = CHARACTER_DEFS[key]
            owned = key in self.player.owned_characters
            active = key == self.player.character
            icon = image_asset(_CHAR_ASSETS[key])
            self._draw_shop_card(rect, cdef.name, self._character_cost(cdef), owned, active, icon, cdef.color, pygame.K_5 + index)

    def _draw_shop_card(self, rect, name, cost, owned, active, icon, accent, key):
        affordable = self.player.gold >= cost
        border = GOLD_COLOR if active else accent
        fill = (28, 61, 62) if active else (12, 35, 52)
        self._draw_panel(*rect, accent=border, fill=fill, r=9, alpha=235)
        if icon:
            factor = min(42 / icon.get_width(), (rect.h - 14) / icon.get_height())
            size = (round(icon.get_width() * factor), round(icon.get_height() * factor))
            position = pygame.Rect(0, 0, *size)
            position.center = (rect.x + 31, rect.centery)
            if self.desktop_controls and isinstance(config.SCR, RenderSurface):
                config.SCR.blit(icon, position, logical_size=size, static=True)
            else:
                config.SCR.blit(scale_surface_cached(icon, size), position)
        text_x = rect.x + 59
        name_width = rect.right - text_x - 7
        if self.desktop_controls:
            self._draw_keycap(key, (rect.right - 16, rect.y + 18))
            name_width -= 23
        self._draw_text_fit(name, self.font_small, WHITE,
                            pygame.Rect(text_x, rect.y + 7, name_width, 22))
        if owned:
            status = '已装备' if active else '已购买'
            color = (141, 237, 184)
        else:
            status = f'{cost} 金币 · ' + ('可购买' if affordable else '金币不足')
            color = GOLD_COLOR if affordable else (177, 199, 213)
        self._draw_text_fit(status, self.font_tiny, color,
                            pygame.Rect(text_x, rect.y + 33, rect.right - text_x - 7, 19))

    def _draw_level_transition(self):
        # 暗色叠加
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 5, 20, 140))
        config.SCR.blit(ov, (0, 0))
        # 中心面板
        pw, ph = 360, 120
        px, py = config.SCREEN_WIDTH // 2 - pw // 2, config.SCREEN_HEIGHT // 2 - ph // 2
        self._draw_panel(px, py, pw, ph, accent=(90, 230, 120), fill=(14, 48, 36), r=16, alpha=226)
        # 关卡文本
        self._draw_title_text(f'第{self.current_level}关 通过!', pygame.Rect(px+20, py+20, pw-40, 50), color=(120, 255, 130), accent=(90, 230, 120))
        # 奖励
        rw = config.CAMPAIGN_REWARDS[self.current_level - 1]
        self._draw_text_fit(f'奖励: {rw} 金币', self.font_med, GOLD_COLOR, pygame.Rect(px+40, py+72, pw-80, 34), align='center')

    def _choice_rects(self):
        x, y = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2 + 19
        return pygame.Rect(x - 150, y, 142, 42), pygame.Rect(x + 8, y, 142, 42)

    def _draw_pause_overlay(self):
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 10, 28, 145))
        config.SCR.blit(ov, (0, 0))
        pw, ph = 320, 150
        px, py = config.SCREEN_WIDTH // 2 - pw // 2, config.SCREEN_HEIGHT // 2 - ph // 2
        self._draw_panel(px, py, pw, ph, accent=(106, 214, 218), fill=(8, 30, 46), r=18, alpha=232)
        if self.exit_confirmation:
            self._draw_title_text('退出本局？', pygame.Rect(px+20, py+26, pw-40, 58), accent=(115, 205, 255))
            cancel, confirm = self._choice_rects()
            self._draw_button('取消', *cancel, key=pygame.K_ESCAPE)
            self._draw_button('确认退出', *confirm, (180, 60, 60), key=pygame.K_RETURN)
            return
        paid = self.state == GameState.PAID_REVIVE
        title = f'花 {self._revive_cost()} 金币复活？' if paid else '暂停'
        self._draw_title_text(title, pygame.Rect(px+20, py+26, pw-40, 58), accent=(115, 205, 255))
        left, right = self._choice_rects()
        self._draw_button('复活' if paid else '继续游戏', *left, key=pygame.K_y if paid else pygame.K_RETURN)
        self._draw_button('结束游戏' if paid else '退出本局', *right, (180, 60, 60), key=pygame.K_n)

    def _game_over_choice_rects(self):
        x = config.SCREEN_WIDTH // 2
        y = config.SCREEN_HEIGHT // 2 + 70
        return pygame.Rect(x - 150, y, 142, 42), pygame.Rect(x + 8, y, 142, 42)

    def _draw_game_over(self):
        # 暗色渐变叠加
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        for y_off in range(config.SCREEN_HEIGHT):
            a = int(180 + 30 * (1 - y_off / config.SCREEN_HEIGHT))
            _rect(ov, (30, 5, 8, a), (0, y_off, config.SCREEN_WIDTH, 1))
        config.SCR.blit(ov, (0, 0))
        # 中心面板
        pw, ph = 380, 280
        px, py = config.SCREEN_WIDTH // 2 - pw // 2, config.SCREEN_HEIGHT // 2 - ph // 2 - 30
        self._draw_panel(px, py, pw, ph, accent=(235, 75, 75), fill=(46, 20, 28), r=16, alpha=226)
        # 标题
        self._draw_title_text('游戏结束', pygame.Rect(px+40, py+32, pw-80, 58), color=(255, 155, 145), accent=(235, 75, 75))
        # 死亡原因
        self._draw_text_fit(self.game_over_reason, self.font_med, (255, 160, 160), pygame.Rect(px+30, py+106, pw-60, 30), align='center')
        # 统计
        self._draw_text_fit(f'击杀数: {self.kill_count}', self.font_med, WHITE, pygame.Rect(px+80, py+152, pw-160, 30), align='center')
        self._draw_text_fit(f'金币: {self.player.gold}', self.font_med, GOLD_COLOR, pygame.Rect(px+80, py+192, pw-160, 30), align='center')
        # 重新开始按钮
        retry, home = self._game_over_choice_rects()
        self._draw_button('重玩本关', *retry, (45, 150, 70), key=pygame.K_RETURN)
        self._draw_button('返回首页', *home, (180, 60, 60), key=pygame.K_n)

    def _draw_infinite_continue(self):
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((10, 6, 18, 175))
        config.SCR.blit(ov, (0, 0))
        pw, ph = 420, 260
        px, py = config.SCREEN_WIDTH // 2 - pw // 2, config.SCREEN_HEIGHT // 2 - ph // 2
        self._draw_panel(px, py, pw, ph, accent=(175, 105, 255), fill=(24, 22, 48), r=16, alpha=232)
        self._draw_title_text('继续无限模式?', pygame.Rect(px+40, py+30, pw-80, 54), accent=(175, 105, 255))
        self._draw_text_fit(self.game_over_reason, self.font_small, (255, 170, 170), pygame.Rect(px+40, py+92, pw-80, 28), align='center')
        self._draw_text_fit(f'当前积分: {self.score}', self.font_med, GOLD_COLOR, pygame.Rect(px+50, py+130, pw-100, 34), align='center')
        self._draw_button('继续' if self.desktop_controls else 'Y - 继续', config.SCREEN_WIDTH//2-170, config.SCREEN_HEIGHT//2+70, 150, 46, (45, 150, 70), key=pygame.K_y)
        self._draw_button('结束' if self.desktop_controls else 'N - 结束', config.SCREEN_WIDTH//2+20, config.SCREEN_HEIGHT//2+70, 150, 46, (180, 60, 60), key=pygame.K_n)

    def _draw_infinite_countdown(self):
        now = config.game_ticks()
        rem = max(0, self.infinite_countdown_end - pygame.time.get_ticks())
        num = max(1, math.ceil(rem / 1000))
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((4, 8, 18, 120))
        config.SCR.blit(ov, (0, 0))
        self._draw_title_text(str(num), pygame.Rect(config.SCREEN_WIDTH//2-80, config.SCREEN_HEIGHT//2-92, 160, 120), color=(255, 245, 180), accent=(255, 130, 80), font=self.font_large)
        self._draw_text_fit('准备继续', self.font_med, (220, 240, 255), pygame.Rect(config.SCREEN_WIDTH//2-110, config.SCREEN_HEIGHT//2+18, 220, 36), align='center')

    def _draw_victory(self):
        # 金色渐变叠加
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        for y_off in range(config.SCREEN_HEIGHT):
            a = int(180 + 30 * (1 - y_off / config.SCREEN_HEIGHT))
            _rect(ov, (5, 20, 5, a), (0, y_off, config.SCREEN_WIDTH, 1))
        config.SCR.blit(ov, (0, 0))
        # 中心面板
        pw, ph = 380, 300
        px, py = config.SCREEN_WIDTH // 2 - pw // 2, config.SCREEN_HEIGHT // 2 - ph // 2 - 30
        self._draw_panel(px, py, pw, ph, accent=(245, 205, 70), fill=(18, 48, 30), r=16, alpha=226)
        # 胜利标题
        self._draw_title_text('胜利', pygame.Rect(px+50, py+28, pw-100, 58), color=GOLD_COLOR, accent=(245, 205, 70))
        self._draw_text_fit('恭喜完成全部关卡！', self.font_med, WHITE, pygame.Rect(px+40, py+96, pw-80, 34), align='center')
        # 帝冠装饰
        self._draw_text_fit('★', self.font_large, GOLD_COLOR, pygame.Rect(px+150, py+132, pw-300, 48), align='center')
        # 统计
        self._draw_text_fit(f'总击杀: {self.kill_count}', self.font_med, WHITE, pygame.Rect(px+80, py+188, pw-160, 30), align='center')
        self._draw_text_fit(f'金币: {self.player.gold}', self.font_med, GOLD_COLOR, pygame.Rect(px+80, py+228, pw-160, 30), align='center')
        seconds = max(0, (self.victory_end - config.game_ticks() + 999) // 1000)
        self._draw_text_fit(f'{seconds} 秒后返回难度选择', self.font_small, (190, 230, 205),
                            pygame.Rect(px+25, py+266, pw-50, 28), align='center')

    def queue_ui_text(self, text, font, color, rect, align='left'):
        style = self._ui_font_styles.get(font)
        if self._ui_labels is None or style is None:
            return False
        if rect.w > 0 and rect.h > 0:
            self._ui_labels.append((str(text), *style, tuple(color[:3]), *rect, align))
        return True

    def _draw_text_fit(self, text, font, color, rect, align='left'):
        if not text or self.queue_ui_text(text, font, color, rect, align):
            return
        target = config.SCR
        native = self.desktop_controls and isinstance(target, RenderSurface)
        blit = target.blit
        shadow_offset = 2
        text = str(text)
        if native:
            rect = pygame.Rect(target.rect(rect))
            blit = target.blit_pixels
            shadow_offset = 1
            logical_size, bold = self._ui_font_styles[font]
            size = target.length(logical_size)
            font = self._desktop_font(size, bold)
            text_w, text_h = font.size(text)
            fit = min(1, max(1, rect.w) / max(1, text_w), max(1, rect.h) / max(1, text_h))
            if fit < 1:
                size = max(1, int(size * fit))
                font = self._desktop_font(size, bold)
            while size > 1 and (font.size(text)[0] > rect.w or font.get_height() > rect.h):
                size -= 1
                font = self._desktop_font(size, bold)
        small_native = native and size <= 18
        if small_native:
            glyph_size = font.size(text)
            large_font = self._desktop_font(size * 2, bold)
            s = small_desktop_label(large_font, text, tuple(color[:3]), glyph_size)
            shadow = small_desktop_label(large_font, text, (0, 8, 20), glyph_size, alpha=100)
        else:
            s = font.render(text, True, color)
            shadow = font.render(text, True, (0, 8, 20))
        max_w, max_h = max(1, rect.w), max(1, rect.h)
        if not native and (s.get_width() > max_w or s.get_height() > max_h + 2):
            scale = min(max_w / max(1, s.get_width()), max_h / max(1, s.get_height()))
            nw = max(1, int(s.get_width() * scale))
            nh = max(1, int(s.get_height() * scale))
            s = pygame.transform.smoothscale(s, (nw, nh))
            shadow = pygame.transform.smoothscale(shadow, (nw, nh))
        if align == 'center':
            pos = s.get_rect(center=rect.center)
        elif align == 'right':
            pos = s.get_rect(midright=(rect.right, rect.centery))
        else:
            pos = s.get_rect(midleft=(rect.left, rect.centery))
        blit(shadow, pos.move(shadow_offset, shadow_offset))
        blit(s, pos)

    def _desktop_font(self, size, bold):
        key = size, bold
        if key not in self._desktop_fonts:
            self._desktop_fonts[key] = make_font(size, bold=bold)
        return self._desktop_fonts[key]

    def _draw_title_text(self, text, rect, color=WHITE, accent=(90, 220, 255), font=None):
        font = font or self.font_large
        if self.queue_ui_text(text, font, color, rect, 'center'):
            return
        if self.desktop_controls and isinstance(config.SCR, RenderSurface):
            self._draw_text_fit(text, font, color, rect, align='center')
            return
        for dx, dy, alpha in ((0, 4, 120), (0, -2, 80), (3, 0, 80), (-3, 0, 80)):
            s = font.render(str(text), True, (*accent[:3], alpha))
            config.SCR.blit(s, s.get_rect(center=rect.center).move(dx, dy))
        self._draw_text_fit(text, font, color, rect, align='center')

    def _draw_title_image(self, y, width):
        # 呼吸动画：2s 一个周期，从 100% 平滑放大到 130% 再缩小回 100%
        now = config.game_ticks()
        t = (now % 2000) / 2000.0
        scale = 1.0 + (TITLE_MAX_SCALE - 1) * (1.0 - math.cos(2 * math.pi * t)) / 2.0
        target_w = max(1, int(width * scale))
        if not self.title_image:
            self._draw_breathing_title_text(y, target_w)
            return
        src_w, src_h = self.title_image.get_size()
        source = self.title_image
        if not self.desktop_controls:
            crop_h = min(src_h, round(src_w * TITLE_CROP_RATIO))
            source = source.subsurface(pygame.Rect(0, (src_h - crop_h) // 2, src_w, crop_h))
            src_h = crop_h
        h = max(1, int(target_w * src_h / max(1, src_w)))
        position = (config.SCREEN_WIDTH // 2 - target_w // 2, y)
        if self.desktop_controls and isinstance(config.SCR, RenderSurface):
            config.SCR.blit(source, position, logical_size=(target_w, h))
        else:
            img = pygame.transform.smoothscale(source, (target_w, h))
            config.SCR.blit(img, position)

    def _draw_breathing_title_text(self, y, width):
        """无标题图片素材时的兜底：用 2 倍字号超采样渲染文字，缩放不模糊。"""
        text = '海洋生物入侵'
        cache = getattr(self, '_title_text_supersample', None)
        if cache is None:
            big_font = make_font(96, bold=True)
            self._title_text_supersample = big_font.render(text, True, (240, 250, 255))
            self._title_text_shadow_cache = big_font.render(text, True, (0, 8, 20))
            cache = self._title_text_supersample
        base_w, base_h = cache.get_size()
        h = max(1, int(width * base_h / max(1, base_w)))
        img = pygame.transform.smoothscale(cache, (width, h))
        shadow = pygame.transform.smoothscale(self._title_text_shadow_cache, (width, h))
        rect = img.get_rect(midtop=(config.SCREEN_WIDTH // 2, y))
        config.SCR.blit(shadow, rect.move(3, 4))
        config.SCR.blit(img, rect)

    def _draw_scrim(self, alpha, color=(2, 16, 25)):
        size = config.SCR.get_size()
        key = size, color
        if getattr(self, '_scrim_key', None) != key:
            self._scrim_key = key
            self._scrim = pygame.Surface(size).convert()
            self._scrim.fill(color)
        self._scrim.set_alpha(alpha)
        config.SCR.blit(self._scrim, (0, 0))

    def _draw_panel(self, x, y, w, h, accent=(90, 210, 255), fill=(10, 26, 48), r=12, alpha=214):
        target = config.SCR
        if isinstance(target, RenderSurface):
            panel = panel_surface(target.length(w), target.length(h), tuple(accent[:3]),
                                  tuple(fill[:3]), target.length(r), alpha,
                                  target.length(1) if self.desktop_controls else 1)
            target.blit_pixels(panel, target.point((x, y)))
        else:
            panel = panel_surface(w, h, tuple(accent[:3]), tuple(fill[:3]), r, alpha)
            target.blit(panel, (x, y))

    def _keycap_width(self, key):
        return min(48, max(16, self.font_keycap.size(self._keycap_text(key))[0] + 8))

    def _draw_keycap(self, key, center):
        rect = pygame.Rect(0, 0, self._keycap_width(key), 16)
        rect.center = center
        self._draw_panel(*rect, accent=(109, 167, 190), fill=(8, 23, 36), r=4, alpha=248)
        self._draw_text_fit(self._keycap_text(key), self.font_keycap, (221, 240, 250),
                            rect.inflate(-6, -2), align='center')

    def _draw_button(self, text, x, y, w, h, color=(40, 130, 210), *, key=None):
        btn = pygame.Rect(x, y, w, h)
        hovered = self._hit(*self.cursor_pos, x, y, w, h)
        fill = tuple((26 if hovered else 10) + c // 4 for c in color)
        border = tuple(min(255, (96 if hovered else 62) + c * 3 // 4) for c in color)
        Draw.rect(config.SCR, (3, 13, 22), btn.move(0, 2), border_radius=9)
        self._draw_panel(*btn, accent=border, fill=fill, r=9, alpha=251)
        label_rect = btn.inflate(-12, -6)
        if self.desktop_controls and key is not None:
            cap_width = self._keycap_width(key)
            if w >= 80:
                self._draw_keycap(key, (btn.right - 7 - cap_width // 2, btn.centery))
                label_rect.w -= cap_width + 5
            else:
                self._draw_keycap(key, (btn.centerx, btn.bottom + 10))
        if self.desktop_controls and isinstance(config.SCR, RenderSurface) and text in ('-', '+', '×'):
            cx, cy = btn.center
            if text == '×':
                Draw.line(config.SCR, WHITE, (cx - 6, cy - 6), (cx + 6, cy + 6), 2)
                Draw.line(config.SCR, WHITE, (cx - 6, cy + 6), (cx + 6, cy - 6), 2)
            else:
                Draw.line(config.SCR, WHITE, (cx - 7, cy), (cx + 7, cy), 2)
                if text == '+':
                    Draw.line(config.SCR, WHITE, (cx, cy - 7), (cx, cy + 7), 2)
            return
        self._draw_text_fit(text, self.font_med, WHITE, label_rect, align='center')
