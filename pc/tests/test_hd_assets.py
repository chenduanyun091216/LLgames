import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import animation, asset_loader, config
from game_core.render import RenderSurface


class DesktopHDAssetsTests(unittest.TestCase):
    def test_boss_sheet_uses_four_hd_frames_only_with_desktop_assets(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        target = RenderSurface(window, (960, 540), config.VIEW_SIZE, config.VIEW_OFFSET)
        self.assertEqual(config.VIEW_SIZE, (2560, 1440))
        self.assertEqual(target.length(162), 432)

        original = animation.frame('boss_attack', 0)
        self.assertEqual(original.get_size(), (160, 160))
        desktop_assets = Path(__file__).resolve().parents[1] / 'assets'
        with patch.object(asset_loader, 'PREFERRED_ASSET_DIR', desktop_assets):
            frames = [animation.frame('boss_attack', index) for index in range(4)]
            self.assertEqual([frame.get_size() for frame in frames], [(512, 512)] * 4)
            self.assertEqual(len(set(frames)), 4)
            self.assertIs(animation.frame('boss_attack', 4), frames[0])
            self.assertEqual(animation.frame('player1_back', 0).get_size(), (192, 192))
        self.assertIs(animation.frame('boss_attack', 0), original)

    def test_redrawn_sheets_keep_original_frame_counts(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        pygame.display.set_mode((1, 1))
        desktop_assets = Path(__file__).resolve().parents[1] / 'assets'
        shared_animations = Path(asset_loader.ASSET_DIR) / 'animations'
        with patch.object(asset_loader, 'PREFERRED_ASSET_DIR', desktop_assets):
            for original in sorted(shared_animations.glob('anim_*.png')):
                if original.stem.startswith(('anim_player1_', 'anim_player2_')):
                    continue
                with self.subTest(sheet=original.name):
                    width, height = pygame.image.load(original).get_size()
                    sheet = asset_loader.image_asset(f'animations/{original.name}')
                    self.assertEqual(sheet.get_size(), (512 * (width // height), 512))
                    self.assertTrue(sheet.get_masks()[-1])

            title = asset_loader.image_asset('ui/title.png')
            self.assertGreaterEqual(title.get_width(), 1595)
            self.assertEqual(asset_loader.image_asset('effects/boss_claw.png').get_size(), (426, 640))
            self.assertEqual(asset_loader.image_asset('effects/boss_ground_fire.png').get_size(), (640, 320))
            for color in ('gold', 'red'):
                trident = asset_loader.image_asset(f'effects/boss_trident_{color}.png')
                bounds = trident.get_bounding_rect(min_alpha=16)
                self.assertGreaterEqual(bounds.width, 75)
                self.assertGreaterEqual(bounds.height, 216)

    def test_desktop_menu_title_has_space_at_peak_scale(self):
        from game_core.game import Game

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)
        with patch.object(game, '_draw_title_image') as title, \
                patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as text:
            game._draw_menu()
        y, width = title.call_args.args
        subtitle = text.call_args_list[0].args[3]
        image = game.title_image
        self.assertLessEqual(y + int(width * 1.3 * image.get_height() / image.get_width()), subtitle.top)

    def test_battle_label_rasterizes_at_window_size(self):
        from game_core.visuals import blit_label

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        target = RenderSurface(window, (960, 540), (2560, 1440), (0, 0), desktop_ui=True)
        font = config.make_font(18, bold=True)
        with patch('game_core.visuals.make_font', wraps=config.make_font) as make_font, \
                patch.object(target, 'blit_pixels', wraps=target.blit_pixels) as blit:
            blit_label(target, font, '?', (240, 245, 255), (480, 270), 18, bold=True)
        make_font.assert_called_once_with(48, bold=True)
        self.assertEqual(blit.call_args.args[1].center, (1280, 720))
