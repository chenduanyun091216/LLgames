"""Presentation only: simulation and gameplay decisions live on the LAN host."""
import asyncio
import json
import platform
import traceback
import pygame


async def main():
    pygame.init()
    screen = pygame.display.set_mode((960, 720))
    pygame.display.set_caption('海洋生物入侵 · 双人联机')
    from online.adapters.presentation import Presentation
    renderer = Presentation(screen)
    bridge = platform.window.LLOnline
    bridge.readyRenderer()
    while True:
        pygame.event.get()  # Drain SDL events; DOM owns input, never accumulate them.
        payload = str(bridge.takeState())
        if payload:
            snapshot = json.loads(payload)
            if snapshot.get("world"):
                renderer.apply(snapshot, int(bridge.slot))
        renderer.draw()
        pygame.display.flip()
        await asyncio.sleep(1 / 60)


async def guarded():
    try:
        await main()
    except Exception:
        traceback.print_exc()
        platform.window.LLOnline.reportError('游戏画面加载失败，请刷新重试。')

asyncio.run(guarded())
