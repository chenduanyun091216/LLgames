import gzip
import socket
import ssl
import struct
import tempfile
import threading
import unittest
import urllib.request
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from web.run_web import OfflineHandler, SetupHandler, prepare_image


class WebServerTests(unittest.TestCase):
    def test_tls_certificate_rejection_logs_without_traceback(self):
        handler = OfflineHandler.__new__(OfflineHandler)
        error = ssl.SSLError('certificate unknown')
        error.reason = 'SSLV3_ALERT_CERTIFICATE_UNKNOWN'
        with patch.object(SimpleHTTPRequestHandler, 'handle', side_effect=error), \
                patch.object(handler, 'log_error') as log_error:
            handler.handle()
            self.assertTrue(handler.close_connection)
            log_error.assert_called_once()
            error.reason = 'UNEXPECTED_MESSAGE'
            with self.assertRaises(ssl.SSLError):
                handler.handle()

    def test_setup_serves_only_guide_and_public_certificate(self):
        handler = partial(SetupHandler, page=b'guide', certificate=b'public certificate')
        with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                with urllib.request.urlopen(base + '/') as response:
                    self.assertEqual(response.read(), b'guide')
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                with urllib.request.urlopen(base + '/rootCA.cer') as response:
                    self.assertEqual(response.headers.get_content_type(), 'application/x-x509-ca-cert')
                    self.assertEqual(response.read(), b'public certificate')
                for path in ('/key.pem', '/rootCA-key.pem', '/index.html', '/sw.js'):
                    with self.assertRaises(urllib.error.HTTPError) as missing:
                        urllib.request.urlopen(base + path)
                    self.assertEqual(missing.exception.code, 404)
            finally:
                server.shutdown()
                worker.join()

    def test_web_images_downsample_sprite_frames_and_bound_background_size(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source_size, default_size, hd_size in (
                ('anim_player1_run.png', (2880, 720), (1152, 288), (1536, 384)),
                ('bg1.png', (2880, 720), (1620, 405), (2160, 540)),
                ('bg2.png', (1920, 2880), (1200, 1800), (1600, 2400)),
            ):
                source = root / name
                Image.new('RGBA', source_size, (10, 20, 30, 150)).save(source)
                output = root / 'output'
                output.mkdir(exist_ok=True)
                hd_output = root / 'hd'
                prepare_image(source, output, hd_output)
                filename = source.with_suffix('.jpg').name if name.startswith('bg') else name
                for directory, expected_size in ((output, default_size), (hd_output, hd_size)):
                    with Image.open(directory / filename) as image:
                        self.assertEqual(image.size, expected_size)
                        if name.startswith('anim'):
                            self.assertEqual(image.getpixel((0, 0)), (10, 20, 30, 150))
                with Image.open(source) as image:
                    self.assertEqual(image.size, source_size)

    def test_web_atlas_preserves_each_frame_without_blending_into_its_neighbor(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'anim_boss_ancient_whale.png'
            original = Image.new('RGBA', (2048, 2012))
            colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 150), (0, 0, 0, 0)]
            for index, color in enumerate(colors):
                x, y = index % 2 * 1024, index // 2 * 1006
                original.paste(color, (x, y, x + 1024, y + 1006))
            original.save(source)
            output = root / 'output'
            output.mkdir()
            hd_output = root / 'hd'
            prepare_image(source, output, hd_output)
            with Image.open(hd_output / source.name) as image:
                self.assertEqual(image.size, (1536, 1508))
                for index, color in enumerate(colors):
                    x, y = index % 2 * 768, index // 2 * 754
                    frame = image.crop((x, y, x + 768, y + 754))
                    self.assertEqual(frame.getextrema(), tuple((value, value) for value in color))
            with Image.open(source) as image:
                self.assertEqual(image.size, original.size)

    def test_client_reset_during_request_line_is_quiet(self):
        connected = threading.Event()

        class ResetHandler(OfflineHandler):
            def setup(self):
                super().setup()
                connected.set()

        with HTTPServer(('127.0.0.1', 0), ResetHandler) as server, patch.object(server, 'handle_error') as log_error:
            server.timeout = 3
            with socket.create_connection(server.server_address, timeout=3) as client:
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                worker = threading.Thread(target=server.handle_request)
                worker.start()
                self.assertTrue(connected.wait(3))
                client.sendall(b'GET / HTTP/1.1')
            worker.join(3)
            self.assertFalse(worker.is_alive())
            log_error.assert_not_called()

    def test_runtime_compression_and_cache_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = b'wasm-runtime' * 100
            path = Path(directory) / 'main.wasm'
            path.write_bytes(payload)
            path.with_suffix('.wasm.gz').write_bytes(gzip.compress(payload))
            server = ThreadingHTTPServer(('127.0.0.1', 0),
                                         partial(OfflineHandler, directory=directory))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                url = f'http://127.0.0.1:{server.server_port}/main.wasm'
                request = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip'})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.headers['Content-Type'], 'application/wasm')
                    self.assertEqual(response.headers['Content-Encoding'], 'gzip')
                    self.assertEqual(response.headers['Cache-Control'], 'no-cache')
                    modified = response.headers['Last-Modified']
                    self.assertEqual(gzip.decompress(response.read()), payload)
                with urllib.request.urlopen(url) as response:
                    self.assertIsNone(response.headers['Content-Encoding'])
                    self.assertEqual(response.read(), payload)
                request.add_header('If-Modified-Since', modified)
                with self.assertRaises(urllib.error.HTTPError) as result:
                    urllib.request.urlopen(request)
                self.assertEqual(result.exception.code, 304)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


    def test_versioned_files_cache_without_caching_html_or_missing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('index.html', 'sw.js', 'ttgames-0123456789abcdef.tar.gz',
                         'shell-0123456789abcdef.css', 'runtime-0123456789abcdef/cdn/main.wasm'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'payload')
            wasm = root / 'runtime-0123456789abcdef/cdn/main.wasm.gz'
            wasm.write_bytes(gzip.compress(b'payload'))
            handler = partial(OfflineHandler, directory=directory)
            with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
                worker = threading.Thread(target=server.serve_forever)
                worker.start()
                try:
                    base = f'http://127.0.0.1:{server.server_port}/'
                    for name in ('', 'index.html', 'sw.js'):
                        with urllib.request.urlopen(base + name) as response:
                            self.assertEqual(response.headers['Cache-Control'], 'no-cache')
                    for name in ('ttgames-0123456789abcdef.tar.gz', 'shell-0123456789abcdef.css',
                                 'runtime-0123456789abcdef/cdn/main.wasm?check=1'):
                        request = urllib.request.Request(base + name, headers={'Accept-Encoding': 'gzip;q=0'})
                        with urllib.request.urlopen(request) as response:
                            self.assertIn('immutable', response.headers['Cache-Control'])
                            self.assertIsNone(response.headers['Content-Encoding'])
                    request = urllib.request.Request(base + 'runtime-0123456789abcdef/cdn/main.wasm?check=1',
                                                     headers={'Accept-Encoding': 'gzip'})
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(response.headers['Content-Encoding'], 'gzip')
                        self.assertEqual(gzip.decompress(response.read()), b'payload')
                    with self.assertRaises(urllib.error.HTTPError) as missing:
                        urllib.request.urlopen(base + 'ttgames-9999999999999999.tar.gz')
                    self.assertEqual(missing.exception.code, 404)
                    self.assertEqual(missing.exception.headers['Cache-Control'], 'no-cache')
                finally:
                    server.shutdown()
                    worker.join()


