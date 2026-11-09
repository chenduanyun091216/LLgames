import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_player_motion_only_when_position_changes(self):
        for package in ('pc', 'web'):
            with self.subTest(package=package):
                player = importlib.import_module(package + '.entities').Player()
                player.move(0, 0)
                self.assertFalse(player.animation_moving)
                player.move(3, 0)
                self.assertTrue(player.animation_moving)
                player.move(0, 0)
                self.assertFalse(player.animation_moving)

    def test_action_frame_finishes(self):
        for package in ('pc', 'web'):
            animation = importlib.import_module(package + '.animation')
            self.assertEqual(animation.action_frame(1000, 1000), 0)
            self.assertEqual(animation.action_frame(1000, 1300), 2)
            self.assertIsNone(animation.action_frame(1000, 1700))

    def test_zongzong_expressions_follow_hits_without_changing_damage(self):
        for package in ('pc', 'web'):
            module = importlib.import_module(package + '.entities')
            config = importlib.import_module(package + '.config')
            enemy = module.Enemy(next(e for e in config.ENEMY_DEFS if e.get('zongzong')))
            enemy.hit_by('pistol', 0.1)
            self.assertEqual(enemy.zong_expression, 0)
            enemy.hit_by('pistol', 0.1)
            self.assertGreaterEqual(enemy.zong_expression, 1)
            enemy.hit_by('pistol', 1000)
            self.assertEqual(enemy.zong_expression, 3)
            self.assertTrue(enemy.is_killed('pistol'))

    def test_zongzong_draws_progressive_expressions(self):
        for package in ('pc', 'web'):
            module = importlib.import_module(package + '.entities')
            config = importlib.import_module(package + '.config')
            enemy = module.Enemy(next(e for e in config.ENEMY_DEFS if e.get('zongzong')))
            clock = (module.pygame.time, 'get_ticks') if package == 'pc' else (config, 'game_ticks')
            canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
            with patch.object(*clock, return_value=1000), patch.object(module.animation, 'frame', wraps=module.animation.frame) as pick:
                enemy.hit_by('pistol', 0.1)
                enemy.draw(canvas)
                pick.assert_called_with('zongzong_hurt', 0)
            with patch.object(*clock, return_value=2000):
                enemy.hit_by('pistol', 0.1)
            with patch.object(*clock, return_value=2300), patch.object(module.animation, 'frame', wraps=module.animation.frame) as pick:
                enemy.draw(canvas)
                pick.assert_called_with('zongzong_hurt', 1)
            with patch.object(*clock, return_value=3000):
                enemy.hit_by('pistol', 1000)
            with patch.object(*clock, return_value=3500), patch.object(module.animation, 'frame', wraps=module.animation.frame) as pick:
                enemy.draw(canvas)
                pick.assert_called_with('zongzong_hurt', 3)

    def test_boss_animation_matches_special_state(self):
        for package in ('pc', 'web'):
            animation = importlib.import_module(package + '.animation')
            niu = SimpleNamespace(bdef={'key': 'boss_niu'}, last_pattern='vortex', animation_attack_at=1000)
            with patch.object(animation, 'frame', wraps=animation.frame) as pick:
                self.assertIsNotNone(animation.boss_frame(niu, 1300))
                pick.assert_called_with('boss_niu_vortex', 2)
            zong = SimpleNamespace(bdef={'key': 'boss_zongzong'}, fusion_mode='rage', fusion_started_at=1000)
            with patch.object(animation, 'frame', wraps=animation.frame) as pick:
                self.assertIsNotNone(animation.boss_frame(zong, 1300))
                pick.assert_called_with('boss_zongzong_rage', 2)

    def test_boss_laser_and_zong_attack_select_their_own_frames(self):
        for package in ('pc', 'web'):
            animation = importlib.import_module(package + '.animation')
            crab = SimpleNamespace(bdef={'key': 'boss_crab'}, laser_warning_start=1000, laser_active_until=0)
            with patch.object(animation, 'frame', wraps=animation.frame) as pick:
                self.assertIsNotNone(animation.boss_frame(crab, 1300))
                pick.assert_called_with('boss_crab_laser', 1)
            crab.laser_warning_start = 0
            crab.laser_active_until = 2000
            with patch.object(animation, 'frame', wraps=animation.frame) as pick:
                self.assertIsNotNone(animation.boss_frame(crab, 1500))
                pick.assert_called_with('boss_crab_laser', 1)
            for phase, action in ((1, 'bomb'), (2, 'wave')):
                boss = SimpleNamespace(bdef={'key': 'boss_zongzong'}, fusion_mode=None,
                                       attack_phase=phase, animation_attack_at=1000)
                with patch.object(animation, 'frame', wraps=animation.frame) as pick:
                    self.assertIsNotNone(animation.boss_frame(boss, 1300))
                    pick.assert_called_with('boss_zongzong_' + action, 2)

    def test_all_bosses_draw_attack_frames(self):
        for package in ('pc', 'web'):
            module = importlib.import_module(package + '.entities')
            special = importlib.import_module(package + '.special_bosses')
            config = importlib.import_module(package + '.config')
            clock = (module.pygame.time, 'get_ticks') if package == 'pc' else (config, 'game_ticks')
            canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
            for definition in config.BOSS_DEFS:
                with self.subTest(package=package, boss=definition['key']):
                    cls = special.NiuBoss if definition['key'] == 'boss_niu' else special.ZongBoss if definition['key'] == 'boss_zongzong' else module.Boss
                    boss = cls(definition, config.DIFFICULTY_PRESETS['easy'])
                    boss.y = 60
                    boss.entered = True
                    boss.animation_attack_at = 1000
                    with patch.object(*clock, return_value=1300), patch.object(module.animation, 'boss_frame', wraps=module.animation.boss_frame) as pick:
                        boss.draw(canvas)
                        self.assertTrue(pick.called)
                        self.assertIsNotNone(pick(boss, 1300))

    def test_every_skill_has_a_dedicated_sheet(self):
        skills = {
            'fire': ('fire_wall', 'fireball'),
            'ice': ('ice_floor', 'ice_balls'),
            'water': ('water_heal', 'water_boost'),
            'radiation': ('lightning', 'magnetic_storm', 'radiation_laser', 'dart_shield'),
        }
        for package in ('pc', 'web'):
            animation = importlib.import_module(package + '.animation')
            for character, names in skills.items():
                for name in names:
                    self.assertIsNotNone(animation.frame('player_' + character + '_' + name, 2), name)

    def test_assets_cover_all_characters_and_bosses(self):
        for package in ('pc', 'web'):
            animation = importlib.import_module(package + '.animation')
            for name in ('player1_back', 'player2_back', 'player_fire_run',
                         'player_ice_run', 'player_water_run', 'player_radiation_run',
                         'boss_lobster_attack', 'boss_crab_attack', 'boss_octopus_attack',
                         'boss_shark_attack', 'boss_dragon_attack', 'boss_attack',
                         'boss_niu_attack', 'boss_zongzong_attack'):
                self.assertIsNotNone(animation.frame(name, 0), name)


if __name__ == '__main__':
    unittest.main()
