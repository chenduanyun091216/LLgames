"""Present native Windows frames with SDL's accelerated renderer."""
import logging
import os

import pygame
from pygame._sdl2 import Renderer, Texture, Window
from pygame._sdl2.sdl2 import error as SDLError

from game_core.config import OCEAN_DEEP


SDL_RENDERER_ACCELERATED = 0x2
SDL_RENDERER_TARGETTEXTURE = 0x8
PANORAMA_UPLOAD_BYTES = 2 * 1024 ** 2


class WindowsPresenter:
    def __init__(self, window, renderer, target_textures):
        self.window = window
        self.renderer = renderer
        # Input and destination rectangles stay in physical window pixels.
        self.renderer.logical_size = (0, 0)
        self.renderer.draw_color = (*OCEAN_DEEP, 255)
        self.target_textures = target_textures
        self.reset_textures()

    def reset_textures(self):
        self.frame = None
        self.background_surface = None
        self.background = None
        self.foreground = None
        self.scene = None
        self.clear_prepared_background()

    def clear_prepared_background(self):
        self.prepared_surface = None
        self.prepared_background = None
        self.prepared_rows = 0

    def prepare_background(self, panorama):
        if panorama is self.background_surface:
            return
        width, height = panorama.get_size()
        try:
            if self.prepared_surface is not panorama:
                self.prepared_surface = panorama
                self.prepared_background = Texture(self.renderer, (width, height), depth=32)
                self.prepared_rows = 0
            rows = min(height - self.prepared_rows, max(1, PANORAMA_UPLOAD_BYTES // (4 * width)))
            if rows > 0:
                area = pygame.Rect(0, self.prepared_rows, width, rows)
                self.prepared_background.update(panorama.subsurface(area), area)
                self.prepared_rows += rows
        except (pygame.error, SDLError) as error:
            logging.warning('Could not prepare the PC panorama: %s', error)
            self.prepared_background = None
            self.prepared_rows = height

    def present(self, surface, source, destination, *, layers_drawn=False):
        if not layers_drawn:
            if surface.get_rect() != source:
                surface = surface.subsurface(source)
            frame = self.frame
            if frame is None or frame.get_rect().size != source.size:
                frame = self.frame = Texture.from_surface(self.renderer, surface)
            else:
                frame.update(surface)
            if destination.size != self.window.size:
                self.renderer.clear()
            frame.draw(dstrect=destination)
        self.renderer.present()

    def draw_layers(self, background, foreground, source, destination, *, fade=0, shade=0):
        scaled = source.size != destination.size
        if (background is None or background.get_size() != source.size or background.get_masks()[3]
                or background.get_alpha() is not None or background.get_colorkey() is not None
                or (scaled and not self.target_textures)):
            return False
        panorama = background.get_abs_parent()
        if self.background_surface is not panorama:
            self.background_surface = panorama
            self.background = None
            if self.prepared_surface is panorama:
                if self.prepared_rows == panorama.get_height():
                    self.background = self.prepared_background
                self.clear_prepared_background()
            if self.background is None:
                try:
                    self.background = Texture.from_surface(self.renderer, panorama)
                except (pygame.error, SDLError) as error:
                    logging.warning('Could not upload the PC panorama: %s', error)
        if self.background is None:
            return False

        if self.foreground is None or self.foreground.get_rect().size != source.size:
            self.foreground = Texture(self.renderer, source.size, depth=32, streaming=True)
            self.foreground.blend_mode = pygame.BLENDMODE_BLEND

        pixels = foreground.surface
        areas = foreground.collect_damage()
        bands = []
        if areas:
            for top in range(source.top, source.bottom, (source.height + 2) // 3):
                band = pygame.Rect(source.left, top, source.width, (source.height + 2) // 3).clip(source)
                visible = [area.clip(band) for area in areas if area.colliderect(band)]
                if visible:
                    bands.append(visible[0].unionall(visible[1:]))
            if sum(band.width * band.height for band in bands) > source.width * source.height * .65:
                bands = [source]
        regions = [band.move(-source.x, -source.y) for band in bands]
        for band, region in zip(bands, regions):
            self.foreground.update(pixels.subsurface(band), region)
        for area in areas:
            pixels.fill((0, 0, 0, 0), area)

        # Composite at the selected resolution before applying any display scaling.
        if scaled:
            if self.scene is None or self.scene.get_rect().size != source.size:
                self.scene = Texture(self.renderer, source.size, depth=32, target=True)
                self.scene.blend_mode = pygame.BLENDMODE_NONE
            self.renderer.target = self.scene
        elif destination.size != self.window.size:
            self.renderer.clear()
        layer_rect = pygame.Rect((0, 0), source.size) if scaled else destination
        try:
            self.background.draw(pygame.Rect(background.get_abs_offset(), source.size), layer_rect)
            if shade:
                self._draw_scrim(layer_rect, (2, 16, 25, shade))
            for region in regions:
                self.foreground.draw(region, region.move(layer_rect.topleft))
            if fade:
                self._draw_scrim(layer_rect, (0, 0, 0, fade))
        finally:
            if scaled:
                self.renderer.target = None
        if scaled:
            if destination.size != self.window.size:
                self.renderer.clear()
            self.scene.draw(dstrect=destination)
        return True

    def _draw_scrim(self, rect, color):
        previous_blend = self.renderer.draw_blend_mode
        try:
            self.renderer.draw_blend_mode = pygame.BLENDMODE_BLEND
            self.renderer.draw_color = color
            self.renderer.fill_rect(rect)
        finally:
            self.renderer.draw_color = (*OCEAN_DEEP, 255)
            self.renderer.draw_blend_mode = previous_blend


def open_windows_presenter(flags):
    if pygame.display.get_driver() != 'windows':
        return None
    os.environ.setdefault('SDL_RENDER_DRIVER', 'direct3d11')
    os.environ.setdefault('SDL_RENDER_SCALE_QUALITY', 'linear')
    try:
        # Let pygame own the SDL renderer and keep an opaque format for Surface.convert().
        pygame.display.set_mode((1, 1), flags | pygame.SCALED)
        driver, renderer_flags = pygame.display._get_renderer_info()
        if renderer_flags & SDL_RENDERER_ACCELERATED:
            window = Window.from_display_module()
            return WindowsPresenter(window, Renderer.from_window(window),
                                    bool(renderer_flags & SDL_RENDERER_TARGETTEXTURE))
        logging.warning('PC display renderer %s is not accelerated; using the window surface', driver)
    except (pygame.error, SDLError) as error:
        logging.warning('Could not initialize the PC display renderer: %s', error)
    return None
