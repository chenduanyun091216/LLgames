import asyncio
import os
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game
from game_core.main import main
from online.client.integrated import LAN


class KeyboardInputTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((960, 720))
        config.update_mobile_view((960, 720))
        self.addCleanup(pygame.quit)
        self.addCleanup(setattr, config, 'campaign_time_ms', config.campaign_time_ms)
        config.campaign_time_ms = 10000

    def test_native_startup_disables_text_input_before_game_receives_keyboard(self):
        class StartupChecked(Exception):
            pass

        with patch('pygame.key.stop_text_input') as stop, \
                patch('game_core.sounds.start_music'), \
                patch('game_core.game.Game') as create_game:
            def check(**kwargs):
                self.assertTrue(kwargs['desktop_controls'])
                stop.assert_called_once_with()
                raise StartupChecked
            create_game.side_effect = check
            with self.assertRaises(StartupChecked):
                asyncio.run(main())

    def test_wasd_moves_and_number_keys_switch_all_owned_characters(self):
        game = Game(desktop_controls=True)
        game._begin_infinite_run()
        for key, dx, dy in ((pygame.K_w, 0, -1), (pygame.K_a, -1, 0),
                            (pygame.K_s, 0, 1), (pygame.K_d, 1, 0)):
            with self.subTest(key=key):
                game.player.x, game.player.y = 480, 250
                keys = defaultdict(bool, {key: True})
                with patch('pygame.key.get_pressed', return_value=keys):
                    game.update()
                self.assertEqual((game.player.x, game.player.y), (480 + 5.2 * dx, 250 + 5.2 * dy))
        for key, character in zip((pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4),
                                   ('ice', 'water', 'fire', 'radiation')):
            with self.subTest(character=character):
                game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=key, mod=0)])
                self.assertEqual(game.player.character, character)

    def test_room_entry_enables_text_input_only_while_editing(self):
        transport = SimpleNamespace(begin=Mock(), reset=Mock())
        lan = LAN(transport)
        with patch('pygame.key.start_text_input') as start, patch('pygame.key.stop_text_input') as stop:
            lan.join_form()
            start.assert_called_once_with()
            lan.start_room('join', '0123')
            stop.assert_called_once_with()
            transport.begin.assert_called_once_with('join', '0123')
            stop.reset_mock()
            lan.join_form()
            lan.home()
            stop.assert_called_once_with()
