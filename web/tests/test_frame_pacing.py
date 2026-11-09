import unittest
from types import SimpleNamespace

from web.main import _browser_frame_deadline, _browser_size


class BrowserFramePacingTests(unittest.TestCase):
    def test_browser_quality_changes_render_pixels(self):
        for density, expected in ((1, (844, 390)), (1.5, (1266, 585)), (2, (1688, 780))):
            window = SimpleNamespace(ttgamesRenderDensity=density)
            self.assertEqual(_browser_size(window, (844, 390)), expected)

    def test_60hz_callback_jitter_does_not_drop_frames(self):
        step = 1 / 60
        deadline = 0.0
        for index in range(120):
            jitter = -0.0015 if index % 2 else 0.0
            deadline = _browser_frame_deadline(index * step + jitter, deadline, step)
            self.assertIsNotNone(deadline)
        self.assertAlmostEqual(deadline, 2.0)

    def test_stall_skips_expired_slots_without_resetting_cadence(self):
        step = 1 / 60
        deadline = _browser_frame_deadline(0.051, step, step)
        self.assertAlmostEqual(deadline, 4 * step)
        self.assertIsNone(_browser_frame_deadline(0.058, deadline, step))
        self.assertAlmostEqual(_browser_frame_deadline(0.066, deadline, step), 5 * step)
