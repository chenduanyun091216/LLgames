import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.abyss_bosses import AbyssProjectile
from game_core.character_fields import draw_air_wave, draw_player_fields
from game_core.entities import BossProjectile, Enemy
from game_core.game import Game
from game_core.render import RenderSurface
from game_core.trench import TrenchSpire


class CharacterUpgradeTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((960, 720))
        self.addCleanup(pygame.quit)
        self.addCleanup(setattr, config, 'campaign_time_ms', config.campaign_time_ms)
        self.now = config.campaign_time_ms = 10000

    def game(self, *, desktop=True, size=(960, 720), level=1):
        config.update_mobile_view(size)
        game = Game(desktop_controls=desktop, web=not desktop, mobile_web=not desktop)
        game._start_game('medium', level)
        game.mobile_controls.auto_fire = False
        return game

    def equip(self, game, key, level):
        if key not in game.player.owned_characters:
            game.player.owned_characters.append(key)
        self.assertTrue(game.try_switch_character(key))
        game.player.character_upgrades[key] = level

    def cast(self, game, value):
        with patch('game_core.game.random.random', return_value=value) as roll:
            if game.player.character == 'radiation':
                game._activate_radiation_laser(game.player)
            else:
                game._handle_mobile_action('skill1')
        return roll

    def test_shop_charges_purchase_price_at_every_level_and_caps_it(self):
        for desktop, size, endless in ((True, (960, 720), False), (False, (390, 844), True),
                                       (False, (844, 390), False)):
            game = self.game(desktop=desktop, size=size)
            if endless:
                game._begin_infinite_run()
            game._open_shop()
            for key, definition in config.CHARACTER_DEFS.items():
                target = f'character_upgrade:{key}'
                cost = game._character_cost(definition)
                with self.subTest(size=size, key=key):
                    if not endless:
                        rects = game._mobile_shop_rects()
                        self.assertNotIn(target, rects)
                        game.player.gold = cost
                        game._handle_click(rects[f'character:{key}'].center)
                        self.assertEqual(game.player.gold, 0)
                    for level in (1, 2, 3):
                        self.assertEqual(game._character_upgrade_cost(key), cost)
                        rect = game._mobile_shop_rects()[target]
                        self.assertTrue(config.SCR.get_rect().contains(rect))
                        game.player.gold = cost - 1
                        game._handle_click(rect.center)
                        self.assertIn('金币不足', game.shop_notice)
                        self.assertEqual(game.player.character_upgrades.get(key, 0), level - 1)
                        game.player.gold = cost
                        game._handle_click(rect.center)
                        self.assertEqual(game.player.gold, 0)
                        self.assertEqual(game.player.character_upgrades[key], level)
                    self.assertNotIn(target, game._mobile_shop_rects())
                    game.draw()

    def test_checkpoints_keep_upgrades_and_refund_progress_after_checkpoint(self):
        game = self.game()
        self.equip(game, 'water', 1)
        game.player.gold = 100
        game._start_level(2)
        self.assertEqual(game.player.character_upgrades['water'], 1)
        game._open_shop()
        game._handle_click(game._mobile_shop_rects()['character_upgrade:water'].center)
        self.assertEqual(game.player.character_upgrades['water'], 2)
        self.assertLess(game.player.gold, 100)
        game._retry_level()
        self.assertEqual(game.player.character_upgrades, {'water': 1})
        self.assertEqual(game.player.gold, 100)

    def test_successful_cast_rolls_once_with_exact_boundary_and_durations(self):
        cases = (
            ('ice', 'enemy_freeze_until', (1000, 1500, 2000)),
            ('water', 'swift_field_until', (2000, 2500, 3000)),
            ('fire', 'fire_shield_until', (3000, 4000, 5000)),
            ('radiation', 'radiation_field_until', (3000, 4000, 5000)),
        )
        for key, attr, durations in cases:
            for level, duration in enumerate(durations, 1):
                with self.subTest(key=key, level=level):
                    game = self.game()
                    self.equip(game, key, level)
                    owner = game if key == 'ice' else game.player
                    self.cast(game, .25).assert_called_once_with()
                    self.assertEqual(getattr(owner, attr), 0)
                    self.cast(game, .0).assert_not_called()
                    game = self.game()
                    self.equip(game, key, level)
                    owner = game if key == 'ice' else game.player
                    self.cast(game, .249).assert_called_once_with()
                    self.assertEqual(getattr(owner, attr), self.now + duration)
        game = self.game()
        self.equip(game, 'ice', 0)
        self.cast(game, .0).assert_not_called()
        self.assertEqual(game.enemy_freeze_until, 0)

    def test_ice_freezes_small_enemy_and_orochi_windup_while_inflight_shot_moves(self):
        game = self.game(level=12)
        game._trigger_boss()
        self.equip(game, 'ice', 3)
        boss = game.boss
        boss.entered, boss.y, boss.fight_start_time = True, 100, self.now - 1000
        boss.side_head, boss.side_head_at = -1, self.now - 500
        enemy = Enemy(next(definition for definition in config.ENEMY_DEFS if definition.get('zongzong')))
        enemy.y = 210
        game.enemies = [enemy]
        shot = BossProjectile(60, 240, 0, 3)
        game.boss_projectiles = [shot]
        self.cast(game, .0)
        original_x = boss.x
        for now in (self.now + 17, self.now + 1999):
            config.campaign_time_ms = now
            game.update()
            self.assertEqual((boss.x, enemy.y), (original_x, 210))
            self.assertEqual(game.boss_projectiles, [shot])
        self.assertGreater(shot.y, 240)
        config.campaign_time_ms = self.now + 2000
        game.update()
        self.assertNotEqual(boss.x, original_x)
        self.assertGreater(enemy.y, 210)
        self.assertEqual(game.boss_projectiles, [shot])
        config.campaign_time_ms = self.now + 2400
        game.update()
        self.assertEqual(len(game.boss_projectiles), 7)

    def test_water_speed_and_fire_shield_expire_at_deadline(self):
        game = self.game()
        self.equip(game, 'water', 1)
        self.cast(game, .0)
        game.player.last_shot_time = self.now
        self.assertFalse(game.player.can_shoot(self.now + 266))
        self.assertTrue(game.player.can_shoot(self.now + 267))
        self.assertAlmostEqual(game._player_speed(game.player, self.now + 1999), 5.2 * 1.3)
        self.assertAlmostEqual(game._player_speed(game.player, self.now + 2000), 5.2)

        game = self.game()
        self.equip(game, 'fire', 3)
        self.cast(game, .0)
        hp = game.player_hp
        game.player_invincible_until = self.now + 1
        game._damage_player(self.now, 2, 'test')
        self.assertEqual(game.player.fire_shield_hits, 3)
        for i, damage in enumerate((100, 2, 1), 1):
            game._damage_player(self.now + i, damage, 'test')
            self.assertEqual(game.player_hp, hp)
            self.assertEqual(game.player.fire_shield_hits, 3 - i)
        game._damage_player(self.now + 4, 1, 'test')
        self.assertEqual(game.player_hp, hp - 1)
        game = self.game()
        self.equip(game, 'fire', 1)
        self.cast(game, .0)
        game._damage_player(self.now + 3000, 1, 'test')
        self.assertEqual(game.player_hp, hp - 1)

    def test_field_timer_stays_near_the_character_when_it_can_clear_a_button_to_the_side(self):
        game = self.game()
        surface = pygame.Surface((480, 1039), pygame.SRCALPHA)
        bounds = pygame.Rect(0, 0, 56, 66)
        bounds.center = (240, 875)
        button = pygame.Rect(106, 739, 60, 60)
        draw_player_fields(surface, game.player, bounds, 1.18, self.now, game.font_countdown,
                           ice_until=self.now + 1000, obstacles=(button,))
        badge = surface.get_bounding_rect()
        self.assertTrue(badge)
        self.assertLessEqual(badge.right, bounds.centerx)
        self.assertFalse(badge.colliderect(button))
        self.assertLess(bounds.top - badge.bottom, 55)

    def test_air_wave_can_expand_into_the_view_after_resizing(self):
        size = (480, 720)
        surface = pygame.Surface(size, pygame.SRCALPHA)
        target = RenderSurface(surface, size, size, (0, 0))
        wave = (800, 460, self.now)
        draw_air_wave(target, wave, self.now)
        self.assertFalse(surface.get_bounding_rect())
        draw_air_wave(target, wave, self.now + 300)
        self.assertTrue(surface.get_bounding_rect())

    def test_radiation_boosts_hits_and_max_level_wave_clears_only_flying_shots_once(self):
        for level in (2, 3):
            with self.subTest(level=level):
                config.campaign_time_ms = self.now
                game = self.game()
                self.equip(game, 'radiation', level)
                with patch('game_core.game.random.random', return_value=0) as roll:
                    game._handle_mobile_action('dart')
                    roll.assert_called_once_with()
                game._shoot(self.now)
                bullet = game.bullets[0]
                enemy = Enemy(config.ENEMY_DEFS[0])
                enemy.y = 150
                enemy.max_hp = 100
                game._apply_bullet_passive(enemy, bullet, self.now)
                self.assertEqual(enemy.damage_taken, 2 * bullet.damage)
                end = game.player.radiation_field_until
                game._apply_bullet_passive(enemy, bullet, end)
                self.assertEqual(enemy.damage_taken, 3 * bullet.damage)

                aimed = AbyssProjectile('guided_missile', 150, 180, speed=3, warning_ms=0, active_ms=10000)
                queued = AbyssProjectile('guided_missile', 150, 180, speed=3, warning_ms=6000)
                ground = TrenchSpire(150, 400, 25, 40, 6000)
                game.boss_projectiles = [aimed, queued, ground]
                game.enemy_projectiles = [BossProjectile(50, 180, 0, 3)]
                game._update_character_fields(end - 1)
                self.assertEqual(len(game.boss_projectiles), 3)
                game._update_character_fields(end)
                self.assertEqual(game.bullets, [bullet])
                if level == 2:
                    self.assertEqual(len(game.boss_projectiles), 3)
                    self.assertIsNone(game.radiation_wave)
                else:
                    self.assertEqual(game.boss_projectiles, [queued, ground])
                    self.assertFalse(game.enemy_projectiles)
                    self.assertEqual(game.radiation_wave, (game.player.x, game.player.y, end))
                    game.enemy_projectiles.append(BossProjectile(80, 180, 0, 3))
                    game._update_character_fields(end + 500)
                    self.assertEqual(len(game.enemy_projectiles), 1)
                    self.assertIsNone(game.radiation_wave)
