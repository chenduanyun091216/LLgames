"""Exercise the unified canvas entry in real Chromium with two browser clients."""
import hashlib
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from PIL import Image, ImageStat
from playwright.async_api import async_playwright

from online.server.app import HOST_KEY
from online.server.host import create_host
from online.server.serve import WEBROOT


async def run(args, report):
    output = Path(args.output)
    report['build_sha256'] = hashlib.sha256((WEBROOT / 'index.html').read_bytes()).hexdigest()
    app = create_host(WEBROOT)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        url = f'http://127.0.0.1:{runner.addresses[0][1]}/'
        async with async_playwright() as playwright:
            options = {'channel': args.channel} if args.channel else {}
            if args.executable:
                options['executable_path'] = args.executable
            browser = await playwright.chromium.launch(**options)
            try:
                report['browser'] = browser.version
                portrait = args.orientation == 'portrait'
                width, height = (390, 844) if portrait else (1280, 720)
                logical_height = round((480 if portrait else 960) * height / width)
                errors = []
                pages = []
                for slot in (1, 2):
                    context = await browser.new_context(viewport={'width': width, 'height': height},
                                                        is_mobile=portrait, has_touch=portrait)
                    page = await context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    await page.goto(url)
                    version = page.locator('#ttgames-version')
                    ready = page.locator('#infobox[data-ready]')
                    # When autoplay is permitted the engine enters the menu without a prompt.
                    await page.locator('#infobox[data-ready]:visible, #ttgames-version:visible').first.wait_for(
                        timeout=args.timeout * 1000)
                    if await ready.is_visible():
                        assert not await version.is_visible()
                        await ready.click()
                    await page.locator('#ttgames-loading').wait_for(state='hidden', timeout=args.timeout * 1000)
                    await version.wait_for(state='visible')
                    assert await version.evaluate("label => getComputedStyle(label).fontSize === '10px'")
                    label, canvas = await version.bounding_box(), await page.locator('#canvas').bounding_box()
                    assert abs(label['y'] - canvas['y'] - 8) < 1
                    assert abs(canvas['x'] + canvas['width'] - label['x'] - label['width'] - 12) < 1
                    await page.screenshot(path=output / f'p{slot}-home.png')
                    pages.append(page)

                async def click(page, rows, index):
                    canvas = await page.locator('#canvas').bounding_box()
                    from game_core import config, menu_ui
                    logical_width = 480 if portrait else 960
                    with patch.multiple(config, SCREEN_WIDTH=logical_width, SCREEN_HEIGHT=logical_height,
                                        MOBILE_LANDSCAPE_VIEW=not portrait):
                        rect = menu_ui.room_action_rects(rows)[index]
                    pos = (canvas['x'] + canvas['width'] * rect.centerx / logical_width,
                           canvas['y'] + canvas['height'] * rect.centery / logical_height)
                    if portrait:
                        await page.touchscreen.tap(*pos)
                    else:
                        await page.mouse.click(*pos)

                async def click_entrance(page, entrance):
                    from game_core import config, menu_ui
                    logical_width = 480 if portrait else 960
                    with patch.multiple(config, SCREEN_WIDTH=logical_width, SCREEN_HEIGHT=logical_height,
                                        MOBILE_LANDSCAPE_VIEW=not portrait):
                        rect = menu_ui.entrance_rects()[entrance]
                    canvas = await page.locator('#canvas').bounding_box()
                    pos = (canvas['x'] + canvas['width'] * rect.centerx / logical_width,
                           canvas['y'] + canvas['height'] * rect.centery / logical_height)
                    if portrait:
                        await page.touchscreen.tap(*pos)
                    else:
                        await page.mouse.click(*pos)

                p1, p2 = pages
                await click_entrance(p1, 'create')
                await p1.wait_for_function('ttgamesLAN.slot === 1')
                await p1.locator('#ttgames-version').wait_for(state='hidden')
                code = app[HOST_KEY].room.code
                await click_entrance(p2, 'join')
                await p2.locator('#ttgames-lan-address').fill(code)
                await p2.locator('#ttgames-lan-join button[value=join]').click()
                await p2.wait_for_function('ttgamesLAN.slot === 2')
                await click(p1, 7, 0)
                await p1.wait_for_function('JSON.parse(ttgamesLAN.state).mode === "infinite"')
                await click(p1, 5, 2)
                await click(p2, 2, 0)
                await p1.wait_for_function('JSON.parse(ttgamesLAN.state).players.every(p => p.ready)')
                await click(p1, 5, 3)
                for slot, page in enumerate(pages, 1):
                    await page.wait_for_function('JSON.parse(ttgamesLAN.state).tick > 5')
                    assert not await page.locator('#ttgames-version').is_visible()
                    await page.locator('#ttgames-offline').wait_for(state='hidden')
                    screenshot = output / f'p{slot}-infinite.png'
                    await page.screenshot(path=screenshot)
                    with Image.open(screenshot) as image:
                        w, h = image.size
                        edges = ((w // 4, 0, w * 3 // 4, 12), (w // 4, h - 12, w * 3 // 4, h)) if portrait else (
                            (0, h // 4, 12, h * 3 // 4), (w - 12, h // 4, w, h * 3 // 4))
                        variation = [round(max(ImageStat.Stat(image.crop(box).convert('RGB')).stddev), 2)
                                     for box in edges]
                    assert min(variation) > 2, variation
                    report['canvases'][f'p{slot}'] = {'width': w, 'height': h, 'edge_variation': variation}
                # Chromium emulation reports zero iOS safe-area insets.
                await p2.bring_to_front()
                inset = await p2.add_style_tag(content='''
                    :root { --game-left: 55px; --game-right: calc(100vw - 34px);
                            --game-bottom: calc(100dvh - 21px); }
                ''')
                await p2.keyboard.press('Tab')
                canvas = p2.locator('#canvas')
                await canvas.focus()
                assert await canvas.evaluate(
                    "canvas => canvas === document.activeElement && getComputedStyle(canvas).outlineStyle === 'none'"
                ), 'Focused game canvas must not draw a line across the safe area'
                await p2.wait_for_function(
                    """() => {
                        const fill = document.getElementById('ttgames-safe-area-fill');
                        if (!fill) return false;
                        const {width, height} = fill;
                        const ctx = fill.getContext('2d');
                        return [[5, height / 2], [width - 5, height / 2],
                                [width / 2, height - 5], [5, height - 5], [width - 5, height - 5]]
                            .every(([x, y]) => {
                                const [r, g, b, a] = ctx.getImageData(x, y, 1, 1).data;
                                return a === 255 && (r || g || b);
                            });
                    }""")
                await p2.screenshot(path=output / 'p2-battle-bottom-safe-area.png')
                await inset.evaluate('style => style.remove()')
                room = app[HOST_KEY].room
                match = room.match_id
                await p2.wait_for_function('JSON.parse(ttgamesLAN.state).tick >= 150')
                desktop_checks = []
                if not portrait:
                    await p1.bring_to_front()
                    await p1.keyboard.press('b')
                    for page in pages:
                        await page.wait_for_function('JSON.parse(ttgamesLAN.state).players.every(p => p.shop_open)')
                    paused_tick = room.game.tick
                    await p1.keyboard.press('Escape')
                    for page in pages:
                        await page.wait_for_function(
                            'tick => { const s = JSON.parse(ttgamesLAN.state); return s.tick > tick && '
                            's.players.every(p => !p.shop_open); }', arg=paused_tick)
                    desktop_checks.append('P1 opens and closes the shop for both players without a second confirmation')
                    await p1.keyboard.press('2')
                    await p1.wait_for_function('JSON.parse(ttgamesLAN.state).players[0].character === "water"')
                    await p1.keyboard.press('k')
                    for page in pages:
                        await page.wait_for_function(
                            '() => { const s = JSON.parse(ttgamesLAN.state); return '
                            's.players.every(p => p.hp > p.max_hp) && '
                            's.world.players.every(p => p.water_haste_until > s.world.time_ms); }')
                    await p1.keyboard.press('l')
                    await p2.wait_for_function(
                        '() => { const w = JSON.parse(ttgamesLAN.state).world; return '
                        'w.players.every(p => p.water_boost_until > w.time_ms); }')
                    desktop_checks.append('Both clients receive temporary HP and water skill buffs from P1')
                x = room.game.all_players[1].x
                if portrait:
                    cdp = await p2.context.new_cdp_session(p2)
                    fire_x, fire_y = width * (480 - 48 - 480 // 50) / 480, height * (logical_height - 80) / logical_height
                    joystick = {'x': 80, 'y': height - 140, 'id': 1}
                    shoot = {'x': fire_x, 'y': fire_y, 'id': 2}
                    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [joystick, shoot]})
                    try:
                        await cdp.send('Input.dispatchTouchEvent',
                                       {'type': 'touchMove', 'touchPoints': [dict(joystick, x=115), shoot]})
                        await p2.wait_for_function(
                            'x => JSON.parse(ttgamesLAN.state).players.find(p => p.slot === 2).x > x + 8', arg=x)
                    finally:
                        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
                else:
                    await p2.bring_to_front()
                    await p2.keyboard.down('d')
                    try:
                        await p2.wait_for_function(
                            'JSON.parse(ttgamesLAN.state).players.find(p => p.slot === 2).x > 720')
                        await p2.screenshot(path=output / 'p2-expanded-battle-edge.png')
                    finally:
                        await p2.keyboard.up('d')
                tick = room.game.tick
                await p1.evaluate('ttgamesLAN.leave()')
                await p2.wait_for_function(
                    'tick => { const state = JSON.parse(ttgamesLAN.state); return state.players.length === 1 && state.tick > tick + 5; }',
                    arg=tick)
                assert room.match_id == match
                assert [peer.slot for peer in room.players] == [2]
                await p2.screenshot(path=output / 'p2-after-p1-exit.png')
                assert not errors, errors
                report['checks'] = ['real Pygbag canvas opens unified home; P1 creates and P2 joins via input',
                                    'both ready and enter the same infinite match',
                                    *desktop_checks,
                                    'P2 moves through the shared controls' if portrait else
                                    'P2 moves past the former right battle boundary using the keyboard',
                                    'background reaches both outer edges and offline notice stays out of battle',
                                    'battle artwork fills simulated side and bottom safe areas, including corners',
                                    'P1 exits through the browser transport and P2 remains in the same match']
                report['scope'] = 'desktop Chromium' if not portrait else 'Chromium phone emulation'
                report['status'] = 'PASS'
            finally:
                await browser.close()
    finally:
        await runner.cleanup()
