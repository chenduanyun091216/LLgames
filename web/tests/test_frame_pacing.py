import unittest

from game_core.main import _browser_size


class BrowserFramePacingTests(unittest.TestCase):
    def test_tablet_hd_increases_resolution_without_raising_default_budget(self):
        self.assertEqual(_browser_size((1194, 834), 1.75), (1460, 1020))
        self.assertEqual(_browser_size((1194, 834), 2), (1718, 1200))

    def test_browser_quality_changes_render_pixels(self):
        self.assertEqual(_browser_size((844, 390), 1.5), (971, 448))
        self.assertEqual(_browser_size((844, 390), 1.75), (1654, 764))
        self.assertEqual(_browser_size((844, 390), 2), (2560, 1183))

    def test_hd_preserves_portrait_ratio(self):
        self.assertEqual(_browser_size((390, 844), 1.75), (764, 1654))
        self.assertEqual(_browser_size((390, 844), 2), (1183, 2560))

    def test_large_window_keeps_hd_larger_than_standard(self):
        self.assertEqual(_browser_size((3840, 2160), 1.5), (1707, 960))
        self.assertEqual(_browser_size((3840, 2160), 1.75), (1813, 1020))
        self.assertEqual(_browser_size((3840, 2160), 2), (2133, 1200))
        self.assertEqual(_browser_size((3840, 1080), 2), (2560, 720))
