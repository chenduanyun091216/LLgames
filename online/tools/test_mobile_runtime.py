"""Real Pygbag build + two independent Chromium touch clients, not a DOM fixture.

Run from the repository root. Keeps Chromium's sandbox enabled. No CDN, mock
transport, renderer-ready injection, gameplay mutation, or public server is used.
"""
import argparse
import asyncio
from collections import deque
import hashlib
import io
import json
from pathlib import Path
import time
import traceback
from urllib.parse import urlsplit

from aiohttp import web
from PIL import Image, ImageStat
from playwright.async_api import async_playwright

from online.server.app import create_app, ROOM_KEY, STATIC_ROOT


async def until(predicate, description, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(.05)
    raise AssertionError(f"Timed out: {description}")


class Client:
    def __init__(self, page, label):
        self.page, self.label = page, label
        self.state = None
        self.sent = deque(maxlen=200)
        self.errors = []
        self.external = set()
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.on('websocket', self.websocket)
        page.on('request', self.request)

    def request(self, request):
        url = urlsplit(request.url)
        if url.scheme in ('http', 'https') and url.hostname not in ('127.0.0.1', 'localhost'):
            self.external.add(request.url)

    def websocket(self, socket):
        def received(payload):
            try:
                message = json.loads(payload)
                if message.get('type') == 'state':
                    self.state = message
            except (ValueError, TypeError):
                pass

        def sent(payload):
            try:
                message = json.loads(payload)
                # Do not retain the hello frame, which can contain a reconnect token.
                if message.get('type') in ('input', 'action'):
                    self.sent.append(message)
            except (ValueError, TypeError):
                pass

        socket.on('framereceived', received)
        socket.on('framesent', sent)

    async def boot(self, timeout):
        """Wait for the real Python renderer; only provide the required user tap."""
        deadline = time.monotonic() + timeout
        tapped = False
        while time.monotonic() < deadline:
            # A lobby button may additionally require a connection. Observe the
            # real renderer flag without calling readyRenderer or mutating it.
            if await self.page.evaluate("typeof rendererReady !== 'undefined' && rendererReady === true"):
                return
            if await self.page.locator('#error').count():
                error = await self.page.locator('#error').inner_text()
                if '加载失败' in error:
                    raise AssertionError(f'{self.label}: {error}')
            box = self.page.locator('#infobox')
            if await box.count() and await box.is_visible():
                text = await box.inner_text()
                if 'click/touch' in text and not tapped:
                    await box.tap()
                    tapped = True
            await asyncio.sleep(.2)
        raise AssertionError(f'{self.label}: real WASM/Pygame renderer not ready in {timeout}s')

    async def join(self, code, slot):
        await self.page.locator('#code').fill(code)
        await self.page.locator('#connect').tap()
        await until(lambda: self.state is not None and len(self.state['players']) >= slot,
                    f'{self.label} joins room')
        # On reconnect the match is already playing, so the lobby/#players is
        # correctly hidden. The live status remains visible in both phases.
        await self.page.locator('#status').filter(has_text=f' · P{slot} · ').wait_for(state='visible')


async def screenshot(client, output, name):
    path = output / f'{name}.png'
    await client.page.screenshot(path=str(path), full_page=True)
    return path.name


async def check_canvas(client):
    canvas = client.page.locator('#canvas')
    box = await canvas.bounding_box()
    width,height=client.state['world_size']
    assert box and abs(box['width'] / box['height'] - width/height) < .015, box
    assert await canvas.get_attribute('width') == str(width)
    assert await canvas.get_attribute('height') == '720'
    # Screenshot pixels, not a fabricated canvas or a readiness-only claim.
    pixels = Image.open(io.BytesIO(await canvas.screenshot())).convert('RGB')
    variation = max(ImageStat.Stat(pixels).stddev)
    assert variation > 8, f'{client.label}: canvas appears blank (variation={variation:.2f})'
    return {'css_width': round(box['width'], 2), 'css_height': round(box['height'], 2),
            'pixel_stddev': round(variation, 2)}


async def multi_touch(client, context, room, slot):
    page = client.page
    stick, shoot = [await page.locator(selector).bounding_box() for selector in ('#stick', '#shoot')]
    assert stick and shoot
    x = stick['x'] + stick['width'] * .85
    y = stick['y'] + stick['height'] * .5
    fire_x, fire_y = shoot['x'] + shoot['width'] / 2, shoot['y'] + shoot['height'] / 2
    session = await context.new_cdp_session(page)
    before = room.snapshot()['world']['players'][slot - 1]
    before_x, before_shot = before['x'], before['last_shot_time']
    client.sent.clear()
    try:
        await session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [
            {'id': 1, 'x': x, 'y': y, 'radiusX': 2, 'radiusY': 2, 'force': 1},
            {'id': 2, 'x': fire_x, 'y': fire_y, 'radiusX': 2, 'radiusY': 2, 'force': 1}]})
        await until(lambda: any(m.get('dx', 0) > .2 and m.get('shoot') for m in client.sent),
                    f'{client.label} simultaneous real touch movement/fire')
        await until(lambda: room.snapshot()['world']['players'][slot - 1]['x'] > before_x + 5,
                    f'{client.label} authoritative movement')
        await until(lambda: room.snapshot()['world']['players'][slot - 1]['last_shot_time'] > before_shot,
                    f'{client.label} authoritative shooting')
    finally:
        await session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        await session.detach()
    client.sent.clear()
    await until(lambda: any(m.get('type') == 'input' and m.get('dx') == 0 and
                           m.get('dy') == 0 and not m.get('shoot') for m in client.sent),
                f'{client.label} input resets after touch release')


