import os
import unittest
from unittest.mock import Mock, PropertyMock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import asset_loader, config
from game_core.game import Game, GameState
from game_core.main import main


class FullscreenTests(unittest.IsolatedAsyncioTestCase):
    def test_prepared_panorama_and_foreground_regions_keep_view_offset(self):
        from pygame._sdl2 import Renderer, Window
        from game_core.render import RenderSurface
        from pc.presenter import WindowsPresenter

        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        window = Window('Presenter test', size=(320, 240), hidden=True)
        renderer = Renderer(window, accelerated=0)
        presenter = WindowsPresenter(window, renderer, target_textures=True)
        panorama = pygame.Surface((160, 232))
        panorama.fill((10, 70, 170))
        background = panorama.subsurface((0, 70, 160, 116))
        background.fill((20, 80, 160))
        with patch('pc.presenter.PANORAMA_UPLOAD_BYTES', 160 * 32 * 4):
            for _ in range(8):
                presenter.prepare_background(panorama)
        prepared = presenter.prepared_background
        source = pygame.Rect(0, 4, 160, 116)
        destination = pygame.Rect(0, 4, 320, 232)
        pixels = pygame.Surface((160, 124), pygame.SRCALPHA)
        foreground = RenderSurface(pixels, source.size, source.size, source.topleft,
                                   track_damage=True, desktop_ui=True)

        foreground.mark(pixels.fill('red', (54, 51, 8, 8)))
        self.assertTrue(presenter.draw_layers(background, foreground, source, destination))
        self.assertIs(presenter.background, prepared)
        self.assertEqual(renderer.to_surface().get_at((114, 104))[:3], (255, 0, 0))

        foreground.mark(pixels.fill('green', (120, 84, 7, 9)))
        self.assertTrue(presenter.draw_layers(background, foreground, source, destination))
        composed = renderer.to_surface()
        self.assertEqual(composed.get_at((114, 104))[:3], (20, 80, 160))
        self.assertEqual(composed.get_at((244, 170))[:3], (0, 255, 0))
        self.assertFalse(pixels.get_bounding_rect())

    async def test_accelerated_presenter_keeps_render_sizes_and_physical_clicks(self):
        presenter = Mock()
        presenter.window.size = (3840, 2160)
        presenter.draw_layers.return_value = False
        frames = []
        game = None

        def open_presenter(flags):
            pygame.display.set_mode((1, 1), flags)
            return presenter

        def make_game(**kwargs):
            nonlocal game
            game = Game(**kwargs)
            game.state = GameState.PAUSED
            game._last_touch_event = -120
            game.draw = Mock()
            return game

        def events():
            if len(frames) == 5:
                return [pygame.event.Event(pygame.QUIT)]
            if len(frames) in (1, 3):
                button = game._pause_quality_rects()[len(frames) == 1]
                pos = tuple(coordinate * 4 for coordinate in button.center)
                return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)]
            if len(frames) == 2:
                return [pygame.event.Event(pygame.RENDER_DEVICE_RESET)]
            return []

        def present(surface, source, destination, *, layers_drawn):
            self.assertEqual(config.VIEW_SCALE, 4)
            self.assertEqual(source.size, surface.get_size())
            self.assertEqual(destination, pygame.Rect(0, 0, 3840, 2160))
            frames.append(source.size)

        presenter.present.side_effect = present
        self.addCleanup(pygame.quit)
        try:
            with patch('pygame.event.get', side_effect=events), \
                    patch('pygame.display.flip') as flip, \
                    patch('game_core.game.Game', side_effect=make_game), \
                    patch.object(Game, '_load_bg'), patch('game_core.background.background_art', return_value=None), \
                    patch('game_core.sounds.start_music'), patch('game_core.sounds.advance_music'), \
                    patch('game_core.sounds.make_sound'):
                await main(open_desktop_presenter=open_presenter)
            self.assertEqual(frames, [(2560, 1440), (2560, 1440), (3840, 2160), (3840, 2160), (2560, 1440)])
            presenter.reset_textures.assert_called_once_with()
            flip.assert_not_called()
        finally:
            asset_loader.pc_4k_assets = False
            config.campaign_time_ms = None

    async def test_native_pause_switch_changes_4k_assets_at_window_resolution(self):
        native = Mock()
        native.maximize.side_effect = lambda: pygame.display.set_mode((2560, 1440), pygame.RESIZABLE)
        frames = []
        game = None

        def make_game(**kwargs):
            nonlocal game
            game = Game(**kwargs)
            game.state = GameState.PAUSED
            game._last_touch_event = -120
            game.update = Mock()
            return game

        def events():
            index = len(frames)
            if index == 5:
                return [pygame.event.Event(pygame.QUIT)]
            if index in (1, 3):
                button = game._pause_quality_rects()[index == 1]
                x, y = button.center
                pos = (round(x * config.VIEW_SCALE), round(y * config.VIEW_SCALE))
                return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)]
            return []

        def flip():
            frames.append((config.VIEW_SIZE, asset_loader.pc_4k_assets))
            self.assertEqual(pygame.display.get_surface().get_size(), (2560, 1440))
            self.assertEqual(game.state, GameState.PAUSED)

        try:
            with patch('pygame._sdl2.Window', Mock(from_display_module=Mock(return_value=native))), \
                    patch('pygame.event.get', side_effect=events), \
                    patch('pygame.display.flip', side_effect=flip), \
                    patch('game_core.game.Game', side_effect=make_game), \
                    patch('game_core.background.background_art', return_value=None), \
                    patch('game_core.sounds.start_music'), patch('game_core.sounds.advance_music'), \
                    patch('game_core.sounds.make_sound'):
                await main()
            self.assertEqual(frames, [((2560, 1440), False), ((2560, 1440), False),
                                      ((2560, 1440), True), ((2560, 1440), True),
                                      ((2560, 1440), False)])
        finally:
            asset_loader.pc_4k_assets = False
            config.campaign_time_ms = None
            pygame.quit()

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
