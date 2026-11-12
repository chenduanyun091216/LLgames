#!/usr/bin/env python3
"""构建离线浏览器版并在局域网提供服务。"""
import argparse
import gzip
import hashlib
import json
import os
import signal
import time
import errno
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import urllib.request
import re
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
WEB_BUILD_DIR = ROOT / '.web-build'
TLS_DIR = WEB_BUILD_DIR / 'tls'
STAGING = WEB_BUILD_DIR / 'ttgames'
RESOURCE_CACHE = WEB_BUILD_DIR / 'resources'
WEBROOT = BUILD / 'web-offline'
MANIFEST = BUILD / '.web-offline-manifest.json'
PYGBAG_VERSION = '0.9.3'
PYBUILD = '3.12'
CDN_COMMIT = '3aa22420805e9b1603a6b950ffae45d6560fac09'
CDN_URL = f'https://pygame-web.github.io/cdn/{PYGBAG_VERSION}/'
CDN_RAW_URL = f'https://raw.githubusercontent.com/pygame-web/cdn/{CDN_COMMIT}/'
PYGBAG_SOURCE_COMMIT = 'df678453b3c9090f1ba659a0a8f740b4437ad8d3'
PYGBAG_RAW_URL = f'https://raw.githubusercontent.com/pygame-web/pygbag/{PYGBAG_SOURCE_COMMIT}/'
FONT_URL = 'https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf'
FONT_LICENSE_URL = 'https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE'
WEB_SOURCE = ROOT / 'web'
GAME_SOURCE = ROOT / 'game_core'
IMAGE_SOURCE = ROOT / 'assets' / 'images'
CUTSCENE_SOURCES = tuple(ROOT / 'assets' / name for name in ('opening', 'ending'))
SOURCE_FILES = tuple(sorted(GAME_SOURCE.glob('*.py')))
SHELL_FILES = tuple(WEB_SOURCE / name for name in ('shell.css', 'shell.js', 'sw.js'))
PYGAME_WHEEL = 'cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl'
PACKAGE_INDEX = f'index-{PYGBAG_VERSION}-cp{PYBUILD.replace(".", "")}.json'
RUNTIME_VERSION = hashlib.sha256(
    f'{CDN_COMMIT}:{PYGBAG_SOURCE_COMMIT}:{PYGAME_WHEEL}:local-index-v1'.encode()
).hexdigest()[:16]
RUNTIME_PATH = f'runtime-{RUNTIME_VERSION}/cdn'
CDN_FILES = (
    PYGAME_WHEEL,
    '0.9.3/cpython312/main.data', '0.9.3/cpython312/main.js', '0.9.3/cpython312/main.wasm',
    '0.9.3/cpythonrc.py', '0.9.3/default.tmpl', '0.9.3/empty.html', '0.9.3/empty.ogg',
    '0.9.3/favicon.png', '0.9.3/index.html', '0.9.3/pythons.html', '0.9.3/pythons.js',
    'lib/dlfcn.js', 'lib/index.html', 'lib/main.html', 'lib/sub.html',
    'lib/enginesound/engine.js', 'lib/enginesound/engine.ogg', 'lib/enginesound/index.html',
    'lib/espeak/index.html', 'lib/espeak/speakClient.js', 'lib/espeak/speakGenerator.js', 'lib/espeak/speakWorker.js',
)


def source_manifest():
    entries = []
    paths = [*SOURCE_FILES, *SHELL_FILES, Path(__file__), ROOT / 'requirements.txt']
    paths.extend(sorted(IMAGE_SOURCE.rglob('*.png')))
    for source in CUTSCENE_SOURCES:
        paths.extend(sorted(path for path in source.iterdir() if path.is_file()))
    for path in paths:
        stat = path.stat()
        entries.append([str(path.relative_to(ROOT)), stat.st_size, stat.st_mtime_ns])
    return {
        'pygbag': PYGBAG_VERSION, 'python': PYBUILD, 'cdn': CDN_COMMIT,
        'pygbag_source': PYGBAG_SOURCE_COMMIT, 'files': entries,
    }


