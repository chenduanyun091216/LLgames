"""Run with python -m online.server --http (or --cert CERT --key KEY)."""
import argparse
import ipaddress
import socket
import ssl
from pathlib import Path
from aiohttp import web
from .app import create_app, ROOM_KEY, STATIC_ROOT

def main():
    parser = argparse.ArgumentParser(description='LLgames private two-player LAN server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--http', action='store_true', help='Explicit insecure local/LAN development mode; no offline installation')
    parser.add_argument('--cert', type=Path)
    parser.add_argument('--key', type=Path)
    args = parser.parse_args()
    try:
        ip = ipaddress.ip_address(args.host)
        if not (ip.is_loopback or ip.is_private or ip.is_unspecified) or ip.is_multicast:
            parser.error('Bind only to a private, loopback, or wildcard address')
    except ValueError:
        parser.error('--host must be a numeric IP address')
    if not 1 <= args.port <= 65535:
        parser.error('Invalid port')
    ctx = None
    if args.http:
        if args.cert or args.key:
            parser.error('Choose --http OR --cert/--key')
    else:
        if not args.cert or not args.key:
            parser.error('Supply --cert and --key, or explicitly opt into --http')
        for path in (args.cert, args.key):
            if path.resolve().is_relative_to(STATIC_ROOT.resolve()):
                parser.error('TLS files must be outside online/build/web')
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(args.cert, args.key)
    app = create_app()
    scheme = 'http' if args.http else 'https'
    print(f'Room code: {app[ROOM_KEY].code}', flush=True)
    hosts = {args.host} if not ip.is_unspecified else {'127.0.0.1'}
    if ip.is_unspecified:
        with __import__('contextlib').suppress(OSError):
            hosts.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None) if ipaddress.ip_address(item[4][0]).is_private)
    for host in sorted(hosts):
        print(f'Open {scheme}://{("["+host+"]") if ":" in host else host}:{args.port}/', flush=True)
    if args.http:
        print('HTTP mode: same-LAN play only; offline/service-worker installation disabled.', flush=True)
    web.run_app(app, host=args.host, port=args.port, ssl_context=ctx)

if __name__ == '__main__':
    main()
