"""Exercise both branches of the actual browser loop with jittered refresh callbacks."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pygame
from game_core import config
from game_core.game import Game
from game_core.main import BROWSER_QUALITIES, _browser_size, main


class BrowserLoopTests(unittest.IsolatedAsyncioTestCase):
    async def run_loop(self, *, lan=False, hz=60, jitter=0, switch_quality=False,
                       ipad=False, inspect_frame=None, set_scene_size=None):
        clock = [0.0]
        callbacks = [0]
        draws, updates = [], []
        browser = SimpleNamespace(innerWidth=400, innerHeight=240, ttgamesRenderDensity=1.75, ttgamesIPad=ipad,
                                  ttgamesSetSceneSize=set_scene_size if ipad else None,
                                  matchMedia=lambda _: SimpleNamespace(matches=True),
                                  document=SimpleNamespace(hidden=False), location=SimpleNamespace(search=''))
        original_game = Game
        def make_game(**kwargs):
            game = original_game(**kwargs)
            game._start_game('easy')
            game.level_title_until = game.level_fade_in_until = 0
            game.draw = lambda *a, **k: draws.append(clock[0])
            game.update = lambda: updates.append(clock[0])
            return game
        class Room:
            page = 'room'
            drawn_to_window = True
            ui_state = (True, False)
            def __init__(self, transport): pass
            def home(self): pass
            def record_rendered_frame(self, *args, **kwargs): pass
            def frame(self, *args):
                if callbacks[0] >= hz * 2:
                    return False
                draws.append(clock[0])
                return True
        async def refresh(_):
            if inspect_frame:
                inspect_frame(browser, callbacks[0])
            callbacks[0] += 1
            clock[0] = callbacks[0] / hz + (jitter if callbacks[0] % 2 else 0)
            if switch_quality:
                if callbacks[0] == 30:
                    browser.ttgamesRenderDensity = 1.5
                elif callbacks[0] == 60:
                    browser.ttgamesRenderDensity = 2
        def events():
            return [pygame.event.Event(pygame.QUIT)] if callbacks[0] >= hz * 2 and not lan else []
        with patch('game_core.main.platform.window', browser, create=True), \
                patch.object(config, 'WEB_SAFE_INSETS', (0, 0, 0, 0)), \
                patch('game_core.main.perf_counter', side_effect=lambda: clock[0]), \
                patch('game_core.main.asyncio.sleep', side_effect=refresh), \
                patch('game_core.game.Game', side_effect=make_game), \
                patch('online.client.integrated.LAN', Room), \
                patch('pygame.event.get', side_effect=events), \
                patch('game_core.sounds.start_music'), patch('game_core.sounds.advance_music'), \
                patch('game_core.sounds.make_sound'), patch('game_core.main.asset_loader.image_asset', return_value=None):
            await main(transport=object() if lan else None)
        config.campaign_time_ms = None
        pygame.quit()
        return draws, updates

    async def test_single_and_lan_do_not_drop_jittered_60hz_callbacks(self):
        for lan in (False, True):
            with self.subTest(lan=lan):
                draws, _ = await self.run_loop(lan=lan, jitter=.012, switch_quality=True)
                self.assertEqual(len(draws), 120)

    async def test_high_refresh_display_keeps_simulation_at_60hz(self):
        draws, updates = await self.run_loop(hz=120)
        self.assertEqual(len(draws), 240)
        self.assertAlmostEqual(len(updates), 120, delta=1)

    async def test_campaign_prepares_next_panorama_during_playing(self):
        with patch('game_core.background.load_panorama', return_value=None) as load:
            await self.run_loop()
        next_level = [call.args for call in load.call_args_list if call.args[0] == 2]
        self.assertEqual(next_level, [(2, _browser_size((400, 240), 1.75), 'images-hd')])

    async def test_ipad_keeps_hd_output_and_touch_mapping_across_quality_changes(self):
        samples = {}
        scene_sizes = []
        def inspect_frame(browser, index):
            screen = pygame.display.get_surface()
            width, height = config.VIEW_SIZE
            if index == 0:
                browser.ttgamesSafeArea = '20,0,10,15'
                screen.fill('magenta', (width, 0, 1, height + 1))
                screen.fill('magenta', (0, height, width + 1, 1))
            elif index == 1:
                self.assertEqual(config.WEB_SAFE_INSETS, (48, 0, 24, 36))
                self.assertEqual(screen.get_at((width, height // 2)), screen.get_at((width - 1, height // 2)))
                self.assertEqual(screen.get_at((width, height)), screen.get_at((width - 1, height - 1)))
            if index in (1, 31, 61, 91):
                output = pygame.display.get_surface().get_size()
                center = config.window_to_game((config.VIEW_SIZE[0] // 2, config.VIEW_SIZE[1] // 2))
                samples[browser.innerWidth, browser.ttgamesRenderDensity] = (
                    output, config.VIEW_SIZE, center)
            if index == 80:
                browser.innerWidth, browser.innerHeight = 240, 400
                browser.ttgamesSafeArea = '0,12,0,18'
            elif index == 91:
                self.assertEqual(config.WEB_SAFE_INSETS, (0, 24, 0, 36))

        with patch.object(pygame.display, 'set_mode', wraps=pygame.display.set_mode) as set_mode:
            await self.run_loop(ipad=True, switch_quality=True, inspect_frame=inspect_frame,
                                set_scene_size=lambda w, h, ow, oh: scene_sizes.append(((w, h), (ow, oh))))
        self.assertEqual(scene_sizes, [
            (_browser_size(v, q), _browser_size(v, 2))
            for v, q in [((400, 240), 1.75), ((400, 240), 1.5), ((400, 240), 2), ((240, 400), 2)]])
        self.assertEqual(set_mode.call_count, 2)  # startup and rotation
        for quality in BROWSER_QUALITIES:
            output, scene, center = samples[400, quality]
            self.assertEqual((output, scene), (_browser_size((400, 240), 2), _browser_size((400, 240), quality)))
            self.assertAlmostEqual(center[0], 480, delta=1)
            self.assertAlmostEqual(center[1], 288, delta=1)
        portrait = _browser_size((240, 400), 2)
        self.assertEqual(samples[240, 2], (portrait, portrait, (240, 400)))
