"""
海洋生物入侵 - Ocean Invaders
入口文件。
"""
import os
import sys
import pygame

if not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'pc'

from . import config
from .config import DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT, FPS

INITIAL_WINDOW_HEIGHT_RATIO = 0.9
INITIAL_WINDOW_ASPECT = 1.2

def _desktop_size():
    try:
        return pygame.display.get_desktop_sizes()[0]
    except (pygame.error, IndexError):
        return DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT

def _initial_window_size(desktop_size):
    desktop_w, desktop_h = desktop_size
    height = max(1, int(round(desktop_h * INITIAL_WINDOW_HEIGHT_RATIO)))
    width = int(round(height * INITIAL_WINDOW_ASPECT))
    if width > desktop_w:
        width = max(1, desktop_w)
        height = max(1, int(round(width / INITIAL_WINDOW_ASPECT)))
    return width, height

def _draw_scaled(window):
    window.fill(config.OCEAN_DEEP)
    if config.SCR.get_size() == config.VIEW_SIZE:
        window.blit(config.SCR, config.VIEW_OFFSET)
    else:
        scaled = pygame.transform.smoothscale(config.SCR, config.VIEW_SIZE)
        window.blit(scaled, config.VIEW_OFFSET)

def main():
    pygame.init()
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
    except Exception:
        pass
    desktop_size = _desktop_size()
    window_size = _initial_window_size(desktop_size)
    os.environ['SDL_VIDEO_WINDOW_POS'] = f'{(desktop_size[0] - window_size[0]) // 2},0'
    window = pygame.display.set_mode(window_size, pygame.RESIZABLE)
    config.update_view(window.get_size())
    pygame.display.set_caption('海洋生物入侵 - Ocean Invaders')
    pygame.mouse.set_visible(True)

    from .game import Game
    from .sounds import start_music
    start_music()
    game = Game()
    running = True

    while running:
        events = pygame.event.get()
        resize_events = (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED)
        resized = any(event.type in resize_events for event in events)
        if resized:
            config.update_view(window.get_size())
            game.resize_view()
        running = game.handle_events(events)
        game.update()
        game.draw()
        _draw_scaled(window)
        pygame.display.flip()
        game.clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    main()
