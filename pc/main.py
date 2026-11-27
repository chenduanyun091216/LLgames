"""启动原生窗口中的共享游戏。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import sys

import pygame

from game_core.main import main as run_game


async def run_native():
    open_desktop_presenter = None
    if sys.platform == 'win32':
        # Request physical window pixels before pygame initializes SDL video.
        os.environ.setdefault('SDL_WINDOWS_DPI_AWARENESS', 'permonitorv2')
        from .presenter import open_windows_presenter as open_desktop_presenter
    from online.client.native import NativeTransport
    transport = NativeTransport()
    transport.host_task = asyncio.create_task(transport.start_host())
    try:
        with ThreadPoolExecutor(max_workers=1) as preload:
            await run_game(transport, open_desktop_presenter=open_desktop_presenter,
                           submit_preload=preload.submit)
    finally:
        await transport.close()


def main():
    try:
        asyncio.run(run_native())
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
