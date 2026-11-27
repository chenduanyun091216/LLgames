import unittest
from unittest.mock import patch

import pygame

from game_core import config
from game_core.game import Game
from game_core.render import RenderSurface, trim_transparent
from game_core.visuals import _glow, draw_glow, draw_water_drift


class RenderTests(unittest.TestCase):
    def test_scroll_reuses_filtered_rows_across_nearby_frames(self):
        from game_core import background
        panorama = pygame.Surface((8, 600))
        for y in range(600):
            panorama.fill((y % 251, 0, 0), (0, y, 8, 1))
        target = pygame.Surface((8, 256))
        with patch.object(background, '_background_panorama', return_value=panorama):
            for y in (33.5, 32.5):
                background.draw_scrolling_background_art(target, (0, 0), 1, target.get_size(), 1 - y / 344)
                for row in (0, 31, 62, 63, 64, 255):
                    self.assertAlmostEqual(target.get_at((0, row)).r, (int(y) + row) % 251 + .5, delta=1)
                if y == 33.5:
                    misses = background._filtered_rows.cache_info().misses
            self.assertEqual(background._filtered_rows.cache_info().misses, misses)

    def test_fractional_background_scroll_blends_adjacent_rows(self):
        from game_core.background import draw_scrolling_background_art

        panorama = pygame.Surface((2, 4))
        for y, red in enumerate((0, 100, 200, 0)):
            panorama.fill((red, 0, 0), (0, y, 2, 1))
        target = pygame.Surface((4, 4))
        with patch('game_core.background._background_panorama', return_value=panorama):
            for progress, expected in ((1, 0), (.875, 25), (.75, 50), (.625, 75), (.5, 100),
                                       (.125, 175), (.01, 200), (0, 200)):
                self.assertTrue(draw_scrolling_background_art(target, (1, 1), 1, (2, 2), progress))
                self.assertAlmostEqual(target.get_at((1, 1)).r, expected, delta=1)
                self.assertEqual(target.get_at((0, 1)).r, 0)
        with patch('game_core.background._background_panorama', return_value=None):
            self.assertFalse(draw_scrolling_background_art(target, (1, 1), 1, (2, 2), .75))

    def test_web_scrim_keeps_the_same_pixels_at_fractional_scale(self):
        game = Game.__new__(Game)
        game.web = True
        pixels = pygame.Surface((130, 80), pygame.SRCALPHA)
        pixels.fill((45, 60, 75, 155))
        expected = pixels.copy()
        logical = (80, 40)
        view = (124, 62)
        offset = (3, 9)
        scrim = pygame.Surface(logical, pygame.SRCALPHA)
        scrim.fill((2, 16, 25))
        scrim.set_alpha(100)
        RenderSurface(expected, logical, view, offset).blit(scrim, (0, 0))
        with patch.object(config, 'SCR', RenderSurface(pixels, logical, view, offset)):
            game._draw_scrim(100)
        self.assertEqual(pygame.image.tobytes(pixels, 'RGBA'), pygame.image.tobytes(expected, 'RGBA'))

    def test_cached_glow_preserves_changing_opacity(self):
        pixels = pygame.Surface((140, 140), pygame.SRCALPHA)
        expected = pixels.copy()
        logical = (80, 80)
        center = (40, 38)
        color = (210, 124, 61)
        render = RenderSurface(pixels, logical, pixels.get_size(), (0, 0))
        baseline = RenderSurface(expected, logical, expected.get_size(), (0, 0))
        art = _glow(21, color).copy()
        draw_glow(render, center, 21, color)
        for opacity in (64, 190, 0, 255):
            pixels.fill((0, 0, 0, 0))
            expected.fill((0, 0, 0, 0))
            art.set_alpha(opacity)
            baseline.blit(art, art.get_rect(center=center))
            with patch('pygame.transform.smoothscale', wraps=pygame.transform.smoothscale) as scale:
                draw_glow(render, center, 21, color, opacity)
            scale.assert_not_called()
            self.assertEqual(pygame.image.tobytes(pixels, 'RGBA'), pygame.image.tobytes(expected, 'RGBA'))

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

    def test_offset_tile_composite_matches_full_world_blit(self):
        target = pygame.Surface((260, 200))
        target.fill((27, 85, 140))
        expected = target.copy()
        foreground = pygame.Surface((200, 140), pygame.SRCALPHA)
        rendered = RenderSurface(foreground, (200, 140), (200, 140), (0, 0), track_damage=True)
        rendered.mark(pygame.draw.circle(foreground, (230, 105, 12, 130), (57, 64), 22))
        rendered.mark(pygame.draw.rect(foreground, (0, 40, 220, 180), (182, 110, 18, 30)))
        expected.blit(foreground, (19, 23))
        rendered.composite_onto(target, offset=(19, 23), blit_flags=0)
        self.assertEqual(pygame.image.tobytes(target, 'RGB'), pygame.image.tobytes(expected, 'RGB'))
        self.assertFalse(foreground.get_bounding_rect())
