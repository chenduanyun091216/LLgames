"""启动原生窗口中的共享游戏。"""
import asyncio
from pathlib import Path

import pygame

from game_core import asset_loader
from game_core.main import main as run_game


def main():
    previous_assets = asset_loader.PREFERRED_ASSET_DIR
    asset_loader.PREFERRED_ASSET_DIR = Path(__file__).resolve().parent / 'assets'
    try:
        asyncio.run(run_game())
    finally:
        asset_loader.PREFERRED_ASSET_DIR = previous_assets
        pygame.quit()


if __name__ == '__main__':
    main()
