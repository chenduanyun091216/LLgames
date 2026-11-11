"""The approved ending illustrations and soundtrack, followed by live results."""
import pygame

from .opening import ASSETS, Opening


class Ending(Opening):
    assets = ASSETS.with_name('ending')
    audio_name = 'ending.ogg'
    quiet_menu_music = False
    narration_volume = .79
    fade_to_level = False
    entry_fade_out_ms = 460
    entry_hold_ms = 0
    cuts = (0, 4085, 9120, 14200, 20210, 23050, 28508)
    duration = cuts[-1] + 4000

    def __init__(self, draw_results):
        super().__init__()
        self.draw_results = draw_results
        self.result_key = None
        self.result = None

    def skip(self):
        if self.elapsed() < self.cuts[-1]:
            self.close()
            self.started_at = pygame.time.get_ticks() - self.cuts[-1]

    def _draw_details(self, image, index, elapsed):
        # The five illustrated scenes already include the party.
        pass

    def _frame(self, index, elapsed, size):
        if index < len(self.cuts) - 2:
            return super()._frame(index, elapsed, size)
        seconds = max(0, (self.duration - self.elapsed() + 999) // 1000)
        key = (size, seconds)
        if self.result_key != key:
            self.result = super()._frame(index - 1, 0, size).copy()
            self.draw_results(self.result, seconds)
            self.result_key = key
        return self.result

