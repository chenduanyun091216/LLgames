"""Browser interaction smoke test with a deterministic transport fixture (no gameplay simulation)."""
import asyncio
import json
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright

WEB = Path(__file__).resolve().parents[1] / 'web'

async def main():
    messages = []
    async def index(_):
        return web.Response(text='<html><head><link rel="stylesheet" href="/shell.css"></head><body><canvas id="canvas" width="960" height="720"></canvas><div id="infobox"></div><script src="/bridge.js"></script><script src="/shell.js"></script></body></html>',content_type='text/html')
    async def websocket(req):
        ws=web.WebSocketResponse(); await ws.prepare(req)
        async for msg in ws:
            data=json.loads(msg.data);messages.append(data)
            if data['type']=='hello':
                await ws.send_json({'type':'welcome','slot':1,'token':'test-token','match_id':'m1'})
                await ws.send_json({'type':'state','version':1,'match_id':'m1','orientation':'portrait','world_size':[480,720],'phase':'lobby','players':[{'slot':1,'orientation':'portrait','connected':True,'ready':True,'alive':True,'hp':100,'max_hp':100},{'slot':2,'orientation':'portrait','connected':True,'ready':True,'alive':True,'hp':100,'max_hp':100}],'gold':200,'lives':3})
            if data['type']=='start':
                await ws.send_json({'type':'state','version':1,'match_id':'m1','orientation':'portrait','world_size':[480,720],'phase':'playing','players':[{'slot':1,'orientation':'portrait','connected':True,'ready':True,'alive':True,'hp':100,'max_hp':100},{'slot':2,'orientation':'portrait','connected':True,'ready':True,'alive':True,'hp':100,'max_hp':100}],'gold':200,'lives':3})
        return ws
    app=web.Application();app.router.add_get('/',index);app.router.add_get('/ws',websocket);app.router.add_static('/',WEB)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1]
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True)
            page=await browser.new_page(viewport={'width':390,'height':844},has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(f'http://127.0.0.1:{port}/');await page.evaluate('LLOnline.readyRenderer()')
            await page.fill('#code','ABCD');await page.click('#connect');await page.wait_for_function("document.querySelector('#start').disabled===false")
            await page.click('#start');await page.wait_for_selector('#controls',state='visible')
            box=await page.locator('#canvas').bounding_box();assert abs(box['width']/box['height']-2/3)<.01
            await page.keyboard.down('KeyW');await page.keyboard.down('Space');await page.wait_for_timeout(100)
            await page.keyboard.up('KeyW');await page.keyboard.up('Space');await page.keyboard.press('KeyQ')
            stick=await page.locator('#stick').bounding_box()
            await page.mouse.move(stick['x']+stick['width']/2,stick['y']+stick['height']/2)
            await page.mouse.down()
            await page.mouse.move(stick['x']+stick['width']*.9,stick['y']+stick['height']/2)
            await page.locator('#stick').dispatch_event('pointercancel',{'pointerId':1,'bubbles':True})
            await page.mouse.up()
            await page.evaluate("window.dispatchEvent(new Event('blur'))")
            await page.wait_for_timeout(100)
            assert any(m.get('shoot') and m.get('dy')==-1 for m in messages),messages
            assert any(m.get('action')=='skill1' for m in messages)
            assert messages[-1].get('dx')==0 and messages[-1].get('dy')==0 and not messages[-1].get('shoot')
            await page.set_viewport_size({'width':844,'height':390})
            await page.wait_for_timeout(100)
            assert any(m.get('type')=='orientation' and m.get('orientation')=='landscape' for m in messages)
            assert await page.locator('#controls').is_hidden()
            await page.set_viewport_size({'width':390,'height':844})
            await page.wait_for_selector('#controls',state='visible')
            assert not errors,errors
            await browser.close()
            print('PASS Chromium mobile-viewport lobby/start, keyboard, pointer cancellation, blur reset, portrait 2:3 letterbox and rotation reports (transport fixture only)')
    finally:
        await runner.cleanup()

if __name__=='__main__':asyncio.run(main())
