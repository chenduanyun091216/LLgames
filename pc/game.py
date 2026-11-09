"""
游戏主逻辑：GameState, Game 类——难度选择、关卡系统、Boss战、商店、UI。
P1: WASD移动 J射击 K/L技能 1-4切换角色 Q/E切换武器
P2: 方向键移动 小键盘1射击 小键盘2/3技能 小键盘Enter激光 小键盘+飞镖 小键盘7/8/9/4切换角色 小键盘5/6切换武器
"""
import math, random, pygame
from . import config
from .asset_loader import image_asset
from .config import (
    WEAPON_SWITCH_COOLDOWN,
    WHITE, GOLD_COLOR, OCEAN_BLUE, SAND_COLOR, PLAYER_HP_GREEN, HEALTH_RED, HEALTH_GREEN,
    make_font, WEAPON_DEFS, CHARACTER_DEFS, _WEAPON_KEYS_ORDERED, _CHAR_KEYS_ORDERED,
    NORMAL_ENEMIES, LARGE_ENEMIES, ENEMY_DEFS,
    DIFFICULTY_PRESETS, BOSS_DEFS, LEVEL_CONFIGS,
    get_level_enemy_defs, get_level_enemy_speed_mult,
)
from .sprites import (
    _circle, _rect, _ellipse, _line, _polygon, _aaline,
    make_player_surface, make_fire_player_surface, make_ice_player_surface,
    make_water_player_surface, make_radiation_player_surface,
    make_weapon_icon, make_coin_surface,
)
from .sounds import play_sound, start_music
from .entities import (
    Player, Enemy, Bullet, Coin, GiftBox, Particle, Explosion,
    FireWall, IceFloor, SkillProjectile,
    MagneticStorm, RadiationLaser, Lightning, Boss, BossProjectile,
    SpinningDarts,
)
from .special_bosses import NiuBoss, ReturningAxe, ZongBoss, ZongReflectBullet

class GameState:
    DIFFICULTY_SELECT = 0; MENU = 1; PLAYING = 2; SHOP = 3
    BOSS_FIGHT = 4; LEVEL_TRANSITION = 5; GAME_OVER = 6; VICTORY = 7
    PAUSED = 8; CUSTOM_DIFFICULTY = 9; MODE_SELECT = 10; INFINITE_CONTINUE = 11
    INFINITE_COUNTDOWN = 12; KEY_SETTINGS = 13; PAID_REVIVE = 14

REVIVE_COST = 100

HARD_WEAPON_AMMO = {'rifle': 40, 'shotgun': 30, 'sniper': 25}
CONTACT_DAMAGE_COOLDOWN = 1000
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
INFINITE_BG_FADE_MS = 900
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
    ('p2_left', 'P2 左移', pygame.K_LEFT), ('p2_right', 'P2 右移', pygame.K_RIGHT),
    ('p2_up', 'P2 上移', pygame.K_UP), ('p2_down', 'P2 下移', pygame.K_DOWN),
    ('p2_shoot', 'P2 射击', pygame.K_KP1), ('p2_skill1', 'P2 技能1', pygame.K_KP2),
    ('p2_skill2', 'P2 技能2', pygame.K_KP3), ('p2_laser', 'P2 辐射激光', pygame.K_KP_ENTER),
    ('p2_dart', 'P2 飞镖', pygame.K_KP_PLUS),
    ('p2_weapon_prev', 'P2 上个武器', pygame.K_KP5), ('p2_weapon_next', 'P2 下个武器', pygame.K_KP6),
    ('p2_char_ice', 'P2 冰人', pygame.K_KP7), ('p2_char_water', 'P2 水人', pygame.K_KP8),
    ('p2_char_fire', 'P2 火人', pygame.K_KP9), ('p2_char_radiation', 'P2 辐射工程师', pygame.K_KP4),
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

