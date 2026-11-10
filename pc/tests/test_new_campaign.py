"""Factory/temple campaign integration shared by the PC and browser entrypoints."""
import os
import random
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
from game_core import config
from game_core.game import Game, GameState
from game_core.abyss_bosses import MechaLizardBoss, AncientWhaleBoss
from game_core.orochi import OrochiBoss


class NewCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def setUp(self):
        self.old_time = config.campaign_time_ms
        config.campaign_time_ms = 1000
        self.addCleanup(setattr, config, 'campaign_time_ms', self.old_time)
        self.geometry = {name: getattr(config, name) for name in
                         ('SCREEN_WIDTH', 'SCREEN_HEIGHT', 'GAME_AREA_LEFT', 'GAME_AREA_RIGHT',
                          'GAME_AREA_BOTTOM', 'MOBILE_LANDSCAPE_VIEW', 'SCR')}
        for name, value in self.geometry.items():
            self.addCleanup(setattr, config, name, value)
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = 960, 720
        config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT, config.GAME_AREA_BOTTOM = 0, 960, 660
        config.MOBILE_LANDSCAPE_VIEW = False
        config.SCR = pygame.Surface((960, 720))

    def game(self, desktop=False, difficulty='medium'):
        game = Game(desktop_controls=desktop)
        game._start_game(difficulty)
        game.mobile_controls.auto_fire = False
        return game

    def test_all_shared_balance_tables_have_eleven_entries(self):
        self.assertEqual(len(config.LEVEL_CONFIGS), 11)
        self.assertEqual(len(config.BOSS_DEFS), 11)
        for name in ('CAMPAIGN_KILLS', 'CAMPAIGN_SPAWN_MS', 'CAMPAIGN_ENEMY_CAP',
                     'CAMPAIGN_BOSS_HP', 'CAMPAIGN_BOSS_ATTACK_MS', 'CAMPAIGN_REINFORCEMENT_MS',
                     'CAMPAIGN_REINFORCEMENT_CAP', 'CAMPAIGN_LARGE_CHANCE', 'CAMPAIGN_SPEED',
                     'CAMPAIGN_REWARDS', 'INFINITE_BOSS_HP', 'INFINITE_BOSS_ATTACK_MS'):
            self.assertEqual(len(getattr(config, name)), 11, name)
        for index, level in enumerate(config.LEVEL_CONFIGS):
            self.assertEqual(level['level'], index + 1)
            self.assertEqual(level['boss_idx'], index)

    def test_eight_factory_temple_orochi_progression_and_final_victory(self):
        game = self.game()
        game._start_level(8)
        for stage, cls in ((8, None), (9, MechaLizardBoss), (10, AncientWhaleBoss), (11, OrochiBoss)):
            self.assertEqual(game.current_level, stage)
            if stage < 11:
                self.assertIsNone(game.boss)
                self.assertTrue(game.level_enemy_defs)
                game._trigger_boss()
            else:
                self.assertEqual(game.state, GameState.BOSS_FIGHT)
                self.assertFalse(game.enemies)
                self.assertFalse(game.level_enemy_defs)
            if cls:
                self.assertIsInstance(game.boss, cls)
            game._kill_boss()
            self.assertFalse(game.boss_projectiles)
            if stage < 11:
                self.assertEqual(game.state, GameState.LEVEL_TRANSITION)
                config.campaign_time_ms = game.level_transition_end
                game.update()
            else:
                self.assertEqual(game.state, GameState.VICTORY)

    def test_new_waves_only_use_their_three_new_species(self):
        game = self.game()
        for level, expected in ((9, config.FACTORY_ENEMY_KEYS), (10, config.TEMPLE_ENEMY_KEYS)):
            game.state = GameState.PLAYING
            game._start_level(level)
            random.seed(410 + level)
            seen = set()
            for _ in range(60):
                game.spawn_enemy()
                enemy = game.enemies.pop()
                seen.add(enemy.edef['key'])
                self.assertEqual(enemy.max_hp, enemy.edef['campaign_hp'])
            self.assertEqual(seen, set(expected))
        for old_level in config.LEVEL_CONFIGS[:8]:
            self.assertFalse(set(old_level['enemy_pool']) & set(config.FACTORY_ENEMY_KEYS + config.TEMPLE_ENEMY_KEYS))

    def test_pc_browser_use_identical_boss_health_interval_and_attack_specs(self):
        fields = ('skill', 'warning_ms', 'active_ms', 'damage', 'speed', 'angle', 'width',
                  'height', 'ring_speed', 'ring_thickness', 'gap_degrees')
        for difficulty in ('easy', 'medium', 'hard'):
            for level in (9, 10):
                specs = []
                for desktop in (False, True):
                    game = self.game(desktop, difficulty)
                    game._start_level(level)
                    game._trigger_boss()
                    boss = game.boss
                    boss.y = 60
                    boss.entered = True
                    attacks = []
                    for i in range(4):
                        shots = boss.attack(1000 + i * 10000, 480, 610)
                        game._add_boss_projectiles(shots)
                        attacks.append([tuple(getattr(p, f) for f in fields) for p in shots])
                    specs.append((boss.hp, boss.attack_interval, attacks))
                self.assertEqual(specs[0], specs[1], (difficulty, level))

    def test_new_shift_shortcuts_and_hud_reach_both_new_stages_and_final(self):
        game = self.game(True)
        for key, level in ((pygame.K_9, 9), (pygame.K_0, 10), (pygame.K_MINUS, 11)):
            game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_SHIFT)])
            self.assertEqual(game.current_level, level)
        left, _, _ = game._hud_controls()
        game._handle_hud_click(left.center)
        self.assertEqual(game.current_level, 10)
        self.assertEqual(game.state, GameState.PLAYING)
        game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SEMICOLON,
                                               mod=pygame.KMOD_SHIFT)])
        self.assertEqual(game.current_level, 10)

    def test_rotation_cancels_new_warning_and_active_geometry_safely(self):
        for infinite in (False, True):
            for level in (9, 10):
                for active in (False, True):
                    config.update_mobile_view((844, 390))
                    game = self.game()
                    game._start_level(level)
                    game._trigger_boss()
                    game.infinite_mode = infinite
                    boss = game.boss
                    boss.entered, boss.y = True, 60
                    for _ in range(4):
                        game._add_boss_projectiles(boss.attack(1000, game.player.x, game.player.y))
                    config.campaign_time_ms = 2800 if active else 1100
                    for shot in game.boss_projectiles:
                        shot.update(game.player.x, game.player.y)
                    previous_area = (config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT, config.GAME_AREA_BOTTOM)
                    config.update_mobile_view((390, 844))
                    hp = game.player_hp
                    game.resize_view(previous_area)
                    self.assertFalse(game.boss_projectiles)
                    self.assertFalse(game.warned_boss_shots)
                    self.assertEqual(game.player_hp, hp)
                    self.assertFalse(boss.should_attack(config.game_ticks()))
                    self.assertTrue(boss.should_attack(config.game_ticks() + boss.attack_interval))
                    config.campaign_time_ms = 1000

    def test_restart_final_is_immediate_boss_without_wave(self):
        game = self.game()
        game._start_level(11)
        game.boss.hp = 1
        game._retry_level()
        self.assertIsInstance(game.boss, OrochiBoss)
        self.assertEqual(game.boss.hp, config.CAMPAIGN_BOSS_HP[10][1])
        self.assertEqual(game.state, GameState.BOSS_FIGHT)
        self.assertFalse(game.enemies)


if __name__ == '__main__':
    unittest.main()
