import os
import hashlib
import random
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame

from game_core import config
from game_core.entities import Enemy
from game_core.game import Game
from game_core.render import RenderSurface


class FactoryEnemiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def setUp(self):
        self.game = Game(desktop_controls=False)
        self.game._start_game('medium')
        self.game._start_level(9, checkpoint=False)

    def spawn(self):
        self.game._spawn_campaign_enemy()
        enemy = self.game.enemies[-1]
        enemy.y = 100
        return enemy

    def test_infinite_factory_enemies_link_and_merge_during_normal_play(self):
        game = self.game
        game._begin_infinite_run(9)
        now = config.game_ticks()
        for _ in range(3):
            game.spawn_enemy()
            game.enemies[-1].y = 100
        self.assertTrue(all(e.edef['key'] in config.FACTORY_ENEMY_KEYS for e in game.enemies))
        self.assertEqual(game._enemy_shots(game.enemies[0], now)[0].skill, 'guided_missile')
        with patch('game_core.game.random.random', return_value=.1):
            game._update_playing(now)
        self.assertTrue(all(e.factory_link_until == now + 2000 for e in game.enemies))
        game.last_spawn_time = now + 2000
        game._update_playing(now + 2000)
        mini, = game.enemies
        self.assertEqual(mini.factory_kind, 'mini_boss')
        self.assertAlmostEqual(mini.max_hp, config.INFINITE_BOSS_HP[8] * .16)
        self.assertIsNone(game.boss)
        game.spawn_enemy()
        enemy = game.enemies[-1]
        game._kill_enemy(enemy)
        self.assertIs(game.enemies[0], mini)
        fragments = game.enemies[1:]
        self.assertIn(len(fragments), (1, 2, 3))
        self.assertTrue(all(e.factory_kind == 'fragment' for e in fragments))

    def test_infinite_temple_enemies_spawn_after_factory_boss_and_reinforce_temple_boss(self):
        game = self.game
        game._begin_infinite_run(9)
        game._trigger_infinite_boss()
        game._kill_boss()
        game.spawn_enemy()
        self.assertIn(game.enemies[0].edef['key'], config.TEMPLE_ENEMY_KEYS)
        game._trigger_infinite_boss()
        game.spawn_enemy()
        self.assertIn(game.enemies[0].edef['key'], config.TEMPLE_ENEMY_KEYS)
        game._kill_boss()
        game.spawn_enemy()
        self.assertIn(game.enemies[0].edef, game.level_enemy_defs)

    def test_three_linked_enemies_survive_at_one_percent_and_die_without_splitting(self):
        group = [self.spawn() for _ in range(3)]
        with patch('game_core.game.random.random', return_value=.1):
            self.game._start_factory_link(1000)
        self.assertTrue(all(e.factory_link_until == 3000 for e in group))
        for enemy in group[:2]:
            enemy.hit_by('pistol', 999)
            self.assertAlmostEqual(enemy.damage_taken, enemy.max_hp * .99)
            self.assertFalse(enemy.is_killed('pistol'))
        self.game._settle_factory_link(2200)
        self.assertEqual(self.game.enemies, group)
        group[2].hit_by('pistol', 999)
        self.game._settle_factory_link(2400)
        self.assertEqual(self.game.enemies, [])
        self.assertEqual(self.game.level_kills, 3)

    def test_link_with_four_visible_enemies_merges_and_only_rolls_once(self):
        for _ in range(4):
            self.spawn()
        with patch('game_core.game.random.random', return_value=.8) as roll:
            self.game._start_factory_link(1000)
            self.game._start_factory_link(1016)
            roll.assert_called_once()
        self.spawn()
        with patch('game_core.game.random.random', return_value=.2):
            self.game._start_factory_link(1500)
        self.game._settle_factory_link(3500)
        mini, = [e for e in self.game.enemies if e.factory_kind == 'mini_boss']
        self.assertAlmostEqual(mini.max_hp, self.game._campaign_value(config.CAMPAIGN_BOSS_HP) * .16)
        self.assertEqual(self.game.level_kills, 0)
        missiles = self.game._enemy_shots(mini, 5000)
        self.assertEqual(len(missiles), 3)
        self.assertTrue(all(m.skill == 'guided_missile' and m.missile_pass == 2 for m in missiles))
        self.game._kill_enemy(mini)
        self.assertEqual(self.game.level_kills, 3)

    def test_unlinked_enemy_splits_once_and_children_fire_small_missiles(self):
        randint = random.randint
        for count in (1, 2, 3):
            with self.subTest(count=count):
                parent = self.spawn()
                parent.x = config.GAME_AREA_LEFT + parent.w / 2
                with patch('game_core.game.random.randint',
                           side_effect=lambda a, b: count if (a, b) == (1, 3) else randint(a, b)):
                    self.game._kill_enemy(parent)
                children = self.game.enemies[:]
                self.assertEqual(len(children), count)
                self.assertGreaterEqual(children[0].rect().left, config.GAME_AREA_LEFT)
                self.assertLessEqual(children[-1].rect().right, config.GAME_AREA_RIGHT)
                for left, right in zip(children, children[1:]):
                    self.assertGreaterEqual(right.rect().left - left.rect().right, left.w // 2)
                self.game._start_factory_link(5000)
                for child in children:
                    self.assertFalse(child.factory_link_until)
                    self.assertAlmostEqual(child.max_hp, parent.max_hp * .25)
                    self.assertLess(child.w, parent.w)
                    missile, = self.game._enemy_shots(child, 5000)
                    self.assertEqual(missile.skill, 'guided_missile')
                    self.assertFalse(missile.unblockable)
                    self.game._kill_enemy(child)
                self.assertEqual(self.game.enemies, [])
                self.assertEqual(self.game.level_kills, count)

    def test_mini_boss_blocks_another_link_until_defeated(self):
        for _ in range(3):
            self.spawn()
        with patch('game_core.game.random.random', return_value=.1):
            self.game._start_factory_link(1000)
        self.game._settle_factory_link(3000)
        mini, = self.game.enemies
        originals = [self.spawn() for _ in range(3)]
        with patch('game_core.game.random.random', return_value=.1) as roll:
            self.game._start_factory_link(3016)
            roll.assert_not_called()
            self.assertTrue(all(not e.factory_link_until for e in originals))
            self.game._kill_enemy(mini)
            self.game._start_factory_link(3032)
            roll.assert_called_once()
        self.assertTrue(all(e.factory_link_until for e in originals))

    def test_mini_boss_is_smaller_and_patrols_using_the_large_boss_walk_frames(self):
        for _ in range(3):
            self.spawn()
        with patch('game_core.game.random.random', return_value=.1):
            self.game._start_factory_link(1000)
        self.game._settle_factory_link(3000)
        mini, = self.game.enemies
        self.assertLess(mini.unscaled_base_w, 110)
        self.assertLess(mini.unscaled_base_h, 96)
        right = config.GAME_AREA_RIGHT - mini.w / 2
        mini.x = right - 2 * mini.speed
        y = mini.y
        positions = []
        for _ in range(8):
            mini.update()
            positions.append(mini.x)
        self.assertGreater(positions[1], positions[0])
        self.assertLess(positions[-1], positions[-2])
        self.assertLessEqual(max(positions), right)
        self.assertEqual(mini.y, y)
        with patch('game_core.entities.animation.frame') as frame:
            frame.return_value = None
            for x in (200, 220):
                mini.x = x
                mini.draw(pygame.Surface((960, 720), pygame.SRCALPHA))
            self.assertEqual({call.args for call in frame.call_args_list},
                             {('boss_mecha_lizard', 2), ('boss_mecha_lizard', 3)})

    def test_boss_casts_walks_and_turns_head_in_a_2k_render(self):
        self.game._trigger_boss()
        boss = self.game.boss
        boss.entered, boss.x, boss.y, boss.breath_start_time = True, 480, 100, 0
        pixels = pygame.Surface((2560, 1440), pygame.SRCALPHA)
        view = RenderSurface(pixels, (960, 720), (1920, 1440), (320, 0))

        def render(now):
            pixels.fill((0, 0, 0, 0))
            with patch.object(config, 'game_ticks', return_value=now):
                boss.draw(view)
            bounds = pixels.get_bounding_rect()
            self.assertGreater(bounds.width, 400)
            self.assertLess(bounds.width, 660)
            return hashlib.sha256(pygame.image.tostring(pixels.subsurface(bounds), 'RGBA')).digest()

        boss.movement_timer = 78
        images = [render(0), render(460)]
        boss.movement_timer = 0
        images.append(render(0))
        boss.movement_timer = 6
        images.append(render(0))
        for skill in boss.SKILLS:
            boss.current_skill, boss.skill_started_at = skill, 1000
            images.append(render(1100))
        self.assertEqual(len(set(images)), 8)

    def test_endless_mechanical_lizard_runs_the_same_emp_dash(self):
        self.game.infinite_mode = True
        self.game.infinite_boss_index = 8
        self.game._trigger_infinite_boss()
        boss = self.game.boss
        boss.entered, boss.y, boss.skill_index = True, 60, 2
        with patch.object(config, 'game_ticks', return_value=1000):
            shot, = boss.attack(1000, 480)
        with patch.object(config, 'game_ticks', return_value=1000 + shot.warning_ms):
            boss.update()
            self.assertEqual(shot.skill, 'emp_ring')
            self.assertAlmostEqual(boss.rect().centery, config.SCREEN_HEIGHT / 2, delta=1)
            self.assertGreater(len(boss.hitboxes()), 1)
