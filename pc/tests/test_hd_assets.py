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
    def test_boss_sheet_uses_four_shared_hd_frames(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        target = RenderSurface(window, (960, 540), config.VIEW_SIZE, config.VIEW_OFFSET)
        self.assertEqual(config.VIEW_SIZE, (2560, 1440))
        self.assertEqual(target.length(162), 432)

        frames = [animation.frame('boss_attack', index) for index in range(4)]
        self.assertEqual([frame.get_size() for frame in frames], [(512, 512)] * 4)
        self.assertEqual(len(set(frames)), 4)
        self.assertIs(animation.frame('boss_attack', 4), frames[0])
        self.assertEqual(animation.frame('player1_back', 0).get_size(),
                         asset_loader.image_asset('players/player1.png').get_size())

    def test_shared_hd_sheets_and_backgrounds(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        pygame.display.set_mode((1, 1))
        assets = Path(asset_loader.ASSET_DIR)
        for path in sorted((assets / 'backgrounds').glob('bg*.png')):
            with self.subTest(background=path.name):
                width, height = pygame.image.load(path).get_size()
                self.assertGreaterEqual(width, 2560)
                self.assertGreaterEqual(height, 1440)

        for name, count in (('boss_attack', 4), ('boss_mecha_lizard', 8)):
            with self.subTest(sheet=name):
                sheet = asset_loader.image_asset(f'animations/bosses/anim_{name}.png')
                self.assertEqual(sheet.get_size(), (512 * count, 512))
                self.assertTrue(sheet.get_masks()[-1])
        for name in ('boss_niu_actions', 'boss_niu_axe_sequence'):
            with self.subTest(sheet=name):
                sheet = asset_loader.image_asset(f'bosses/{name}.png')
                self.assertEqual(sheet.get_size(), (1312, 1199))
                self.assertTrue(sheet.get_masks()[-1])
        self.assertGreaterEqual(asset_loader.image_asset('ui/title.png').get_width(), 1595)
        self.assertEqual(asset_loader.image_asset('effects/boss_claw.png').get_size(), (426, 640))

    def test_desktop_home_title_does_not_overlap_start_button(self):
        from game_core import menu_ui
        from game_core.game import Game

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)
        with patch.object(menu_ui, '_art', wraps=menu_ui._art) as art:
            game._draw_menu()
        title, box = art.call_args_list[0].args
        self.assertIs(title, game.title_image)
        self.assertLessEqual(box.bottom, game._mobile_menu_rects()['start'].top)
        self.assertEqual(len(art.call_args_list), 17)

    def test_orochi_idle_art_has_headroom_at_1440p(self):
        from game_core.orochi import OrochiBoss

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        target = RenderSurface(window, (960, 540), config.VIEW_SIZE, config.VIEW_OFFSET)
        boss = OrochiBoss(config.BOSS_DEFS[-1], config.DIFFICULTY_PRESETS['hard'])
        with patch.object(target, 'blit') as blit:
            boss._draw_idle(target, boss.spawned_at)
        frame = blit.call_args.args[0]
        shown_size = blit.call_args.kwargs['logical_size']
        for actual, shown in zip(frame.get_size(), shown_size):
            self.assertGreaterEqual(actual, round(target.length(shown) * 1.2))

    def test_abyss_laser_warning_art_covers_peak_size_at_1440p(self):
        from game_core import entities

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        target = RenderSurface(window, (960, 540), config.VIEW_SIZE, config.VIEW_OFFSET)
        boss = entities.Boss(config.BOSS_DEFS[5], config.DIFFICULTY_PRESETS['hard'])
        boss.laser_warning_start, boss.breath_start_time = 1600, 200
        with patch.object(config, 'game_ticks', return_value=1600), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            boss.draw(target)
        image = draw.call_args.args[1]
        source = draw.call_args.kwargs['source']
        for actual, logical in zip(source.get_size(), image.get_size()):
            self.assertGreaterEqual(actual, round(target.length(logical) * 1.15))

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
