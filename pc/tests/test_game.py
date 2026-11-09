import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from pc import config
from pc.game import Game, GameState


class DesktopGameTests(unittest.TestCase):
    def test_difficulty_then_local_coop_with_keyboard(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((960, 720), pygame.RESIZABLE)
        config.update_view(window.get_size())
        self.assertEqual((config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT), (0, 960))
        game = Game()
        game.draw()
        game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0)])
        self.assertEqual(game.state, GameState.MODE_SELECT)
        game.draw()
        game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0)])
        self.assertEqual(len(game.players), 2)
        self.assertEqual(game.state, GameState.PLAYING)
        game.update()
        game.draw()
