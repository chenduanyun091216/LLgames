import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game, GameState
from run_pc import main


class DesktopGameTests(unittest.TestCase):
    def test_keyboard_moves_and_fires_in_campaign_and_boss_fight(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((960, 540))
        config.update_mobile_view((960, 540))
        game = Game(desktop_controls=True)
        game._start_game('medium')
        for boss_fight in (False, True):
            with self.subTest(boss_fight=boss_fight):
                if boss_fight:
                    game._start_level(6)
                    self.assertEqual(game.state, GameState.BOSS_FIGHT)
                now = config.game_ticks() + 1000
                update = game._update_boss_fight if boss_fight else game._update_playing
                x, y = game.player.x, game.player.y
                with patch('pygame.key.get_pressed', return_value={pygame.K_w: True, pygame.K_a: True}), \
                        patch.object(game, '_shoot') as shoot:
                    update(now)
                    shoot.assert_not_called()
                self.assertLess(game.player.x, x)
                self.assertLess(game.player.y, y)
                x, y = game.player.x, game.player.y
                with patch('pygame.key.get_pressed', return_value={
                        pygame.K_j: True, pygame.K_s: True, pygame.K_d: True}), \
                        patch.object(game, '_shoot') as shoot:
                    update(now)
                    shoot.assert_called_once_with(now, game.player)
                self.assertGreater(game.player.x, x)
                self.assertGreater(game.player.y, y)

        game.player.character = 'radiation'
        game.handle_events([
            pygame.event.Event(pygame.KEYDOWN, key=key, mod=0)
            for key in (pygame.K_k, pygame.K_l, pygame.K_r)
        ])
        self.assertTrue(game.lightnings)
        self.assertTrue(game.magnetic_storms)
        self.assertTrue(game.dart_shields)

    def test_desktop_entry_starts_web_campaign_with_one_player(self):
        frames = []
        draw = Game.draw

        def record_frame(game, *args, **kwargs):
            frames.append((game.state, len(game.players), game.desktop_controls))
            return draw(game, *args, **kwargs)

        events = [
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0)],
            [pygame.event.Event(pygame.QUIT)],
        ]
        with patch.object(config, 'campaign_time_ms', None), \
                patch.object(Game, 'draw', record_frame), \
                patch('pygame.event.get', side_effect=events):
            main()

        self.assertEqual(frames[0], (GameState.PLAYING, 1, True))
