import unittest
from unittest.mock import patch

from game_core import config
from game_core.main import BROWSER_QUALITIES, _browser_size


class BrowserFramePacingTests(unittest.TestCase):
    @patch.dict(vars(config))
    def test_tablet_background_covers_the_canvas_at_every_quality(self):
        for viewport in ((1194, 744), (744, 1194)):
            for quality in BROWSER_QUALITIES:
                with self.subTest(viewport=viewport, quality=quality):
                    canvas_size = _browser_size(viewport, quality)
                    config.update_mobile_view(canvas_size, viewport)
                    self.assertEqual(config.VIEW_SIZE, canvas_size)
                    self.assertEqual(config.VIEW_OFFSET, (0, 0))

    def test_tablet_hd_increases_resolution_without_raising_default_budget(self):
        self.assertEqual(_browser_size((1194, 834), 1.75), (1460, 1020))
        self.assertEqual(_browser_size((1194, 834), 2), (1718, 1200))

    def test_tablet_canvas_fits_sdl_eight_pixel_alpha_loop(self):
        for viewport in ((1194, 790), (790, 1194), (1366, 941)):
            for quality in BROWSER_QUALITIES:
                with self.subTest(viewport=viewport, quality=quality):
                    width, height = _browser_size(viewport, quality)
                    self.assertEqual(width * height % 8, 0)
                    expected_short_edge = max(width, height) * min(viewport) / max(viewport)
                    self.assertAlmostEqual(min(width, height), expected_short_edge, delta=1)

    def test_browser_quality_changes_render_pixels(self):
        self.assertEqual(_browser_size((844, 390), 1.5), (971, 448))
        self.assertEqual(_browser_size((844, 390), 1.75), (1654, 764))
        self.assertEqual(_browser_size((844, 390), 2), (2560, 1183))

    def test_hd_preserves_portrait_ratio(self):
        self.assertEqual(_browser_size((390, 844), 1.75), (764, 1654))
        self.assertEqual(_browser_size((390, 844), 2), (1183, 2560))

    def test_large_window_keeps_hd_larger_than_standard(self):
        self.assertEqual(_browser_size((3840, 2160), 1.5), (1707, 960))
        self.assertEqual(_browser_size((3840, 2160), 1.75), (1808, 1017))
        self.assertEqual(_browser_size((3840, 2160), 2), (2133, 1200))
        self.assertEqual(_browser_size((3840, 1080), 2), (2560, 720))
