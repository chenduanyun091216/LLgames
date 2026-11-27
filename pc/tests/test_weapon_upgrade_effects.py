import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.entities import Enemy
from game_core.game import Game
from online.adapters.core_adapter import OnlineGame
from online.adapters.presentation import Presentation


class WeaponUpgradeEffectsTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((960, 720))
        self.addCleanup(pygame.quit)
        self.addCleanup(setattr, config, 'campaign_time_ms', config.campaign_time_ms)
        config.campaign_time_ms = 10000

    def game(self, weapon, level, endless=False):
        config.update_mobile_view((960, 720))
        game = Game(desktop_controls=True)
        if endless:
            game._begin_infinite_run()
        else:
            game._start_game('medium')
        game.player.current_weapon = weapon
        game.player.weapon_upgrades[weapon] = level
        return game

    def fire(self, game, roll):
        game.bullets.clear()
        with patch('game_core.game.random.random', return_value=roll) as random:
            self.assertTrue(game._shoot(10000))
        return random

    def test_rifle_damage_speed_and_red_round_probability_at_every_level(self):
        for endless in (False, True):
            for level, chance in enumerate(config.RIFLE_RED_CHANCES, 1):
                with self.subTest(endless=endless, level=level):
                    game = self.game('rifle', level, endless)
                    self.fire(game, chance).assert_called_once_with()
                    normal = game.bullets[0]
                    base = config.CAMPAIGN_BULLET_DAMAGE['rifle']
                    self.assertAlmostEqual(normal.damage, base * (1 + .1 * level))
                    gap = math.ceil(math.ceil(200 / .70) / (1 + config.RIFLE_SPEED_PER_LEVEL * level))
                    self.assertFalse(game.player.can_shoot(10000 + gap - 1))
                    self.assertTrue(game.player.can_shoot(10000 + gap))
                    self.fire(game, chance - .001).assert_called_once_with()
                    red = game.bullets[0]
                    self.assertTrue(red.rifle_explosive)
                    self.assertEqual(red.color, (255, 55, 45))
                    self.assertEqual(red.radius, normal.radius * 3)
                    self.assertAlmostEqual(red.damage, normal.damage * 1.5)
                    red.draw(config.SCR)

    def test_shotgun_four_rounds_have_two_red_centers_and_two_yellow_edges(self):
        for level, chance in enumerate(config.SHOTGUN_EXTRA_CHANCES, 1):
            with self.subTest(level=level):
                game = self.game('shotgun', level)
                self.fire(game, chance).assert_called_once_with()
                self.assertEqual(len(game.bullets), 3)
                self.fire(game, chance - .001).assert_called_once_with()
                shots = game.bullets
                self.assertEqual([b.angle for b in shots], [-18, -6, 6, 18])
                self.assertEqual([b.color for b in shots],
                                 [(255, 230, 40), (255, 55, 45), (255, 55, 45), (255, 230, 40)])
                self.assertEqual([b.radius for b in shots], [10, 13, 13, 10])
                total_damage = 4 * (1 + .36 * level)
                center_damage = total_damage * (.5 + (.6 - .5) * level / 3)
                self.assertAlmostEqual(sum(b.damage for b in shots), total_damage)
                self.assertAlmostEqual(sum(b.damage for b in shots[1:3]), center_damage)

    def test_unupgraded_weapons_do_not_roll_for_special_effects(self):
        for weapon in ('rifle', 'shotgun', 'sniper'):
            game = self.game(weapon, 0)
            self.fire(game, 0).assert_not_called()
            self.assertEqual(len(game.bullets), 3 if weapon == 'shotgun' else 1)
            self.assertFalse(getattr(game.bullets[0], 'rifle_explosive', False))

    def test_sniper_haste_rolls_only_on_missiles_and_expires_after_three_seconds(self):
        for level, chance in enumerate(config.SNIPER_HASTE_CHANCES, 1):
            with self.subTest(level=level):
                game = self.game('sniper', level)
                self.fire(game, 0).assert_not_called()
                self.assertAlmostEqual(game.bullets[0].damage, 3.25 + .7 * level)
                game.player.sniper_shots = 3
                self.fire(game, chance).assert_called_once_with()
                self.assertEqual(game.player.sniper_haste_until, 0)
                game.player.sniper_shots = 3
                self.fire(game, chance - .001).assert_called_once_with()
                self.assertEqual(game.player.sniper_haste_until, 13000)
                self.assertEqual(game.bullets[0].damage, config.SNIPER_MISSILE_DAMAGE[level - 1])
                delay = math.ceil(config.WEAPON_DEFS['sniper'].fire_rate / .70) / (1 + .10 * level)
                normal_gap = math.ceil(delay)
                fast_gap = math.ceil(delay / 1.5)
                for now, gap in ((12999, fast_gap), (13000, normal_gap)):
                    game.player.last_shot_time = now - gap + 1
                    self.assertFalse(game.player.can_shoot(now))
                    game.player.last_shot_time -= 1
                    self.assertTrue(game.player.can_shoot(now))

    def test_rifle_explosion_hits_primary_and_nearby_enemies_once(self):
        for boss_fight in (False, True):
            with self.subTest(boss_fight=boss_fight):
                game = self.game('rifle', 2)
                game.mobile_controls.auto_fire = False
                self.fire(game, 0)
                red = game.bullets[0]
                red.x, red.y, red.speed = 480, 250, 0
                enemies = []
                for x in (480, 550, 700):
                    enemy = Enemy(config.ENEMY_DEFS[0])
                    enemy.x, enemy.y, enemy.speed, enemy.max_hp = x, 240, 0, 100
                    enemies.append(enemy)
                if boss_fight:
                    game._trigger_boss()
                    game.boss.entered, game.boss.x, game.boss.y = True, 480, 100
                    game.bullets = [red]
                game.enemies = enemies
                base = config.CAMPAIGN_BULLET_DAMAGE['rifle'] * 1.2
                with patch('game_core.game.play_sound') as sound:
                    game.update()
                self.assertAlmostEqual(enemies[0].damage_taken, base * 3.5)
                self.assertAlmostEqual(enemies[1].damage_taken, base * 2)
                self.assertEqual(enemies[2].damage_taken, 0)
                self.assertNotIn(red, game.bullets)
                blasts = [effect for effect in game.explosions if getattr(effect, 'shockwave_radius', 0) == 100]
                self.assertEqual(len(blasts), 1)
                sound.assert_any_call('grenade')

    def test_online_snapshot_preserves_red_round_and_sniper_haste(self):
        game = OnlineGame(mode='infinite')
        player = game.all_players[1]
        player.current_weapon = 'rifle'
        player.weapon_upgrades['rifle'] = 3
        with game._capture_sounds(), patch('game_core.game.random.random', return_value=0):
            game._shoot(10000, player)
        player.current_weapon = 'sniper'
        player.weapon_upgrades['sniper'] = 3
        player.sniper_shots = 3
        with game._capture_sounds(), patch('game_core.game.random.random', return_value=0):
            game._shoot(10000, player)
        data = game.snapshot()
        presentation = Presentation(pygame.Surface(game.world_size), integrated=True)
        with patch('online.adapters.presentation.play_sound'):
            presentation.apply(data, local_slot=2)
        self.assertEqual(presentation.view.player.sniper_haste_until, 13000)
        red = presentation.view.bullets[0]
        self.assertTrue(red.rifle_explosive)
        self.assertEqual(red.radius, 30)
        self.assertEqual(tuple(red.color), (255, 55, 45))
        presentation.draw()

    def test_rifle_red_round_hits_boss_with_direct_and_area_damage(self):
        game = self.game('rifle', 3)
        game._trigger_boss()
        game.boss.entered, game.boss.y = True, 150
        game.mobile_controls.auto_fire = False
        self.fire(game, 0)
        red = game.bullets[0]
        red.x, red.y = game.boss.rect().center
        red.speed = 0
        hp = game.boss.hp
        with patch.object(game, '_update_boss_actor', return_value=False):
            game.update()
        expected = config.CAMPAIGN_BULLET_DAMAGE['rifle'] * 1.3 * 3.5
        self.assertAlmostEqual(hp - game.boss.hp, expected)
        self.assertNotIn(red, game.bullets)

    def test_sniper_haste_refreshes_without_stacking_and_new_run_clears_it(self):
        game = self.game('sniper', 1)
        for now in (10000, 11000):
            game.player.sniper_shots = 3
            with patch('game_core.game.random.random', return_value=0):
                game._shoot(now)
            self.assertEqual(game.player.sniper_haste_until, now + 3000)
        normal_gap = math.ceil(config.WEAPON_DEFS['sniper'].fire_rate / .70)
        fast_gap = math.ceil(normal_gap / 1.1 / 1.5)
        self.assertFalse(game.player.can_shoot(11000 + fast_gap - 1))
        self.assertTrue(game.player.can_shoot(11000 + fast_gap))
        game._start_game('medium')
        self.assertEqual(game.player.sniper_haste_until, 0)
        game.player.sniper_haste_until = 20000
        game._begin_infinite_run()
        self.assertEqual(game.player.sniper_haste_until, 0)
