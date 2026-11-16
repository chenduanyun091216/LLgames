"""启动原生窗口中的共享游戏。"""
import asyncio

import pygame

from game_core.main import main as run_game


async def run_native():
    from online.client.native import NativeTransport
    transport = NativeTransport()
    transport.host_task = asyncio.create_task(transport.start_host())
    try:
        await run_game(transport)
    finally:
        await transport.close()


def main():
    try:
        asyncio.run(run_native())
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
