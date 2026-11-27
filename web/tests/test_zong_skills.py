import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
from game_core import config
from game_core.entities import Enemy
from game_core.game import Game
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
        self.assertEqual(boss.snow_until, 8000)
        self.assertFalse(boss.should_attack(4001))
        with patch('game_core.config.game_ticks', return_value=8001):
            boss.update()
            self.assertEqual(boss.snow_until, 8000)

    def test_split_body_resistance_uses_mode_and_damage_source(self):
        for mode, resisted in (('easy', 1), ('medium', .75), ('hard', .5), ('infinite', .5)):
            with self.subTest(mode=mode):
                game = Game()
                game.current_level = 8
                game.infinite_boss_index = 7
                game.infinite_mode = mode == 'infinite'
                game.difficulty = config.DIFFICULTY_PRESETS['hard' if game.infinite_mode else mode]
                with patch('game_core.game.start_music'), patch('game_core.game.play_sound'):
                    if game.infinite_mode:
                        game._trigger_infinite_boss()
                    else:
                        game._trigger_boss()
                boss = game.boss
                self.assertIsInstance(boss, ZongBoss)
                boss.y = Enemy.ENTRY_DAMAGE_Y
                for index, box in enumerate(boss.hitboxes()):
                    for source in ('bullet', 'skill'):
                        with self.subTest(index=index, source=source):
                            before = boss.body_hp[:]
                            boss.hit_by('pistol', 2, source=source, hit_rect=box)
                            reduced = source == ('bullet', 'skill')[index]
                            self.assertAlmostEqual(before[index] - boss.body_hp[index],
                                                   2 * (resisted if reduced else 1))
                            self.assertEqual(before[1 - index], boss.body_hp[1 - index])

    def test_opening_and_rage_snow_use_difficulty_durations(self):
        for tier, duration in enumerate((3000, 4000, 5000)):
            with self.subTest(tier=tier):
                boss = self.make_boss()
                boss.bdef['campaign_tier'] = tier
                with patch.object(boss, '_choose_attack_skill', return_value='snow'):
                    boss.attack(4000, 200)
                self.assertEqual(boss.snow_until, 4000 + duration)
                boss.next_fusion_time = 10000
                boss.fusion_warning_mode = 'rage'
                with patch('game_core.config.game_ticks', return_value=10000), \
                        patch('game_core.special_bosses.random.random', return_value=0):
                    boss.update()
                self.assertEqual(boss.snow_until, 10000 + duration)

    def test_only_shield_fusion_heals_each_body_once_up_to_its_maximum(self):
        for mode in ('shield', 'rage'):
            with self.subTest(mode=mode):
                boss = self.make_boss()
                body_max = boss.max_hp / 2
                boss.body_hp = [body_max * .5, body_max * .9]
                boss.hp = sum(boss.body_hp)
                boss.fusion_mode = mode
                boss.fusion_until = 10000
                with patch('game_core.config.game_ticks', return_value=9999):
                    boss.update()
                self.assertAlmostEqual(boss.hp, body_max * 1.4)
                for now in (10000, 10001):
                    with patch('game_core.config.game_ticks', return_value=now):
                        boss.update()
                    fractions = (.65, 1) if mode == 'shield' else (.5, .9)
                    for hp, fraction in zip(boss.body_hp, fractions):
                        self.assertAlmostEqual(hp, body_max * fraction)
                    self.assertAlmostEqual(boss.hp, sum(boss.body_hp))

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
        width_scale = (config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT) / 480
        self.assertTrue(all(shot.r == round(round(42 * width_scale) * .65) for shot in shots))
        self.assertTrue(all(shot.speed == 12 for shot in shots))
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
        frames = []
        for age in (0, 150):
            surface = pygame.Surface((440, 440), pygame.SRCALPHA)
            with patch('game_core.config.game_ticks', return_value=shot.spawn_time + age):
                shot.draw(surface)
            frames.append(pygame.image.tobytes(surface, 'RGBA'))
            self.assertTrue(surface.get_bounding_rect().collidepoint(200, 200))
        self.assertNotEqual(*frames)
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
        with patch.object(boss, '_choose_attack_skill', return_value='bomb'):
            bombs = boss.attack(1000, 200)
        self.assertEqual([bomb.color for bomb in bombs], ['black', 'yellow', 'red'])
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
        boss = self.make_boss()
        with patch.object(boss, '_choose_attack_skill', return_value='bomb'):
            bomb = boss.attack(1000, 200)[0]
        bomb.spawn_time = 1000
        with patch('game_core.config.game_ticks', return_value=7000):
            bomb.update(9000, 9000)
        self.assertFalse(bomb.alive)
        self.assertFalse(bomb.proximity_detonated)
