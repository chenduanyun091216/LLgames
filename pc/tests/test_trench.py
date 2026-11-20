"""Regression checks for the trench encounter and its shared artwork."""
import json
import unittest
from unittest.mock import patch

import pygame

from game_core import animation, asset_loader, config, sprites
from game_core.game import Game, GameState
from game_core.render import RenderSurface
from game_core.trench import (ShieldfishBoss, TrenchBolt, TrenchSpire, _pose,
                              cannon_muzzle, cannon_shots, draw_cannon_charge, enemy_shots)
from online.adapters.core_adapter import OnlineGame
from online.adapters.presentation import Presentation


class TrenchTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1, 1))
        view_fields = ('SCREEN_WIDTH', 'SCREEN_HEIGHT', 'GAME_AREA_BOTTOM', 'GAME_AREA_LEFT',
                       'GAME_AREA_RIGHT', 'MOBILE_LANDSCAPE_VIEW', 'VIEW_SIZE', 'VIEW_SCALE',
                       'VIEW_OFFSET', 'SCR')
        restore_view = patch.multiple(config, **{key: getattr(config, key) for key in view_fields})
        restore_view.start()
        self.addCleanup(restore_view.stop)
        config.update_mobile_view((390, 844))
        self.clock = patch.object(config, 'campaign_time_ms', 10000)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        for name in ('game_core.game.play_sound', 'game_core.entities.play_sound'):
            sound = patch(name)
            sound.start()
            self.addCleanup(sound.stop)

    def boss(self):
        game = Game(desktop_controls=False)
        game._start_game('medium', 11)
        game._trigger_boss()
        boss = game.boss
        boss.y = 60
        boss.entered = True
        return boss

    def test_wave_uses_twelve_approved_species_and_each_has_six_frames(self):
        game = Game(desktop_controls=False)
        game._start_game('medium', 11)
        self.assertEqual(game.state, GameState.PLAYING)
        for _ in range(12):
            game.spawn_enemy()
        names = [enemy.edef['key'] for enemy in game.enemies]
        self.assertEqual(len(names), 12)
        self.assertEqual(set(names), set(config.TRENCH_ENEMY_KEYS))
        for name in names:
            with self.subTest(enemy=name):
                frames = [animation.frame('enemy_' + name, i) for i in range(6)]
                self.assertTrue(all(max(frame.get_bounding_rect(min_alpha=100).size) >= 384 for frame in frames))
                self.assertEqual(len({pygame.image.tobytes(frame, 'RGBA') for frame in frames}), 6)
        game._trigger_boss()
        self.assertFalse(game.enemies)
        self.assertIsInstance(game.boss, ShieldfishBoss)

    def test_enemy_frame_is_scaled_directly_to_high_resolution_output(self):
        game = Game(desktop_controls=False)
        game._start_game('medium', 11)
        game.spawn_enemy()
        enemy = game.enemies[0]
        enemy.x, enemy.y = 150, 95
        frame = animation.frame('enemy_' + enemy.edef['key'], 0)
        target = RenderSurface(pygame.Surface((960, 1440)), (480, 720),
                               (960, 1440), (0, 0))
        with patch.object(sprites, '_resize_sprite', wraps=sprites._resize_sprite) as resize:
            enemy.draw(target)
        source, size = resize.call_args.args
        self.assertIs(source, frame)
        self.assertGreater(size[0], enemy.w)

    def test_boss_frames_and_opening_rotation(self):
        boss = self.boss()
        atlas = asset_loader.image_asset('animations/bosses/anim_boss_shieldfish.png')
        first = []
        for row in range(5):
            frames = [pygame.image.tobytes(_pose(atlas, row, n), 'RGBA') for n in range(6)]
            self.assertEqual(len(set(frames)), 6)
            first.append(frames[0])
        self.assertEqual(len(set(first)), 5)
        seen = []
        for _ in boss.SKILLS:
            boss.attack(config.game_ticks(), boss.x, config.GAME_AREA_BOTTOM * .8)
            seen.append(boss.current_skill)
            config.campaign_time_ms += 6000
        self.assertEqual(seen[0], 'trench_roll')
        self.assertEqual(set(seen), set(boss.SKILLS))

    def test_wave_fans_and_boss_only_cannons(self):
        game = Game(desktop_controls=False)
        game._start_game('medium', 11)
        for _ in range(12):
            game.spawn_enemy()
            shots = enemy_shots(game.enemies[-1], game.player, config.game_ticks())
            self.assertEqual(len(shots), 4)
            for first, second in zip(shots, shots[1:]):
                self.assertAlmostEqual(second.angle - first.angle, 16)
        self.assertIsNone(game.trench_boss_background(config.VIEW_SIZE))
        game._update_trench_cannons(config.game_ticks() + 40000)
        self.assertFalse(game.enemy_projectiles)
        game._trigger_boss()
        self.assertIsNotNone(game.trench_boss_background(config.VIEW_SIZE))
        game._update_trench_cannons(game.trench_cannon_at - 1)
        self.assertFalse(game.enemy_projectiles)
        game._update_trench_cannons(game.trench_cannon_at)
        left = game.enemy_projectiles[:]
        game._update_trench_cannons(game.trench_cannon_at)
        right = game.enemy_projectiles[6:]
        self.assertEqual(len(left), 6)
        self.assertEqual(len(right), 6)
        self.assertTrue(all(shot.kind == 'fire' and shot.damage == 2 and shot.angle > 0 for shot in left))
        self.assertTrue(all(shot.kind == 'ice' and shot.damage == 1 and shot.angle < 0 for shot in right))
        self.assertLess(left[0].x, right[0].x)
        game.player_invincible_until = 0
        now = config.game_ticks()
        game._resolve_enemy_shot(right[0], game.player, now)
        self.assertEqual(game.player.niu_freeze_until, now + 2000)
        self.assertFalse(game.player.can_shoot(now + 1999))
        self.assertTrue(game.player.can_shoot(now + 2000))

    def test_cannons_fire_from_the_painted_muzzles(self):
        for size in ((390, 844), (844, 390), (960, 720)):
            config.update_mobile_view(size)
            desktop = size == (960, 720)
            if desktop:
                config.MOBILE_LANDSCAPE_VIEW = False
            game = Game(desktop_controls=desktop)
            game._start_game('medium', 11)
            game._trigger_boss()
            art = game.trench_boss_background((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
            lit = art.copy()
            draw_cannon_charge(lit, 0, config.TRENCH_CANNON['opening'], 0)
            for side in (0, 1):
                muzzle = cannon_muzzle(side)
                self.assertLess(muzzle[1], config.SCREEN_HEIGHT * .18)
                red, green, blue, _ = art.get_at(tuple(round(axis) for axis in muzzle))
                if side == 0:
                    self.assertGreater(red, max(green, blue) * 1.15)
                else:
                    self.assertGreater(blue, red * 1.6)
                    self.assertGreater(green, 55)
                red, green, blue, _ = lit.get_at(tuple(round(axis) for axis in muzzle))
                if side == 0:
                    self.assertGreater(red, max(green, blue) * 2)
                else:
                    self.assertGreater(blue, max(red, green) * 1.2)
                shots = cannon_shots(side)
                angles = [abs(shot.angle) for shot in shots]
                self.assertEqual(max(angles) - min(angles), 35 if size[0] < size[1] else 50)
                self.assertTrue(all(shot.r == (12 if side == 0 else 11) for shot in shots))
                self.assertTrue(all((shot.x, shot.y) == muzzle for shot in shots))
                for shot in shots:
                    old_y = shot.y
                    config.campaign_time_ms += 17
                    shot.update()
                    self.assertGreater(shot.y, old_y)
                shot = shots[2]
                start = shot.x
                for _ in range(60):
                    config.campaign_time_ms += 17
                    shot.update()
                self.assertTrue(shot.alive)
                self.assertGreater((shot.x - start) * (1 if side == 0 else -1), 75)

    def test_rolling_exits_below_and_reenters_at_the_top(self):
        game = Game(desktop_controls=False)
        game._start_game('medium', 11)
        game._trigger_boss()
        boss = game.boss
        boss.y, boss.entered = 60, True
        now = config.game_ticks()
        self.assertEqual(boss.attack(now, boss.x, 550), [])
        config.campaign_time_ms = now + 900
        boss.update()
        self.assertEqual((boss.x, boss.y), boss.motion_start)
        game.player.x, game.player.y = 145, 580
        config.campaign_time_ms = now + 1000
        boss.update(game.player)
        self.assertEqual(boss.recovery_at - config.game_ticks(), 420)
        impact_x, impact_y = game.player.rect().center
        game.player.x += 100
        config.campaign_time_ms += round(420 * boss.roll_fraction)
        boss.update(game.player)
        self.assertAlmostEqual(boss.x, impact_x, delta=2)
        self.assertAlmostEqual(boss.y + boss.h / 2, impact_y, delta=2)
        config.campaign_time_ms = boss.recovery_at - 1
        boss.update()
        self.assertTrue(boss.rolling(config.game_ticks()))
        self.assertGreater(boss.y, config.SCREEN_HEIGHT)
        config.campaign_time_ms = boss.recovery_at
        boss.update()
        self.assertEqual(boss.y, -boss.h)

    def test_bones_reaim_and_threshold_armor_launches_after_one_second(self):
        boss = self.boss()
        now = config.game_ticks()
        boss._last_attack_skill = 'trench_roll'
        boss._pending_attack_skill = 'trench_bones'
        shots = boss.attack(now, boss.x, 500)
        self.assertEqual([shot.warning_ms for shot in shots], [480, 480, 900, 900, 1320, 1320, 1740, 1740])
        config.campaign_time_ms = now + 480
        shots[0].update(boss.x - 100, 600)
        config.campaign_time_ms = now + 900
        shots[2].update(boss.x + 100, 600)
        self.assertLess(shots[0].angle, 0)
        self.assertGreater(shots[2].angle, 0)
        self.assertLess(shots[0].speed, 6)
        self.assertEqual(shots[0].r, round(24 * boss.size_scale))
        boss.hit_by('rifle', boss.max_hp * .52)
        shards = boss.armor_shots()
        self.assertEqual(len(shards), 8)
        self.assertFalse(boss.armor_shots())
        shard = shards[0]
        self.assertEqual(shard.r, round(18 * boss.size_scale))
        config.campaign_time_ms = shard.spawn_time + 999
        shard.update(boss.x, 620)
        self.assertFalse(shard.launched)
        config.campaign_time_ms += 1
        shard.update(boss.x, 620)
        self.assertTrue(shard.launched)
        self.assertGreater(shard.speed, shots[0].speed)

    def test_lan_snapshot_preserves_spire_state_and_draws_warning(self):
        game = OnlineGame()
        game._start_level(11)
        game._trigger_boss()
        boss = game.boss
        boss.entered, boss.y = True, 60
        boss._last_attack_skill = 'trench_roll'
        boss._pending_attack_skill = 'trench_spires'
        now = config.game_ticks()
        game._add_boss_projectiles(boss.attack(now, boss.x, 500))
        game.enemy_projectiles.extend([
            TrenchBolt('ice', 25, 300, speed=5.4),
        ])
        spire = game.boss_projectiles[0]
        victim = pygame.Rect(spire.x - 5, spire.y - 28, 10, 20)
        self.assertFalse(spire.hits_rect(victim))
        config.campaign_time_ms = now + spire.warning_ms + 135
        self.assertTrue(spire.hits_rect(victim))
        snapshot = json.loads(json.dumps(game.snapshot()))
        view = Presentation(pygame.Surface(tuple(snapshot['world_size'])))
        view.apply(snapshot, 1)
        self.assertEqual(view.view.boss.current_skill, 'trench_spires')
        self.assertEqual(view.view.enemy_projectiles[0].kind, 'ice')
        restored = view.view.boss_projectiles[0]
        self.assertIsInstance(restored, TrenchSpire)
        self.assertEqual(restored.height, spire.height)
        canvas = pygame.Surface((960, 720), pygame.SRCALPHA)
        restored.draw(canvas)
        view.view.boss.draw(canvas)
        self.assertTrue(canvas.get_bounding_rect())
