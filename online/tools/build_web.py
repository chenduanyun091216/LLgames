#!/usr/bin/env python3
"""Build original Pygbag renderer and vendored runtime, exclusively under online/."""
import argparse
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONLINE = ROOT / 'online'


def configured_builder():
    spec = importlib.util.spec_from_file_location('llonline_web_builder', ROOT / 'web/run_web.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.BUILD = ONLINE / 'build'
    builder.WEB_BUILD_DIR = ONLINE / '.web-build'
    builder.TLS_DIR = builder.WEB_BUILD_DIR / 'tls'
    builder.STAGING = builder.WEB_BUILD_DIR / 'ttgames'
    builder.RESOURCE_CACHE = builder.WEB_BUILD_DIR / 'resources'
    builder.WEBROOT = builder.BUILD / 'web'
    builder.MANIFEST = builder.BUILD / '.manifest.json'
    builder.SHELL_FILES = tuple(ONLINE / 'web' / name for name in ('shell.css','shell.js','sw.js'))
    return builder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Rebuild (the default; cache downloads are reused)')
    parser.parse_args()
    b = configured_builder()
    b.prepare_sources()
    shutil.copy2(ONLINE / 'client/main.py', b.STAGING / 'main.py')
    package = b.STAGING / 'online'
    package.mkdir()
    (package / '__init__.py').write_text('')
    for name in ('adapters','shared'):
        if (ONLINE / name).is_dir():
            shutil.copytree(ONLINE / name, package / name, ignore=shutil.ignore_patterns('__pycache__'))
    output = b.build_pygbag()
    b.finalize_webroot(output)
    # Transport is loaded before the deferred shell; no service worker or CDN requests at run time.
    shutil.copy2(ONLINE / 'web/bridge.js', b.WEBROOT / 'bridge.js')
    index = b.WEBROOT / 'index.html'
    html = index.read_text()
    html = html.replace('<head>', '<head><script src="bridge.js"></script>')
    index.write_text(html)
    print(f'Online web build: {b.WEBROOT}')


if __name__ == '__main__':
    main()
