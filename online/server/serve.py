"""Serve the integrated build without taking over an occupied port."""
import asyncio
import errno
import ipaddress
import json
import signal
import sys
from pathlib import Path

from aiohttp import web

from .app import HOST_KEY
from .host import create_host

WEBROOT = Path(__file__).resolve().parents[2] / 'build' / 'web-offline'


async def serve(host, port, *, root=WEBROOT, tls=None, addresses=(), lan_warning='', setup_port=None):
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    signal_installed = False
    try:
        loop.add_signal_handler(signal.SIGTERM, stopping.set)
        signal_installed = True
    except (NotImplementedError, RuntimeError):
        pass
    if not (root / 'index.html').is_file():
        raise FileNotFoundError(f'缺少 Web 构建：{root}')
    ip = ipaddress.ip_address(host)
    if not (ip.is_private or ip.is_loopback or ip.is_unspecified) or ip.is_multicast:
        raise ValueError('联机服务只监听局域网地址')
    runner = web.AppRunner(create_host(root, lan_warning=lan_warning))
    await runner.setup()
    try:
        site = web.TCPSite(runner, host, port, ssl_context=tls)
        await site.start()
        port = runner.addresses[0][1]
        scheme = 'https' if tls else 'http'
        names = [host] if not ip.is_unspecified else [*addresses, '127.0.0.1']
        names = [name if ':' not in name else f'[{name}]' for name in names]
        urls = [f'{scheme}://{name}:{port}/' for name in names]
        room_host = runner.app[HOST_KEY]
        room_host.public_url = urls[0]
        if setup_port is not None:
            room_host.setup_url = f'http://{names[0]}:{setup_port}/'
        print(json.dumps({'port': port, 'urls': urls}), flush=True)
        if lan_warning:
            print(lan_warning, file=sys.stderr, flush=True)
        await stopping.wait()
    finally:
        if signal_installed:
            loop.remove_signal_handler(signal.SIGTERM)
        await runner.cleanup()


def run_native_host():
    from web.run_web import GAME_PORT, SETUP_PORT, TLS_DIR, load_lan_tls, serve_lan_site

    cert = TLS_DIR / 'cert.pem'
    try:
        tls, setup_certificate = load_lan_tls(cert, TLS_DIR / 'key.pem', TLS_DIR / 'rootCA.pem')
        serve_lan_site('0.0.0.0', GAME_PORT, SETUP_PORT, tls, setup_certificate, cert)
    except (OSError, ValueError) as exc:
        message = f'HTTPS 联机服务启动失败：{exc}'
        if isinstance(exc, OSError) and exc.errno == errno.EADDRINUSE:
            message = f'联机端口 {SETUP_PORT} 或 {GAME_PORT} 已被占用'
        print(json.dumps({'error': message}), flush=True)


if __name__ == '__main__':
    run_native_host()
