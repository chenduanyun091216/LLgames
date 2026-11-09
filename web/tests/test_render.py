import unittest
from unittest.mock import patch

import pygame

from game_core.render import RenderSurface, trim_transparent
from game_core.visuals import draw_water_drift


class RenderTests(unittest.TestCase):
    def test_cached_trim_preserves_centered_art_and_limits_damage(self):
        art = pygame.Surface((80, 80), pygame.SRCALPHA)
        art.fill((80, 170, 200, 120), (31, 35, 18, 11))
        original = pygame.Surface((120, 120), pygame.SRCALPHA)
        original.blit(art, art.get_rect(center=(60, 60)))
        cropped, dx, dy = trim_transparent(art)
        actual = pygame.Surface(original.get_size(), pygame.SRCALPHA)
        actual.blit(cropped, (60 + dx, 60 + dy))
        self.assertEqual(cropped.get_size(), (18, 11))
        self.assertIs(cropped, trim_transparent(art)[0])
        self.assertEqual(pygame.image.tobytes(actual, 'RGBA'), pygame.image.tobytes(original, 'RGBA'))

    def test_restore_background_also_clears_margins(self):
        size = (100, 101)
        target = pygame.Surface(size)
        foreground = pygame.Surface(size, pygame.SRCALPHA)
        background = pygame.Surface((100, 99))
        background.fill('green')
        expected = target.copy()
        expected.fill('blue')
        expected.blit(background, (0, 1))
        target.blit(expected, (0, 0))
        rendered = RenderSurface(foreground, (100, 99), (100, 99), (0, 1), track_damage=True)
        rendered.mark(foreground.fill('red', (44, 0, 10, 101)))
        rendered.composite_onto(target)
        rendered.restore_background(target, background, 'blue')
        self.assertEqual(pygame.image.tobytes(target, 'RGB'), pygame.image.tobytes(expected, 'RGB'))

    def test_steady_bubbles_reuse_scaled_art(self):
        pixels = pygame.Surface((1688, 780), pygame.SRCALPHA)
        rendered = RenderSurface(pixels, (960, 444), pixels.get_size(), (0, 0))
        draw_water_drift(rendered, 0)
        expected = pygame.image.tobytes(pixels, 'RGBA')
        pixels.fill((0, 0, 0, 0))
        with patch('pygame.transform.smoothscale', wraps=pygame.transform.smoothscale) as scale:
            draw_water_drift(rendered, 0)
        scale.assert_not_called()
        self.assertEqual(pygame.image.tobytes(pixels, 'RGBA'), expected)
