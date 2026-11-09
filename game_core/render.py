"""Draw in game coordinates on a higher resolution browser surface."""
from functools import lru_cache

import pygame


@lru_cache(maxsize=24)
def _scaled_static_image(image, size):
    return pygame.transform.smoothscale(image, size)


@lru_cache(maxsize=128)
def trim_transparent(image):
    bounds = image.get_bounding_rect()
    return (image.subsurface(bounds), bounds.x - image.get_width() // 2,
            bounds.y - image.get_height() // 2)


class RenderSurface:
    TILE = 48

    def __init__(self, surface, logical_size, view_size, offset, *, track_damage=False, desktop_ui=False):
        self.surface = surface
        self.logical_size = logical_size
        self.scale = view_size[0] / logical_size[0]
        self.offset = offset
        self.desktop_ui = desktop_ui
        self.tile = 32 if not desktop_ui else self.TILE
        self._dirty_rows = ([0] * ((surface.get_height() + self.tile - 1) // self.tile)
                            if track_damage else None)
        self._previous_areas = []

    def get_size(self):
        return self.logical_size

    def point(self, position):
        x, y = position
        ox, oy = self.offset
        return round(x * self.scale) + ox, round(y * self.scale) + oy

    def length(self, value):
        return max(1, round(value * self.scale)) if value else 0

    def rect(self, rect):
        return (*self.point(rect[:2]), *(self.length(value) for value in rect[2:]))

    def blit(self, image, position, *, static=False, logical_size=None):
        width, height = logical_size or image.get_size()
        size = self.length(width), self.length(height)
        if min(size) == 0:
            return
        if size != image.get_size():
            image = (_scaled_static_image(image, size) if static
                     else pygame.transform.smoothscale(image, size))
        self.blit_pixels(image, self.point(position[:2]))

    def mark(self, rect):
        rows = self._dirty_rows
        if rows is not None and rect:
            left = rect.left // self.tile
            right = (rect.right - 1) // self.tile
            mask = ((1 << (right - left + 1)) - 1) << left
            for row in range(rect.top // self.tile, (rect.bottom - 1) // self.tile + 1):
                rows[row] |= mask
        return rect

    def blit_pixels(self, image, position):
        self.mark(self.surface.blit(image, position))

    def restore_background(self, target, background, margin_color='black'):
        bounds = background.get_rect(topleft=self.offset)
        if bounds == target.get_rect():
            for area in self._previous_areas:
                target.blit(background, area.topleft, area)
            return
        for area in self._previous_areas:
            if not bounds.contains(area):
                target.fill(margin_color, area)
            visible = area.clip(bounds)
            if visible:
                target.blit(background, visible.topleft, visible.move(-bounds.x, -bounds.y))

    def composite_onto(self, target):
        """Blend only touched tiles, then clear them for the next frame."""
        tile = self.tile
        bounds = self.surface.get_rect()
        self._previous_areas.clear()
        for row, mask in enumerate(self._dirty_rows):
            while mask:
                left = (mask & -mask).bit_length() - 1
                end = left
                while mask & (1 << end):
                    end += 1
                mask &= ~(((1 << (end - left)) - 1) << left)
                area = pygame.Rect(left * tile, row * tile, (end - left) * tile, tile).clip(bounds)
                target.blit(self.surface, area.topleft, area, special_flags=pygame.BLEND_ALPHA_SDL2)
                self.surface.fill((0, 0, 0, 0), area)
                self._previous_areas.append(area)
            self._dirty_rows[row] = 0


class Draw:
    @staticmethod
    def circle(surface, color, position, radius, width=0):
        if isinstance(surface, RenderSurface):
            position, radius, width = surface.point(position), surface.length(radius), surface.length(width)
            return surface.mark(pygame.draw.circle(surface.surface, color, position, radius, width))
        return pygame.draw.circle(surface, color, position, radius, width)

    @staticmethod
    def rect(surface, color, rect, width=0, border_radius=0):
        if isinstance(surface, RenderSurface):
            rect, width = surface.rect(rect), surface.length(width)
            border_radius = surface.length(border_radius)
            return surface.mark(pygame.draw.rect(surface.surface, color, rect, width, border_radius))
        return pygame.draw.rect(surface, color, rect, width, border_radius)

    @staticmethod
    def ellipse(surface, color, rect, width=0):
        if isinstance(surface, RenderSurface):
            rect, width = surface.rect(rect), surface.length(width)
            return surface.mark(pygame.draw.ellipse(surface.surface, color, rect, width))
        return pygame.draw.ellipse(surface, color, rect, width)

    @staticmethod
    def polygon(surface, color, points, width=0):
        if isinstance(surface, RenderSurface):
            points, width = [surface.point(point) for point in points], surface.length(width)
            return surface.mark(pygame.draw.polygon(surface.surface, color, points, width))
        return pygame.draw.polygon(surface, color, points, width)

    @staticmethod
    def line(surface, color, start, end, width=1):
        if isinstance(surface, RenderSurface):
            start, end, width = surface.point(start), surface.point(end), surface.length(width)
            return surface.mark(pygame.draw.line(surface.surface, color, start, end, width))
        return pygame.draw.line(surface, color, start, end, width)

    @staticmethod
    def lines(surface, color, closed, points, width=1):
        if isinstance(surface, RenderSurface):
            points, width = [surface.point(point) for point in points], surface.length(width)
            return surface.mark(pygame.draw.lines(surface.surface, color, closed, points, width))
        return pygame.draw.lines(surface, color, closed, points, width)

    @staticmethod
    def arc(surface, color, rect, start, end, width=1):
        if isinstance(surface, RenderSurface):
            rect, width = surface.rect(rect), surface.length(width)
            return surface.mark(pygame.draw.arc(surface.surface, color, rect, start, end, width))
        return pygame.draw.arc(surface, color, rect, start, end, width)

    @staticmethod
    def aaline(surface, color, start, end):
        if isinstance(surface, RenderSurface):
            return Draw.line(surface, color, start, end)
        return pygame.draw.aaline(surface, color, start, end)


@lru_cache(maxsize=8)
def _effect_buffer(size):
    return pygame.Surface(size, pygame.SRCALPHA)


def effect_layer(target, size):
    """Keep effect coordinates logical while drawing into physical pixels."""
    if not isinstance(target, RenderSurface):
        return pygame.Surface(size, pygame.SRCALPHA)
    pixels = tuple(target.length(value) for value in size)
    buffer = _effect_buffer(pixels)
    buffer.fill((0, 0, 0, 0))
    return RenderSurface(buffer, size, pixels, (0, 0))


def blit_effect(target, layer, position):
    if isinstance(layer, RenderSurface):
        target.blit_pixels(layer.surface, target.point(position))
    else:
        target.blit(layer, position)