def download(url, target, min_size):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size >= min_size:
        return
    print(f'下载构建资源：{url}')
    request = urllib.request.Request(url, headers={'User-Agent': 'TTgames-web-builder'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, target.open('wb') as output:
            shutil.copyfileobj(response, output)
    except OSError:
        target.unlink(missing_ok=True)
        curl = shutil.which('curl')
        if not curl:
            raise
        subprocess.run([
            curl, '--fail', '--location', '--silent', '--show-error', '--retry', '3',
            '--retry-all-errors', '--connect-timeout', '15', '--max-time', '300',
            '--output', str(target), url,
        ], check=True)
    if target.stat().st_size < min_size:
        target.unlink(missing_ok=True)
        raise RuntimeError(f'下载文件不完整：{target}')


def _atlas_layout(image, name):
    if name == 'anim_boss_ancient_whale':
        return 8, 6, 448
    if name == 'anim_boss_orochi_idle':
        return 6, 4, 624
    if name == 'anim_boss_orochi_split':
        return 4, 3, 384
    if re.fullmatch(r'anim_boss_(lobster|crab|octopus|shark|dragon)_(attack|laser)', name):
        return max(1, image.width // image.height), 1, 512
    return max(1, image.width // image.height), 1, 384


def _resize_atlas(image, columns, rows, max_edge):
    from PIL import Image

    width, height = image.width // columns, image.height // rows
    if max(width, height) <= max_edge:
        return image
    scale = max_edge / max(width, height)
    size = max(1, round(width * scale)), max(1, round(height * scale))
    atlas = Image.new('RGBA', (size[0] * columns, size[1] * rows))
    for row in range(rows):
        for column in range(columns):
            frame = image.crop((column * width, row * height,
                                (column + 1) * width, (row + 1) * height))
            atlas.paste(frame.resize(size, Image.Resampling.LANCZOS),
                        (column * size[0], row * size[1]))
    return atlas


DEFAULT_ASSET_SCALE = 0.75


def prepare_image(path, target_images, hd_images):
    from PIL import Image

    background = re.fullmatch(r'bg[0-9]+|background', path.stem)
    atlas = path.stem.startswith('anim_')
    # UI icons are small on both tiers. A single copy also keeps the startup title shared.
    limits = {'enemies': 512, 'players': 512, 'bosses': 1024, 'effects': 768,
              'weapons': 384, 'ui': 1280, 'animations': 768}
    name = path.with_suffix('.jpg').name if background else path.name
    with Image.open(path) as source:
        original = source.convert('RGB' if background else 'RGBA')
        if background:
            max_size = (1600, 2400) if source.height > source.width else (2160, 2160)
        elif atlas:
            columns, rows, edge = _atlas_layout(source, path.stem)
        else:
            limit = 512 if path.name == 'coin.png' else limits.get(path.parent.name)
            max_size = (limit, limit) if limit else source.size

        previous_size = None
        default_scale = 1 if path.parent.name in ('ui', 'weapons') else DEFAULT_ASSET_SCALE
        variants = [(target_images, default_scale)]
        if default_scale < 1:
            variants.append((hd_images, 1))
        for directory, scale in variants:
            if atlas:
                image = _resize_atlas(original, columns, rows, round(edge * scale))
            else:
                image = original.copy()
                image.thumbnail(tuple(round(value * scale) for value in max_size), Image.Resampling.LANCZOS)
            if image.size == previous_size:
                continue
            previous_size = image.size
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / name
            if background:
                image.save(target, quality=94, subsampling=0, optimize=True)
            elif image.size == source.size:
                shutil.copy2(path, target)
            else:
                options = {'icc_profile': source.info['icc_profile']} if 'icc_profile' in source.info else {}
                image.save(target, optimize=True, **options)


def prepare_sources():
    # Windows can keep the staging directory open even when its contents can be removed.
    if STAGING.is_symlink() or STAGING.is_junction():
        raise RuntimeError(f'构建暂存目录不能是链接：{STAGING}')
    STAGING.mkdir(parents=True, exist_ok=True)
    for path in STAGING.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    package = STAGING / GAME_SOURCE.name
    package.mkdir()
    for source in SOURCE_FILES:
        shutil.copy2(source, package / source.name)
    (STAGING / 'main.py').write_text(
        'import asyncio\nimport pygame\nfrom game_core.main import main\nasyncio.run(main())\n', encoding='utf-8')
    target_images = STAGING / 'assets' / 'images'
    target_images.mkdir(parents=True)
    hd_images = STAGING / 'assets' / 'images-hd'
    # Downsample shared originals for browser decoding while keeping sprite alpha lossless.
    for path in sorted(IMAGE_SOURCE.rglob('*.png')):
        if path.stem.startswith('ui_'):
            continue  # The web UI does not load these desktop assets.
        category = path.parent.relative_to(IMAGE_SOURCE)
        prepare_image(path, target_images / category, hd_images / category)
    for source in CUTSCENE_SOURCES:
        shutil.copytree(source, STAGING / 'assets' / source.name)
    font_dir = STAGING / 'assets' / 'fonts'
    cached_font_dir = RESOURCE_CACHE / 'fonts'
    download(FONT_URL, cached_font_dir / 'NotoSansCJKsc-Regular.otf', 1_000_000)
    download(FONT_LICENSE_URL, cached_font_dir / 'OFL.txt', 500)
    shutil.copytree(cached_font_dir, font_dir, dirs_exist_ok=True)
    from fontTools import subset
    # Include all source characters plus basic Latin used by dynamic HUD numbers.
    text = ''.join(path.read_text(encoding='utf-8') for path in SOURCE_FILES)
    options = subset.Options()
    font = subset.load_font(str(font_dir / 'NotoSansCJKsc-Regular.otf'), options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=text + ''.join(chr(code) for code in range(32, 127)))
    subsetter.subset(font)
    subset.save_font(font, str(font_dir / 'NotoSansCJKsc-Regular.otf'), options)
    font.close()
    template = RESOURCE_CACHE / 'default.tmpl'
    download(CDN_RAW_URL + f'{PYGBAG_VERSION}/default.tmpl', template, 10_000)
    shutil.copy2(template, STAGING / 'default.tmpl')


def build_pygbag():
    try:
        import pygbag
    except ImportError as exc:
        raise RuntimeError('缺少网页构建器，请在项目根目录执行 python -m pip install -r requirements.txt') from exc
    if pygbag.VERSION != PYGBAG_VERSION:
        raise RuntimeError(f'需要 pygbag=={PYGBAG_VERSION}，当前是 {pygbag.VERSION}')
    command = [
        sys.executable, '-m', 'pygbag', '--build', '--PYBUILD', PYBUILD,
        '--cdn', CDN_URL, '--template', 'default.tmpl', '--can_close', '1',
        '--icon', 'assets/images/ui/title.png', '--title', '海洋生物入侵', '.',
    ]
    subprocess.run(command, cwd=STAGING, check=True)
    result = STAGING / 'build' / 'web'
    if not (result / 'index.html').is_file():
        raise RuntimeError(f'Pygbag 没有生成预期文件：{result / "index.html"}')
    return result


def package_runtime():
    for relative_path in CDN_FILES:
        minimum_size = 1_000_000 if relative_path.endswith(('.wasm', '.data')) else 1
        cached = RESOURCE_CACHE / 'cdn' / relative_path
        download(CDN_RAW_URL + relative_path, cached, minimum_size)
        target = WEBROOT / RUNTIME_PATH / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, target)
    cached = RESOURCE_CACHE / 'cdn' / PYGBAG_VERSION / 'browserfs.min.js'
    download(PYGBAG_RAW_URL + 'static/browserfs.min.js', cached, 10_000)
    target = WEBROOT / RUNTIME_PATH / PYGBAG_VERSION / 'browserfs.min.js'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, target)
    runtime = WEBROOT / RUNTIME_PATH
    (runtime / PACKAGE_INDEX).write_text(json.dumps({'-CDN-': './', 'pygame': PYGAME_WHEEL}),
                                         encoding='utf-8')
    pyrc = runtime / PYGBAG_VERSION / 'cpythonrc.py'
    source = pyrc.read_text(encoding='utf-8')
    anchor = '        from platform import window, document, ffi'
    if source.count(anchor) != 1:
        raise RuntimeError('Pygbag 本地索引插入点已变更')
    pyrc.write_text(source.replace(anchor, anchor +
        '\n        from urllib.parse import urljoin\n'
        f'        os.environ["PYGPI"] = urljoin(str(window.location.href), "{RUNTIME_PATH}/")'),
        encoding='utf-8')


def finalize_webroot(pygbag_output):
    shutil.rmtree(WEBROOT, ignore_errors=True)
    shutil.copytree(pygbag_output, WEBROOT)
    html = (WEBROOT / 'index.html').read_text(encoding='utf-8')
    cdn = f'{RUNTIME_PATH}/{PYGBAG_VERSION}/'
    html = html.replace(CDN_URL, cdn).replace(f'{cdn}/browserfs.min.js', f'{cdn}browserfs.min.js')
    # Fetch and compile pygame while the game archive is downloading; only then invite the first tap.
    html = html.replace('    bundle = "ttgames"', '    from aio import pep0723\n'
                        '    pygame_ready = asyncio.create_task(pep0723.pip_install("pygame"))\n'
                        '    bundle = "ttgames"')
    html = html.replace('    # test/wait user media interaction',
                        '    await pygame_ready\n    import pygame\n'
                        '    if not hasattr(pygame, "init"):\n'
                        '        raise RuntimeError("Local pygame runtime did not load")\n\n'
                        '    # test/wait user media interaction')
    html = html.replace(f'src="{cdn}empty.html"', 'src="about:blank"')
    html = html.replace('data-os="vtx,snd,gui"', 'data-os="snd,gui"')
    html = html.replace('user_canvas : 0,', 'user_canvas : 1,')
    html = html.replace('<html lang="en-us">', '<html lang="zh-CN">')
    html = re.sub(r'<meta name="viewport"[^>]*>', '', html)
    html = html.replace('Loading, please wait ...', '正在加载游戏…')
    html = html.replace('    bundle = "ttgames"',
                        '    platform.window.ttgamesLoadStage(1)\n    bundle = "ttgames"')
    html = html.replace('    # preloader will change',
                        '    platform.window.ttgamesLoadStage(2)\n    # preloader will change')
    html = html.replace('    # test/wait user media interaction',
                        '    platform.window.ttgamesLoadStage(3)\n    # test/wait user media interaction')
    html = html.replace('<div id="infobox">正在加载游戏…</div>',
                        '<div id="infobox">正在加载游戏…</div>'
                        '<div id="ttgames-loading"><progress max="100" value="0" aria-label="游戏加载进度（估计）"></progress>'
                        '<div class="loading-details"><span class="loading-status" role="status">正在加载浏览器运行环境</span>'
                        '<span class="loading-percent">约 0%</span></div></div>')

    html = html.replace('platform.document.body.style.background = "#7f7f7f"', 'pass')
    shell_names = {}
    for path in SHELL_FILES[:2]:
        payload = path.read_bytes()
        name = f'{path.stem}-{hashlib.sha256(payload).hexdigest()[:16]}{path.suffix}'
        (WEBROOT / name).write_bytes(payload)
        shell_names[path.suffix] = name
    html = html.replace('</head>',
                        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                        f'<link rel="stylesheet" href="{shell_names[".css"]}">'
                        f'<script defer src="{shell_names[".js"]}"></script></head>')
    html = html.replace('</body>', '<canvas id="ttgames-ui" aria-hidden="true"></canvas>'
                        '<div id="ttgames-offline" role="status"></div>'
                        '<button id="ttgames-fullscreen" type="button" aria-label="进入全屏" title="进入全屏">⛶</button>'
                        '<details id="ttgames-quality" hidden><summary aria-label="画质设置" title="画质设置">⚙</summary>'
                        '<fieldset><legend>画质设置</legend>'
                        '<label><input type="radio" name="quality" value="1.5">标准 <span></span></label>'
                        '<label><input type="radio" name="quality" value="1.75" checked>默认 <span></span></label>'
                        '<label><input type="radio" name="quality" value="2">高清 <span></span></label>'
                        '</fieldset></details></body>')
    from PIL import Image
    with Image.open(WEBROOT / 'favicon.png') as icon:
        icon.thumbnail((96, 96), Image.Resampling.LANCZOS)
        icon.save(WEBROOT / 'favicon.png', optimize=True)
    remote_resources = [
        token for token in ('src="http://', 'src="https://', 'href="http://', 'href="https://')
        if token in html
    ]
    if remote_resources:
        raise RuntimeError(f'网页入口仍引用外部资源：{remote_resources}')
    archive = WEBROOT / 'ttgames.tar.gz'
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
    archive.rename(WEBROOT / f'ttgames-{digest}.tar.gz')
    html = html.replace('ttgames.tar.gz', f'ttgames-{digest}.tar.gz')
    (WEBROOT / 'index.html').write_text(html, encoding='utf-8')
    for unused_archive in WEBROOT.glob('*.apk'):
        unused_archive.unlink()
    package_runtime()
    for path in (WEBROOT / RUNTIME_PATH).rglob('*'):
        if path.suffix in ('.wasm', '.data', '.js', '.py'):
            path.with_name(path.name + '.gz').write_bytes(gzip.compress(path.read_bytes(), compresslevel=6, mtime=0))
    precache = [
        './', 'favicon.png', *shell_names.values(), f'ttgames-{digest}.tar.gz',
        f'{RUNTIME_PATH}/{PACKAGE_INDEX}', f'{RUNTIME_PATH}/{PYGAME_WHEEL}',
        *(cdn + name for name in ('pythons.js', 'browserfs.min.js', 'cpythonrc.py', 'empty.ogg',
                                  f'cpython{PYBUILD.replace(".", "")}/main.js',
                                  f'cpython{PYBUILD.replace(".", "")}/main.wasm',
                                  f'cpython{PYBUILD.replace(".", "")}/main.data')),
    ]
    sw = SHELL_FILES[2].read_text(encoding='utf-8')
    version = hashlib.sha256(html.encode() + sw.encode()).hexdigest()[:16]
    sw = sw.replace('__BUILD_VERSION__', version).replace('__PRECACHE__', json.dumps(precache))
    (WEBROOT / 'sw.js').write_text(sw, encoding='utf-8')
    manifest = source_manifest()
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


class OfflineHandler(SimpleHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # The client closed the connection during request or response I/O.
            self.close_connection = True
        except ssl.SSLError as exc:
            if exc.reason not in ('SSLV3_ALERT_CERTIFICATE_UNKNOWN', 'TLSV1_ALERT_UNKNOWN_CA'):
                raise
            self.close_connection = True
            self.log_error('客户端拒绝了 HTTPS 证书，已关闭本次连接（%s）', exc.reason)

    def send_head(self):
        self._gzip_response = False
        self._resource_path = urlsplit(self.path).path
        original_path = self.path
        encodings = {}
        for entry in self.headers.get('Accept-Encoding', '').lower().split(','):
            name, _, quality = entry.partition(';')
            encodings[name.strip()] = quality.partition('=')[2].strip() if quality else '1'
        try:
            accepts_gzip = float(encodings.get('gzip', encodings.get('*', '0'))) > 0
        except ValueError:
            accepts_gzip = False
        if accepts_gzip:
            compressed_path = self._resource_path + '.gz'
            compressed = Path(self.translate_path(compressed_path))
            if compressed.is_file() and not self._resource_path.endswith('.tar.gz'):
                self.path = compressed_path
                self._gzip_response = True
        try:
            return super().send_head()
        finally:
            self.path = original_path

    def end_headers(self):
        path = getattr(self, '_resource_path', '')
        versioned = (re.search(r'/runtime-[0-9a-f]{16}/cdn/', path) or
                     re.search(r'/(?:ttgames|shell)-[0-9a-f]{16}\.(?:tar\.gz|js|css)$', path))
        # Apply immutable only to resources that exist; a missing deployment file must stay retryable.
        cache = ('public, max-age=31536000, immutable'
                 if versioned and Path(self.translate_path(path)).is_file() else 'no-cache')
        self.send_header('Cache-Control', cache)
        self.send_header('Vary', 'Accept-Encoding')
        if getattr(self, '_gzip_response', False):
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def guess_type(self, path):
        if path.endswith('.gz'):
            path = path[:-3]
        if path.endswith('.wasm'):
            return 'application/wasm'
        return super().guess_type(path)


class SetupHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, page, certificate):
        self.routes = {
            '/': ('text/html; charset=utf-8', page),
            '/rootCA.cer': ('application/x-x509-ca-cert', certificate),
        }
        super().__init__(*args)

    def do_HEAD(self):
        response = self.routes.get(self.path)
        if response is None:
            self.send_error(404)
            return None
        content_type, payload = response
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        return payload

    def do_GET(self):
        payload = self.do_HEAD()
        if payload is not None:
            self.wfile.write(payload)


def lan_addresses(cert=None):
    if cert is not None:
        # CPython 的证书解析可读取已签发的 IP，避免主机名解析只返回虚拟网卡。
        try:
            names = ssl._ssl._test_decode_cert(os.fspath(cert)).get('subjectAltName', ())
        except (OSError, ValueError):
            names = ()
        signed_addresses = {
            address for kind, address in names
            if kind == 'IP Address' and ':' not in address and not address.startswith('127.')
        }
        if signed_addresses:
            return sorted(signed_addresses)

    addresses = set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = result[4][0]
            if not address.startswith('127.'):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def release_port(port):
    """启动前强制结束指定 TCP 端口的监听进程，不依赖终端密码输入。"""
    if sys.platform == 'win32':
        return  # Windows 直接绑定端口，端口占用时由系统报告。
    try:
        result = subprocess.run(
            ['lsof', '-t', f'-iTCP:{port}', '-sTCP:LISTEN'],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'无法检查端口 {port}，请确认 lsof 可用且有执行权限') from exc
    if result.returncode not in (0, 1):
        raise RuntimeError(f'lsof 检查端口 {port} 失败：{result.stderr.strip()}')
    for pid in sorted({int(value) for value in result.stdout.split()}):
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise RuntimeError(f'没有权限结束占用端口 {port} 的进程 {pid}，请手动结束该进程') from exc
        print(f'已结束占用端口 {port} 的进程：{pid}')


def serve(host, port, tls=None, setup_port=8000, setup_certificate=None, cert=None):
    release_port(port)
    handler = partial(OfflineHandler, directory=str(WEBROOT))
    # SIGKILL 已发送后，给操作系统最多一秒释放监听套接字。
    for attempt in range(21):
        try:
            server = ThreadingHTTPServer((host, port), handler)
            break
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE or attempt == 20:
                raise
            time.sleep(0.05)
    scheme = 'https' if tls else 'http'
    setup_server = setup_thread = None
    try:
        if tls:
            server.socket = tls.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        if tls and setup_certificate is not None:
            page = (WEB_SOURCE / 'setup.html').read_text(encoding='utf-8')
            page = page.replace('__GAME_PORT__', str(server.server_port)).encode('utf-8')
            setup_handler = partial(SetupHandler, page=page, certificate=setup_certificate)
            setup_server = ThreadingHTTPServer((host, setup_port), setup_handler)
            setup_thread = threading.Thread(target=setup_server.serve_forever)
            setup_thread.start()
            print(f'证书安装入口本机地址：http://127.0.0.1:{setup_server.server_port}/')
        print(f'浏览器游戏本机地址：{scheme}://127.0.0.1:{server.server_port}/')
        for address in lan_addresses(cert):
            if setup_server:
                print(f'1. 首次安装证书 → http://{address}:{setup_server.server_port}/')
                print(f'2. 打开游戏 → {scheme}://{address}:{server.server_port}/')
            else:
                print(f'打开游戏 → {scheme}://{address}:{server.server_port}/')
        print('按 Ctrl+C 停止服务。')
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n网页服务已停止。')
    finally:
        server.server_close()
        if setup_server:
            if setup_thread.is_alive():
                setup_server.shutdown()
                setup_thread.join()
            setup_server.server_close()


def main():
    parser = argparse.ArgumentParser(description='构建并通过局域网 HTTPS 提供 TTgames 手机网页版本')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--force', action='store_true', help='强制重新构建网页资源')
    parser.add_argument('--cert', type=Path, default=TLS_DIR / 'cert.pem', help='HTTPS PEM 证书路径')
    parser.add_argument('--key', type=Path, default=TLS_DIR / 'key.pem', help='HTTPS PEM 私钥路径')
    parser.add_argument('--setup-port', type=int, default=8000, help='证书安装入口的 HTTP 端口')
    parser.add_argument('--setup-ca', type=Path, help='供手机安装的根 CA 公共 PEM 证书')
    parser.add_argument('--http', action='store_true', help='使用普通 HTTP 调试，或在 HTTPS 反向代理后运行')
    args = parser.parse_args()

    tls = None
    setup_certificate = None
    if not args.build_only and not args.http:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            tls.load_cert_chain(args.cert, args.key, password=lambda: b'')
        except OSError as exc:
            parser.error(f'无法加载 HTTPS 证书或私钥：{exc}。请按 docs/网页版使用与部署.md 配置证书，或用 --http 调试。')
        ca = args.setup_ca
        if ca is None and args.cert.resolve() == (TLS_DIR / 'cert.pem').resolve():
            local_ca = TLS_DIR / 'rootCA.pem'
            if local_ca.is_file():
                ca = local_ca
        if ca is not None:
            try:
                pem = ca.read_text(encoding='ascii').strip()
                if not re.fullmatch(r'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----', pem):
                    raise ValueError('必须提供单个公共 PEM 证书')
                ssl.create_default_context(cadata=pem)
                setup_certificate = ssl.PEM_cert_to_DER_cert(pem)
            except (OSError, ValueError) as exc:
                parser.error(f'无法加载供下载的根证书：{exc}')

    current = source_manifest()
    if args.force or not (WEBROOT / 'index.html').is_file() or not MANIFEST.is_file():
        needs_build = True
    else:
        try:
            needs_build = json.loads(MANIFEST.read_text(encoding='utf-8')) != current
        except (OSError, json.JSONDecodeError):
            needs_build = True
    if needs_build:
        prepare_sources()
        pygbag_output = build_pygbag()
        finalize_webroot(pygbag_output)
    else:
        print('复用已构建的离线网页包。')
    if not args.build_only:
        serve(args.host, args.port, tls, args.setup_port, setup_certificate,
              cert=args.cert if tls else None)


if __name__ == '__main__':
    main()
