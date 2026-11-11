import unittest

from game_core.config import FPS
from game_core.main import _browser_frame_deadline, _browser_size


class BrowserFramePacingTests(unittest.TestCase):
    def test_browser_quality_changes_render_pixels(self):
        self.assertEqual(_browser_size((844, 390), 1.5), (971, 448))
        self.assertEqual(_browser_size((844, 390), 1.75), (1654, 764))
        self.assertEqual(_browser_size((844, 390), 2), (2337, 1080))

    def test_hd_preserves_portrait_ratio(self):
        self.assertEqual(_browser_size((390, 844), 1.75), (764, 1654))
        self.assertEqual(_browser_size((390, 844), 2), (1080, 2337))

    def test_large_window_keeps_hd_larger_than_standard(self):
        self.assertEqual(_browser_size((3840, 2160), 1.5), (1707, 960))
        self.assertEqual(_browser_size((3840, 2160), 1.75), (1813, 1020))
        self.assertEqual(_browser_size((3840, 2160), 2), (1920, 1080))
        self.assertEqual(_browser_size((3840, 1080), 2), (2560, 720))

    def test_60hz_callback_jitter_does_not_drop_frames(self):
        step = 1 / FPS
        deadline = 0.0
        for index in range(120):
            jitter = -0.004 if index % 2 else 0.0
            deadline = _browser_frame_deadline(index * step + jitter, deadline, step)
            self.assertIsNotNone(deadline)
        self.assertAlmostEqual(deadline, 2.0)

    def test_stall_skips_expired_slots_without_resetting_cadence(self):
        step = 1 / 60
        deadline = _browser_frame_deadline(0.051, step, step)
        self.assertAlmostEqual(deadline, 4 * step)
        self.assertIsNone(_browser_frame_deadline(0.058, deadline, step))
        self.assertAlmostEqual(_browser_frame_deadline(0.066, deadline, step), 5 * step)
