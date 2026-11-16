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
from game_core.main import main


class BrowserLoopTests(unittest.IsolatedAsyncioTestCase):
    async def run_loop(self, *, lan=False, hz=60, jitter=0):
        clock = [0.0]
        callbacks = [0]
        draws, updates = [], []
        browser = SimpleNamespace(innerWidth=400, innerHeight=240, ttgamesRenderDensity=1.75,
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
            def frame(self, *args):
                if callbacks[0] >= hz * 2:
                    return False
                draws.append(clock[0])
                return True
        async def refresh(_):
            callbacks[0] += 1
            clock[0] = callbacks[0] / hz + (jitter if callbacks[0] % 2 else 0)
        def events():
            return [pygame.event.Event(pygame.QUIT)] if callbacks[0] >= hz * 2 and not lan else []
        with patch('game_core.main.platform.window', browser, create=True), \
                patch('game_core.main.perf_counter', side_effect=lambda: clock[0]), \
                patch('game_core.main.asyncio.sleep', side_effect=refresh), \
                patch('game_core.game.Game', side_effect=make_game), \
                patch('online.client.integrated.LAN', Room), \
                patch('pygame.event.get', side_effect=events), \
                patch('game_core.sounds.start_music'), patch('game_core.sounds.advance_music'), \
                patch('game_core.sounds.make_sound'), patch('game_core.main.asset_loader.image_asset'):
            await main(transport=object() if lan else None)
        config.campaign_time_ms = None
        pygame.quit()
        return draws, updates

    async def test_single_and_lan_do_not_drop_jittered_60hz_callbacks(self):
        for lan in (False, True):
            with self.subTest(lan=lan):
                draws, _ = await self.run_loop(lan=lan, jitter=.012)
                self.assertEqual(len(draws), 120)

    async def test_high_refresh_display_keeps_simulation_at_60hz(self):
        draws, updates = await self.run_loop(hz=120)
        self.assertEqual(len(draws), 240)
        self.assertAlmostEqual(len(updates), 120, delta=1)
