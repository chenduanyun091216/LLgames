"""Six illustrated scenes and their timing against the opening narration."""
from bisect import bisect_right
from collections import OrderedDict
from math import sin
from pathlib import Path
from random import Random

import pygame

from .animation import frame
from .sounds import ensure_audio, set_music_volume, start_music, stop_music


ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'opening'
CUTS = (0, 3960, 6930, 11730, 16550, 21910, 28875)
FADE_MS = 460
FPS = 6

# Bottom-center coordinates and visible height, relative to the 16:9 artwork.
ACTORS = (
    (('player1', .465, .619, .106),),
    (('player1', .473, .579, .056),),
    (('player1', .505, .31, .16),),
    (('player1', .19, .74, .19), ('player_water', .75, .73, .16)),
    (('player_water', .31, .68, .19), ('player_ice', .43, .68, .19),
     ('player1', .55, .68, .21), ('player_fire', .67, .68, .19),
     ('player_radiation', .79, .68, .19)),
    (('player_radiation', .20, .67, .16), ('player_water', .30, .67, .16),
     ('player_ice', .40, .67, .16), ('player_fire', .50, .67, .16),
     ('player1', .60, .67, .16)),
)


def opening_viewport(size):
    """Take the largest centered 16:9 rectangle inside the device viewport."""
    width, height = size
    unit = min(width // 16, height // 9)
    rect = pygame.Rect(0, 0, unit * 16, unit * 9)
    rect.center = (width // 2, height // 2)
    return rect


class Opening:
    assets = ASSETS
    cuts = CUTS
    audio_name = 'opening.ogg'
    quiet_menu_music = True
    narration_volume = .76
    fade_to_level = True
    entry_fade_out_ms = 0
    entry_hold_ms = 1000

    def __init__(self):
        self.scenes = OrderedDict()
        self.frames = OrderedDict()
        self.sprites = {}
        self.sprite_size = None
        random = Random(18)
        self.particles = [(random.random(), random.random(), random.random()) for _ in range(42)]
        self.channel = None
        self.pending_sound = None
        self.entry = None
        self._scene(0)
        entry_delay = self.entry_fade_out_ms + self.entry_hold_ms
        if ensure_audio():
            if self.quiet_menu_music:
                start_music()
                set_music_volume(.13)
            try:
                sound = pygame.mixer.Sound(str(self.assets / self.audio_name))
                sound.set_volume(self.narration_volume)
                if not self.quiet_menu_music:
                    stop_music(fade_ms=self.entry_fade_out_ms)
                if entry_delay:
                    self.pending_sound = sound
                else:
                    self.channel = sound.play()
            except (OSError, pygame.error):
                pass
        self.started_at = pygame.time.get_ticks() + entry_delay

    def elapsed(self):
        return pygame.time.get_ticks() - self.started_at

    def close(self):
        self.pending_sound = None
        if self.channel is not None:
            self.channel.stop()
            self.channel = None
        if self.quiet_menu_music:
            stop_music(fade_ms=300)

    def _scene(self, index):
        if index not in self.scenes:
            background = pygame.image.load(str(self.assets / f'scene-{index + 1}.jpg')).convert()
            self.scenes[index] = [background, None]
            if len(self.scenes) > 2:
                self.scenes.popitem(last=False)
        self.scenes.move_to_end(index)
        return self.scenes[index]

    def _draw_actors(self, image, index, elapsed):
        width, height = image.get_size()
        if self.sprite_size != (width, height):
            self.sprites.clear()
            self.sprite_size = (width, height)
        for order, (character, x, y, scale) in enumerate(ACTORS[index]):
            motion = 'run' if index == 5 else 'idle'
            pose = 0 if index < 3 else (elapsed // 360 + order) % 4
            visible_height = max(1, round(height * scale))
            angle = -23 if index == 2 else 0
            key = (character, motion, pose, visible_height, angle)
            if key not in self.sprites:
                sprite = frame(f'{character}_{motion}', pose)
                if sprite is None:
                    continue
                bounds = sprite.get_bounding_rect(min_alpha=45)
                if not bounds.height:
                    continue
                size = (max(1, round(bounds.width * visible_height / bounds.height)), visible_height)
                sprite = pygame.transform.smoothscale(sprite.subsurface(bounds), size)
                sprite.fill((225, 235, 246), special_flags=pygame.BLEND_RGB_MULT)
                self.sprites[key] = pygame.transform.rotozoom(sprite, angle, 1) if angle else sprite
            sprite = self.sprites[key]
            drift = min(.026, elapsed * .000004) if index == 5 or index == 3 and order == 0 else 0
            bob = sin(elapsed / 820 + order) * .003 if index >= 3 else 0
            image.blit(sprite, sprite.get_rect(midbottom=(round(width * (x + drift)),
                                                           round(height * (y + bob)))))

    def _draw_particles(self, image, index, elapsed):
        width, height = image.get_size()
        for x, y, depth in self.particles:
            if index < 2:
                px = round(width * ((x - elapsed * .000023) % 1))
                py = round(height * ((y + elapsed * (.00006 + depth * .00008)) % 1))
                image.fill((86, 134, 163), (px, py, 1, max(1, height // 135)))
            else:
                px = round(width * ((x + sin(elapsed / 2000 + y * 9) * .007) % 1))
                py = round(height * ((y - elapsed * (.000013 + depth * .000022)) % 1))
                pygame.draw.circle(image, (78, 137, 158), (px, py),
                                   max(1, round(height * (.001 + depth * .002))), 1)

    def _draw_details(self, image, index, elapsed):
        self._draw_actors(image, index, elapsed)
        self._draw_particles(image, index, elapsed)

    def _frame(self, index, elapsed, size):
        duration = self.cuts[index + 1] - self.cuts[index]
        step = min(elapsed, duration - 1) * FPS // 1000
        key = (index, step, size)
        if key not in self.frames:
            background, scaled = scene = self._scene(index)
            if scaled is None or scaled.get_size() != size:
                scaled = scene[1] = pygame.transform.smoothscale(background, size)
            image = scaled.copy()
            frame_time = step * 1000 // FPS
            self._draw_details(image, index, frame_time)
            self.frames[key] = image
            if len(self.frames) > 2:
                self.frames.popitem(last=False)
        self.frames.move_to_end(key)
        return self.frames[key]

    def draw(self, target):
        elapsed = min(self.elapsed(), self.cuts[-1] - 1)
        if self.entry_fade_out_ms and elapsed < -self.entry_hold_ms:
            if self.entry is None and isinstance(target, pygame.Surface):
                self.entry = target.copy()
        else:
            self.entry = None
        rect = opening_viewport(target.get_size())
        target.fill((0, 0, 0))
        if elapsed < 0:
            if self.entry is not None:
                self._draw_entry(target, min(1, (-elapsed - self.entry_hold_ms) / self.entry_fade_out_ms))
            return
        if self.pending_sound is not None:
            self.channel = self.pending_sound.play()
            self.pending_sound = None
        if not rect.width:
            return
        index = bisect_right(self.cuts, elapsed) - 1
        local_time = elapsed - self.cuts[index]
        current = self._frame(index, local_time, rect.size)
        remaining = self.cuts[-1] - elapsed
        if self.fade_to_level and remaining < FADE_MS:
            current.set_alpha(round(255 * remaining / FADE_MS))
        target.blit(current, rect.topleft)
        current.set_alpha(None)
        if elapsed < FADE_MS:
            self._draw_entry(target, 1 - elapsed / FADE_MS)
        if index and local_time < FADE_MS:
            previous = self._frame(index - 1, self.cuts[index] - self.cuts[index - 1] - 1, rect.size)
            fraction = local_time / FADE_MS
            previous.set_alpha(round(255 * (1 - fraction * fraction * (3 - 2 * fraction))))
            target.blit(previous, rect.topleft)
            previous.set_alpha(None)

    def _draw_entry(self, target, opacity):
        entry = self.entry
        if entry is None:
            entry = pygame.Surface(target.get_size())
        elif entry.get_size() != target.get_size():
            entry = pygame.transform.smoothscale(entry, target.get_size())
        entry.set_alpha(round(255 * opacity))
        target.blit(entry, (0, 0))