async def run(args, report):
    index = STATIC_ROOT / 'index.html'
    if not index.is_file():
        raise RuntimeError('Build missing. Run python -m online.tools.build_web first.')
    report['index_sha256'] = hashlib.sha256(index.read_bytes()).hexdigest()
    report['scope'] = 'Actual Pygbag build; two Chromium mobile touch emulators, not physical phones'
    app = create_app(code='MOBILE12')
    room = app[ROOM_KEY]
    runner = web.AppRunner(app)
    await runner.setup()
    server = web.TCPSite(runner, '127.0.0.1', 0)
    await server.start()
    port = server._server.sockets[0].getsockname()[1]
    url = f'http://127.0.0.1:{port}/'
    clients = []
    browser = None
    playwright = None
    try:
        playwright = await async_playwright().start()
        options = {'headless': True, 'chromium_sandbox': True}
        if args.channel:
            options['channel'] = args.channel
        if args.executable:
            options['executable_path'] = args.executable
        browser = await playwright.chromium.launch(**options)
        report['browser_version'] = browser.version
        contexts = []
        viewport = {'width':844,'height':390} if args.orientation=='landscape' else {'width':390,'height':844}
        for slot in (1,2):
            context = await browser.new_context(viewport=viewport, is_mobile=True,
                                                has_touch=True, device_scale_factor=1)
            contexts.append(context)
            client = Client(await context.new_page(), f'P{slot}')
            clients.append(client)
            client.page.set_default_timeout(15000)
            await client.page.goto(url, wait_until='domcontentloaded', timeout=args.timeout * 1000)
            await client.boot(args.timeout)
            await screenshot(client, args.output, f'p{slot}-lobby')
            await client.join(room.code, slot)
            await client.page.wait_for_function("document.querySelector('#ready')?.disabled === false")
            await client.page.locator('#ready').tap()
            await until(lambda: room.players[slot - 1].ready, f'P{slot} ready')
            report['checks'].append(f'P{slot}: real renderer loaded, joined and readied')
        p1, p2 = clients
        await p1.page.locator('#difficulty').select_option('easy')
        await p1.page.locator('#start').tap()
        await until(lambda: all(c.state and c.state['phase'] == 'playing' and
                               not c.state['paused'] for c in clients), 'both clients running')
        for slot, (client, context) in enumerate(zip(clients, contexts), 1):
            await client.page.locator('#controls').wait_for(state='visible')
            await multi_touch(client, context, room, slot)
            report['checks'].append(f'P{slot}: simultaneous joystick/fire, server movement/fire, release reset')
            report['canvases'][f'p{slot}-initial'] = await check_canvas(client)
            await screenshot(client, args.output, f'p{slot}-playing')
        assert p1.state['match_id'] == p2.state['match_id']
        report['checks'].append('Both clients receive the same match')

        await p1.page.locator('[data-action="shop_open"]').tap()
        await until(lambda: all(c.state and c.state.get('pause_reason') == 'shop' for c in clients),
                    'shop pause reaches both clients')
        for client in clients:
            await client.page.locator('#shop').wait_for(state='visible')
        tick = room.game.tick
        await asyncio.sleep(.4)
        assert room.game.tick == tick, 'Simulation advanced while both shops were open'
        await screenshot(p1, args.output, 'p1-shop-paused')
        await p1.page.locator('[data-action="shop_close"]').tap()
        await asyncio.sleep(.2)
        assert room.game.tick == tick, 'Closing only one shop resumed the game'
        await p2.page.locator('[data-action="shop_close"]').tap()
        await until(lambda: room.game.tick > tick, 'closing both shops resumes game')
        report['checks'].append('Shop pauses both clients; one close stays paused; both close resumes')

        # A real reload closes the WebSocket. Do not monkey-patch visibility,
        # bridge state, transport, readiness, or authentication storage.
        old_match = room.match_id
        await p2.page.reload(wait_until='domcontentloaded', timeout=args.timeout * 1000)
        await until(lambda: p1.state and p1.state.get('pause_reason') == 'disconnected',
                    'P1 observes actual P2 reload disconnection')
        tick = room.game.tick
        await asyncio.sleep(.4)
        assert room.game.tick == tick, 'Simulation advanced after disconnection'
        await screenshot(p1, args.output, 'p1-disconnected-pause')
        await p2.boot(args.timeout)
        p2.state = None
        await p2.join(room.code, 2)
        await until(lambda: not room.pause_reason() and room.game.tick > tick,
                    'same-tab session token reconnect resumes match')
        assert room.match_id == old_match and len(room.players) == 2
        await screenshot(p2, args.output, 'p2-reconnected')
        report['checks'].append('Real reload pauses match; original P2 reconnects and preserves match')

        rotated={'width':viewport['height'],'height':viewport['width']}
        for slot,client in enumerate(clients,1):
            await client.page.set_viewport_size(rotated)
            await until(lambda: room.pause_reason()=='orientation_mismatch','rotation pauses authority')
            tick=room.game.tick
            await asyncio.sleep(.2)
            assert room.game.tick==tick
            assert await client.page.locator('#controls').is_hidden()
            report['canvases'][f'p{slot}-rotated']=await check_canvas(client)
            await screenshot(client,args.output,f'p{slot}-rotated')
            await client.page.set_viewport_size(viewport)
            await until(lambda: not room.pause_reason() and room.game.tick>tick,'matching orientation resumes')
        report['checks'].append(f'Both clients use {args.orientation}; either rotation pauses authority, geometry stays fixed, matching restores play')
        for client in clients:
            assert not client.errors, f'{client.label} JavaScript errors: {client.errors}'
            assert not client.external, f'{client.label} external runtime requests: {sorted(client.external)}'
            assert '加载失败' not in await client.page.locator('#error').inner_text()
        report['checks'].append('No page JavaScript errors or external HTTP(S) runtime asset requests')
        report['status'] = 'PASS'
        report['limitations'] = [
            'This is Chromium emulation, not Android hardware or iOS Safari.',
            'Screenshots still require human visual review for overlap/readability.',
            'Does not certify audio quality, real Wi-Fi, browser backgrounding, or full boss victory.',
        ]
    except Exception:
        for client in clients:
            try:
                await screenshot(client, args.output, f'{client.label.lower()}-failure')
            except Exception:
                pass
        raise
    finally:
        try:
            if browser:
                await browser.close()
        finally:
            if playwright:
                await playwright.stop()
            await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orientation',choices=('landscape','portrait'),default='landscape')
    parser.add_argument('--output', type=Path, default=Path('online/.test-mobile-runtime'))
    parser.add_argument('--timeout', type=int, default=180, help='Real renderer startup limit in seconds')
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument('--channel', choices=('chrome', 'msedge'), help='Use an already-installed browser')
    browser.add_argument('--executable', help='Explicit existing Chromium executable path')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'FAIL', 'checks': [], 'canvases': {}}
    try:
        asyncio.run(run(args, report))
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = f'{type(error).__name__}: {error}'
        (args.output / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'Report and screenshots: {args.output.resolve()}')
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
