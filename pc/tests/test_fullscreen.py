import os
import unittest
from unittest.mock import Mock, PropertyMock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game
from game_core.main import main


class FullscreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_windows_window_stays_transparent_until_the_first_frame_is_presented(self):
        order = Mock()
        native = order.window
        opacity = PropertyMock(side_effect=order.opacity)
        def make_game(**kwargs):
            game = Game(**kwargs)
            game.handle_events = lambda events: not events
            game.update = Mock()
            game.draw = order.draw
            return game

        try:
            with patch('pygame.display.get_driver', return_value='windows'), \
                    patch('pygame.display.set_mode', wraps=pygame.display.set_mode) as set_mode, \
                    patch('pygame._sdl2.Window', Mock(from_display_module=Mock(return_value=native))), \
                    patch.object(type(native), 'opacity', opacity, create=True), \
                    patch('pygame.event.get', side_effect=[[], [pygame.event.Event(pygame.QUIT)]]), \
                    patch('pygame.display.flip', side_effect=order.flip), \
                    patch('game_core.game.Game', side_effect=make_game), \
                    patch('game_core.sounds.start_music'), patch('game_core.sounds.advance_music'), \
                    patch('game_core.sounds.make_sound'), patch('game_core.main.asset_loader.image_asset'):
                await main()
            set_mode.assert_called_once_with((960, 720), pygame.RESIZABLE | pygame.HIDDEN)
            self.assertEqual([call[0] for call in order.mock_calls],
                             ['opacity', 'window.show', 'window.maximize', 'draw', 'flip', 'opacity'])
            self.assertEqual([call.args for call in opacity.call_args_list], [(0,), (1,)])
        finally:
            config.campaign_time_ms = None
            pygame.quit()

    async def test_f11_toggles_before_single_player_or_lan_event_dispatch(self):
        for lan in (False, True):
            with self.subTest(lan=lan):
                original_game = Game
                native = Mock()
                native.set_fullscreen.side_effect = lambda **kwargs: pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
                native.set_windowed.side_effect = lambda: pygame.display.set_mode((960, 720), pygame.RESIZABLE)
                frames, received = [], []
                batches = [
                    [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11, mod=0)],
                    [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11, mod=0, repeat=True)],
                    [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11, mod=0)],
                    [pygame.event.Event(pygame.QUIT)],
                ]

                def events():
                    return batches.pop(0)

                def record(events):
                    received.extend(events)
                    frames.append(pygame.display.get_surface().get_size())
                    return not any(event.type == pygame.QUIT for event in events)

                def make_game(**kwargs):
                    game = original_game(**kwargs)
                    game.handle_events = record
                    game.draw = lambda *args, **kwargs: None
                    game.update = lambda: None
                    game.resize_view = Mock()
                    return game

                class Room:
                    page = 'room'
                    drawn_to_window = True
                    ui_state = (False, False)
                    def __init__(self, transport): pass
                    def home(self): pass
                    def frame(self, game, events, *args): return record(events)

                try:
                    with patch('pygame._sdl2.Window', Mock(from_display_module=Mock(return_value=native))), \
                            patch('pygame.event.get', side_effect=events), \
                            patch('game_core.game.Game', side_effect=make_game), \
                            patch('online.client.integrated.LAN', Room), \
                            patch('game_core.sounds.start_music'), patch('game_core.sounds.advance_music'), \
                            patch('game_core.sounds.make_sound'), patch('game_core.main.asset_loader.image_asset'):
                        await main(transport=object() if lan else None)
                    native.set_fullscreen.assert_called_once_with(desktop=True)
                    native.set_windowed.assert_called_once_with()
                    self.assertEqual(frames[:3], [(1920, 1080), (1920, 1080), (960, 720)])
                    self.assertFalse(any(event.type == pygame.KEYDOWN and event.key == pygame.K_F11 for event in received))
                finally:
                    config.campaign_time_ms = None
                    pygame.quit()
