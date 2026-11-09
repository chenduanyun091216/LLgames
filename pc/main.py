"""启动原生窗口中的共享游戏。"""
import asyncio

import pygame

from game_core.main import main as run_game


def main():
    try:
        asyncio.run(run_game())
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
