import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game, GameState, LEVEL_FADE_MS
from game_core.opening import CUTS, FADE_MS, Opening, opening_viewport


class OpeningTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((960, 720))
        config.update_mobile_view((960, 720))

    def test_campaign_opening_finishes_before_starting_level_one(self):
        game = Game(desktop_controls=True)
        game._select_campaign('easy')
        with patch.object(game, '_start_level', wraps=game._start_level) as start_level:
            game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0)])
            self.assertEqual(game.state, GameState.OPENING)
            start_level.assert_not_called()
            for elapsed in (*CUTS[:-1], CUTS[-1] - 1):
                with patch.object(game.opening, 'elapsed', return_value=elapsed):
                    game.update()
                    game.draw_opening(pygame.display.get_surface())
                    self.assertEqual(game.state, GameState.OPENING)
            with patch.object(game.opening, 'elapsed', return_value=CUTS[-1]):
                game.update()
            start_level.assert_called_once_with(1)
        self.assertEqual(game.state, GameState.PLAYING)
        self.assertIsNone(game.opening)
        self.assertGreater(game.level_fade_in_until, game._level_title_ticks())
        self.assertLessEqual(game.level_fade_in_until - game._level_title_ticks(), LEVEL_FADE_MS)

    def test_touch_skips_opening_and_direct_level_selection_bypasses_it(self):
        game = Game(web=True, mobile_web=True)
        game._select_campaign('easy')
        game._start_selected_campaign()
        self.assertEqual(game.state, GameState.OPENING)
        game.handle_events([pygame.event.Event(pygame.FINGERDOWN, finger_id=1, x=0.5, y=0.5)])
        self.assertEqual((game.state, game.current_level), (GameState.PLAYING, 1))
        self.assertIsNone(game.opening)
        game._select_campaign('easy')
        game.selected_level = 2
        game._start_selected_campaign()
        self.assertEqual((game.state, game.current_level), (GameState.PLAYING, 2))

    def test_viewport_keeps_sixteen_by_nine_centered_on_wide_and_tall_screens(self):
        for size, expected in (((1920, 1080), (0, 0, 1920, 1080)),
                               ((1920, 720), (320, 0, 1280, 720)),
                               ((960, 720), (0, 90, 960, 540)),
                               ((720, 1280), (0, 438, 720, 405))):
            with self.subTest(size=size):
                self.assertEqual(opening_viewport(size), pygame.Rect(expected))

    def test_first_scene_fades_in_from_black(self):
        opening = Opening()
        self.addCleanup(opening.close)
        target = pygame.Surface((320, 180))
        frame = target.copy()
        frame.fill((200, 120, 80))
        with patch.object(opening, '_frame', return_value=frame):
            for elapsed in (0, FADE_MS // 2, FADE_MS):
                with patch.object(opening, 'elapsed', return_value=elapsed):
                    opening.draw(target)
                    self.assertEqual(target.get_at((160, 90)).r, 200 * elapsed // FADE_MS)

    def test_opening_holds_black_for_one_second_before_image_and_audio(self):
        with patch('pygame.time.get_ticks', return_value=500):
            opening = Opening()
        self.addCleanup(opening.close)
        self.assertEqual(opening.started_at, 1500)
        sound = opening.pending_sound
        self.assertIsNotNone(sound)
        self.assertAlmostEqual(sound.get_volume(), .76, delta=.01)
        target = pygame.Surface((320, 180))
        frame = target.copy()
        frame.fill((0, 0, 200))
        with patch.object(opening, '_frame', return_value=frame):
            for elapsed in (-1000, -1):
                target.fill((100, 0, 0))
                with patch.object(opening, 'elapsed', return_value=elapsed):
                    opening.draw(target)
                self.assertEqual(target.get_at((160, 90))[:3], (0, 0, 0))
                self.assertIs(opening.pending_sound, sound)
                self.assertIsNone(opening.channel)
            with patch.object(opening, 'elapsed', return_value=0):
                opening.draw(target)
            self.assertEqual(target.get_at((160, 90))[:3], (0, 0, 0))
            self.assertIsNone(opening.pending_sound)
            self.assertIsNotNone(opening.channel)
            with patch.object(opening, 'elapsed', return_value=FADE_MS // 2):
                opening.draw(target)
            self.assertEqual(target.get_at((160, 90))[:3], (0, 0, 100))
            with patch.object(opening, 'elapsed', return_value=CUTS[-1] - 1):
                opening.draw(target)
            self.assertEqual(target.get_at((160, 90))[:3], (0, 0, 0))

    def test_first_three_scenes_keep_the_fisherman_still(self):
        opening = Opening()
        self.addCleanup(opening.close)
        size = (960, 540)
        with patch.object(opening, '_draw_particles'):
            for index in range(4):
                duration = CUTS[index + 1] - CUTS[index]
                start = pygame.image.tobytes(opening._frame(index, 0, size), 'RGB')
                end = pygame.image.tobytes(opening._frame(index, duration - 1, size), 'RGB')
                with self.subTest(scene=index + 1):
                    self.assertEqual(start == end, index < 3)