class WindowsPortTests(unittest.TestCase):
    def test_windows_does_not_run_posix_port_cleanup(self):
        from web.run_web import release_port
        with patch('web.run_web.sys.platform', 'win32'), \
                patch('web.run_web.subprocess.run') as run, patch('web.run_web.os.kill') as kill:
            release_port(8000)
        run.assert_not_called()
        kill.assert_not_called()


@patch('web.run_web.sys.platform', 'linux')
@patch('web.run_web.signal.SIGKILL', 9, create=True)
class PortCleanupTests(unittest.TestCase):
    def test_kills_only_listening_processes_on_requested_port(self):
        import signal
        from unittest.mock import patch
        from web.run_web import release_port
        with patch('web.run_web.subprocess.run') as run, \
                patch('web.run_web.os.kill') as kill:
            run.return_value.returncode = 0
            run.return_value.stdout = '12345\n12345\n'
            release_port(8000)
        self.assertEqual(run.call_args.args[0],
                         ['lsof', '-t', '-iTCP:8000', '-sTCP:LISTEN'])
        kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_missing_lsof_and_permission_errors_are_explicit(self):
        from unittest.mock import patch
        from web.run_web import release_port
        with patch('web.run_web.subprocess.run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, 'lsof'):
                release_port(8000)
        with patch('web.run_web.subprocess.run') as run, \
                patch('web.run_web.os.kill', side_effect=PermissionError):
            run.return_value.returncode = 0
            run.return_value.stdout = '12345\n'
            with self.assertRaisesRegex(RuntimeError, '权限'):
                release_port(8000)

    def test_process_that_already_exited_is_ignored(self):
        from unittest.mock import patch
        from web.run_web import release_port
        with patch('web.run_web.subprocess.run') as run, \
                patch('web.run_web.os.kill', side_effect=ProcessLookupError):
            run.return_value.returncode = 0
            run.return_value.stdout = '12345\n'
            release_port(8000)
