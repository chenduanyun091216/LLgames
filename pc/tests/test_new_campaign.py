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
                     'CAMPAIGN_REWARDS', 'INFINITE_BOSS_HP', 'INFINITE_BOSS_ATTACK_MS',
                     'INFINITE_REINFORCEMENT_MS', 'INFINITE_REINFORCEMENT_CAP'):
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

    def test_temple_rifts_stagger_worms_and_destroyed_eye_stays_gone(self):
        for difficulty, batch_size in (('easy', 3), ('medium', 4), ('hard', 6)):
            with self.subTest(difficulty=difficulty):
                game = self.game(difficulty=difficulty)
                game._start_level(10)
                game._update_temple_enemies(1000)
                game._update_temple_enemies(9500)
                left, right = game.enemies
                self.assertLess(left.x, right.x)
                self.assertEqual(left.temple_worms_left, batch_size)
                self.assertEqual(right.temple_worms_left, batch_size)
                game._update_temple_enemies(left.temple_spawn_at)
                self.assertEqual(len(game.enemies), 3)
                self.assertEqual(right.temple_worms_left, batch_size)
                game._kill_enemy(left)
                for _ in range(batch_size):
                    game._update_temple_enemies(right.temple_spawn_at)
                self.assertEqual(game.level_kills, 0)
                self.assertEqual(len(game.enemies), 2 + batch_size)
                game._update_temple_enemies(right.temple_spawn_at)
                self.assertNotIn(left, game.enemies)
                self.assertEqual(right.temple_worms_left, batch_size)
                game._start_level(11)
                self.assertFalse(game.enemies)

    def test_temple_rifts_wait_at_worm_cap_and_resume_when_slot_opens(self):
        game = self.game(difficulty='hard')
        game._start_level(10)
        game._update_temple_enemies(1000)
        game._update_temple_enemies(9500)
        left, right = game.enemies
        for now in range(9980, 12500, 20):
            game._update_temple_enemies(now)
        worms = [enemy for enemy in game.enemies if enemy.temple_kind == 'worm']
        self.assertEqual(len(worms), 10)
        remaining = left.temple_worms_left + right.temple_worms_left
        self.assertEqual(remaining, 2)
        game._kill_enemy(worms[0])
        game._update_temple_enemies(12500)
        self.assertEqual(sum(enemy.temple_kind == 'worm' for enemy in game.enemies), 10)
        self.assertEqual(left.temple_worms_left + right.temple_worms_left, 1)

    def test_infinite_leaks_remove_enemies_and_use_shared_hit_protection(self):
        game = self.game()
        game._begin_infinite_run(10)
        for _ in range(3):
            game.spawn_enemy()
        first, second, third = game.enemies[:]
        self.assertFalse(game._resolve_leak(first, 1000))
        self.assertFalse(game._resolve_leak(second, 1649))
        self.assertEqual(game.player_hp, 4)
        self.assertFalse(game._resolve_leak(third, 1650))
        self.assertEqual(game.player_hp, 3)
        self.assertEqual(game.leak_count, 3)
        self.assertFalse(game.enemies)

    def test_infinite_orochi_has_no_reinforcements_and_temple_has_no_boss_rifts(self):
        game = self.game()
        game._begin_infinite_run(10)
        game._trigger_infinite_boss()
        game._update_temple_enemies(1000)
        game._update_temple_enemies(15000)
        self.assertFalse(game.enemies)
        game._kill_boss()
        game._trigger_infinite_boss()
        game.last_spawn_time = 0
        game._update_boss_fight(25000)
        self.assertFalse(game.enemies)

    def test_temple_worm_inherits_thirty_percent_hp_and_pursues(self):
        game = self.game()
        game._start_level(10)
        game.spawn_enemy()
        parent, = game.enemies
        parent.y = 100
        with patch('game_core.game.random.random', return_value=0), patch(
                'game_core.game.random.randint', return_value=1):
            game._update_temple_enemies(1000)
        worm = game.enemies[-1]
        self.assertEqual(worm.temple_kind, 'worm')
        self.assertAlmostEqual(worm.max_hp, parent.max_hp * .3)
        start_y = worm.y
        worm.update(game.player)
        self.assertGreater(worm.y, start_y)
        worm.hit_by('pistol', worm.max_hp)
        self.assertTrue(worm.is_killed('pistol'))

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
                        with patch('game_core.abyss_bosses.random.uniform', side_effect=random.Random(i).uniform):
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
                    config.campaign_time_ms += boss.attack_interval
                    if isinstance(boss, AncientWhaleBoss):
                        boss.fight_start_time = config.game_ticks() - 5000
                        for _ in range(200):
                            if boss.should_attack(config.game_ticks()):
                                break
                            boss.update()
                    self.assertTrue(boss.should_attack(config.game_ticks()))
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
