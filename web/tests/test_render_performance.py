"""Pixel-preserving Web rendering regressions."""
from collections import OrderedDict
import unittest
from unittest.mock import patch

import pygame

from game_core import asset_loader
from game_core.render import RenderSurface
from game_core.sprites import _lit_sprite, _resize_sprite, blit_lit_sprite


class WebRenderPerformanceTests(unittest.TestCase):
    def test_scaled_assets_keep_recent_sizes_within_the_pixel_budget(self):
        image = pygame.Surface((2, 2), pygame.SRCALPHA)
        image.fill((20, 130, 220, 170))
        with patch.multiple(asset_loader, _SCALED_CACHE=OrderedDict(), _scaled_cache_bytes=0,
                            SCALE_CACHE_LIMIT=152, _IMAGE_CACHE={'fixture.png': image}), \
                patch.object(asset_loader, '_image_path', return_value='fixture.png'):
            first = asset_loader.image_asset('fixture.png', (3, 3))
            recent = asset_loader.image_asset('fixture.png', (4, 4))
            self.assertIs(asset_loader.image_asset('fixture.png', (3, 3)), first)
            asset_loader.image_asset('fixture.png', (5, 5))
            self.assertIs(asset_loader.image_asset('fixture.png', (3, 3)), first)
            rebuilt = asset_loader.image_asset('fixture.png', (4, 4))
            self.assertIsNot(rebuilt, recent)
            self.assertEqual(pygame.image.tobytes(rebuilt, 'RGBA'), pygame.image.tobytes(recent, 'RGBA'))

    def test_web_sprite_trims_padding_without_changing_pixels(self):
        image = pygame.Surface((100, 100), pygame.SRCALPHA)
        pygame.draw.circle(image, (20, 130, 220, 170), (50, 50), 12)
        surface = pygame.Surface((240, 240), pygame.SRCALPHA)
        expected = surface.copy()
        render = RenderSurface(surface, (120, 120), (240, 240), (0, 0), track_damage=True)
        expected.blit(_lit_sprite(_resize_sprite(image, (200, 200)), (100, 200, 255), 140), (17, 17))
        blit_lit_sprite(render, image, (10, 10), (100, 200, 255))
        self.assertEqual(pygame.image.tobytes(surface, 'RGBA'), pygame.image.tobytes(expected, 'RGBA'))
        self.assertLess(sum(mask.bit_count() for mask in render._dirty_rows), 16)

    def test_offscreen_image_is_not_scaled(self):
        surface = pygame.Surface((320, 240), pygame.SRCALPHA)
        render = RenderSurface(surface, (160, 120), (320, 240), (0, 0))
        image = pygame.Surface((20, 20), pygame.SRCALPHA)
        with patch('pygame.transform.smoothscale', wraps=pygame.transform.smoothscale) as scale:
            for position in ((160, 0), (-20, 0), (0, 120), (0, -20)):
                render.blit(image, position)
        scale.assert_not_called()

    def test_vertical_damage_runs_merge_without_extra_pixels(self):
        foreground = pygame.Surface((131, 143), pygame.SRCALPHA)
        target = pygame.Surface((160, 170))
        target.fill((23, 48, 71))
        expected = target.copy()
        render = RenderSurface(foreground, foreground.get_size(), foreground.get_size(),
                               (0, 0), track_damage=True)
        render.mark(foreground.fill((180, 90, 35, 127), (32, 0, 32, 96)))
        render.mark(foreground.fill((30, 80, 200, 190), (96, 96, 35, 47)))
        expected.blit(foreground, (7, 9), special_flags=pygame.BLEND_ALPHA_SDL2)
        render.composite_onto(target, offset=(7, 9))
        self.assertEqual(pygame.image.tobytes(target, 'RGB'), pygame.image.tobytes(expected, 'RGB'))
        self.assertEqual(render._previous_areas, [pygame.Rect(32, 0, 32, 96), pygame.Rect(96, 96, 35, 47)])
        self.assertFalse(foreground.get_bounding_rect())
        self.assertFalse(any(render._dirty_rows))

    def test_partly_visible_image_preserves_pixels(self):
        for position in ((-9, 5), (152, 110)):
            surface = pygame.Surface((320, 240), pygame.SRCALPHA)
            expected = surface.copy()
            image = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(image, (20, 130, 220, 170), (10, 10), 10)
            render = RenderSurface(surface, (160, 120), (320, 240), (0, 0))
            expected.blit(pygame.transform.smoothscale(image, (40, 40)), render.point(position))
            render.blit(image, position)
            self.assertEqual(pygame.image.tobytes(surface, 'RGBA'), pygame.image.tobytes(expected, 'RGBA'))
