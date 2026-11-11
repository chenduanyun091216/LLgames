import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
from game_core import config
from game_core.render import RenderSurface
from game_core.special_bosses import ZongBoss, ZongReflectBullet


class ZongSkillsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def make_boss(self):
        definition = dict(next(item for item in config.BOSS_DEFS if item['key'] == 'boss_zongzong'))
        definition.update(campaign_tier=1, campaign_level=8, easy_campaign=True)
        boss = ZongBoss(definition, SimpleNamespace(boss_hp_mult=1, boss_homing_mult=1))
        boss.entered = True
        boss.fight_start_time = 1000
        return boss

    def test_opening_snow_once_after_three_seconds(self):
        boss = self.make_boss()
        self.assertFalse(boss.should_attack(3999))
        self.assertTrue(boss.should_attack(4000))
        with patch('game_core.entities.random.choice', return_value='snow'):
            self.assertEqual(boss.attack(4000, 200), [])
        self.assertEqual(boss.snow_until, 7000)
        self.assertFalse(boss.should_attack(4001))
        with patch('game_core.config.game_ticks', return_value=7001):
            boss.update()
            self.assertEqual(boss.snow_until, 7000)

    def test_snow_composites_only_visible_effect_tiles(self):
        size = (960, 540)
        output = (1920, 1080)
        canvas = pygame.Surface(output, pygame.SRCALPHA)
        view = RenderSurface(canvas, size, output, (0, 0), track_damage=True)
        with patch.object(config, 'SCREEN_WIDTH', size[0]), \
                patch.object(config, 'SCREEN_HEIGHT', size[1]), \
                patch.object(config, 'game_ticks', return_value=1000):
            ZongBoss.draw_snow(view, 2000, config.make_font(16), 20)
        dirty_tiles = sum(row.bit_count() for row in view._dirty_rows)
        total_tiles = (output[0] // view.tile) * len(view._dirty_rows)
        self.assertGreater(dirty_tiles, 0)
        self.assertLess(dirty_tiles, total_tiles // 2)

    def test_bombs_have_three_distinct_colors(self):
        boss = self.make_boss()
        with patch('game_core.entities.random.choice', return_value='bomb'):
            self.assertEqual([p.color for p in boss.attack(1000, 200)], ['black', 'yellow', 'red'])

    def test_reflected_bullet_tracks_gently(self):
        bullet = ZongReflectBullet(100, 100)
        bullet.update(300, 500)
        self.assertGreater(bullet.x, 100)
        self.assertLessEqual(bullet.x - 100, 2)

    def test_fireball_volley_links_only_neighbors(self):
        shots = self.make_boss()._fireball_fan()
        self.assertEqual(len(shots), 8)
        self.assertIsNone(shots[0].lightning_previous)
        self.assertIs(shots[1].lightning_previous, shots[0])
        self.assertIs(shots[-1].lightning_previous, shots[-2])

    def test_crescent_charge_locks_position_and_fires_four_aimed_shots(self):
        boss = self.make_boss()
        boss.y = 60
        boss.next_fusion_time = 999999
        with patch('game_core.entities.random.choice', return_value='wave'):
            self.assertEqual(boss.attack(10000, boss.x + 200, 500), [])
        start_x = boss.x
        for now, count, target_x in ((11499, 0, start_x), (11500, 1, start_x + 200),
                                     (11799, 1, start_x), (11800, 2, start_x),
                                     (12100, 3, start_x - 200), (12400, 4, start_x + 100)):
            with patch('game_core.config.game_ticks', return_value=now):
                boss.update(target_x, 500)
            self.assertEqual(boss.x, start_x)
            self.assertEqual(len(boss.crescent_projectiles), count)
        shots = boss.crescent_projectiles
        self.assertGreater(shots[0].angle, 0)
        self.assertAlmostEqual(shots[1].angle, 0)
        self.assertLess(shots[2].angle, 0)
        self.assertGreater(shots[3].angle, 0)
        with patch('game_core.config.game_ticks', return_value=12401):
            boss.update()
        self.assertNotEqual(boss.x, start_x)

    def test_crescent_moves_and_rotates_at_arbitrary_angle(self):
        from game_core.special_bosses import CrescentWave
        shot = CrescentWave(200, 200, 70, angle=90)
        before = shot.rect()
        shot.update()
        self.assertGreater(shot.x, 200)
        self.assertAlmostEqual(shot.y, 200)
        self.assertEqual(before.height, before.width)

    def test_idle_expressions_change_and_hits_temporarily_show_sadness(self):
        boss = self.make_boss()
        boss.y = boss.ENTRY_DAMAGE_Y if hasattr(boss, 'ENTRY_DAMAGE_Y') else 100
        self.assertNotEqual(boss.expression_frame(1000, 0), boss.expression_frame(5000, 0))
        with patch('game_core.config.game_ticks', return_value=6000):
            boss.hit_by('pistol', amount=1)
        self.assertEqual(boss.expression_frame(6100, 0), 2)
        self.assertNotEqual(boss.expression_frame(7500, 0), 2)

    def test_new_expression_sheet_has_four_distinct_frames(self):
        from game_core import animation
        frames = [animation.frame('boss_zongzong_expressions', i) for i in range(4)]
        self.assertTrue(all(frame is not None for frame in frames))
        self.assertEqual(len({pygame.image.tostring(frame, 'RGBA') for frame in frames}), 4)

    def test_three_bombs_detonate_immediately_only_near_player(self):
        boss = self.make_boss()
        bombs = boss.attack(1000, 200)
        for bomb in bombs:
            with self.subTest(color=bomb.color):
                bomb.x, bomb.y = 300, 300
                bomb.spawn_time = 1000
                with patch('game_core.config.game_ticks', return_value=1500):
                    bomb.update(600, 600)
                    self.assertTrue(bomb.alive)
                    bomb.update(bomb.x + 10, bomb.y)
                self.assertFalse(bomb.alive)
                self.assertTrue(bomb.proximity_detonated)
                self.assertEqual(bomb.explode_radius, round(bomb.r * 1.5))

    def test_expired_bomb_does_not_proximity_detonate(self):
        bomb = self.make_boss().attack(1000, 200)[0]
        bomb.spawn_time = 1000
        with patch('game_core.config.game_ticks', return_value=7000):
            bomb.update(9000, 9000)
        self.assertFalse(bomb.alive)
        self.assertFalse(bomb.proximity_detonated)