class Game:
    def __init__(self):
        self.clock = pygame.time.Clock()
        self.font_large = make_font(48, bold=True)
        self.font_med = make_font(28, bold=True)
        self.font_small = make_font(20)
        self.font_tiny = make_font(16)
        self.title_image = image_asset('title.png')
        self.custom_fields = [
            ('spawn_interval_start', '初始刷怪间隔', 200, 4000, 100),
            ('spawn_interval_min', '最小刷怪间隔', 100, 2000, 50),
            ('spawn_decrease', '每次击杀加速', 0, 30, 1),
            ('enemy_speed_mult', '敌人速度倍率', 0.50, 3.00, 0.05),
            ('weapon_cost_mult', '武器价格倍率', 0.20, 3.00, 0.05),
            ('character_cost_mult', '角色价格倍率', 0.20, 3.00, 0.05),
            ('skill_cd_mult', '技能冷却倍率', 0.20, 3.00, 0.05),
            ('bullet_cost_rifle', '步枪每发金币', 0, 5, 1),
            ('bullet_cost_shotgun', '散弹枪每发金币', 0, 8, 1),
            ('bullet_cost_sniper', '狙击每发金币', 0, 8, 1),
            ('boss_hp_mult', 'Boss 血量倍率', 0.30, 4.00, 0.05),
            ('enemy_attack_interval_min', '小怪最短开火间隔', 1000, 10000, 250),
            ('enemy_attack_interval_max', '小怪最长开火间隔', 1500, 14000, 250),
            ('boss_attack_mult', 'Boss 攻击间隔倍率', 0.50, 2.50, 0.05),
            ('boss_homing_mult', 'Boss追击倍率', 0.50, 3.00, 0.05),
        ]
        self.controls = DEFAULT_CONTROLS.copy()
        self.setting_key_action = None
        self.reset()

    def reset(self):
        self.state = GameState.DIFFICULTY_SELECT
        self.difficulty = None
        self.two_player = False
        self.infinite_mode = False
        self.selecting_infinite_mode = False
        self.infinite_boss_index = 0
        self.next_infinite_boss_time = 0
        self.infinite_start_time = 0
        self.infinite_music_variant = 0
        self.infinite_background_level = 1
        self.player_invincible_until = 0
        self.infinite_countdown_end = 0
        self.infinite_resume_state = GameState.PLAYING
        self.player = Player()
        self.player.x = config.SCREEN_WIDTH // 2 - 80
        self.player.surface = make_player_surface('player1.png')
        self.player.sprite_asset = 'player1.png'
        self.player2 = Player()
        self.player2.x = config.SCREEN_WIDTH // 2 + 80
        self.player2.surface = make_player_surface('player2.png')
        self.player2.sprite_asset = 'player2.png'
        self.player2.owned_weapons = self.player.owned_weapons
        self.player2.owned_characters = self.player.owned_characters
        self.enemies = []; self.bullets = []; self.coins = []; self.particles = []
        self.gift_boxes = []
        self.gift_messages = []
        self.explosions = []
        self.fire_walls = []; self.ice_floors = []; self.skill_projectiles = []
        self.magnetic_storms = []; self.radiation_lasers = []; self.lightnings = []
        self.dart_shields = []
        self.laser_impacts = []; self.last_laser_hit_sound = 0
        self.water_heal_effects = []
        self.muzzle_flashes = []
        self.boss = None; self.boss_projectiles = []
        self.enemy_projectiles = []
        self.current_level = 1; self.level_kills = 0; self.kill_count = 0; self.score = 0
        self.chapter = 1
        self.lives = 3
        self.revive_count = 0
        self.spawn_interval = 2000; self.min_spawn_interval = 800; self.spawn_decrease = 5
        self.last_spawn_time = 0; self.last_switch_time = -9999
        self.game_over_reason = ''
        self.pause_prev_state = GameState.PLAYING
        self.cursor_pos = (config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)
        self.player_hp = 5; self.max_player_hp = 5
        self.water_temp_hp_until = 0; self.water_passive_kills = 0
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0; self.next_gift_time = 0
        self.level_transition_end = 0
        self.level_title_until = 0
        self.bg_transition_until = 0
        self.bg_transition_prev = None
        self.custom_values = self._difficulty_to_values(DIFFICULTY_PRESETS['medium'])
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

    def resize_view(self):
        self.bg_transition_prev = None
        self.bg_transition_until = 0
        self.bg = self._load_bg()
        size_scale = 1.0
        for player in self.players:
            player_width = player.rect().w
            half_width = player_width // 2
            min_x = max(40, config.GAME_AREA_LEFT + half_width)
            max_x = min(config.SCREEN_WIDTH - 40,
                        config.GAME_AREA_RIGHT - (player_width + 1) // 2)
            player.x = max(min_x, min(max_x, player.x))
            player.y = max(80, min(config.GAME_AREA_BOTTOM - 14, player.y))
        for enemy in self.enemies:
            enemy.set_size_scale(size_scale)
            half_width = enemy.w // 2
            right_half_width = (enemy.w + 1) // 2
            enemy.x = max(config.GAME_AREA_LEFT + half_width,
                          min(config.GAME_AREA_RIGHT - right_half_width, enemy.x))
        if self.boss:
            self.boss.set_size_scale(size_scale)
            boss_rect = self.boss.rect()
            left_extent = max(0, int(self.boss.x) - boss_rect.left)
            right_extent = max(0, boss_rect.right - int(self.boss.x))
            self.boss.x = max(config.GAME_AREA_LEFT + left_extent,
                              min(config.GAME_AREA_RIGHT - right_extent, self.boss.x))

    @property
    def players(self):
        return (self.player, self.player2) if self.two_player else (self.player,)

    def _key(self, action):
        return self.controls.get(action, DEFAULT_CONTROLS[action])

    def _key_name(self, key):
        if key in KEY_LABELS:
            return KEY_LABELS[key]
        name = pygame.key.name(key)
        return name.upper() if len(name) == 1 else name

    def _control_name(self, action):
        return self._key_name(self._key(action))

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
            if event.type == pygame.KEYDOWN:
                if pygame.K_1 <= event.key <= pygame.K_8 and event.mod & pygame.KMOD_SHIFT:
                    self._jump_to_level(event.key - pygame.K_0)
                    continue
                if self.setting_key_action:
                    if event.key != pygame.K_ESCAPE:
                        self.controls[self.setting_key_action] = event.key
                    self.setting_key_action = None
                    continue
                if event.key == pygame.K_ESCAPE:
                    if not self._handle_escape():
                        return False
                    continue
                self._handle_keydown(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(config.window_to_game(event.pos))
            if event.type == pygame.MOUSEMOTION:
                self.cursor_pos = config.window_to_game(event.pos)
        return True

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
        elif self.state in (GameState.CUSTOM_DIFFICULTY, GameState.MODE_SELECT):
            self.state = GameState.DIFFICULTY_SELECT
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
        if k == pygame.K_p and pygame.key.get_mods() & pygame.KMOD_CTRL:
            now = pygame.time.get_ticks()
            for p in self.players:
                p.rage_until = now + 20000
            self.rage_banner_until = now + 3000
            play_sound('level_up')
            return
        if k == pygame.K_h and s in (GameState.PLAYING, GameState.BOSS_FIGHT, GameState.PAUSED):
            if s == GameState.PAUSED:
                self.state = self.pause_prev_state
            else:
                self.pause_prev_state = s
                self.state = GameState.PAUSED
            return
        if s == GameState.DIFFICULTY_SELECT:
            if k == pygame.K_1: self._start_game('easy')
            elif k == pygame.K_2: self._start_game('medium')
            elif k == pygame.K_3: self._start_game('hard')
            elif k == pygame.K_4: self._start_infinite_game()
            elif k == pygame.K_c: self.state = GameState.CUSTOM_DIFFICULTY
        elif s == GameState.CUSTOM_DIFFICULTY:
            if k in (pygame.K_RETURN, pygame.K_SPACE): self._start_custom_game()
        elif s == GameState.MODE_SELECT:
            if k == pygame.K_1: self._begin_selected_run(False)
            elif k == pygame.K_2: self._begin_selected_run(True)
        elif s == GameState.MENU:
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = GameState.PLAYING; self.last_spawn_time = pygame.time.get_ticks()
            elif k == pygame.K_b: self.state = GameState.SHOP
            elif k == pygame.K_c: self.state = GameState.KEY_SETTINGS
        elif s == GameState.KEY_SETTINGS:
            if k == pygame.K_r: self.controls = DEFAULT_CONTROLS.copy()
        elif s == GameState.GAME_OVER or s == GameState.VICTORY:
            if k in (pygame.K_RETURN, pygame.K_SPACE): self.reset()
        elif s == GameState.PAID_REVIVE:
            if k in (pygame.K_y, pygame.K_RETURN): self._paid_revive()
            elif k == pygame.K_n: self.state = GameState.GAME_OVER
        elif s == GameState.INFINITE_CONTINUE:
            if k in (pygame.K_y, pygame.K_RETURN, pygame.K_SPACE): self._continue_infinite()
            elif k in (pygame.K_n, pygame.K_ESCAPE): self.reset()
        elif s in (GameState.PLAYING, GameState.BOSS_FIGHT):
            if k == self._key('p1_weapon_prev'): self.cycle_weapon(self.player, -1)
            elif k == self._key('p1_weapon_next'): self.cycle_weapon(self.player, 1)
            elif self.two_player and k == self._key('p2_weapon_prev'): self.cycle_weapon(self.player2, -1)
            elif self.two_player and k == self._key('p2_weapon_next'): self.cycle_weapon(self.player2, 1)
            elif k == self._key('p1_char_ice'): self.try_switch_character('ice', self.player)
            elif k == self._key('p1_char_water'): self.try_switch_character('water', self.player)
            elif k == self._key('p1_char_fire'): self.try_switch_character('fire', self.player)
            elif k == self._key('p1_char_radiation'): self.try_switch_character('radiation', self.player)
            elif k == self._key('p1_laser'): self._activate_radiation_laser(self.player)
            elif k == self._key('p1_dart'): self._activate_dart_shield(self.player)
            elif self.two_player and k == self._key('p2_laser'): self._activate_radiation_laser(self.player2)
            elif self.two_player and k == self._key('p2_dart'): self._activate_dart_shield(self.player2)
            elif self.two_player and k == self._key('p2_char_ice'): self.try_switch_character('ice', self.player2)
            elif self.two_player and k == self._key('p2_char_water'): self.try_switch_character('water', self.player2)
            elif self.two_player and k == self._key('p2_char_fire'): self.try_switch_character('fire', self.player2)
            elif self.two_player and k == self._key('p2_char_radiation'): self.try_switch_character('radiation', self.player2)
            # 商店
            elif k == pygame.K_b: self.state = GameState.SHOP
            self._handle_skill_key(self.player, k, self._key('p1_skill1'), self._key('p1_skill2'))
            if self.two_player:
                self._handle_skill_key(self.player2, k, self._key('p2_skill1'), self._key('p2_skill2'))
        elif s == GameState.SHOP:
            if k == pygame.K_b: self.state = GameState.PLAYING
            elif pygame.K_1 <= k <= pygame.K_4:
                self._buy_or_equip_weapon(_WEAPON_KEYS_ORDERED[k - pygame.K_1])
            elif pygame.K_5 <= k <= pygame.K_8:
                self._buy_or_equip_character(_CHAR_KEYS_ORDERED[k - pygame.K_5])

    def _handle_click(self, pos):
        mx, my = pos; s = self.state
        if s == GameState.DIFFICULTY_SELECT: self._click_difficulty(mx, my)
        elif s == GameState.CUSTOM_DIFFICULTY: self._click_custom_difficulty(mx, my)
        elif s == GameState.MODE_SELECT:
            if self._hit(mx, my, config.SCREEN_WIDTH//2-220, 285, 180, 58): self._begin_selected_run(False)
            elif self._hit(mx, my, config.SCREEN_WIDTH//2+40, 285, 180, 58): self._begin_selected_run(True)
        elif s == GameState.MENU:
            if self._hit(mx, my, config.SCREEN_WIDTH//2-110, 490, 220, 54):
                self.state = GameState.PLAYING; self.last_spawn_time = pygame.time.get_ticks()
            elif self._hit(mx, my, config.SCREEN_WIDTH//2-110, 560, 220, 48):
                self.state = GameState.SHOP
            elif self._hit(mx, my, config.SCREEN_WIDTH//2-110, 624, 220, 48):
                self.state = GameState.KEY_SETTINGS
        elif s == GameState.PLAYING: self.cursor_pos = (mx, my)
        elif s == GameState.SHOP: self._handle_shop_click(mx, my)
        elif s == GameState.PAID_REVIVE:
            revive, end_run = self._choice_rects()
            if revive.collidepoint(pos): self._paid_revive()
            elif end_run.collidepoint(pos): self.state = GameState.GAME_OVER
        elif s == GameState.KEY_SETTINGS: self._handle_key_settings_click(mx, my)
        elif s == GameState.INFINITE_CONTINUE:
            if self._hit(mx, my, config.SCREEN_WIDTH//2-170, config.SCREEN_HEIGHT//2+70, 150, 46): self._continue_infinite()
            elif self._hit(mx, my, config.SCREEN_WIDTH//2+20, config.SCREEN_HEIGHT//2+70, 150, 46): self.reset()
        elif s in (GameState.GAME_OVER, GameState.VICTORY): self.reset()

    def _click_difficulty(self, mx, my):
        if self._hit(mx, my, config.SCREEN_WIDTH//2 - 190, config.SCREEN_HEIGHT - 92, 170, 42):
            self.state = GameState.CUSTOM_DIFFICULTY
            return
        if self._hit(mx, my, config.SCREEN_WIDTH//2 + 20, config.SCREEN_HEIGHT - 92, 170, 42):
            self.state = GameState.KEY_SETTINGS
            return
        keys = list(DIFFICULTY_PRESETS.keys()); card_w = 200
        total = 4*card_w + 3*22; sx = (config.SCREEN_WIDTH - total)//2; sy = 322
        for i, key in enumerate(keys):
            if self._hit(mx, my, sx+i*(card_w+22), sy, card_w, 260):
                self._start_game(key); return
        if self._hit(mx, my, sx+3*(card_w+22), sy, card_w, 260):
            self._start_infinite_game()

    def _hit(self, mx, my, rx, ry, rw, rh):
        return rx <= mx <= rx+rw and ry <= my <= ry+rh

    # ═══ Game Flow ════════════════════════════════════════════════════════════
    def _start_game(self, diff_key):
        self.selecting_infinite_mode = False
        self.difficulty = DIFFICULTY_PRESETS[diff_key]
        self.state = GameState.MODE_SELECT

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
        self.state = GameState.MODE_SELECT

    def _start_infinite_game(self):
        self.selecting_infinite_mode = True
        self.difficulty = DIFFICULTY_PRESETS['hard']
        self.state = GameState.MODE_SELECT

    def _begin_selected_run(self, two_player=False):
        if self.selecting_infinite_mode:
            self._begin_infinite_run(two_player)
        else:
            self._begin_run(two_player)

    def _jump_to_level(self, level):
        self.setting_key_action = None
        if self.infinite_mode or self.selecting_infinite_mode:
            self._begin_infinite_run(self.two_player, level)
            return
        if self.difficulty is None:
            self.difficulty = DIFFICULTY_PRESETS['medium']
        self._begin_run(self.two_player, level)

    def _begin_run(self, two_player=False, start_level=1):
        self.selecting_infinite_mode = False
        self.two_player = two_player
        self.player.x = config.SCREEN_WIDTH // 2 - (80 if two_player else 0)
        self.player.y = config.GAME_AREA_BOTTOM - 14
        self.player.current_weapon = 'pistol'
        self.player.character = None
        self.player.surface = make_player_surface('player1.png')
        self.player.sprite_asset = 'player1.png'
        self.player.skill_cooldowns = {}
        self.player.skill_active_until = {}
        self.player.skill_active_cd = {}
        self.player.water_boost_until = 0
        self.player.water_haste_until = 0
        self.player.gift_speed_until = 0
        self.player.rage_until = 0
        self.player.weapon_ammo = {}
        self.player2.x = config.SCREEN_WIDTH // 2 + 80
        self.player2.y = config.GAME_AREA_BOTTOM - 14
        self.player2.current_weapon = 'pistol'
        self.player2.character = None
        self.player2.surface = make_player_surface('player2.png')
        self.player2.sprite_asset = 'player2.png'
        self.player2.skill_cooldowns = {}
        self.player2.skill_active_until = {}
        self.player2.skill_active_cd = {}
        self.player2.water_boost_until = 0
        self.player2.water_haste_until = 0
        self.player2.gift_speed_until = 0
        self.player2.rage_until = 0
        self.player2.weapon_ammo = {}
        self.infinite_mode = False
        self.lives = 3
        self.revive_count = 0
        self._apply_difficulty(start_level)
    
    def _begin_infinite_run(self, two_player=False, start_chapter=1):
        self.selecting_infinite_mode = False
        self.infinite_mode = True
        self.two_player = two_player
        self.difficulty = DIFFICULTY_PRESETS['hard']
        self.player.x = config.SCREEN_WIDTH // 2 - (80 if two_player else 0)
        self.player.y = config.GAME_AREA_BOTTOM - 14
        self.player.owned_weapons = list(_WEAPON_KEYS_ORDERED)
        self.player.owned_characters = list(_CHAR_KEYS_ORDERED)
        self.player.current_weapon = 'pistol'
        self.player.character = None
        self.player.surface = make_player_surface('player1.png')
        self.player.sprite_asset = 'player1.png'
        self.player.skill_cooldowns = {}
        self.player.skill_active_until = {}
        self.player.skill_active_cd = {}
        self.player.water_boost_until = 0
        self.player.water_haste_until = 0
        self.player.gift_speed_until = 0
        self.player.rage_until = 0
        self.player.weapon_ammo = {}
        self.player.gold = 0
        self.player2.x = config.SCREEN_WIDTH // 2 + 80
        self.player2.y = config.GAME_AREA_BOTTOM - 14
        self.player2.owned_weapons = self.player.owned_weapons
        self.player2.owned_characters = self.player.owned_characters
        self.player2.current_weapon = 'pistol'
        self.player2.character = None
        self.player2.surface = make_player_surface('player2.png')
        self.player2.sprite_asset = 'player2.png'
        self.player2.skill_cooldowns = {}
        self.player2.skill_active_until = {}
        self.player2.skill_active_cd = {}
        self.player2.water_boost_until = 0
        self.player2.water_haste_until = 0
        self.player2.gift_speed_until = 0
        self.player2.rage_until = 0
        self.player2.weapon_ammo = {}
        self.current_level = 1; self.level_kills = 0; self.kill_count = 0; self.score = 0
        self.chapter = start_chapter
        self.lives = 3
        self.revive_count = 0
        self.infinite_background_level = start_chapter
        self.max_player_hp = 5; self.player_hp = self.max_player_hp
        self.spawn_interval = 900; self.min_spawn_interval = 280; self.spawn_decrease = 8
        self.boss = None; self.boss_projectiles.clear(); self.enemy_projectiles.clear()
        self.enemies.clear(); self.bullets.clear(); self.coins.clear(); self.gift_boxes.clear(); self.gift_messages.clear(); self.explosions.clear()
        self.fire_walls.clear(); self.ice_floors.clear(); self.skill_projectiles.clear()
        self.magnetic_storms.clear(); self.radiation_lasers.clear(); self.lightnings.clear()
        self.dart_shields.clear(); self.laser_impacts.clear()
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0
        self.bg = self._load_bg()
        now = pygame.time.get_ticks()
        self.last_spawn_time = now
        self._schedule_next_gift(now)
        self.infinite_start_time = now
        self.infinite_music_variant = 0
        self.player_invincible_until = 0
        self.next_infinite_boss_time = now + 25000
        self.infinite_boss_index = start_chapter - 1
        self.level_enemy_defs = get_level_enemy_defs(LEVEL_CONFIGS[-1])
        self.level_title_until = 0
        self.bg_transition_until = 0
        self.bg_transition_prev = None
        start_music(self.infinite_background_level, infinite=True, variant=self.infinite_music_variant)
        self.state = GameState.PLAYING

    def _apply_difficulty(self, start_level=1):
        self.spawn_interval = self.difficulty.spawn_interval_start
        self.min_spawn_interval = self.difficulty.spawn_interval_min
        self.spawn_decrease = self.difficulty.spawn_decrease
        self.current_level = 1; self.level_kills = 0; self.kill_count = 0
        self.chapter = start_level
        self.max_player_hp = 3 if self.difficulty.name == '困难' else 5
        self.player_hp = self.max_player_hp
        self.boss = None; self.boss_projectiles.clear()
        self.enemy_projectiles.clear()
        self.gift_boxes.clear()
        self.gift_messages.clear()
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0
        self.state = GameState.PLAYING
        self._start_level(start_level)
        self.last_spawn_time = pygame.time.get_ticks()

    def _difficulty_to_values(self, diff):
        return {name: getattr(diff, name) for name, _, _, _, _ in self.custom_fields}

    def _click_custom_difficulty(self, mx, my):
        panel_x, row_y, row_step = config.SCREEN_WIDTH // 2 - 360, 148, 31
        for i, (key, _, min_v, max_v, step) in enumerate(self.custom_fields):
            y = row_y + i * row_step
            if self._hit(mx, my, panel_x + 560, y, 34, 30):
                self.custom_values[key] = max(min_v, self.custom_values[key] - step)
                if isinstance(min_v, int) and isinstance(step, int): self.custom_values[key] = int(self.custom_values[key])
                return
            if self._hit(mx, my, panel_x + 602, y, 34, 30):
                self.custom_values[key] = min(max_v, self.custom_values[key] + step)
                if isinstance(min_v, int) and isinstance(step, int): self.custom_values[key] = int(self.custom_values[key])
                return
        if self._hit(mx, my, config.SCREEN_WIDTH//2 - 190, 626, 170, 50):
            self.custom_values = self._difficulty_to_values(DIFFICULTY_PRESETS['medium'])
        elif self._hit(mx, my, config.SCREEN_WIDTH//2 + 20, 626, 170, 50):
            self._start_custom_game()

    def _handle_key_settings_click(self, mx, my):
        row_w, row_h, row_gap = 246, 28, 6
        sx, sy = config.SCREEN_WIDTH // 2 - 258, 138
        for i, (action, _, _) in enumerate(CONTROL_DEFS):
            col = i // 15
            row = i % 15
            x = sx + col * 270
            y = sy + row * (row_h + row_gap)
            if self._hit(mx, my, x, y, row_w, row_h):
                self.setting_key_action = action
                return
        if self._hit(mx, my, config.SCREEN_WIDTH//2 - 190, 656, 170, 44):
            self.controls = DEFAULT_CONTROLS.copy()
            self.setting_key_action = None
        elif self._hit(mx, my, config.SCREEN_WIDTH//2 + 20, 656, 170, 44):
            self.setting_key_action = None
            self.state = GameState.MENU

    def _start_level(self, n):
        self.current_level = n; self.level_kills = 0
        self.bg = self._load_bg()
        self.level_title_until = pygame.time.get_ticks() + 2200
        self.boss = None; self.boss_projectiles.clear()
        self.fire_walls.clear(); self.ice_floors.clear()
        self.skill_projectiles.clear(); self.magnetic_storms.clear(); self.radiation_lasers.clear(); self.lightnings.clear()
        self.dart_shields.clear(); self.laser_impacts.clear()
        self.enemies.clear(); self.bullets.clear(); self.gift_boxes.clear(); self.gift_messages.clear(); self.explosions.clear(); self.muzzle_flashes.clear()
        self.enemy_projectiles.clear()
        self.level_enemy_defs = get_level_enemy_defs(LEVEL_CONFIGS[n-1])
        self.gift_fire_until = 0; self.gift_ice_until = 0; self.gift_lightning_remaining = 0; self.gift_lightning_next = 0; self.gift_lightning_icon_until = 0
        self.rage_banner_until = 0
        now = pygame.time.get_ticks()
        self.last_spawn_time = now
        self._schedule_next_gift(now)
        start_music(n)
        if LEVEL_CONFIGS[n-1].get('boss_on_start'):
            self._trigger_boss()

    def _trigger_boss(self):
        if self.boss:
            self._settle_boss_if_killed()
            return
        lcfg = LEVEL_CONFIGS[self.current_level-1]; bdef = BOSS_DEFS[lcfg['boss_idx']]
        self.boss = self._make_boss(bdef)
        self.boss_projectiles.clear(); self.enemy_projectiles.clear(); self.bullets.clear()
        self.last_spawn_time = pygame.time.get_ticks()
        start_music(self.current_level, boss=True)
        play_sound('boss_appear'); self.state = GameState.BOSS_FIGHT

    def _trigger_infinite_boss(self):
        boss_number = self.infinite_boss_index
        bdef = BOSS_DEFS[boss_number % len(BOSS_DEFS)]
        self.infinite_boss_index += 1
        self.boss = self._make_boss(bdef)
        self.boss.damage_mult = self._infinite_damage_mult()
        self._scale_infinite_boss(self.boss, boss_number)
        self.boss_projectiles.clear(); self.enemy_projectiles.clear(); self.bullets.clear()
        self.last_spawn_time = pygame.time.get_ticks()
        start_music(self.infinite_background_level, boss=True, infinite=True)
        play_sound('boss_appear'); self.state = GameState.BOSS_FIGHT

    def _make_boss(self, bdef):
        cls = NiuBoss if bdef['key'] == 'boss_niu' else ZongBoss if bdef['key'] == 'boss_zongzong' else Boss
        return cls(bdef, self.difficulty)

    def _player_defeated(self, reason):
        self.game_over_reason = reason
        if self.infinite_mode:
            self.state = GameState.INFINITE_CONTINUE
        else:
            self.lives -= 1
            if self.lives > 0:
                self._resume_after_defeat()
                return
            self.state = (GameState.PAID_REVIVE if self.player.gold >= REVIVE_COST
                          else GameState.GAME_OVER)
        play_sound('game_over')

    def _paid_revive(self):
        if self.state != GameState.PAID_REVIVE or self.player.gold < REVIVE_COST:
            return
        self.player.gold -= REVIVE_COST
        self.lives = 1
        self._resume_after_defeat()

    def _clear_invaded_enemies(self):
        self.enemies = [e for e in self.enemies if not e.reached_bottom()]

    def _continue_infinite(self):
        self.revive_count += 1
        self._resume_after_defeat()

    def _resume_after_defeat(self):
        now = pygame.time.get_ticks()
        self._clear_invaded_enemies()
        self.player_hp = self.max_player_hp
        self.infinite_countdown_end = now + 3000
        self.player_invincible_until = self.infinite_countdown_end + 2000
        self.infinite_resume_state = GameState.BOSS_FIGHT if self.boss else GameState.PLAYING
        self.last_spawn_time = now
        self.state = GameState.INFINITE_COUNTDOWN

    def _level_complete(self):
        lcfg = LEVEL_CONFIGS[self.current_level-1]
        self.player.gold += int(lcfg['gold_reward'] * self.difficulty.weapon_cost_mult)
        play_sound('level_up')
        if self.current_level >= len(LEVEL_CONFIGS): self.state = GameState.VICTORY
        else:
            self.state = GameState.LEVEL_TRANSITION
            self.level_transition_end = pygame.time.get_ticks() + 2000

    # ═══ Weapons & Skills ═════════════════════════════════════════════════════
    def _equipped_by_other(self, player, attr, key):
        if attr == 'current_weapon' and key == 'pistol':
            return False
        return any(other is not player and getattr(other, attr) == key for other in self.players)

    def _hard_ammo_mode(self):
        return self.difficulty and self.difficulty.name == '困难' and not self.infinite_mode

    def _refill_hard_weapon(self, player, key):
        if self._hard_ammo_mode() and key in HARD_WEAPON_AMMO:
            player.weapon_ammo[key] = HARD_WEAPON_AMMO[key]

    def _consume_hard_ammo(self, player, key):
        if not self._hard_ammo_mode() or key == 'pistol':
            return True
        ammo = player.weapon_ammo.get(key, 0)
        if ammo <= 0:
            if key in player.owned_weapons:
                player.owned_weapons.remove(key)
            player.current_weapon = 'pistol'
            return False
        ammo -= 1
        if ammo <= 0:
            player.weapon_ammo.pop(key, None)
            if key in player.owned_weapons:
                player.owned_weapons.remove(key)
            player.current_weapon = 'pistol'
        else:
            player.weapon_ammo[key] = ammo
        return True

    def _weapon_status_text(self, key, owned):
        if self._hard_ammo_mode() and key in HARD_WEAPON_AMMO:
            ammo = self.player.weapon_ammo.get(key, 0)
            if owned:
                return f'弹药 {ammo}/{HARD_WEAPON_AMMO[key]}'
            return f'{self._weapon_cost(key)}金币'
        return None

    def _handle_skill_key(self, player, key, skill1_key, skill2_key):
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
        now = pygame.time.get_ticks()
        skill_type = 'fisher_grenade'
        if not self._skill_ready(player, skill_type, now):
            return
        self._start_skill_effect(player, skill_type, FISHER_GRENADE_COOLDOWN, 900, now)
        self.skill_projectiles.append(SkillProjectile(player.x, player.y - 28, 0, 6, 'grenade', owner=player, skill_type=skill_type))
        play_sound('grenade')

    def _skill_ready(self, player, skill_type, now):
        return (now >= player.skill_cooldowns.get(skill_type, 0) and
                now >= getattr(player, 'skill_active_until', {}).get(skill_type, 0))

    def _start_skill_effect(self, player, skill_type, cd_ms, active_ms, now=None):
        now = pygame.time.get_ticks() if now is None else now
        player.animation_skill = skill_type
        player.animation_skill_at = now
        if active_ms <= 0:
            player.skill_cooldowns[skill_type] = now + cd_ms
            return
        player.skill_active_until[skill_type] = now + active_ms
        player.skill_active_cd[skill_type] = cd_ms

    def _finish_skill_effect(self, player, skill_type, now=None):
        if not player or skill_type not in getattr(player, 'skill_active_until', {}):
            return
        now = pygame.time.get_ticks() if now is None else now
        cd_ms = player.skill_active_cd.pop(skill_type, 0)
        player.skill_active_until.pop(skill_type, None)
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
        now = pygame.time.get_ticks()
        if now - self.last_switch_time < WEAPON_SWITCH_COOLDOWN: return False
        if self.infinite_mode and key == 'pistol':
            return False  # 无限模式手枪置灰，不可切换
        if self._hard_ammo_mode() and key != 'pistol' and player.weapon_ammo.get(key, 0) <= 0:
            if key in player.owned_weapons:
                player.owned_weapons.remove(key)
            return False
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
        now = pygame.time.get_ticks()
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
        if self.infinite_mode:
            return 0
        if self._hard_ammo_mode():
            return 0
        if not self.difficulty: return 0
        if wkey == 'rifle': return self._round_cost(self.difficulty.bullet_cost_rifle)
        if wkey == 'shotgun': return self._round_cost(self.difficulty.bullet_cost_shotgun)
        if wkey == 'sniper': return self._round_cost(self.difficulty.bullet_cost_sniper)
        return 0

    def _round_cost(self, cost):
        return max(0, int(math.ceil(cost / 5.0) * 5))

    def _weapon_cost(self, key):
        cost = WEAPON_DEFS[key].cost
        if self.difficulty:
            cost = cost * self.difficulty.weapon_cost_mult
        return self._round_cost(cost)

    def _player_speed(self, player, now):
        speed = Player.SPEED
        if now < player.water_boost_until:
            speed *= 1.6
        if now < getattr(player, 'rage_until', 0):
            speed = max(speed, Player.SPEED * 2)  # 终极狂暴：移动速度大幅提升
        if isinstance(self.boss, NiuBoss) and any(
                rect.colliderect(player.rect()) for rect in self.boss.lightning_rects(now)):
            speed *= 0.6
        if now < player.niu_slow_until:
            speed *= 0.5
        if now < player.snow_slow_until:
            speed *= 0.5
        return speed

    def _heal_player(self, amount, increase_max=False, temporary_ms=0):
        if increase_max:
            self.max_player_hp = min(5, self.max_player_hp + amount)
        if temporary_ms > 0:
            self.player_hp = min(self.max_player_hp + amount, self.player_hp + amount)
        else:
            self.player_hp = min(self.max_player_hp, self.player_hp + amount)
        if temporary_ms > 0:
            self.water_temp_hp_until = max(self.water_temp_hp_until, pygame.time.get_ticks() + temporary_ms)

    def _expire_water_temp_hp(self, now):
        if self.water_temp_hp_until and now >= self.water_temp_hp_until:
            self.player_hp = min(self.player_hp, self.max_player_hp)
            self.water_temp_hp_until = 0

    def _schedule_next_gift(self, now):
        self.next_gift_time = now + random.randint(GIFT_DROP_MIN_MS, GIFT_DROP_MAX_MS)

    def _maybe_spawn_gift(self, now):
        if not self.next_gift_time:
            self._schedule_next_gift(now)
        if now >= self.next_gift_time:
            self.gift_boxes.append(GiftBox())
            self._schedule_next_gift(now)

    def _is_zongzong(self, e):
        return getattr(e, 'is_zongzong', False)

    def _show_immune(self, e, now=None):
        if self._is_zongzong(e):
            now = pygame.time.get_ticks() if now is None else now
            if now < getattr(e, 'immune_text_until', 0):
                return True
            e.show_immune(now)
            self._spawn_hit_effect(e.x, e.y + e.h // 2, (255, 230, 150), False)
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
            # 闪电礼包加强：共 3 次，每次间隔 3s（打开瞬间第 1 次，6s 内打完）
            self.gift_lightning_remaining = 3
            self.gift_lightning_next = now
            self.gift_lightning_icon_until = now + 6000  # 屏幕中心闪电图标显示到 3 次闪电结束
            play_sound('lightning')
        elif box.kind == 'fire':
            self.gift_fire_until = now + GIFT_BUFF_MS
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

    def _maybe_fire_gift_lightning(self, now):
        if self.gift_lightning_remaining <= 0 or now < self.gift_lightning_next:
            return
        self.gift_lightning_remaining -= 1
        self.gift_lightning_next = now + 3000
        # 闪电从屏幕正中心向四周的怪物发射
        self._gift_lightning(now, config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)

    def _gift_lightning(self, now, x, y):
        targets = self.enemies[:]
        if self.boss:
            targets.append(self.boss)
        if targets:
            # 红黄混合闪电：红 + 黄两层叠加
            self.lightnings.append(Lightning(x, y, [(e, e.x, e.y + e.h // 2) for e in targets], color=(255, 60, 40)))
            self.lightnings.append(Lightning(x, y, [(e, e.x, e.y + e.h // 2) for e in targets], color=(255, 220, 70)))
        for e in self.enemies[:]:
            if self._show_immune(e, now):
                continue
            e.hit_by('sniper', GIFT_LIGHTNING_DAMAGE * self._gift_damage_mult(now))
            self._spawn_hit_effect(e.x, e.y + e.h // 2, (255, 55, 45), e.is_large)
            if e.is_killed('sniper'):
                self._kill_enemy(e)
        if self.boss:
            self.boss.hit_by('sniper', GIFT_LIGHTNING_DAMAGE * self._gift_damage_mult(now))
            self._spawn_hit_effect(self.boss.x, self.boss.y + self.boss.h // 2, (255, 55, 45), True)
            self._settle_boss_if_killed()
        play_sound('lightning')

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
        if hit_player:
            self._apply_niu_ice_axe_effect(p, hit_player, now)
        if hit_player and self._damage_player(now, getattr(p, 'damage', 1), getattr(p, 'blast_reason', '被小粽粽炸弹击败！')):
            return True
        play_sound('hit')
        return False

    def _apply_niu_ice_axe_effect(self, projectile, player, now):
        if (isinstance(self.boss, NiuBoss) and isinstance(projectile, ReturningAxe)
                and not projectile.red and not self._player_is_invincible(now)):
            player.niu_freeze_until = max(player.niu_freeze_until, now + 1000)
            player.niu_slow_until = max(player.niu_slow_until, now + 3000)

    def _gift_damage_mult(self, now):
        return 2.0 if now < self.gift_fire_until else 1.0

    def _blocked_by_fire_wall(self, rect, wall_rects=None):
        wall_rects = wall_rects if wall_rects is not None else [fw.rect() for fw in self.fire_walls]
        return any(rect.colliderect(fr) for fr in wall_rects)

    def _block_enemy_with_fire_walls(self, e, wall_rects=None):
        er = e.rect()
        wall_rects = wall_rects if wall_rects is not None else [fw.rect() for fw in self.fire_walls]
        for fr in wall_rects:
            if er.colliderect(fr):
                e.y = fr.top - e.h
                return

    def _pull_projectiles_to_storms(self, projectiles):
        now = pygame.time.get_ticks()
        for p in projectiles[:]:
            if getattr(p, 'unblockable', False):
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
        now = pygame.time.get_ticks()
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
        self.explosions.append(Explosion(ms.x, ms.y, (165, 255, 90), 34))
        self.particles.append(Particle(ms.x, ms.y, (205, 255, 120), 30))
        for e in self.enemies[:]:
            ex, ey = e.x, e.y + e.h // 2
            dist = math.hypot(ex - ms.x, ey - ms.y)
            if dist >= ms.radius:
                continue
            if self._show_immune(e):
                continue
            e.hit_by('pistol', 1.0 * self._gift_damage_mult(pygame.time.get_ticks()))
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
            e.apply_slow(pygame.time.get_ticks(), 900, 0.45)
            self.particles.append(Particle(e.x, e.y + e.h // 2, (190, 255, 115), 12))
            if e.is_killed('pistol'):
                self._kill_enemy(e)
        if include_boss and self.boss and self._storm_hits_boss(ms):
            self.boss.hit_by('pistol', 1.0 * self._gift_damage_mult(pygame.time.get_ticks()),
                             hit_rect=self._boss_hitbox_in_radius(ms.x, ms.y, ms.radius))
            if self._settle_boss_if_killed():
                return
        play_sound('storm')

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
            if include_boss and damage_now and self._storm_hits_boss(ms):
                self.boss.hit_by('pistol', 0.75 * self._gift_damage_mult(now),
                                 hit_rect=self._boss_hitbox_in_radius(ms.x, ms.y, ms.radius))
                if self._settle_boss_if_killed():
                    return
            for e in self.enemies[:]:
                if ms.contains(e):
                    if self._show_immune(e, now):
                        continue
                    if ms.can_pull(now):
                        ms.pull(e)
                    if damage_now:
                        e.hit_by('pistol', 0.5 * self._gift_damage_mult(now))
                        if e.is_killed('pistol'):
                            self._kill_enemy(e)

    def _storm_hits_boss(self, ms):
        return self._boss_in_radius(ms.x, ms.y, ms.radius)

    def _boss_in_radius(self, x, y, radius):
        return self._boss_hitbox_in_radius(x, y, radius) is not None

    def _boss_hitbox_in_radius(self, x, y, radius):
        if not self.boss:
            return None
        for br in self.boss.hitboxes():
            closest_x = max(br.left, min(x, br.right))
            closest_y = max(br.top, min(y, br.bottom))
            if math.hypot(x - closest_x, y - closest_y) <= radius:
                return br
        return None

    def _activate_skill(self, sk, player=None):
        player = player or self.player
        now = pygame.time.get_ticks()
        cd_mult = self.difficulty.skill_cd_mult if self.difficulty else 1.0
        cd_ms = int(sk.cooldown_ms * (0.5 if self.infinite_mode else cd_mult))
        if not self._skill_ready(player, sk.skill_type, now): return
        px, py = player.x, player.y - 28
        st = sk.skill_type
        if st == 'fire_wall':
            lifetime = 2500 if self.infinite_mode else 5000
            fw = FireWall(px, max(100, py - 40), lifetime)
            fw.owner = player; fw.skill_type = st
            self._start_skill_effect(player, st, cd_ms, lifetime, now)
            self.fire_walls.append(fw)
            play_sound('fire_cast')
        elif st == 'fireball':
            self._start_skill_effect(player, st, cd_ms, 2500, now)
            for angle in (-14, 0, 14):
                self.skill_projectiles.append(SkillProjectile(px, py, angle, 8, 'fireball', piercing=True, owner=player, skill_type=st))
            play_sound('fire_cast')
        elif st == 'ice_floor':
            ice = IceFloor(px, py)
            ice.owner = player; ice.skill_type = st
            self._start_skill_effect(player, st, cd_ms, 8000, now)
            self.ice_floors.append(ice)
            play_sound('ice_cast')
        elif st == 'ice_balls':
            self._start_skill_effect(player, st, cd_ms, 2500, now)
            for a in (-56, -40, -24, -8, 8, 24, 40, 56): self.skill_projectiles.append(SkillProjectile(px, py, a, 7, 'ice_ball', owner=player, skill_type=st))
            play_sound('ice_cast')
        elif st == 'lightning':
            self._start_skill_effect(player, st, cd_ms, 300, now)
            targets = self.enemies[:]
            if self.boss:
                targets.append(self.boss)
            targets.sort(key=lambda target: (
                target.x - px) ** 2 + (target.y + target.h // 2 - py) ** 2)
            targets = targets[:5]
            if targets:
                self.lightnings.append(Lightning(px, py, [(e, e.x, e.y+e.h//2) for e in targets]))
                for e in targets:
                    if self._show_immune(e, now):
                        continue
                    e.hit_by('sniper', 2.0 * self._gift_damage_mult(now))
                    if e is self.boss:
                        self._settle_boss_if_killed()
                    elif e.is_killed('sniper'):
                        self._kill_enemy(e)
                play_sound('lightning')
        elif st == 'magnetic_storm':
            ms = MagneticStorm(px, max(120, player.y - 170))
            ms.owner = player; ms.skill_type = st
            self._start_skill_effect(player, st, cd_ms, 3000, now)
            self.magnetic_storms.append(ms)
            play_sound('storm')
        elif st == 'water_heal':
            self._start_skill_effect(player, st, cd_ms, 5000, now)
            if self.player_hp >= self.max_player_hp:
                self._heal_player(1, temporary_ms=15000)
            else:
                self._heal_player(1)
            player.water_haste_until = now + 5000
            self.player_invincible_until = max(self.player_invincible_until, now + 2000)
            self.water_heal_effects.append((player.x, player.y - 16, now))
            play_sound('water_cast')
        elif st == 'water_boost':
            self._start_skill_effect(player, st, cd_ms, 10000, now)
            for target in self.players:
                target.water_boost_until = now + 10000
            play_sound('level_up')

    def _activate_radiation_laser(self, player=None):
        now = pygame.time.get_ticks()
        cd_mult = self.difficulty.skill_cd_mult if self.difficulty else 1.0
        self._expire_radiation_lasers(now, cd_mult)
        candidates = (player,) if player else self.players
        for player in candidates:
            if player.character != 'radiation':
                continue
            active = next((laser for laser in self.radiation_lasers if laser.owner is player and not laser.is_expired(now)), None)
            if active:
                active.whip(now)
                play_sound('laser')
                return
            skill_type = 'radiation_laser'
            cd_ms = int(12000 * (0.5 if self.infinite_mode else cd_mult))
            if now < player.skill_cooldowns.get(skill_type, 0):
                return
            player.animation_skill = 'radiation_laser'
            player.animation_skill_at = now
            laser = RadiationLaser(player, 5000)
            laser.cooldown_ms = cd_ms
            self.radiation_lasers.append(laser)
            play_sound('laser')
            return

    def _activate_dart_shield(self, player):
        """辐射工程师 R 技能：8 个齿纹飞盘环绕自身 5 秒，结束后向外飞出。"""
        if not player or player.character != 'radiation':
            return
        now = pygame.time.get_ticks()
        skill_type = 'dart_shield'
        if not self._skill_ready(player, skill_type, now):
            return
        if any(s.owner is player and not s.is_gone(now) for s in self.dart_shields):
            return
        cd_mult = self.difficulty.skill_cd_mult if self.difficulty else 1.0
        cd_ms = int(20000 * (0.5 if self.infinite_mode else cd_mult))
        self._start_skill_effect(player, skill_type, cd_ms, 5000, now)
        self.dart_shields.append(SpinningDarts(player, 5000))
        play_sound('dart_cast')

    # ═══ Update ═══════════════════════════════════════════════════════════════
    def update(self):
        now = pygame.time.get_ticks()
        self._expire_active_skills(now)
        self._maybe_fire_gift_lightning(now)
        if self.state == GameState.INFINITE_COUNTDOWN:
            if now >= self.infinite_countdown_end:
                self.state = self.infinite_resume_state
            return
        if self.state == GameState.LEVEL_TRANSITION:
            if now >= self.level_transition_end:
                self._start_level(self.current_level+1)
                if self.state != GameState.BOSS_FIGHT:
                    self.state = GameState.PLAYING
            return
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

    def _player_is_invincible(self, now):
        return now < self.player_invincible_until

    def _damage_player(self, now, amount, reason):
        if self._player_is_invincible(now):
            return False
        self.player_hp -= amount
        if self.player_hp <= 0:
            self._player_defeated(reason)
            return True
        return False

    def _enemy_contact_damage(self, e):
        if e.is_large:
            return 3
        return 1 if e.edef['key'] == 'goldfish' else 2

    def _damage_player_on_contacts(self, now):
        for e in self.enemies[:]:
            if now - e.last_contact_damage_time < CONTACT_DAMAGE_COOLDOWN:
                continue
            if self._hit_player(e.rect()):
                e.last_contact_damage_time = now
                amount = self._enemy_contact_damage(e)
                if self._damage_player(now, amount, f'被{e.edef["name"]}撞击击败！'):
                    return True
        if self.boss and any(self._hit_player(br) for br in self.boss.hitboxes()) and not self._player_is_invincible(now):
            self.player_hp = 0
            self._player_defeated(f'被{self.boss.name}撞击击败！')
            return True
        return False

    def _hit_enemy_with_fireball(self, sp, e, now):
        if id(e) in sp.hit_targets:
            return
        if self._show_immune(e, now):
            sp.hit_targets.add(id(e))
            return
        e.hit_by('sniper', sp.damage * self._gift_damage_mult(now))
        sp.hit_targets.add(id(e))
        sp.damage *= 0.7
        if not e.burning:
            e.burning = True; e.burn_start = now; e.last_burn_tick = now
        e.burn_damage = True
        self._spawn_hit_effect(sp.x, sp.y, (255, 130, 35), e.is_large)
        if e.is_killed('sniper'):
            self._kill_enemy(e)

    def _hit_boss_with_fireball(self, sp):
        if not self.boss or id(self.boss) in sp.hit_targets:
            return
        self.boss.hit_by('sniper', sp.damage * self._gift_damage_mult(pygame.time.get_ticks()), hit_rect=sp.rect())
        sp.hit_targets.add(id(self.boss))
        sp.damage *= 0.7
        self._spawn_hit_effect(sp.x, sp.y, (255, 150, 60), True)
        self._settle_boss_if_killed()

    def _explode_grenade(self, sp, include_boss=False):
        self.explosions.append(Explosion(sp.x, sp.y, (120, 145, 80), 26))
        self.particles.append(Particle(sp.x, sp.y, (225, 210, 130), 18))
        for e in self.enemies[:]:
            if math.hypot(e.x - sp.x, e.y + e.h // 2 - sp.y) <= FISHER_GRENADE_RADIUS:
                if self._show_immune(e):
                    continue
                e.hit_by('pistol', FISHER_GRENADE_DAMAGE * self._gift_damage_mult(pygame.time.get_ticks()))
                self._spawn_hit_effect(e.x, e.y + e.h // 2, (225, 210, 130), e.is_large)
                if e.is_killed('pistol'):
                    self._kill_enemy(e)
        if include_boss and self.boss:
            boss_hitbox = self._boss_hitbox_in_radius(sp.x, sp.y, FISHER_GRENADE_RADIUS)
            if boss_hitbox:
                self.boss.hit_by('pistol', FISHER_GRENADE_DAMAGE * self._gift_damage_mult(pygame.time.get_ticks()),
                                 hit_rect=boss_hitbox)
                self._spawn_hit_effect(sp.x, sp.y, (225, 210, 130), True)
                self._settle_boss_if_killed()
        play_sound('hit')

    def _move_player_from_keys(self, player, keys, now, left, right, up, down):
        if now < player.niu_freeze_until:
            return
        dx = 0; dy = 0
        speed = self._player_speed(player, now)
        if self._pressed_key(keys, left): dx -= speed
        if self._pressed_key(keys, right): dx += speed
        if self._pressed_key(keys, up): dy -= speed
        if self._pressed_key(keys, down): dy += speed
        player.move(dx, dy)

    def _infinite_density(self, now):
        if not self.infinite_mode:
            return 1
        elapsed = max(0, now - self.infinite_start_time)
        if elapsed <= 10000:
            return 5
        raw_target = 5 + int((elapsed - 10000) // 5000) * 2
        if raw_target < 20:
            return raw_target
        bucket = int(elapsed // 5000)
        return random.Random(bucket).randint(20, 26)

    def _infinite_health_mult(self, now):
        if not self.infinite_mode:
            return 1.0
        elapsed = max(0, now - self.infinite_start_time)
        raw_target = 5 if elapsed <= 10000 else 5 + int((elapsed - 10000) // 5000) * 2
        if raw_target < 20:
            return 1.0
        over_ms = max(0, elapsed - 50000)
        return 1.0 + over_ms / 120000 * 0.25

    def _infinite_damage_mult(self):
        """无限模式：每完成一轮 Boss 循环，角色所有伤害（子弹/技能）+30%。"""
        if not self.infinite_mode:
            return 1.0
        cycle = max(0, self.infinite_boss_index - 1) // len(BOSS_DEFS)
        return 1.0 + cycle * 0.30

    def _scale_infinite_boss(self, boss, boss_number):
        cycle = boss_number // len(BOSS_DEFS)
        if cycle <= 0:
            return
        final_base_hp = math.ceil(BOSS_DEFS[-1]['base_hp'] * self.difficulty.boss_hp_mult * 2)
        extra_steps = boss_number - len(BOSS_DEFS)
        hp_mult = 1.0 + INFINITE_BOSS_CYCLE_HP_GROWTH + extra_steps * INFINITE_BOSS_STEP_HP_GROWTH
        boss.max_hp = max(boss.max_hp, math.ceil(final_base_hp * hp_mult))
        boss.hp = boss.max_hp
        if isinstance(boss, ZongBoss):
            boss.body_hp = [boss.max_hp / 2, boss.max_hp / 2]

    def _spawn_infinite_enemies_to_target(self, now, divisor=1):
        target = max(1, self._infinite_density(now) // divisor)
        missing = target - len(self.enemies)
        if missing <= 0:
            return
        for _ in range(min(missing, 2)):
            self.spawn_enemy()

    def _enemy_required_hits(self, e, weapon_name):
        wdef = WEAPON_DEFS[weapon_name]
        needed = wdef.large_shots if e.is_large else wdef.normal_shots
        return max(1, math.ceil(needed * getattr(e, 'health_mult', 1.0)))

    def _expire_radiation_lasers(self, now, cd_mult=None):
        if cd_mult is None:
            cd_mult = self.difficulty.skill_cd_mult if self.difficulty else 1.0
        for laser in self.radiation_lasers[:]:
            if not laser.is_expired(now):
                continue
            cd_ms = getattr(laser, 'cooldown_ms', int(12000 * (0.5 if self.infinite_mode else cd_mult)))
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
                    self._spawn_hit_effect(e.x, e.y + e.h // 2, (180, 60, 80), e.is_large)
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
                self._spawn_hit_effect(self.boss.x, self.boss.y + self.boss.h // 2, (180, 60, 80), True)
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
                    e.hit_by('sniper', 0.45 * self._gift_damage_mult(now))
                    laser.push(e)
                    self._spawn_hit_effect(e.x, e.y + e.h // 2, (120, 255, 120), e.is_large)
                    if e.is_killed('sniper'):
                        self._kill_enemy(e)
                        if self.state not in (GameState.PLAYING, GameState.BOSS_FIGHT):
                            return
            if self.boss and self.boss.collides(lr) and laser.can_damage(self.boss, now):
                previous_hp = self.boss.hp
                self.boss.hit_by('sniper', 0.35 * self._gift_damage_mult(now), hit_rect=lr)
                if self.boss.hp < previous_hp:
                    self.boss.apply_slow(now, 600, 0.85)
                self._spawn_hit_effect(self.boss.x, self.boss.y + self.boss.h // 2, (190, 70, 255), True)
                # 激光命中 Boss：灼烧冲击特效 + 音效（节流）
                impact_x = self.boss.x + random.randint(-24, 24)
                impact_y = self.boss.y + self.boss.h // 2 + random.randint(-14, 22)
                self.laser_impacts.append((impact_x, impact_y, now))
                if now - self.last_laser_hit_sound >= 220:
                    play_sound('laser_hit')
                    self.last_laser_hit_sound = now
                if self._settle_boss_if_killed():
                    return

    def _shoot(self, now, player=None):
        player = player or self.player
        if not player.current_weapon:
            return False
        wkey = player.current_weapon; cost = self._bullet_cost(wkey)
        if self._hard_ammo_mode() and wkey != 'pistol' and player.weapon_ammo.get(wkey, 0) <= 0:
            if wkey in player.owned_weapons:
                player.owned_weapons.remove(wkey)
            player.current_weapon = 'pistol'
            return False
        shot_count = 3 if wkey == 'shotgun' else 1
        total_cost = cost * shot_count
        if total_cost > 0:
            if self.player.gold < total_cost: return False
            self.player.gold -= total_cost
        shots = player.shoot(now)
        for b in shots:
            b.source_player = player
            if wkey == 'rifle':
                b.damage = 1.3
            if now < self.gift_fire_until:
                b.gift_kind = 'fire'
                b.radius = 6
            elif now < self.gift_ice_until:
                b.gift_kind = 'ice'
                b.radius = 6
                b.damage = 2.2
        self.bullets.extend(shots)
        self._consume_hard_ammo(player, wkey)
        self.muzzle_flashes.append((player, now))
        play_sound(f'shoot_{wkey}')
        return True

    def _apply_bullet_passive(self, e, b, now):
        damage = b.damage
        if b.weapon_name == 'shotgun':
            damage *= 0.5
        if b.character == 'fire':
            damage *= 1.5
            if not e.burning:
                e.burning = True; e.burn_start = now; e.last_burn_tick = now
                e.burn_damage = False
        elif b.character == 'ice':
            e.apply_slow(now, 4000, 0.7)
        elif b.character == 'radiation':
            e.infected = True
            e.infected_weapon = b.weapon_name
        if getattr(b, 'gift_kind', None) == 'ice':
            e.frozen = True
            e.frozen_until = now + 2000
        shooter = getattr(b, 'source_player', self.player)
        if now < shooter.water_boost_until:
            damage *= 1.5
        damage *= self._gift_damage_mult(now)
        e.hit_by(b.weapon_name, damage)

    def _bullet_hit_color(self, b):
        if getattr(b, 'gift_kind', None) == 'fire':
            return (255, 105, 35)
        if getattr(b, 'gift_kind', None) == 'ice':
            return (45, 115, 230)
        return WEAPON_DEFS[b.weapon_name].color

    def _character_cost(self, cdef):
        cost = cdef.cost
        if self.difficulty:
            if self.difficulty.name == '简单':
                cost -= 10
            elif self.difficulty.name == '困难':
                cost += 10
            elif self.difficulty.name == '自定义':
                cost = cost * self.difficulty.character_cost_mult
        return self._round_cost(cost)

    def _update_playing(self, now):
        keys = pygame.key.get_pressed()
        self._move_player_from_keys(self.player, keys, now, self._key('p1_left'), self._key('p1_right'), self._key('p1_up'), self._key('p1_down'))
        if self.two_player:
            self._move_player_from_keys(self.player2, keys, now, self._key('p2_left'), self._key('p2_right'), self._key('p2_up'), self._key('p2_down'))
        self._expire_water_temp_hp(now)
        if self._key_pressed(keys, 'p1_shoot') and self.player.can_shoot(now):
            self._shoot(now, self.player)
        if self.two_player and self.player2.current_weapon and self._key_pressed(keys, 'p2_shoot') and self.player2.can_shoot(now):
            self._shoot(now, self.player2)
        if self.infinite_mode and now >= self.next_infinite_boss_time and not self.boss:
            self._trigger_infinite_boss()
            return
        if now - self.last_spawn_time >= self.spawn_interval:
            if self.infinite_mode:
                self._spawn_infinite_enemies_to_target(now)
            else:
                self.spawn_enemy()
            self.last_spawn_time = now
        self._maybe_spawn_gift(now)
        fire_wall_rects = [fw.rect() for fw in self.fire_walls]
        for b in self.bullets[:]:
            b.update()
            if b.is_offscreen(): self.bullets.remove(b)
        for e in self.enemies[:]:
            e.update()
            self._block_enemy_with_fire_walls(e, fire_wall_rects)
            if e.should_attack(now):
                self.enemy_projectiles.extend(e.attack(now, self._nearest_player(e.x, e.y).x))
            if e.reached_bottom() and not self._player_is_invincible(now):
                self._player_defeated(f'{e.edef["name"]} 入侵成功！'); return
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
            elif self._blocked_by_fire_wall(ep.rect(), fire_wall_rects):
                self.enemy_projectiles.remove(ep)
            elif self._blocked_by_ice_floor(ep):
                self.enemy_projectiles.remove(ep)
            elif self._blocked_by_dart_shield(ep.block_rect(), now):
                self._spawn_hit_effect(ep.x, ep.y, (140, 255, 150), False)
                self.enemy_projectiles.remove(ep)
            elif getattr(ep, 'bomb', False) and self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._explode_enemy_bomb(ep, now): return
            elif self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._damage_player(now, 1, '被怪物子弹击败！'): return
        for b in self.bullets[:]:
            br = b.rect()
            if self._handle_bullet_gift_hit(b, now):
                continue
            for e in self.enemies[:]:
                if (br.right < e.x - e.w // 2 or br.left > e.x + e.w // 2 or
                        br.bottom < e.y or br.top > e.y + e.h):
                    continue
                if id(e) not in b.hit_targets and br.colliderect(e.rect()):
                    self._apply_bullet_passive(e, b, now); b.hit_targets.add(id(e)); play_sound('hit')
                    self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), e.is_large)
                    if e.is_killed(b.weapon_name):
                        self._kill_enemy(e)
                        if self.state != GameState.PLAYING:
                            break
                    if b.weapon_name == 'sniper':
                        b.damage *= 0.7
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
                if (sr.right < e.x - e.w // 2 or sr.left > e.x + e.w // 2 or
                        sr.bottom < e.y or sr.top > e.y + e.h):
                    continue
                if sr.colliderect(e.rect()):
                    if sp.ptype == 'grenade':
                        self._explode_grenade(sp)
                        self._remove_skill_projectile(sp, now); break
                    elif sp.ptype == 'fireball':
                        self._hit_enemy_with_fireball(sp, e, now)
                        if not sp.piercing: self._remove_skill_projectile(sp, now); break
                    elif sp.ptype == 'ice_ball':
                        if self._show_immune(e, now):
                            self._remove_skill_projectile(sp, now); break
                        e.hit_by('pistol', self._gift_damage_mult(now)); e.frozen = True; e.frozen_until = now + 4000
                        self._spawn_hit_effect(sp.x, sp.y, (150, 220, 255), e.is_large)
                        if e.is_killed('pistol'): self._kill_enemy(e)
                        self._remove_skill_projectile(sp, now); break
        for fw in self.fire_walls[:]:
            if fw.is_expired():
                self.fire_walls.remove(fw)
                self._finish_skill_effect(getattr(fw, 'owner', None), getattr(fw, 'skill_type', None), now)
        for ice in self.ice_floors[:]:
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
                for e in self.enemies[:]:
                    if math.hypot(e.x-hx, e.y+e.h//2-hy) < ice.freeze_radius:
                        if self._is_zongzong(e):
                            self._show_immune(e, now)
                            continue
                        e.frozen = True; e.frozen_until = now + 4000
                self.particles.append(Particle(hx, hy, (150, 220, 255), 10))
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
            n = self._enemy_required_hits(e, w)
            if (e.hits.get(w, 0) + e.burn_hits) >= n: self._kill_enemy(e)
        for c in self.coins[:]:
            c.update()
            if self._hit_player(c.rect()):
                self.player.gold += c.value; play_sound('coin'); self.coins.remove(c)
            elif c.is_offscreen(): self.coins.remove(c)
        for box in self.gift_boxes[:]:
            box.update()
            if box.is_offscreen():
                self.gift_boxes.remove(box)
        for p in self.particles[:]:
            p.update()
            if p.is_dead(): self.particles.remove(p)
        for ex in self.explosions[:]:
            ex.update()
            if ex.is_dead(): self.explosions.remove(ex)

    def _update_special_boss_hazards(self, now):
        boss = self.boss
        if not isinstance(boss, NiuBoss):
            return False
        if now < boss.vortex_until:
            for player in self.players:
                dx, dy = boss.vortex_x - player.x, boss.vortex_y - player.y
                distance = math.hypot(dx, dy)
                if 1 < distance < 260:
                    pull = 0.9 + (1 - distance / 260) * 1.2
                    player.move(dx / distance * pull, dy / distance * pull)
        if now < boss.vortex_until and now >= boss.vortex_next_tick:
            boss.vortex_next_tick = now + 650
            self.explosions.append(Explosion(boss.vortex_x + random.randint(-70, 70),
                                             boss.vortex_y + random.randint(-70, 70), (255, 105, 30), 14))
            for player in self.players:
                if math.hypot(player.x - boss.vortex_x, player.y - boss.vortex_y) <= 155:
                    if self._damage_player(now, 1, '被牛魔王的漩涡击败！'):
                        return True
                    break
            for e in self.enemies[:]:
                if math.hypot(e.x - boss.vortex_x, e.y + e.h // 2 - boss.vortex_y) > 155:
                    continue
                e.hit_by('pistol', 1.0)
                boss.hp = min(boss.max_hp, boss.hp + boss.max_hp * 0.012)
                self.explosions.append(Explosion(e.x, e.y + e.h // 2, (255, 100, 35), 9))
                if e.is_killed('pistol'):
                    self.enemies.remove(e)
                    self.explosions.append(Explosion(e.x, e.y + e.h // 2, (255, 145, 45), 18))
        if now >= boss.lightning_warning_until and now >= boss.lightning_next_tick and boss.lightning_rects(now):
            boss.lightning_next_tick = now + 650
            if any(self._hit_player(rect) for rect in boss.lightning_rects(now)):
                if self._damage_player(now, 2, '被牛魔王的激光闪电击败！'):
                    return True
        return False

    def _update_boss_fight(self, now):
        if not self.boss: return
        if self._settle_boss_if_killed():
            return
        keys = pygame.key.get_pressed()
        self._move_player_from_keys(self.player, keys, now, self._key('p1_left'), self._key('p1_right'), self._key('p1_up'), self._key('p1_down'))
        if self.two_player:
            self._move_player_from_keys(self.player2, keys, now, self._key('p2_left'), self._key('p2_right'), self._key('p2_up'), self._key('p2_down'))
        self._expire_water_temp_hp(now)
        self.boss.update()
        if isinstance(self.boss, ZongBoss) and now < self.boss.snow_until:
            for player in self.players:
                player.snow_slow_until = max(player.snow_slow_until, self.boss.snow_until)
        if isinstance(self.boss, ZongBoss) and self.boss.pending_projectiles:
            self.boss_projectiles.extend(self.boss.pending_projectiles)
            self.boss.pending_projectiles.clear()
        if self._damage_player_on_contacts(now):
            return
        death_lasers = self.boss.death_laser_rects(now)
        if any(self._hit_player(rect) for rect in death_lasers):
            if self._damage_player(now, 1, f'被{self.boss.name}毁灭激光击败！'): return
        boss_spawn_interval = 1500 if self.current_level >= 6 else max(self.spawn_interval, 2400)
        if self.infinite_mode:
            boss_spawn_interval = 1600
        if now - self.last_spawn_time >= boss_spawn_interval:
            if self.infinite_mode:
                self._spawn_infinite_enemies_to_target(now, 2)
            else:
                self.spawn_enemy()
            self.last_spawn_time = now
        self._maybe_spawn_gift(now)
        fire_wall_rects = [fw.rect() for fw in self.fire_walls]
        for e in self.enemies[:]:
            e.update()
            self._block_enemy_with_fire_walls(e, fire_wall_rects)
            if e.should_attack(now):
                self.enemy_projectiles.extend(e.attack(now, self._nearest_player(e.x, e.y).x))
            if e.reached_bottom() and not self._player_is_invincible(now):
                self._player_defeated(f'{e.edef["name"]} 入侵成功！'); return
        if self._update_special_boss_hazards(now):
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
            elif self._blocked_by_fire_wall(ep.rect(), fire_wall_rects):
                self.enemy_projectiles.remove(ep)
            elif self._blocked_by_ice_floor(ep):
                self.enemy_projectiles.remove(ep)
            elif self._blocked_by_dart_shield(ep.block_rect(), now):
                self._spawn_hit_effect(ep.x, ep.y, (140, 255, 150), False)
                self.enemy_projectiles.remove(ep)
            elif getattr(ep, 'bomb', False) and self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._explode_enemy_bomb(ep, now): return
            elif self._hit_player(ep.rect()):
                self.enemy_projectiles.remove(ep)
                if self._damage_player(now, 1, '被怪物子弹击败！'): return
        if self.boss.should_attack(now):
            self.boss_projectiles.extend(self.boss.attack(now, self._nearest_player(self.boss.x, self.boss.y).x))
            self.boss.animation_attack_at = now
        self._pull_projectiles_to_storms(self.boss_projectiles)
        for bp in self.boss_projectiles[:]:
            target = self._nearest_player(bp.x, bp.y)
            bp.update(target_x=target.x, target_y=target.y)
            if getattr(bp, 'impact_pending', False):
                bp.impact_pending = False
                if self._explode_enemy_bomb(bp, now): return
            if not bp.alive:
                self.boss_projectiles.remove(bp)
                if getattr(bp, 'bomb', False) and self._explode_enemy_bomb(bp, now): return
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
            elif self._hit_player(bp.rect()):
                if not hasattr(bp, 'impact_pending'):
                    self.boss_projectiles.remove(bp)
                if now - getattr(bp, 'last_player_hit', -9999) >= 800:
                    bp.last_player_hit = now
                    if isinstance(bp, ReturningAxe) and not bp.red:
                        hit_player = self._hit_player(bp.rect())
                        if hit_player:
                            self._apply_niu_ice_axe_effect(bp, hit_player, now)
                    if self._damage_player(now, bp.damage, f'被{self.boss.name}击败！'): return
        if self._key_pressed(keys, 'p1_shoot') and self.player.can_shoot(now):
            self._shoot(now, self.player)
        if self.two_player and self.player2.current_weapon and self._key_pressed(keys, 'p2_shoot') and self.player2.can_shoot(now):
            self._shoot(now, self.player2)
        for b in self.bullets[:]:
            b.update()
            if b.is_offscreen(): self.bullets.remove(b)
            else:
                if self._handle_bullet_gift_hit(b, now):
                    continue
                br = b.rect()
                hit_enemy = False
                for e in self.enemies[:]:
                    if (br.right < e.x - e.w // 2 or br.left > e.x + e.w // 2 or
                            br.bottom < e.y or br.top > e.y + e.h):
                        continue
                    if id(e) not in b.hit_targets and br.colliderect(e.rect()):
                        hit_enemy = True
                        self._apply_bullet_passive(e, b, now); b.hit_targets.add(id(e)); play_sound('hit')
                        self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), e.is_large)
                        if e.is_killed(b.weapon_name):
                            self._kill_enemy(e)
                        if b.weapon_name == 'sniper':
                            b.damage *= 0.7
                        else:
                            if b in self.bullets: self.bullets.remove(b)
                            break
                if (not hit_enemy) and self.boss and b in self.bullets and self.boss.collides(br):
                    damage = b.damage * (1.5 if b.character == 'fire' else 1.0)
                    if b.weapon_name == 'shotgun':
                        damage *= 0.5
                    shooter = getattr(b, 'source_player', self.player)
                    if now < shooter.water_boost_until:
                        damage *= 1.5
                    damage *= self._gift_damage_mult(now)
                    if isinstance(self.boss, ZongBoss) and self.boss.reflects_bullet():
                        self.boss_projectiles.append(ZongReflectBullet(b.x, b.y))
                    previous_hp = self.boss.hp
                    self.boss.hit_by(b.weapon_name, damage, source='bullet', hit_rect=br)
                    if self.boss.hp < previous_hp and (b.character == 'ice' or getattr(b, 'gift_kind', None) == 'ice'):
                        self.boss.apply_slow(now, 4000, 0.7)
                    self.bullets.remove(b)
                    play_sound('hit')
                    self._spawn_hit_effect(b.x, b.y, self._bullet_hit_color(b), True)
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
                if (sr.right < e.x - e.w // 2 or sr.left > e.x + e.w // 2 or
                        sr.bottom < e.y or sr.top > e.y + e.h):
                    continue
                if sr.colliderect(e.rect()):
                    if sp.ptype == 'grenade':
                        self._explode_grenade(sp, include_boss=True)
                        self._remove_skill_projectile(sp, now)
                        if self.state != GameState.BOSS_FIGHT:
                            return
                        break
                    elif sp.ptype == 'fireball':
                        self._hit_enemy_with_fireball(sp, e, now)
                        if not sp.piercing: self._remove_skill_projectile(sp, now); break
                    elif sp.ptype == 'ice_ball':
                        if self._show_immune(e, now):
                            self._remove_skill_projectile(sp, now); break
                        e.hit_by('pistol', self._gift_damage_mult(now)); e.frozen = True; e.frozen_until = now + 4000
                        self._spawn_hit_effect(sp.x, sp.y, (150, 220, 255), e.is_large)
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
                elif sp.ptype == 'fireball':
                    self._hit_boss_with_fireball(sp)
                else:
                    self.boss.hit_by('sniper', self._gift_damage_mult(now), hit_rect=sr)
                if sp.ptype == 'ice_ball' and self.boss and self.boss.hp < previous_hp:
                    self.boss.apply_slow(now, 4000, 0.7)
                    self._spawn_hit_effect(sp.x, sp.y, (150, 220, 255), True)
                if not (sp.ptype == 'fireball' and sp.piercing): self._remove_skill_projectile(sp, now)
                if self._settle_boss_if_killed():
                    return
        for fw in self.fire_walls[:]:
            if fw.is_expired():
                self.fire_walls.remove(fw)
                self._finish_skill_effect(getattr(fw, 'owner', None), getattr(fw, 'skill_type', None), now)
        self._update_magnetic_storms(now, include_boss=True)
        if self.state != GameState.BOSS_FIGHT:
            return
        self._pull_projectiles_to_storms(self.boss_projectiles)
        self._pull_projectiles_to_storms(self.enemy_projectiles)
        for ice in self.ice_floors[:]:
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
                for e in self.enemies[:]:
                    if math.hypot(e.x-hx, e.y+e.h//2-hy) < ice.freeze_radius:
                        if self._is_zongzong(e):
                            self._show_immune(e, now)
                            continue
                        e.frozen = True; e.frozen_until = now + 4000
                self.particles.append(Particle(hx, hy, (150, 220, 255), 10))
                ice.hit(hx)
                if not ice.alive:
                    self._shatter_ice_floor(ice, now)
                continue
            if self.boss and self.boss.collides(ice.rect()):
                previous_hp = self.boss.hp
                self.boss.hit_by('pistol', 0.5 * self._gift_damage_mult(now), hit_rect=ice.rect())
                if self.boss.hp < previous_hp:
                    self.boss.apply_slow(now, 4000, 0.7)
                self.particles.append(Particle(ice.x, ice.y, (150, 220, 255), 10))
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
            n = self._enemy_required_hits(e, w)
            if (e.hits.get(w, 0) + e.burn_hits) >= n: self._kill_enemy(e)
        for c in self.coins[:]:
            c.update()
            if self._hit_player(c.rect()):
                self.player.gold += c.value; play_sound('coin'); self.coins.remove(c)
            elif c.is_offscreen(): self.coins.remove(c)
        for box in self.gift_boxes[:]:
            box.update()
            if box.is_offscreen():
                self.gift_boxes.remove(box)
        for p in self.particles[:]:
            p.update()
            if p.is_dead(): self.particles.remove(p)
        for ex in self.explosions[:]:
            ex.update()
            if ex.is_dead(): self.explosions.remove(ex)

    def _settle_boss_if_killed(self):
        if self.boss and self.boss.is_killed():
            self._kill_boss()
            return True
        return False

    def _advance_infinite_background(self, now):
        self.bg_transition_prev = self.bg
        self.infinite_background_level = self.infinite_background_level % len(LEVEL_CONFIGS) + 1
        self.bg = self._load_bg()
        self.bg_transition_until = now + INFINITE_BG_FADE_MS

    def _kill_boss(self):
        if not self.boss:
            return
        self.chapter += 1
        b = self.boss; self.particles.append(Particle(b.x, b.y+b.h//2, (255, 200, 50), 30))
        self.explosions.append(Explosion(b.x, b.y+b.h//2, (255, 130, 70), 28))
        self.boss_projectiles.clear()
        if self.infinite_mode:
            self.score += 100
            self.kill_count += 1
            self.boss = None
            now = pygame.time.get_ticks()
            self.next_infinite_boss_time = now + 25000
            self.infinite_music_variant += 1
            self._advance_infinite_background(now)
            start_music(self.infinite_background_level, infinite=True, variant=self.infinite_music_variant)
            play_sound('kill')
            self.state = GameState.PLAYING
            return
        for _ in range(5): self.coins.append(Coin(b.x+random.randint(-20,20), b.y+random.randint(-10,10), 3))
        self._heal_player(1)
        play_sound('kill'); self.boss = None; self._level_complete()

    def _try_boss_absorb_minions(self, now):
        if self.infinite_mode or self.current_level != 6 or not self.boss.entered:
            return
        if not self.boss.next_absorb_time:
            self.boss.next_absorb_time = now + random.randint(8000, 14000)
            return
        if now < self.boss.next_absorb_time:
            return
        self.boss.next_absorb_time = now + random.randint(8000, 14000)
        minions = [e for e in self.enemies if not e.is_large]
        if not minions or random.random() >= 0.35:
            return
        minions.sort(key=lambda e: math.hypot(e.x - self.boss.x, e.y - self.boss.y))
        absorbed = minions[:3]
        for e in absorbed:
            if e in self.enemies:
                self.enemies.remove(e)
                self.explosions.append(Explosion(e.x, e.y + e.h // 2, (145, 45, 220), 16))
                self.particles.append(Particle(e.x, e.y + e.h // 2, (210, 90, 255), 16))
                self.boss.hp = min(self.boss.max_hp, self.boss.hp + self.boss.max_hp * 0.18)
        self.particles.append(Particle(self.boss.x, self.boss.y + self.boss.h // 2, (210, 60, 255), 34))
        play_sound('coin')

    def spawn_enemy(self):
        large_pool = [e for e in self.level_enemy_defs if e['is_large']]
        zong_pool = [e for e in self.level_enemy_defs if e['key'] == 'zongzong']
        normal_pool = [e for e in self.level_enemy_defs if not e['is_large'] and e['key'] != 'zongzong']
        large_chances = [0.0, 0.08, 0.12, 0.16, 0.20]
        large_chance = INFINITE_LARGE_ENEMY_CHANCE if self.infinite_mode else large_chances[min(self.current_level, len(large_chances)) - 1]
        zong_chance = ZONGZONG_SPAWN_CHANCE * (2 if (self.infinite_background_level if self.infinite_mode else self.current_level) == 8 else 1)
        if zong_pool and random.random() < zong_chance:
            edef = random.choice(zong_pool)
        elif large_pool and random.random() < large_chance:
            edef = random.choice(large_pool)
        else: edef = random.choice(normal_pool or self.level_enemy_defs)
        e = Enemy(edef)
        if self.difficulty:
            e.speed *= self.difficulty.enemy_speed_mult
            if not self.infinite_mode:
                e.speed *= get_level_enemy_speed_mult(self.difficulty.name, self.current_level)
            amin = int(self.difficulty.enemy_attack_interval_min)
            amax = int(self.difficulty.enemy_attack_interval_max)
            if not self.infinite_mode and self.current_level >= 6:
                amin = int(amin * 0.75)
                amax = int(amax * 0.75)
            e.attack_interval_min = min(amin, amax)
            e.attack_interval_max = max(amin, amax)
            e.attack_interval = random.randint(e.attack_interval_min, e.attack_interval_max)
        if self.infinite_mode:
            now = pygame.time.get_ticks()
            e.health_mult *= self._infinite_health_mult(now)
            e.speed *= 0.82
            e.damage_mult = self._infinite_damage_mult()
        if not e.is_large and random.random() < FAST_ENEMY_CHANCE:
            e.speed *= 2
            e.fast_variant = True
        e.attack_interval_min = max(500, int(e.attack_interval_min * ENEMY_ATTACK_INTERVAL_MULT))
        e.attack_interval_max = max(e.attack_interval_min, int(e.attack_interval_max * ENEMY_ATTACK_INTERVAL_MULT))
        e.attack_interval = random.randint(e.attack_interval_min, e.attack_interval_max)
        self.enemies.append(e)

    def _kill_enemy(self, e):
        if e not in self.enemies: return
        self.enemies.remove(e); self.kill_count += 1; self.level_kills += 1
        if any(player.character == 'water' for player in self.players):
            self.water_passive_kills += 1
            if self.water_passive_kills % 10 == 0:
                self._heal_player(1, increase_max=True)
        self.score += e.gold_value * (10 if self.infinite_mode else 1)
        if not self.infinite_mode:
            self.player.gold += e.gold_value
        self.spawn_interval = max(self.min_spawn_interval, self.spawn_interval - self.spawn_decrease)
        play_sound('kill')
        cx, cy = e.x, e.y+e.h//2
        if not self.infinite_mode:
            for _ in range(e.gold_value): self.coins.append(Coin(cx+random.randint(-10,10), cy+random.randint(-5,5), 1))
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
                if math.hypot(other.x-cx, other.y+other.h//2-cy) < 130:
                    if self._show_immune(other):
                        continue
                    other.hit_by(blast_weapon, 2.0 * self._gift_damage_mult(pygame.time.get_ticks()))
                    self._spawn_hit_effect(other.x, other.y+other.h//2, (120, 255, 80), other.is_large)
                    if other.is_killed(blast_weapon):
                        self._kill_enemy(other)
        lcfg = LEVEL_CONFIGS[self.current_level-1]
        if (not self.infinite_mode) and self.level_kills >= lcfg['kills_needed'] and self.state == GameState.PLAYING:
            self._trigger_boss()

    def _spawn_hit_effect(self, x, y, color, heavy=False):
        # 冲击波 + 火花 + 白色闪光，打击感更强
        self.explosions.append(Explosion(x, y, color, 14 if heavy else 10))
        self.particles.append(Particle(x, y, color, 18 if heavy else 12))
        self.particles.append(Particle(x, y, (255, 255, 255), 6 if heavy else 4))

    # ═══ Shop ═════════════════════════════════════════════════════════════════
    def _buy_or_equip_weapon(self, key):
        if key not in self.player.owned_weapons:
            cost = self._weapon_cost(key)
            if self.player.gold >= cost:
                self.player.gold -= cost
                self.player.owned_weapons.append(key)
                self._refill_hard_weapon(self.player, key)
                self.try_switch_weapon(key, self.player)
                play_sound('buy')
            else:
                play_sound('error')
        else:
            if self.try_switch_weapon(key, self.player):
                self.state = GameState.PLAYING
            else:
                play_sound('error')

    def _buy_or_equip_character(self, key):
        cdef = CHARACTER_DEFS[key]
        if key in self.player.owned_characters:
            if self.try_switch_character(key, self.player):
                self.state = GameState.PLAYING
            else:
                play_sound('error')
            return
        cost = self._character_cost(cdef)
        if self.player.gold >= cost:
            self.player.gold -= cost
            self.player.owned_characters.append(key)
            self.try_switch_character(key, self.player)
            play_sound('buy')
            self.state = GameState.PLAYING
        else:
            play_sound('error')

    def _handle_shop_click(self, mx, my):
        card_w, card_h, gap = 210, 76, 14
        sx = (config.SCREEN_WIDTH - len(_WEAPON_KEYS_ORDERED) * card_w - (len(_WEAPON_KEYS_ORDERED) - 1) * gap) // 2
        for i, key in enumerate(_WEAPON_KEYS_ORDERED):
            if self._hit(mx, my, sx + i * (card_w + gap), 160, card_w, card_h):
                self._buy_or_equip_weapon(key)
                return
        for i, key in enumerate(_CHAR_KEYS_ORDERED):
            if self._hit(mx, my, sx + i * (card_w + gap), 342, card_w, card_h):
                self._buy_or_equip_character(key)
                return

    # ═══ Draw ═════════════════════════════════════════════════════════════════
    def draw(self):
        config.SCR.blit(self.bg, (0, 0))
        if self.bg_transition_prev:
            now = pygame.time.get_ticks()
            if now < self.bg_transition_until:
                alpha = int(255 * (self.bg_transition_until - now) / INFINITE_BG_FADE_MS)
                prev = self.bg_transition_prev.copy()
                prev.set_alpha(alpha)
                config.SCR.blit(prev, (0, 0))
            else:
                self.bg_transition_prev = None
        s = self.state
        if s == GameState.DIFFICULTY_SELECT: self._draw_difficulty_select()
        elif s == GameState.CUSTOM_DIFFICULTY: self._draw_custom_difficulty()
        elif s == GameState.MODE_SELECT: self._draw_mode_select()
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

    def _draw_difficulty_select(self):
        self._draw_title_image(16, 460)
        self._draw_text_fit('选择难度', self.font_med, (210, 236, 255), pygame.Rect(config.SCREEN_WIDTH//2-120, 278, 240, 36), align='center')
        keys = list(DIFFICULTY_PRESETS.keys()); names = ['简单', '中等', '困难', '无限']
        card_colors = [(15, 60, 15), (15, 50, 80), (50, 15, 15), (42, 44, 72)]
        accent_colors = [(80, 220, 80), (240, 200, 50), (220, 80, 80), (130, 210, 255)]
        descs = ['轻松防守，适合熟悉节奏', '金币压力适中，标准挑战', '高成本，高血量，敌人更快', '全角色全武器，无CD生存挑战']
        card_w, sy = 200, 322; total = 4*card_w + 3*22; sx = (config.SCREEN_WIDTH-total)//2
        for i, key in enumerate(keys + ['custom']):
            cx = sx + i*(card_w+22)
            self._draw_menu_card(cx, sy, card_w, 260, accent_colors[i], card_colors[i])
            self._draw_text_fit(names[i], self.font_med, WHITE, pygame.Rect(cx+22, sy+40, card_w-44, 38), align='center')
            self._draw_text_fit(descs[i], self.font_tiny, (200, 215, 230), pygame.Rect(cx+20, sy+84, card_w-40, 44), align='center')
            self._draw_role_badge(cx+card_w//2, sy+150, accent_colors[i], i)
            self._draw_text_fit(f'按 {i+1} 选择', self.font_small, WHITE, pygame.Rect(cx+24, sy+166, card_w-48, 26), align='center')
            if key == 'custom':
                sts = ['技能半CD  自动全解锁', '怪物密度逐步增加']
            else:
                diff = DIFFICULTY_PRESETS[key]
                sts = [f'敌速 {diff.enemy_speed_mult:.2f}x  价格 {diff.weapon_cost_mult:.2f}x']
                all_free = diff.bullet_cost_rifle == 0 and diff.bullet_cost_shotgun == 0 and diff.bullet_cost_sniper == 0
                sts.append('子弹免费' if all_free else f'子弹 {diff.bullet_cost_rifle}/{diff.bullet_cost_shotgun}/{diff.bullet_cost_sniper} 金')
            for j, stxt in enumerate(sts):
                self._draw_text_fit(stxt, self.font_tiny, (200, 215, 230), pygame.Rect(cx+16, sy+208+j*20, card_w-32, 18), align='center')
        self._draw_button('自定义难度', config.SCREEN_WIDTH//2 - 190, config.SCREEN_HEIGHT - 92, 170, 42, (40, 120, 60))
        self._draw_button('按键设置', config.SCREEN_WIDTH//2 + 20, config.SCREEN_HEIGHT - 92, 170, 42, (80, 105, 170))
        # 底部署名
        self._draw_text_fit('本游戏由粽子和粽子爸爸联合设计开发！', self.font_small, (170, 210, 240),
                            pygame.Rect(0, config.SCREEN_HEIGHT - 46, config.SCREEN_WIDTH, 26), align='center')

    def _draw_custom_difficulty(self):
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((3, 12, 28, 185))
        config.SCR.blit(ov, (0, 0))
        px, py, pw, ph = config.SCREEN_WIDTH//2 - 388, 40, 776, 650
        row_x = config.SCREEN_WIDTH//2 - 360
        self._draw_panel(px, py, pw, ph, accent=(110, 210, 255), fill=(10, 26, 50), r=18, alpha=226)
        self._draw_title_text('自定义难度', pygame.Rect(px+40, py+22, pw-80, 48), accent=(110, 210, 255))
        self._draw_text_fit('点击 - / + 调整参数，回车或开始按钮进入游戏', self.font_small, (190, 225, 245), pygame.Rect(px+80, py+70, pw-160, 26), align='center')
        row_y, row_step = 148, 31
        for i, (key, label, min_v, max_v, step) in enumerate(self.custom_fields):
            y = row_y + i * row_step
            self._draw_panel(row_x, y, 720, 30, accent=(70, 155, 210), fill=(6, 18, 34), r=8, alpha=150)
            self._draw_text_fit(label, self.font_small, (225, 240, 255), pygame.Rect(row_x+18, y+2, 210, 26))
            value = self.custom_values[key]
            vtxt = f'{value:.2f}' if isinstance(value, float) else str(value)
            self._draw_text_fit(vtxt, self.font_small, GOLD_COLOR, pygame.Rect(row_x+244, y+2, 120, 26), align='right')
            ratio = (float(value) - float(min_v)) / max(0.001, float(max_v) - float(min_v))
            _rect(config.SCR, (26, 50, 80, 220), (row_x+380, y+11, 150, 8), border_radius=4)
            _rect(config.SCR, (100, 210, 255, 220), (row_x+380, y+11, int(150 * ratio), 8), border_radius=4)
            self._draw_step_button('-', row_x+560, y)
            self._draw_step_button('+', row_x+602, y)
        self._draw_button('重置中等', config.SCREEN_WIDTH//2 - 190, 626, 170, 50, (40, 120, 60))
        self._draw_button('开始游戏', config.SCREEN_WIDTH//2 + 20, 626, 170, 50)

    def _draw_step_button(self, text, x, y, size=(34, 30)):
        w, h = size
        _rect(config.SCR, (0, 0, 0, 85), (x+2, y+3, w, h), border_radius=8)
        _rect(config.SCR, (35, 95, 150, 235), (x, y, w, h), border_radius=7)
        _rect(config.SCR, (145, 225, 255, 150), (x, y, w, h), border_radius=7, width=1)
        _rect(config.SCR, (255, 255, 255, 38), (x+4, y+4, max(1, w-8), 9), border_radius=4)
        self._draw_text_fit(text, self.font_med, WHITE, pygame.Rect(x, y-1, w, h), align='center')

    def _draw_role_badge(self, x, y, color, idx):
        _circle(config.SCR, (0, 0, 0, 80), (x, y), 24)
        _circle(config.SCR, color, (x, y), 21)
        _circle(config.SCR, (255, 255, 255, 90), (x-6, y-7), 6)
        if idx == 3:
            _rect(config.SCR, (20, 45, 70, 220), (x-10, y-8, 20, 16), border_radius=4)
            _line(config.SCR, (130, 255, 160), (x-12, y), (x+12, y), 2)

    def _draw_mode_select(self):
        self._draw_title_text('选择游戏模式', pygame.Rect(config.SCREEN_WIDTH//2-220, 100, 440, 58), accent=(120, 225, 255))
        if self.selecting_infinite_mode:
            self._draw_text_fit('当前模式: 无限', self.font_small, GOLD_COLOR, pygame.Rect(config.SCREEN_WIDTH//2-140, 170, 280, 26), align='center')
        elif self.difficulty:
            self._draw_text_fit(f'当前难度: {self.difficulty.name}', self.font_small, GOLD_COLOR, pygame.Rect(config.SCREEN_WIDTH//2-140, 170, 280, 26), align='center')
        card_y = 285
        self._draw_button('1  单人游戏', config.SCREEN_WIDTH//2-220, card_y, 180, 58)
        self._draw_button('2  双人游戏', config.SCREEN_WIDTH//2+40, card_y, 180, 58, (40, 120, 60))
        p1 = self.player.surface
        p2 = self.player2.surface
        if p1:
            config.SCR.blit(p1, p1.get_rect(center=(config.SCREEN_WIDTH//2-130, 455)))
        if p2:
            config.SCR.blit(p2, p2.get_rect(center=(config.SCREEN_WIDTH//2+130, 455)))
        p1 = f'P1: {self._control_name("p1_shoot")}射击 / {self._control_name("p1_skill1")},{self._control_name("p1_skill2")}技能 / {self._control_name("p1_weapon_prev")},{self._control_name("p1_weapon_next")}换武器'
        p2 = f'P2: {self._control_name("p2_shoot")}射击 / {self._control_name("p2_skill1")},{self._control_name("p2_skill2")}技能 / {self._control_name("p2_laser")}激光 / {self._control_name("p2_dart")}飞镖'
        self._draw_text_fit(p1, self.font_tiny, (220, 235, 250), pygame.Rect(config.SCREEN_WIDTH//2-300, 540, 600, 20), align='center')
        self._draw_text_fit(p2, self.font_tiny, (220, 235, 250), pygame.Rect(config.SCREEN_WIDTH//2-330, 566, 660, 20), align='center')

    def _draw_menu(self):
        # 顶部标题区柔和渐变背景
        title_bg = pygame.Surface((config.SCREEN_WIDTH, 150), pygame.SRCALPHA)
        for y_off in range(150):
            a = int(90 + 70 * (1 - y_off / 150))
            _rect(title_bg, (10, 30, 60, max(0, a)), (0, y_off, config.SCREEN_WIDTH, 1))
        config.SCR.blit(title_bg, (0, 0))

        # 呼吸标题（2s 周期放大到 130%，下方内容预留了呼吸空间）
        self._draw_title_image(16, 500)
        # 副标题 + 两侧装饰线
        tag_w = 90
        tag_y = 316
        _line(config.SCR, (60, 160, 220, 120), (config.SCREEN_WIDTH//2 - 260, tag_y),
              (config.SCREEN_WIDTH//2 - 260 + tag_w, tag_y), 2)
        _line(config.SCR, (60, 160, 220, 120), (config.SCREEN_WIDTH//2 + 260 - tag_w, tag_y),
              (config.SCREEN_WIDTH//2 + 260, tag_y), 2)
        self._draw_text_fit('消灭入侵的海洋生物！', self.font_med, (200, 230, 255),
                            pygame.Rect(0, 302, config.SCREEN_WIDTH, 30), align='center')
        if self.difficulty:
            dt = self.font_small.render(f'当前难度: {self.difficulty.name}', True, GOLD_COLOR)
            config.SCR.blit(dt, dt.get_rect(center=(config.SCREEN_WIDTH//2, 342)))
        # 武器预览卡片
        yw, cw, sp = 372, 150, 14
        tw = len(WEAPON_DEFS)*cw+(len(WEAPON_DEFS)-1)*sp
        sx = (config.SCREEN_WIDTH-tw)//2
        for i, (key, wdef) in enumerate(WEAPON_DEFS.items()):
            cx = sx + i*(cw+sp)
            hovered = self._hit(*self.cursor_pos, cx, yw, cw, 78)
            accent = (140, 215, 255) if hovered else (85, 185, 245)
            self._draw_panel(cx, yw, cw, 78, accent=accent, fill=(12, 36, 68), r=12, alpha=205)
            icon = self.weapon_icons[key]
            config.SCR.blit(icon, icon.get_rect(center=(cx+cw//2, yw+24)))
            self._draw_text_fit(wdef.name, self.font_small, WHITE,
                                pygame.Rect(cx+12, yw+38, cw-24, 20), align='center')
            cost = self._weapon_cost(key)
            self._draw_text_fit('免费' if cost==0 else f'{cost}金币', self.font_tiny, GOLD_COLOR,
                                pygame.Rect(cx+12, yw+57, cw-24, 18), align='center')
        # 底部按钮区域（柔和聚焦渐变）
        btn_h = config.SCREEN_HEIGHT - 470
        btn_bg = pygame.Surface((config.SCREEN_WIDTH, btn_h), pygame.SRCALPHA)
        for y_off in range(btn_h):
            t = y_off / max(1, btn_h - 1)
            a = int(66 * (1 - t) + 20 * t)
            _rect(btn_bg, (5, 20, 50, max(0, a)), (0, y_off, config.SCREEN_WIDTH, 1))
        config.SCR.blit(btn_bg, (0, 470))
        self._draw_button('开 始 游 戏', config.SCREEN_WIDTH//2 - 110, 490, 220, 54)
        self._draw_button('商    店', config.SCREEN_WIDTH//2 - 110, 560, 220, 48, (40, 120, 60))
        self._draw_button('按 键 设 置', config.SCREEN_WIDTH//2 - 110, 624, 220, 48, (80, 105, 170))

    def _draw_key_settings(self):
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((3, 12, 28, 190))
        config.SCR.blit(ov, (0, 0))
        px, py, pw, ph = config.SCREEN_WIDTH//2 - 410, 38, 820, 672
        self._draw_panel(px, py, pw, ph, accent=(130, 210, 255), fill=(10, 26, 50), r=16, alpha=230)
        self._draw_title_text('按键设置', pygame.Rect(px+40, py+20, pw-80, 48), accent=(130, 210, 255))
        hint = '点击一项后按新的键；Esc取消当前录入或返回菜单；横排数字和小键盘数字会分开显示'
        self._draw_text_fit(hint, self.font_tiny, (190, 225, 245), pygame.Rect(px+50, py+68, pw-100, 22), align='center')
        row_w, row_h, row_gap = 246, 28, 6
        sx, sy = config.SCREEN_WIDTH // 2 - 258, 138
        for i, (action, label, _) in enumerate(CONTROL_DEFS):
            col = i // 15
            row = i % 15
            x = sx + col * 270
            y = sy + row * (row_h + row_gap)
            active = action == self.setting_key_action
            fill = (60, 88, 42) if active else (9, 24, 44)
            accent = (255, 230, 120) if active else (70, 155, 210)
            self._draw_panel(x, y, row_w, row_h, accent=accent, fill=fill, r=7, alpha=185)
            self._draw_text_fit(label, self.font_tiny, (225, 240, 255), pygame.Rect(x+12, y+5, 112, 20))
            key_text = '按新键...' if active else self._control_name(action)
            color = GOLD_COLOR if active else (150, 225, 255)
            self._draw_text_fit(key_text, self.font_tiny, color, pygame.Rect(x+130, y+5, 104, 20), align='right')
        self._draw_button('恢复默认', config.SCREEN_WIDTH//2 - 190, 656, 170, 44, (40, 120, 60))
        self._draw_button('返   回', config.SCREEN_WIDTH//2 + 20, 656, 170, 44)

    def _draw_game(self):
        for e in self.enemies: e.draw(config.SCR)
        for c in self.coins: c.draw(config.SCR)
        for box in self.gift_boxes: box.draw(config.SCR)
        for b in self.bullets: b.draw(config.SCR)
        for ep in self.enemy_projectiles: ep.draw(config.SCR)
        for p in self.particles: p.draw(config.SCR)
        for ex in self.explosions: ex.draw(config.SCR)
        for fw in self.fire_walls: fw.draw(config.SCR)
        for ice in self.ice_floors: ice.draw(config.SCR)
        for sp in self.skill_projectiles: sp.draw(config.SCR)
        for ms in self.magnetic_storms: ms.draw(config.SCR)
        for laser in self.radiation_lasers: laser.draw(config.SCR)
        for shield in self.dart_shields: shield.draw(config.SCR)
        self._draw_laser_impacts()
        for lt in self.lightnings:
            if not lt.is_expired(): lt.draw(config.SCR)
        for bp in self.boss_projectiles: bp.draw(config.SCR)
        if self.boss: self.boss.draw(config.SCR)
        self._draw_water_heal_effects()
        self._draw_muzzle_flashes()
        for i, player in enumerate(self.players, 1):
            player.draw(config.SCR)
            self._draw_invincible_shield(player)
            self._draw_niu_freeze(player)
            self._draw_player_label(player, f'P{i}')
            self._draw_water_boost_status(player)
        ZongBoss.draw_snow(config.SCR, max(player.snow_slow_until for player in self.players), self.font_small)
        self._draw_hud()
        self._draw_level_title()
        self._draw_gift_lightning_icon()
        self._draw_rage_banner()

    def _draw_rage_banner(self):
        """终极狂暴提示：屏幕中间红金大字，持续约 3s。"""
        now = pygame.time.get_ticks()
        if now >= self.rage_banner_until:
            return
        rem = self.rage_banner_until - now
        alpha = min(235, int(rem / 3000 * 235))
        pulse = 1 + 0.06 * math.sin(now * 0.012)
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
        """闪电礼包激活期间（3 次闪电打完为止），在屏幕正中心显示脉动闪电图标。"""
        now = pygame.time.get_ticks()
        if now >= self.gift_lightning_icon_until:
            return
        cx, cy = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2
        s = 1 + 0.10 * math.sin(now * 0.009)
        # 光晕
        _circle(config.SCR, (255, 220, 90, 40), (cx, cy), int(46 * s), 3)
        _circle(config.SCR, (255, 235, 160, 30), (cx, cy), int(56 * s), 1)
        # 底板（半透明深色圆盘）
        _circle(config.SCR, (20, 30, 55, 130), (cx, cy), int(34 * s))
        _circle(config.SCR, (255, 210, 80, 110), (cx, cy), int(34 * s), 2)
        # 金色闪电
        pts = [
            (cx + 7 * s, cy - 20 * s), (cx - 5 * s, cy + 1 * s), (cx - 1 * s, cy + 1 * s),
            (cx - 7 * s, cy + 13 * s), (cx + 6 * s, cy - 7 * s), (cx + 2 * s, cy - 7 * s),
        ]
        _polygon(config.SCR, (255, 215, 60), pts)
        _polygon(config.SCR, (255, 248, 180), pts, 1)
        # 环绕星点
        for i in range(6):
            a = now * 0.008 + i * math.tau / 6
            px = cx + math.cos(a) * 42 * s
            py = cy + math.sin(a) * 42 * s
            _circle(config.SCR, (255, 240, 160, 150), (int(px), int(py)), 2)

    def _draw_gift_messages(self):
        now = pygame.time.get_ticks()
        for msg in self.gift_messages[:]:
            text, color, end, start = msg
            if now >= end:
                self.gift_messages.remove(msg)
                continue
            life = max(1, end - start)
            t = (now - start) / life
            alpha = max(0, min(230, int(230 * (1.0 - max(0, t - 0.55) / 0.45))))
            y = 118 - int(18 * t)
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
        now = pygame.time.get_ticks()
        if not self._player_is_invincible(now):
            return
        rem = self.player_invincible_until - now
        pulse = 1 + 0.12 * math.sin(now * 0.02)
        alpha = min(170, 70 + rem // 18)
        _circle(config.SCR, (190, 235, 255, alpha), (int(player.x), int(player.y)), int(48 * pulse), 3)
        _circle(config.SCR, (255, 255, 255, alpha // 2), (int(player.x), int(player.y)), int(36 * pulse), 2)

    def _draw_niu_freeze(self, player):
        now = pygame.time.get_ticks()
        if now >= player.niu_freeze_until:
            return
        cx, cy = int(player.x), int(player.y)
        _circle(config.SCR, (105, 215, 255, 210), (cx, cy), 39, 3)
        for angle in (0, 60, 120):
            rad = math.radians(angle)
            dx, dy = math.cos(rad) * 29, math.sin(rad) * 29
            _line(config.SCR, (205, 250, 255), (cx - dx, cy - dy), (cx + dx, cy + dy), 3)

    def _draw_level_title(self):
        now = pygame.time.get_ticks()
        if now >= self.level_title_until:
            return
        lcfg = LEVEL_CONFIGS[self.current_level-1]
        rem = self.level_title_until - now
        alpha = min(230, int(rem / 2200 * 230))
        ov = pygame.Surface((config.SCREEN_WIDTH, 120), pygame.SRCALPHA)
        _rect(ov, (4, 14, 30, alpha), (0, 0, config.SCREEN_WIDTH, 120))
        config.SCR.blit(ov, (0, 96))
        self._draw_text_fit(f'第{self.current_level}关', self.font_med, GOLD_COLOR, pygame.Rect(0, 116, config.SCREEN_WIDTH, 34), align='center')
        self._draw_title_text(lcfg['title'], pygame.Rect(0, 150, config.SCREEN_WIDTH, 58), accent=(120, 225, 255))

    def _draw_laser_impacts(self):
        """激光命中 Boss 的灼烧冲击动画：扩散双环 + 放射火花 + 灼烧亮点。"""
        now = pygame.time.get_ticks()
        for impact in self.laser_impacts[:]:
            ix, iy, t0 = impact
            age = now - t0
            if age > 300:
                self.laser_impacts.remove(impact)
                continue
            p = age / 300
            fade = 1.0 - p
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
        now = pygame.time.get_ticks()
        for x, y, start in self.water_heal_effects[:]:
            age = now - start
            if age >= 700:
                self.water_heal_effects.remove((x, y, start))
                continue
            t = age / 700
            alpha = int(180 * (1 - t))
            radius = int(14 + 42 * t)
            _circle(config.SCR, (80, 230, 255, alpha), (x, y), radius, 3)
            _circle(config.SCR, (210, 255, 255, alpha), (x, y), max(4, int(10 * (1 - t))))
            for a in range(0, 360, 72):
                rad = math.radians(a + age * 0.25)
                _circle(config.SCR, (130, 245, 255, alpha), (x + math.cos(rad) * radius, y + math.sin(rad) * radius * 0.65), 3)

    def _draw_muzzle_flashes(self):
        now = pygame.time.get_ticks()
        for player, start in self.muzzle_flashes[:]:
            age = max(0, now - start)
            if age >= 90:
                self.muzzle_flashes.remove((player, start))
                continue
            t = age / 90
            alpha = int(245 * (1 - t))
            x, y = player.x, player.y - 34
            flame_h = int(30 * (1 - t)) + 8
            flame_w = int(20 * (1 - t)) + 8
            _polygon(config.SCR, (255, 35, 24, alpha),
                     [(x, y - flame_h), (x - flame_w, y + 4), (x, y + flame_h // 3), (x + flame_w, y + 4)])
            _polygon(config.SCR, (255, 190, 60, alpha),
                     [(x, y - flame_h + 7), (x - flame_w // 2, y + 2), (x, y + 4), (x + flame_w // 2, y + 2)])
            _circle(config.SCR, (255, 45, 20, alpha // 2), (x, y), flame_w)

    def _draw_player_label(self, player, label):
        weapon = WEAPON_DEFS[player.current_weapon].name if player.current_weapon else '未装备'
        char = CHARACTER_DEFS[player.character].name if player.character else '默认'
        text = f'{label} {char}/{weapon}'
        cx = int(player.x)
        tx = max(8, min(config.SCREEN_WIDTH - 112, cx - 56))
        ty = min(config.GAME_AREA_BOTTOM - 22, int(player.y + 38))
        _rect(config.SCR, (5, 18, 34, 145), (tx, ty, 112, 16), border_radius=5)
        color = (255, 230, 160) if label == 'P1' else (170, 230, 255)
        self._draw_text_fit(text, self.font_tiny, color, pygame.Rect(tx + 5, ty + 1, 102, 13), align='center')

    def _draw_water_status_badge(self, cx, ty, label, bg, border, text_color):
        tw, th = 86, 22
        tx = max(8, min(config.SCREEN_WIDTH - tw - 8, cx - tw // 2))
        ty = max(56, ty)
        _rect(config.SCR, (*bg, 210), (tx, ty, tw, th), border_radius=6)
        _rect(config.SCR, (*border, 160), (tx, ty, tw, th), border_radius=6, width=1)
        self._draw_text_fit(label, self.font_tiny, text_color, pygame.Rect(tx + 6, ty + 2, tw - 12, th - 4), align='center')

    def _draw_water_boost_status(self, player):
        now = pygame.time.get_ticks()
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

    def _draw_hud(self):
        # 玻璃面板辅助函数
        def _glass(x, y, w, h, r=8):
            self._draw_panel(x, y, w, h, accent=(70, 175, 230), fill=(5, 18, 36), r=r, alpha=168)
        def _skill_row(x, y, w, key, label, status, color, progress=0.0, muted=False):
            bg = (18, 32, 54, 150) if not muted else (16, 22, 34, 135)
            _rect(config.SCR, bg, (x, y, w, 19), border_radius=5)
            _rect(config.SCR, (*color, 150), (x, y, w, 19), border_radius=5, width=1)
            fill_w = int((w - 4) * max(0.0, min(1.0, progress)))
            if fill_w > 0:
                _rect(config.SCR, (*color, 48), (x + 2, y + 2, fill_w, 15), border_radius=4)
            _rect(config.SCR, (*color, 230), (x + 5, y + 4, 22, 11), border_radius=4)
            self._draw_text_fit(key, self.font_tiny, (8, 16, 24), pygame.Rect(x + 6, y + 2, 20, 15), align='center')
            text_c = (235, 245, 255) if not muted else (145, 155, 165)
            self._draw_text_fit(label, self.font_tiny, text_c, pygame.Rect(x + 32, y + 2, 76, 15))
            self._draw_text_fit(status, self.font_tiny, color if not muted else (150, 150, 150), pygame.Rect(x + 108, y + 2, w - 114, 15), align='right')
        now = pygame.time.get_ticks()
        # 金币面板
        _glass(6, 6, 100, 32)
        config.SCR.blit(self.coin_surface, (12, 10))
        self._draw_text_fit(f' {self.player.gold}', self.font_med, GOLD_COLOR, pygame.Rect(40, 6, 58, 28))
        # 章节面板（每打完一个 boss +1）
        _glass(110, 6, 100, 32)
        self._draw_text_fit(f'第 {self.chapter} 章', self.font_med, (255, 215, 0),
                            pygame.Rect(114, 6, 92, 28), align='center')
        # 击杀
        _glass(6, 42, 100, 24)
        st = self.font_small.render(f'击杀: {self.kill_count}', True, WHITE)
        config.SCR.blit(st, (14, 42))
        # 复活次数（无限模式）
        _glass(110, 42, 100, 24)
        lives_text = f'复活: {self.revive_count}' if self.infinite_mode else f'生命: {self.lives}'
        rt = self.font_small.render(lives_text, True, (170, 235, 255))
        config.SCR.blit(rt, (118, 42))
        # 关卡进度
        lcfg = LEVEL_CONFIGS[self.current_level-1]
        _glass(6, 70, 140, 24)
        lt = self.font_small.render(f'无限 积分:{self.score}' if self.infinite_mode else f'第{self.current_level}关 {self.level_kills}/{lcfg["kills_needed"]}', True, WHITE)
        config.SCR.blit(lt, (12, 70))
        if self.infinite_mode:
            elapsed = max(0, (pygame.time.get_ticks() - self.infinite_start_time) // 1000)
            _glass(6, 98, 140, 24)
            tt = self.font_small.render(f'时长: {elapsed // 60:02d}:{elapsed % 60:02d}', True, (200, 230, 255))
            config.SCR.blit(tt, (14, 98))
        # 武器面板
        wdef = WEAPON_DEFS[self.player.current_weapon]
        right_x, right_w = config.SCREEN_WIDTH - 226, 220
        _glass(right_x, 6, right_w, 30)
        self._draw_text_fit(wdef.name, self.font_small, (200, 230, 255), pygame.Rect(right_x + 8, 7, 92, 18))
        cost = self._bullet_cost(self.player.current_weapon)
        ammo = self._weapon_status_text(self.player.current_weapon, True)
        cost_text = ammo or (f'-{cost}金/发' if cost>0 else '免费')
        cost_color = GOLD_COLOR if cost>0 or ammo else (100, 200, 100)
        self._draw_text_fit(cost_text, self.font_tiny, cost_color, pygame.Rect(right_x + 108, 7, 86, 18), align='right')
        # 角色技能面板
        if self.player.character:
            cdef = CHARACTER_DEFS[self.player.character]
            skill_panel_h = 118 if self.player.character == 'radiation' else 64
            _glass(right_x, 40, right_w, skill_panel_h)
            self._draw_text_fit(cdef.name, self.font_tiny, cdef.color, pygame.Rect(right_x + 10, 43, right_w - 20, 16))
            for i, sk in enumerate(cdef.skills):
                active_end = self.player.skill_active_until.get(sk.skill_type, 0)
                active_rem = max(0, active_end - now)
                cd_end = self.player.skill_cooldowns.get(sk.skill_type, 0)
                rem = max(0, cd_end - now)
                cd_ms = max(1, getattr(sk, 'cooldown_ms', 1))
                status = f'生效中 {active_rem/1000:.1f}s' if active_rem > 0 else f'冷却 {rem/1000:.1f}s' if rem > 0 else '就绪'
                progress = 1.0 if active_rem > 0 else 1 - rem / cd_ms if rem > 0 else 1.0
                key_name = self._control_name('p1_skill1' if sk.key_name == 'K' else 'p1_skill2')
                _skill_row(right_x + 8, 60+i*21, right_w - 16, key_name, sk.name, status, cdef.color, progress, rem > 0)
            if self.player.character == 'radiation':
                cd_end = self.player.skill_cooldowns.get('radiation_laser', 0)
                rem = max(0, cd_end - now)
                laser_active = any(laser.owner is self.player and not laser.is_expired(now) for laser in self.radiation_lasers)
                laser_status = '照射中' if laser_active else f'冷却 {rem/1000:.1f}s' if rem > 0 else '甩激光'
                laser_progress = 1.0 if laser_active else 1 - rem / 12000 if rem > 0 else 1.0
                _skill_row(right_x + 8, 102, right_w - 16, self._control_name('p1_laser'), '辐射激光', laser_status, (150, 245, 120), laser_progress, rem > 0)
                active_end = self.player.skill_active_until.get('dart_shield', 0)
                active_rem = max(0, active_end - now)
                cd_end = self.player.skill_cooldowns.get('dart_shield', 0)
                rem = max(0, cd_end - now)
                flying = any(s.owner is self.player and s.released and not s.is_gone(now)
                             for s in self.dart_shields)
                dart_status = f'护盾中 {active_rem/1000:.1f}s' if active_rem > 0 else '飞出中' if flying else f'冷却 {rem/1000:.1f}s' if rem > 0 else '就绪'
                dart_progress = 1.0 if active_rem > 0 else 0.45 if flying else 1 - rem / 20000 if rem > 0 else 1.0
                dart_color = (235, 85, 110) if not flying else (255, 205, 95)
                _skill_row(right_x + 8, 123, right_w - 16, self._control_name('p1_dart'), '旋刃飞盘', dart_status, dart_color, dart_progress, rem > 0)
        else:
            _glass(right_x, 40, right_w, 42)
            self._draw_text_fit('渔民', self.font_tiny, (255, 230, 160), pygame.Rect(right_x + 8, 42, right_w - 16, 16))
            active_end = self.player.skill_active_until.get('fisher_grenade', 0)
            active_rem = max(0, active_end - pygame.time.get_ticks())
            cd_end = self.player.skill_cooldowns.get('fisher_grenade', 0)
            rem = max(0, cd_end - pygame.time.get_ticks())
            cd_text = f'生效 {active_rem/1000:.1f}s' if active_rem > 0 else f'{rem/1000:.1f}s' if rem > 0 else '手雷'
            cd_c = (150, 150, 150) if active_rem > 0 or rem > 0 else WHITE
            self._draw_text_fit(f'{self._control_name("p1_skill1")}: {cd_text}', self.font_tiny, cd_c, pygame.Rect(right_x + 8, 59, right_w - 16, 15))
        char_list_y = 166 if self.player.character == 'radiation' else 110
        _glass(right_x, char_list_y, right_w, 54)
        for i, key in enumerate(_CHAR_KEYS_ORDERED):
            cdef = CHARACTER_DEFS[key]
            col = i % 2
            row = i // 2
            cell_w = (right_w - 16) // 2
            x = right_x + 6 + col * (cell_w + 4)
            y = char_list_y + 6 + row * 22
            active1 = key == self.player.character
            active2 = self.two_player and key == self.player2.character
            if key in self.player.owned_characters:
                _rect(config.SCR, (25, 50, 80, 120), (x, y, cell_w, 19), border_radius=4)
            color = (255, 80, 80) if active1 else (255, 220, 60) if active2 else (210, 230, 255) if key in self.player.owned_characters else (100, 115, 130)
            char_key = self._control_name(('p1_char_ice', 'p1_char_water', 'p1_char_fire', 'p1_char_radiation')[i])
            self._draw_text_fit(f'{char_key}-{cdef.name}', self.font_tiny, color, pygame.Rect(x + 4, y + 2, cell_w - 8, 15), align='center')
        gift_y = char_list_y + 62
        buff_end = max(self.gift_fire_until, self.gift_ice_until)
        if now < buff_end:
            gift_kind = '火弹礼包' if self.gift_fire_until >= self.gift_ice_until else '冰弹礼包'
            gift_color = (255, 105, 35) if gift_kind == '火弹礼包' else (45, 115, 230)
            _glass(right_x, gift_y, right_w, 30)
            self._draw_text_fit(f'{gift_kind} 剩余 {((buff_end - now) / 1000):.1f}s', self.font_tiny, gift_color,
                                pygame.Rect(right_x + 8, gift_y + 6, right_w - 16, 18), align='center')
        elif self.gift_messages:
            text, color, end, _start = self.gift_messages[-1]
            if now < end:
                _glass(right_x, gift_y, right_w, 30)
                self._draw_text_fit(text, self.font_tiny, color, pygame.Rect(right_x + 8, gift_y + 6, right_w - 16, 18), align='center')
        speed_end = max((getattr(p, 'gift_speed_until', 0) for p in self.players), default=0)
        if now < speed_end:
            _glass(right_x, gift_y + 32, right_w, 26)
            self._draw_text_fit(f'极速礼包 剩余 {((speed_end - now) / 1000):.1f}s', self.font_tiny, (255, 215, 90),
                                pygame.Rect(right_x + 8, gift_y + 34, right_w - 16, 18), align='center')
        # 终极狂暴倒计时（红金主题，狂暴期间常驻右侧）
        rage_end = max((getattr(p, 'rage_until', 0) for p in self.players), default=0)
        if now < rage_end:
            rage_y = gift_y + 64
            rage_rem = max(0, rage_end - now)
            rage_bg = pygame.Surface((right_w, 26), pygame.SRCALPHA)
            _rect(rage_bg, (70, 12, 14, 205), (0, 0, right_w, 26), border_radius=6)
            _rect(rage_bg, (255, 110, 55, 215), (0, 0, right_w, 26), border_radius=6, width=1)
            _rect(rage_bg, (255, 230, 140, 160), (4, 4, right_w - 8, 4), border_radius=2)
            config.SCR.blit(rage_bg, (right_x, rage_y))
            sec = rage_rem / 1000
            self._draw_text_fit(f'终极狂暴 剩余 {sec:.1f}s', self.font_tiny, (255, 235, 150),
                                pygame.Rect(right_x + 8, rage_y + 4, right_w - 16, 18), align='center')
        # 底部武器栏
        by, bw, bh = config.SCREEN_HEIGHT-44, 360, 40; bx = config.SCREEN_WIDTH//2 - bw//2
        _glass(bx-4, by-4, bw+8, bh+8)
        for i, (key, _) in enumerate(WEAPON_DEFS.items()):
            slot_w = bw // len(WEAPON_DEFS)
            sw = slot_w - 2; ix = bx + i*slot_w + 1
            owned = key in self.player.owned_weapons; active = key == self.player.current_weapon
            active2 = self.two_player and key == self.player2.current_weapon
            disabled = self.infinite_mode and key == 'pistol'
            if disabled:  # 无限模式手枪置灰
                _rect(config.SCR, (22, 22, 30, 150), (ix, by, sw, bh), border_radius=6)
                dim = self.weapon_icons[key].copy()
                dim.set_alpha(70)
                config.SCR.blit(dim, (ix+sw//2-28, by+6))
                continue
            if active: _rect(config.SCR, (40, 120, 220, 200), (ix, by, sw, bh), border_radius=6)
            elif active2: _rect(config.SCR, (85, 105, 45, 200), (ix, by, sw, bh), border_radius=6)
            elif owned: _rect(config.SCR, (30, 50, 80, 160), (ix, by, sw, bh), border_radius=6)
            config.SCR.blit(self.weapon_icons[key], (ix+sw//2-28, by+6))
            kc = (200, 230, 255) if owned else (80, 80, 80)
            mark = 'P1' if active else 'P2' if active2 else ''
            config.SCR.blit(self.font_tiny.render(mark, True, kc), (ix+3, by+2))
        hbw = 200
        hx = config.SCREEN_WIDTH//2 - hbw//2
        gs = pygame.Surface((hbw + 8, 20), pygame.SRCALPHA)
        _rect(gs, (15, 30, 60, 180), (0, 0, hbw + 8, 20), border_radius=6)
        _rect(gs, (40, 80, 140, 60), (1, 1, hbw + 6, 18), border_radius=5, width=1)
        config.SCR.blit(gs, (hx - 4, config.SCREEN_HEIGHT - 56))
        _rect(config.SCR, (40, 15, 15), (hx, config.SCREEN_HEIGHT - 50, hbw, 8), border_radius=4)
        _rect(config.SCR, HEALTH_RED, (hx, config.SCREEN_HEIGHT - 50, hbw, 8), border_radius=4)
        filled = int(hbw * self.player_hp / self.max_player_hp)
        if filled > 0:
            _rect(config.SCR, PLAYER_HP_GREEN, (hx, config.SCREEN_HEIGHT - 50, filled, 8), border_radius=4)
            _rect(config.SCR, (100, 255, 100), (hx, config.SCREEN_HEIGHT - 49, filled, 3))
        ht = self.font_tiny.render(f'HP: {self.player_hp}/{self.max_player_hp}', True, WHITE)
        config.SCR.blit(ht, ht.get_rect(center=(config.SCREEN_WIDTH//2, config.SCREEN_HEIGHT - 62)))

    def _draw_shop_overlay(self):
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        # 更深更柔和的暗色叠加
        for y in range(config.SCREEN_HEIGHT):
            a = int(215 + 20 * (1 - y / config.SCREEN_HEIGHT))
            pygame.draw.line(ov, (5, 15, 35, a), (0, y), (config.SCREEN_WIDTH, y))
        config.SCR.blit(ov, (0, 0))
        self._draw_title_text('商店', pygame.Rect(config.SCREEN_WIDTH//2-120, 34, 240, 52), accent=(110, 225, 255))
        self._draw_text_fit(f'金币: {self.player.gold}', self.font_med, GOLD_COLOR, pygame.Rect(config.SCREEN_WIDTH//2-120, 92, 240, 30), align='center')
        card_w, card_h, gap = 210, 76, 14
        sx = (config.SCREEN_WIDTH - len(_WEAPON_KEYS_ORDERED) * card_w - (len(_WEAPON_KEYS_ORDERED) - 1) * gap) // 2
        self._draw_text_fit('武 器', self.font_med, WHITE, pygame.Rect(0, 126, config.SCREEN_WIDTH, 30), align='center')
        for i, key in enumerate(_WEAPON_KEYS_ORDERED):
            wdef = WEAPON_DEFS[key]; owned = key in self.player.owned_weapons; active = key == self.player.current_weapon
            occupied = self._equipped_by_other(self.player, 'current_weapon', key)
            cx, yr, cw, ch = sx + i * (card_w + gap), 160, card_w, card_h
            disabled = self.infinite_mode and key == 'pistol'
            if disabled:  # 无限模式手枪置灰
                self._draw_panel(cx, yr, cw, ch, accent=(58, 58, 66), fill=(22, 22, 30), r=10, alpha=226)
                _circle(config.SCR, (90, 90, 100), (cx + 18, yr + 18), 13)
                self._draw_text_fit(str(i + 1), self.font_small, (120, 120, 130), pygame.Rect(cx + 9, yr + 7, 18, 22), align='center')
                dim = self.weapon_icons[key].copy()
                dim.set_alpha(70)
                config.SCR.blit(dim, (cx + 18, yr + 36))
                self._draw_text_fit(wdef.name, self.font_small, (130, 130, 140), pygame.Rect(cx + 80, yr + 8, 76, 24))
                self._draw_text_fit('无限模式禁用', self.font_tiny, (110, 110, 120), pygame.Rect(cx + 80, yr + 34, 118, 18))
                self._draw_text_fit('置灰', self.font_tiny, (110, 110, 120), pygame.Rect(cx + 128, yr + 55, 68, 18), align='right')
                continue
            bg_base = (150, 36, 42) if active else (85, 60, 25) if occupied else (30, 60, 100) if owned else (25, 40, 70)
            self._draw_panel(cx, yr, cw, ch, accent=tuple(min(255, c + 65) for c in bg_base), fill=bg_base, r=10, alpha=226)
            _circle(config.SCR, (255, 230, 160), (cx + 18, yr + 18), 13)
            self._draw_text_fit(str(i + 1), self.font_small, (20, 30, 50), pygame.Rect(cx + 9, yr + 7, 18, 22), align='center')
            config.SCR.blit(self.weapon_icons[key], (cx + 18, yr + 36))
            self._draw_text_fit(wdef.name, self.font_small, WHITE, pygame.Rect(cx + 80, yr + 8, 76, 24))
            self._draw_text_fit(f'{wdef.normal_shots}枪(小) {wdef.large_shots}枪(大)', self.font_tiny, (180, 210, 240), pygame.Rect(cx + 80, yr + 34, 118, 18))
            cost = self._weapon_cost(key)
            ammo_label = self._weapon_status_text(key, owned)
            label = '已装备' if active else 'P2装备中' if occupied else ammo_label if ammo_label else '已购买' if owned else ('免费' if cost == 0 else f'{cost}金币')
            color = (255, 235, 120) if not owned else (255, 190, 90) if occupied else (120, 255, 140) if active else (160, 220, 255)
            self._draw_text_fit(label, self.font_tiny, color, pygame.Rect(cx + 128, yr + 55, 68, 18), align='right')
        self._draw_text_fit('角 色', self.font_med, WHITE, pygame.Rect(0, 306, config.SCREEN_WIDTH, 30), align='center')
        for i, key in enumerate(_CHAR_KEYS_ORDERED):
            cdef = CHARACTER_DEFS[key]; owned = key in self.player.owned_characters; active = key == self.player.character
            occupied = self._equipped_by_other(self.player, 'character', key)
            cx, yr, cw, ch = sx + i * (card_w + gap), 342, card_w, card_h
            bc = (150, 36, 42) if active else (85, 60, 25) if occupied else (80, 50, 40) if key=='fire' else (20, 95, 120) if key=='water' else (40, 60, 120) if key=='ice' else (60, 30, 100)
            self._draw_panel(cx, yr, cw, ch, accent=tuple(min(255, c + 65) for c in bc), fill=bc, r=10, alpha=226)
            _circle(config.SCR, (255, 230, 160), (cx + 18, yr + 18), 13)
            self._draw_text_fit(str(i + 5), self.font_small, (20, 30, 50), pygame.Rect(cx + 9, yr + 7, 18, 22), align='center')
            _circle(config.SCR, (0, 0, 0, 80), (cx + 36, yr + 48), 16)
            _circle(config.SCR, cdef.color, (cx + 36, yr + 48), 14)
            self._draw_text_fit(cdef.name, self.font_small, WHITE, pygame.Rect(cx + 62, yr + 8, 80, 24))
            self._draw_text_fit(' / '.join(sk.name for sk in cdef.skills), self.font_tiny, cdef.color, pygame.Rect(cx + 62, yr + 34, 112, 18))
            cost = self._character_cost(cdef)
            label = '已装备' if active else 'P2装备中' if occupied else '已购买' if owned else f'{cost}金币'
            color = (255, 235, 120) if not owned else (255, 190, 90) if occupied else (120, 255, 140) if active else (160, 220, 255)
            self._draw_text_fit(label, self.font_tiny, color, pygame.Rect(cx + 128, yr + 55, 68, 18), align='right')
        tip = self.font_tiny.render('玩家1: 1-4 买/装备武器    5-8 买/装备角色    B 关闭商店', True, (150, 180, 200))
        config.SCR.blit(tip, tip.get_rect(center=(config.SCREEN_WIDTH//2, config.SCREEN_HEIGHT-20)))

    def _draw_level_transition(self):
        # 暗色叠加
        ov = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        for y_off in range(config.SCREEN_HEIGHT):
            a = int(120 + 40 * (1 - y_off / config.SCREEN_HEIGHT))
            _rect(ov, (0, 5, 20, a), (0, y_off, config.SCREEN_WIDTH, 1))
        config.SCR.blit(ov, (0, 0))
        # 中心面板
        pw, ph = 360, 120
        px, py = config.SCREEN_WIDTH // 2 - pw // 2, config.SCREEN_HEIGHT // 2 - ph // 2
        self._draw_panel(px, py, pw, ph, accent=(90, 230, 120), fill=(14, 48, 36), r=16, alpha=226)
        # 关卡文本
        self._draw_title_text(f'第{self.current_level}关 通过!', pygame.Rect(px+20, py+20, pw-40, 50), color=(120, 255, 130), accent=(90, 230, 120))
        # 奖励
        rw = int(LEVEL_CONFIGS[self.current_level-1]['gold_reward'] * self.difficulty.weapon_cost_mult)
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
        self._draw_panel(px, py, pw, ph, accent=(115, 205, 255), fill=(12, 34, 68), r=18, alpha=232)
        paid = self.state == GameState.PAID_REVIVE
        title = f'花 {REVIVE_COST} 金币复活？' if paid else '暂 停'
        self._draw_title_text(title, pygame.Rect(px+20, py+26, pw-40, 58), accent=(115, 205, 255))
        if paid:
            left, right = self._choice_rects()
            self._draw_button('复活' if paid else '继续游戏', *left)
            self._draw_button('结束游戏' if paid else '退出本局', *right, (180, 60, 60))
        else:
            self._draw_text_fit('按 H 继续游戏', self.font_small, (190, 230, 255), pygame.Rect(px+60, py+94, pw-120, 28), align='center')

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
        self._draw_title_text('游 戏 结 束', pygame.Rect(px+40, py+32, pw-80, 58), color=(255, 92, 92), accent=(235, 75, 75))
        # 死亡原因
        self._draw_text_fit(self.game_over_reason, self.font_med, (255, 160, 160), pygame.Rect(px+30, py+106, pw-60, 30), align='center')
        # 统计
        self._draw_text_fit(f'击杀数: {self.kill_count}', self.font_med, WHITE, pygame.Rect(px+80, py+152, pw-160, 30), align='center')
        self._draw_text_fit(f'金币: {self.player.gold}', self.font_med, GOLD_COLOR, pygame.Rect(px+80, py+192, pw-160, 30), align='center')
        # 重新开始按钮
        self._draw_button('重新开始', config.SCREEN_WIDTH//2 - 80, py + ph - 40, 160, 44, (200, 60, 60))

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
        self._draw_button('Y - 继续', config.SCREEN_WIDTH//2-170, config.SCREEN_HEIGHT//2+70, 150, 46, (45, 150, 70))
        self._draw_button('N - 结束', config.SCREEN_WIDTH//2+20, config.SCREEN_HEIGHT//2+70, 150, 46, (180, 60, 60))

    def _draw_infinite_countdown(self):
        now = pygame.time.get_ticks()
        rem = max(0, self.infinite_countdown_end - now)
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
        self._draw_title_text('胜    利!', pygame.Rect(px+50, py+28, pw-100, 58), color=GOLD_COLOR, accent=(245, 205, 70))
        self._draw_text_fit('所有关卡已通过!', self.font_med, WHITE, pygame.Rect(px+60, py+96, pw-120, 34), align='center')
        # 帝冠装饰
        self._draw_text_fit('★', self.font_large, GOLD_COLOR, pygame.Rect(px+150, py+132, pw-300, 48), align='center')
        # 统计
        self._draw_text_fit(f'总击杀: {self.kill_count}', self.font_med, WHITE, pygame.Rect(px+80, py+188, pw-160, 30), align='center')
        self._draw_text_fit(f'金币: {self.player.gold}', self.font_med, GOLD_COLOR, pygame.Rect(px+80, py+228, pw-160, 30), align='center')
        self._draw_button('再来一局', config.SCREEN_WIDTH//2 - 80, py + ph - 40, 160, 44, (50, 200, 80))

    def _draw_text_fit(self, text, font, color, rect, align='left'):
        if not text:
            return
        s = font.render(str(text), True, color)
        shadow = font.render(str(text), True, (0, 8, 20))
        max_w, max_h = max(1, rect.w), max(1, rect.h)
        if s.get_width() > max_w or s.get_height() > max_h + 2:
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
        config.SCR.blit(shadow, pos.move(2, 2))
        config.SCR.blit(s, pos)

    def _draw_title_text(self, text, rect, color=WHITE, accent=(90, 220, 255), font=None):
        font = font or self.font_large
        for dx, dy, alpha in ((0, 4, 120), (0, -2, 80), (3, 0, 80), (-3, 0, 80)):
            s = font.render(str(text), True, (*accent[:3], alpha))
            config.SCR.blit(s, s.get_rect(center=rect.center).move(dx, dy))
        self._draw_text_fit(text, font, color, rect, align='center')

    def _draw_title_image(self, y, width):
        # 呼吸动画：2s 一个周期，从 100% 平滑放大到 130% 再缩小回 100%
        now = pygame.time.get_ticks()
        t = (now % 2000) / 2000.0
        scale = 1.0 + 0.30 * (1.0 - math.cos(2 * math.pi * t)) / 2.0
        target_w = max(1, int(width * scale))
        if not self.title_image:
            self._draw_breathing_title_text(y, target_w)
            return
        src_w, src_h = self.title_image.get_size()
        src_h = min(src_h, 390)
        source = self.title_image.subsurface(pygame.Rect(0, 0, src_w, src_h))
        h = max(1, int(target_w * src_h / max(1, src_w)))
        # 直接从高清源图平滑缩放，放大后依旧清晰不发糊
        img = pygame.transform.smoothscale(source, (target_w, h))
        config.SCR.blit(img, img.get_rect(midtop=(config.SCREEN_WIDTH // 2, y)))

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

    def _draw_panel(self, x, y, w, h, accent=(90, 210, 255), fill=(10, 26, 48), r=12, alpha=214):
        _rect(config.SCR, (0, 0, 0, 92), (x + 5, y + 7, w, h), border_radius=r + 2)
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        for row in range(h):
            t = row / max(1, h - 1)
            c = (
                min(255, int(fill[0] + 18 * (1 - t))),
                min(255, int(fill[1] + 22 * (1 - t))),
                min(255, int(fill[2] + 30 * (1 - t))),
                alpha,
            )
            pygame.draw.line(panel, c, (0, row), (w, row))
        _rect(panel, (*accent[:3], 115), (0, 0, w, h), border_radius=r, width=2)
        _rect(panel, (255, 255, 255, 36), (3, 3, w - 6, max(8, h // 3)), border_radius=max(1, r - 3), width=1)
        if h >= 18:
            _rect(panel, (*accent[:3], 150), (14, 10, max(1, w - 28), 3), border_radius=2)
        config.SCR.blit(panel, (x, y))

    def _draw_menu_card(self, x, y, w, h, accent, fill):
        self._draw_panel(x, y, w, h, accent=accent, fill=fill, r=14, alpha=226)
        _rect(config.SCR, (*accent[:3], 210), (x + 22, y + 20, w - 44, 4), border_radius=2)
        _rect(config.SCR, (*accent[:3], 48), (x + 10, y + 10, w - 20, h - 20), border_radius=10, width=1)

    def _draw_button(self, text, x, y, w, h, color=(40, 130, 210)):
        btn = pygame.Rect(x, y, w, h)
        hovered = self._hit(*self.cursor_pos, x, y, w, h)
        base = tuple(min(255, c + 26) for c in color) if hovered else color
        _rect(config.SCR, (0, 0, 0, 110), btn.move(4, 5), border_radius=12)
        for sy in range(h):
            t = sy / max(1, h)
            boost = 42 * (1 - t)
            lc = tuple(max(0, min(255, int(base[i] + boost - 12 * t))) for i in range(3))
            pygame.draw.line(config.SCR, lc, (x + 4, y + sy), (x + w - 4, y + sy))
        border = tuple(min(255, c + 76) for c in base)
        _rect(config.SCR, border, btn, border_radius=10, width=3 if hovered else 2)
        _rect(config.SCR, (255, 255, 255, 42), btn.inflate(-8, -8), border_radius=7, width=1)
        if hovered:
            _rect(config.SCR, (255, 255, 255, 60), btn.inflate(-4, -4), border_radius=9, width=1)
        self._draw_text_fit(text, self.font_med, WHITE, btn.inflate(-18, -8), align='center')
