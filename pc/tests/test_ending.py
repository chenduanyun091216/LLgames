import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game, GameState
from game_core.opening import FADE_MS


class EndingTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        self.window = pygame.display.set_mode((720, 960))
        config.update_mobile_view(self.window.get_size())
        self.game = Game(desktop_controls=True, campaign_ending=True)
        self.game._start_game('medium', len(config.LEVEL_CONFIGS))
        self.game._trigger_boss()

    def test_final_boss_plays_ending_and_draws_real_campaign_results(self):
        game = self.game
        game.campaign_start_level = 1
        game.campaign_started_at = config.game_ticks() - 125000
        game.campaign_enemies_defeated = 193
        game.campaign_bosses_defeated = 10
        game.campaign_deaths = 2
        game.campaign_restarts = 1
        game.player.gold = 274
        game._kill_boss()
        self.assertEqual(game.state, GameState.ENDING)
        ending = game.ending
        self.assertEqual(game.campaign_bosses_defeated, 11)
        with patch.object(game, '_draw_victory', wraps=game._draw_victory) as draw:
            for elapsed in ending.cuts[:-2]:
                with patch.object(ending, 'elapsed', return_value=elapsed + 200):
                    game.draw_ending(self.window)
            draw.assert_not_called()
        with patch.object(ending, 'elapsed', return_value=ending.cuts[-2] + 500):
            with patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as text:
                game.draw_ending(self.window)
        values = {str(call.args[0]) for call in text.call_args_list}
        for value in ('战役通关', '02:05', '193', '11', '2', '1', str(game.player.gold), '9 秒后返回首页'):
            self.assertIn(value, values)
        self.assertEqual(self.window.get_at((360, 0))[:3], (0, 0, 0))
        with patch.object(ending, 'elapsed', return_value=ending.duration):
            game.update()
        self.assertEqual(game.state, GameState.MENU)

    def test_skip_stops_narration_and_keeps_live_results(self):
        game = self.game
        game._kill_boss()
        self.assertEqual(game.state, GameState.ENDING)
        ending = game.ending
        key = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0)
        game.handle_events([key])
        self.assertIsNone(ending.channel)
        self.assertIsNone(ending.pending_sound)
        self.assertGreaterEqual(ending.elapsed(), ending.cuts[-1])
        started_at = ending.started_at
        game.handle_events([key])
        self.assertEqual(ending.started_at, started_at)
        with patch.object(game, '_draw_victory', wraps=game._draw_victory) as draw:
            game.draw_ending(self.window)
            draw.assert_called_once()
        self.assertEqual(game.state, GameState.ENDING)

    def test_battle_fades_to_black_before_ending_image_and_audio(self):
        self.game._kill_boss()
        ending = self.game.ending
        target = pygame.Surface((320, 180))
        target.fill((200, 0, 0))
        frame = target.copy()
        frame.fill((0, 0, 200))
        sound = ending.pending_sound
        self.assertIsNotNone(sound)
        self.assertAlmostEqual(sound.get_volume(), .79, delta=.01)
        with patch.object(ending, '_frame', return_value=frame):
            with patch.object(ending, 'elapsed', return_value=-ending.entry_fade_out_ms // 2):
                ending.draw(target)
                self.assertIs(ending.pending_sound, sound)
                self.assertIsNone(ending.channel)
                self.assertEqual(target.get_at((160, 90))[:3], (100, 0, 0))
            with patch.object(ending, 'elapsed', return_value=0):
                ending.draw(target)
                self.assertIsNone(ending.pending_sound)
                self.assertEqual(target.get_at((160, 90))[:3], (0, 0, 0))
            with patch.object(ending, 'elapsed', return_value=FADE_MS // 2):
                ending.draw(target)
                self.assertEqual(target.get_at((160, 90))[:3], (0, 0, 100))
        ending.close()
