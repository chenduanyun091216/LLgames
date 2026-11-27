import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import animation, asset_loader, config
from game_core.render import RenderSurface


class DesktopHDAssetsTests(unittest.TestCase):
    def test_4k_uses_shared_art_for_effects_with_bad_transparent_edges(self):
        effects = ('effects/lightning_reactor.png', 'effects/mecha_emp_ring.png')
        clean = 'ui/coin.png'
        with TemporaryDirectory() as folder:
            assets = Path(folder)
            for variant in ('images', 'images_lg', 'images-hd'):
                for name in (*effects, clean):
                    path = assets / variant / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
            directory = str(assets / 'images')
            for name in effects:
                with self.subTest(name=name):
                    self.assertEqual(Path(asset_loader._image_path(directory, name, 'images_lg')),
                                     assets / 'images' / name)
                    self.assertEqual(Path(asset_loader._image_path(directory, name, 'images-hd')),
                                     assets / 'images-hd' / name)
            self.assertEqual(Path(asset_loader._image_path(directory, clean, 'images_lg')),
                             assets / 'images_lg' / clean)

    def test_4k_campaign_reuses_panorama_for_logical_background(self):
        from game_core import background
        from game_core.game import Game

        pygame.init()
        self.addCleanup(pygame.quit)
        size = (1280, 720)
        pygame.display.set_mode(size)
        config.update_mobile_view(size)
        game = Game(desktop_controls=True, scroll_campaign_backgrounds=True)
        game.difficulty = config.DIFFICULTY_PRESETS['medium']
        background.clear_background_cache()
        self.addCleanup(background.clear_background_cache)

        def load_art(name, size, *, panorama=False, variant=None):
            return pygame.Surface((size[0], size[0] * 3 // 2) if panorama else size)

        with patch.object(asset_loader, 'pc_4k_assets', True), \
                patch.object(background, 'cover_image_asset', side_effect=load_art) as load:
            self.assertEqual(game._load_bg().get_size(), config.SCR.get_size())
            self.assertEqual(game.scrolling_background(size).get_size(), size)

        load.assert_called_once_with('backgrounds/bg1.jpg', size, panorama=True, variant='images_lg')

    def test_native_pause_selects_4k_and_preserves_choice_across_runs(self):
        from game_core.game import Game, GameState
        from game_core.main import _desktop_render_size

        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((960, 540))
        config.update_mobile_view((960, 540))
        game = Game(desktop_controls=True)
        game.state = GameState.PAUSED
        self.assertEqual(game.desktop_quality, 2)
        self.assertEqual(_desktop_render_size((3840, 2160), 2), (2560, 1440))
        self.assertEqual(_desktop_render_size((1920, 1080), 2), (1920, 1080))
        game._handle_click(game._pause_quality_rects()[1].center)
        self.assertEqual(game.desktop_quality, 4)
        self.assertEqual(game.state, GameState.PAUSED)
        self.assertEqual(_desktop_render_size((1920, 1080), 4), (1920, 1080))
        self.assertEqual(_desktop_render_size((1440, 2560), 4), (1440, 2560))
        self.assertEqual(_desktop_render_size((3840, 2160), 4), (3840, 2160))
        self.assertEqual(_desktop_render_size((5120, 2880), 4), (3840, 2160))
        game.reset()
        self.assertEqual(game.desktop_quality, 4)
        game.state = GameState.PAUSED
        game._handle_click(game._pause_quality_rects()[0].center)
        self.assertEqual(game.desktop_quality, 2)

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
        self.assertEqual(animation.frame('player1_back', 0).get_size(), (512, 512))

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
                sheet = asset_loader.image_asset(f'animations/bosses/{name}.png')
                self.assertEqual(sheet.get_size(), (1312, 1199))
                self.assertTrue(sheet.get_masks()[-1])
        self.assertGreaterEqual(asset_loader.image_asset('ui/title.png').get_width(), 1595)
        self.assertEqual(asset_loader.image_asset('effects/boss_claw.png').get_size(), (426, 640))

    def test_desktop_home_title_does_not_overlap_mode_buttons(self):
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
        self.assertTrue(all(box.bottom <= rect.top for rect in game._mobile_menu_rects().values()))

    def test_orochi_idle_art_has_headroom_at_1440p(self):
        from game_core.orochi import OrochiBoss

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((2560, 1440))
        config.update_mobile_view(window.get_size())
        target = RenderSurface(window, (960, 540), config.VIEW_SIZE, config.VIEW_OFFSET)
        boss = OrochiBoss(config.BOSS_DEFS[-1], config.DIFFICULTY_PRESETS['hard'])
        with patch.object(target, 'blit') as blit:
            boss.draw(target)
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
        source = draw.call_args.kwargs['source']
        size = draw.call_args.kwargs['logical_size']
        for actual, logical in zip(source.get_size(), size):
            self.assertGreaterEqual(actual, round(target.length(logical) * 1.15))

    def test_boss_entrance_draws_from_full_resolution_art_at_4k(self):
        from game_core import entities
        from game_core.special_bosses import NiuBoss

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((3840, 2160))
        target = RenderSurface(window, (960, 540), window.get_size(), (0, 0), desktop_ui=True)
        difficulty = config.DIFFICULTY_PRESETS['hard']
        with patch.object(asset_loader, 'pc_4k_assets', True), \
                patch.object(config, 'game_ticks', return_value=2400), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            for definition in config.BOSS_DEFS[:7]:
                cls = NiuBoss if definition['key'] == 'boss_niu' else entities.Boss
                boss = cls(definition, difficulty)
                boss.y = 0
                boss.breath_start_time = 1000
                with self.subTest(boss=definition['key']):
                    boss.draw(target, visual_scale=config.ACTOR_BASE_SCALE)
                    source = draw.call_args.kwargs['source']
                    original = asset_loader.image_asset(boss.sprite_asset)
                    self.assertEqual(source.get_size(), original.get_size())
                    if isinstance(boss, NiuBoss):
                        self.assertIs(source, original)
                        for actual, logical in zip(source.get_size(), draw.call_args.kwargs['logical_size']):
                            self.assertGreaterEqual(actual, target.length(logical))
                        boss.entered = True
                        boss.draw(target, visual_scale=config.ACTOR_BASE_SCALE)
                        self.assertIs(draw.call_args.kwargs['source'], boss._body_frame(2400))

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

    def test_desktop_label_reuses_pixels_when_moved(self):
        from game_core.game import Game

        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((960, 540))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)
        target = RenderSurface(window, (480, 270), window.get_size(), (0, 0), desktop_ui=True)
        label = pygame.Rect(20, 20, 180, 28)
        with patch.object(config, 'SCR', target), patch.object(target, 'blit_pixels') as blit:
            game._draw_text_fit('HP 5/5', game.font_small, (255, 255, 255), label)
            game._draw_text_fit('HP 5/5', game.font_small, (255, 255, 255), label.move(15, 10))
            game._draw_text_fit('HP 4/5', game.font_small, (255, 255, 255), label)

        first_shadow, first_text, moved_shadow, moved_text, _, updated_text = (
            call.args for call in blit.call_args_list)
        self.assertIs(first_shadow[0], moved_shadow[0])
        self.assertIs(first_text[0], moved_text[0])
        self.assertEqual(first_text[1].move(30, 20), moved_text[1])
        self.assertIsNot(first_text[0], updated_text[0])

    def test_4k_sprite_reuses_intermediate_art_across_animation_sizes(self):
        from game_core.sprites import blit_lit_sprite

        pygame.init()
        self.addCleanup(pygame.quit)
        target = RenderSurface(pygame.Surface((384, 216), pygame.SRCALPHA),
                               (192, 108), (384, 216), (0, 0), desktop_ui=True)
        source = pygame.Surface((1024, 1024), pygame.SRCALPHA)
        source.fill((80, 180, 230, 255))
        with patch.object(asset_loader, 'pc_4k_assets', True), \
                patch('pygame.transform.smoothscale', wraps=pygame.transform.smoothscale) as scale:
            for size in (64, 60):
                image = pygame.Surface((size, size), pygame.SRCALPHA)
                blit_lit_sprite(target, image, (20, 20), (255, 255, 255), source=source)

        self.assertEqual([call.args[0].get_size() for call in scale.call_args_list],
                         [(1024, 1024), (256, 256), (256, 256)])
