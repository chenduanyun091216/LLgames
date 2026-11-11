"""Serve the built Phaser game over HTTPS."""

import argparse
import ssl
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    project = Path(__file__).resolve().parents[1]
    dist = project / 'dist'
    tls_dir = project.parent / '.web-build' / 'tls'
    parser = argparse.ArgumentParser(description='通过 HTTPS 启动 Phaser Web 版')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8011)
    parser.add_argument('--cert', type=Path, default=tls_dir / 'cert.pem')
    parser.add_argument('--key', type=Path, default=tls_dir / 'key.pem')
    args = parser.parse_args()

    if not (dist / 'index.html').is_file():
        parser.error('缺少构建产物，请先执行 npm run build')

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        tls.load_cert_chain(args.cert, args.key)
    except OSError as exc:
        parser.error(f'无法读取 HTTPS 证书或私钥：{exc}')

    handler = partial(SimpleHTTPRequestHandler, directory=dist)
    try:
        with ThreadingHTTPServer((args.host, args.port), handler) as server:
            server.socket = tls.wrap_socket(
                server.socket, server_side=True, do_handshake_on_connect=False
            )
            print(f'Phaser HTTPS: https://{args.host}:{server.server_port}/', flush=True)
            server.serve_forever()
    except OSError as exc:
        parser.exit(1, f'无法启动 HTTPS 服务：{exc}\n')
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
