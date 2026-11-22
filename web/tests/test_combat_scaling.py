import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import unittest
from unittest.mock import patch

import pygame

from game_core import config
from game_core import entities as E
from game_core.game import Game
from game_core.render import Draw, RenderSurface, scaled_surface, effect_layer, blit_effect


class CombatScalingTests(unittest.TestCase):
    def game(self, *, web=False, online=False, percent=100):
        game = Game.__new__(Game)
        game.web = web
        game.mobile_web = web
        game.online_view = online
        game.actor_scale_percent = percent
        return game

    def test_scaling_preserves_anchor_and_tracks_damage(self):
        pixels = pygame.Surface((400, 300), pygame.SRCALPHA)
        target = RenderSurface(pixels, (200, 150), (400, 300), (0, 0), track_damage=True)
        scaled = scaled_surface(target, (100, 75), 1.5)
        self.assertEqual(scaled.point((100, 75)), target.point((100, 75)))
        Draw.circle(scaled, 'white', (100, 75), 10)
        self.assertEqual(pixels.get_bounding_rect().size, (60, 60))
        self.assertIs(scaled._dirty_rows, target._dirty_rows)
        destination = pygame.Surface((400, 300), pygame.SRCALPHA)
        target.composite_onto(destination)
        self.assertEqual(destination.get_bounding_rect().size, (60, 60))

    def test_effect_layers_receive_the_same_scale(self):
        pixels = pygame.Surface((200, 200), pygame.SRCALPHA)
        target = scaled_surface(pixels, (100, 100), 1.5)
        layer = effect_layer(target, (20, 20))
        Draw.circle(layer, 'white', (10, 10), 10)
        blit_effect(target, layer, (90, 90))
        self.assertEqual(pixels.get_bounding_rect(), pygame.Rect(85, 85, 30, 30))

    def test_pc_rendering_remains_unchanged_at_every_setting(self):
        pixels = pygame.Surface((200, 200), pygame.SRCALPHA)
        for percent in (50, 100, 150):
            game = self.game(percent=percent)
            with patch.object(config, 'SCR', pixels):
                self.assertIs(game._combat_surface((100, 100)), pixels)

    def test_web_and_online_scale_both_actors_and_projectiles(self):
        pixels = pygame.Surface((400, 300), pygame.SRCALPHA)
        for web, online in ((True, False), (False, True)):
            for percent in (50, 100, 150):
                game = self.game(web=web, online=online, percent=percent)
                with patch.object(config, 'SCR', pixels):
                    for actor in (False, True):
                        target = game._combat_surface((100, 100), actor=actor)
                        pixels.fill((0, 0, 0, 0))
                        Draw.circle(target, 'white', (100, 100), 20)
                        self.assertEqual(pixels.get_bounding_rect().size, (40 * percent // 100,) * 2)

    def test_online_compensation_matches_desktop_pixels_without_moving_centers(self):
        pixels = pygame.Surface((1440, 1080), pygame.SRCALPHA)
        target = RenderSurface(pixels, (960, 720), pixels.get_size(), (0, 0))
        game = self.game(online=True)
        game.presentation_scale = 2 / 1.5
        with patch.object(config, 'SCR', target):
            scaled = game._combat_surface((480, 360))
            self.assertEqual(scaled.point((480, 360)), target.point((480, 360)))
            self.assertEqual(scaled.length(20), 40)

    def test_zoom_does_not_change_player_motion_limits(self):
        player = type('Player', (), {'character': None})()
        for web, online in ((True, False), (False, True)):
            game = self.game(web=web, online=online)
            before = game._player_visual_scale(player)
            game.actor_scale_percent = 150
            self.assertEqual(game._player_visual_scale(player), before)

    def test_projectile_pixels_scale_without_changing_physics(self):
        pixels = pygame.Surface((500, 500), pygame.SRCALPHA)
        game = self.game(web=True)
        shot = E.BossProjectile(250, 250, 20, 3)
        original = shot.rect(), shot.x, shot.y, shot.speed, shot.r, shot.damage
        sizes = []
        with patch.object(config, 'SCR', pixels), patch.object(config, 'game_ticks', return_value=100):
            for percent in (50, 100, 150):
                game.actor_scale_percent = percent
                pixels.fill((0, 0, 0, 0))
                game._draw_combat_entity(shot)
                sizes.append(pixels.get_bounding_rect().width)
                self.assertEqual((shot.rect(), shot.x, shot.y, shot.speed, shot.r, shot.damage), original)
        self.assertLess(sizes[0], sizes[1])
        self.assertLess(sizes[1], sizes[2])

    def test_chain_lightning_scales_width_without_moving_targets(self):
        game = self.game(web=True, percent=150)
        target = type('Target', (), {'x': 150, 'y': 100, 'h': 20})()
        bolt = E.Lightning(100, 200, [target], 1)
        with patch.object(config, 'game_ticks', return_value=bolt.spawn_time + 100), \
                patch('game_core.entities.draw_electric_arc') as draw:
            game._draw_combat_entity(bolt)
        self.assertEqual(draw.call_args.args[1:3], ((100, 200), (150, 110)))
        self.assertEqual(draw.call_args.kwargs['visual_scale'], 1.5)


class IntegratedCombatScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_complete_room_matches_local_pc_scale_and_redraws_after_zoom(self):
        from types import SimpleNamespace
        from online.adapters.core_adapter import OnlineGame
        from online.client.integrated import LAN

        for room_orientation in ('landscape', 'portrait'):
            host = OnlineGame(orientation=room_orientation)
            host.level_title_until = host.level_fade_in_until = 0
            state = dict(host.snapshot(), match_id='sizes', mode='campaign',
                         paused=True, pause_reason='manual_pause')
            for web in (False, True):
                for size in ((1920, 1080), (960, 720), (390, 844)):
                    with self.subTest(room=room_orientation, web=web, size=size):
                        window = pygame.display.set_mode(size)
                        config.update_mobile_view(size)
                        game = Game(web=web, mobile_web=web, desktop_controls=not web)
                        local_scale = config.VIEW_SCALE
                        local_entity = (config.MOBILE_LANDSCAPE_ENTITY_SCALE if config.MOBILE_LANDSCAPE_VIEW
                                        else config.MOBILE_PORTRAIT_ENTITY_SCALE)
                        room_entity = (config.MOBILE_LANDSCAPE_ENTITY_SCALE if room_orientation == 'landscape'
                                       else config.MOBILE_PORTRAIT_ENTITY_SCALE)
                        client = LAN(SimpleNamespace(slot=1, error='', send=lambda message: None))
                        client.battle(game, state, [], False, None, window)
                        for percent in (50, 100, 150):
                            client.presentation.view.actor_scale_percent = percent
                            with patch.object(E.Player, 'draw', autospec=True) as draw:
                                client.battle(game, state, [], False, None, window)
                            self.assertTrue(draw.called)
                            surface = draw.call_args.args[1]
                            self.assertAlmostEqual(surface.scale, local_scale * local_entity / room_entity * percent / 100)
                            self.assertEqual(draw.call_args.kwargs['visual_scale'], config.ACTOR_BASE_SCALE)
                        self.assertEqual(client.presentation.surface.get_size(), tuple(state['world_size']))


if __name__ == '__main__':
    unittest.main()
