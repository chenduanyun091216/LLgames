import unittest
from types import SimpleNamespace

from game_core.main import _browser_frame_deadline, _browser_render_step, _browser_size


class BrowserFramePacingTests(unittest.TestCase):
    def test_browser_quality_changes_render_pixels(self):
        for density, expected in ((1, (971, 448)), (1.5, (971, 448)), (2, (2337, 1080))):
            window = SimpleNamespace(ttgamesRenderDensity=density)
            self.assertEqual(_browser_size(window, (844, 390)), expected)

    def test_hd_preserves_portrait_ratio(self):
        window = SimpleNamespace(ttgamesRenderDensity=2)
        self.assertEqual(_browser_size(window, (390, 844)), (1080, 2337))

    def test_large_window_keeps_hd_larger_than_default(self):
        default = SimpleNamespace(ttgamesRenderDensity=1.5)
        hd = SimpleNamespace(ttgamesRenderDensity=2)
        self.assertEqual(_browser_size(default, (3840, 2160)), (1707, 960))
        self.assertEqual(_browser_size(hd, (3840, 2160)), (1920, 1080))
        self.assertEqual(_browser_size(hd, (3840, 1080)), (2560, 720))

    def test_hd_draws_every_other_60hz_callback(self):
        step = _browser_render_step(True)
        self.assertEqual(_browser_render_step(False), 1 / 60)
        self.assertEqual(step, 1 / 30)
        deadline = 0.0
        for index in range(120):
            next_deadline = _browser_frame_deadline(index / 60, deadline, step)
            self.assertEqual(next_deadline is None, index % 2 == 1)
            if next_deadline is not None:
                deadline = next_deadline

    def test_60hz_callback_jitter_does_not_drop_frames(self):
        step = 1 / 60
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
