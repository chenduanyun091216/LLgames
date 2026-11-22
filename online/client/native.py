"""Native LAN transport and child-process ownership."""
import asyncio
import contextlib
import errno
import json
import os
import secrets
import ssl
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import aiohttp

from online.shared.protocol import UNIFIED_VERSION


class NativeTransport:
    def __init__(self):
        self.session = None
        self.connection = None
        self.socket = None
        self.ended = False
        self.state = None
        self.slot = 0
        self.seq = 0
        self.error = ''
        self.address = ''
        self.host = None
        self.host_task = None
        self.origin = ''
        self.local_tls = None
        self.orientation = 'landscape'
        self.hidden = False
        self.invite = ''
        self.leave_id = None
        self.create_id = None

    async def start_host(self):
        from web.run_web import GAME_PORT, TLS_DIR

        origin = f'https://127.0.0.1:{GAME_PORT}'
        try:
            ca = TLS_DIR / 'rootCA.pem'
            self.local_tls = ssl.create_default_context(cafile=ca if ca.is_file() else None)
            if await self.use_local_host(origin):
                return
            command = [sys.executable, '--lan-host'] if '__compiled__' in globals() or getattr(sys, 'frozen', False) else [
                sys.executable, '-m', 'online.server.serve']
            self.host = await asyncio.create_subprocess_exec(
                *command, cwd=Path(__file__).resolve().parents[2], stdout=asyncio.subprocess.PIPE,
                env=dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT='1'))
            info = json.loads(await asyncio.wait_for(self.host.stdout.readline(), 10))
            if error := info.get('error'):
                if not await self.use_local_host(origin):
                    self.address = error
                return
            if not await self.use_local_host(origin):
                raise ValueError('联机网页服务未就绪')
        except (OSError, TimeoutError, ValueError, aiohttp.ClientError) as exc:
            self.address = f'联机服务启动失败：{exc}'

    async def use_local_host(self, origin):
        try:
            async with self.http().get(origin + '/health', ssl=self.local_tls) as response:
                if not response.ok:
                    raise ValueError('8001 未运行 TTgames 联机服务')
                info = await response.json()
        except aiohttp.ClientConnectorError as exc:
            # Windows IOCP may report refusal as EINVAL / ERROR_CONNECTION_REFUSED.
            if exc.errno == errno.ECONNREFUSED or getattr(exc.os_error, 'winerror', None) == 1225:
                return False
            raise
        if info.get('version') != UNIFIED_VERSION or not info.get('ready') or not info.get('url'):
            raise ValueError('8001 的 TTgames 联机服务未就绪')
        self.origin = origin
        self.address = info.get('lan_warning') or info['url']
        return True

    def http(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        return self.session

    async def request(self, path, data):
        async with self.http().post(self.target + path, json=data, headers={'Origin': self.target},
                                    ssl=self.local_tls if self.target == self.origin else True) as response:
            result = await response.json()
            if not response.ok:
                raise ValueError(result.get('error', '请求失败'))
            return result

    def begin(self, mode, value=''):
        self.reset()
        self.connection = asyncio.create_task(self.connect(mode, value))

    async def connect(self, mode, value):
        try:
            if mode == 'create':
                if not self.origin:
                    raise ValueError('本机联机服务未就绪')
                self.target = self.origin
                if self.create_id is None:
                    self.create_id = secrets.token_hex(16)
                result = await self.request('/rooms', {'request_id': self.create_id})
                self.code, self.host_token, self.invite = result['code'], result['host_token'], result['invite_url']
            elif len(value) == 4 and value.isascii() and value.isdigit():
                if not self.origin:
                    raise ValueError('本机联机服务未就绪')
                self.target, self.code, self.host_token = self.origin, value, None
            else:
                url = urlsplit(value if '://' in value else 'http://' + value)
                self.target = f'{url.scheme}://{url.netloc}'
                self.code = parse_qs(url.query).get('room', [''])[0]
                self.host_token = None
                if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or not self.code.isascii() or len(self.code) != 4 or not self.code.isdigit():
                    raise ValueError('请输入四位房间号或有效邀请链接')
            self.token = None
            self.room_id = None
            while True:
                try:
                    await self.receive()
                except (aiohttp.ClientError, OSError, TimeoutError):
                    if self.token is None:
                        raise
                if self.token is None:
                    raise ValueError('连接已关闭')
                self.error = '连接中断，正在重连'
                await asyncio.sleep(1)
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as exc:
            self.error = str(exc)

    async def receive(self):
        async with self.http().ws_connect(self.target + '/ws', origin=self.target, heartbeat=10,
                                          ssl=self.local_tls if self.target == self.origin else True,
                                          max_msg_size=16 * 1024 * 1024) as ws:
            self.socket = ws
            self.seq = 0
            hello = {'type': 'hello', 'version': UNIFIED_VERSION, 'code': self.code}
            if self.token:
                hello['token'] = self.token
            elif self.host_token:
                hello['host_token'] = self.host_token
            await ws.send_json(hello)
            try:
                async for packet in ws:
                    if packet.type != aiohttp.WSMsgType.TEXT:
                        break
                    msg = packet.json()
                    if msg['type'] == 'welcome':
                        self.slot, self.token, self.room_id = msg['slot'], msg['token'], msg['room_id']
                        self.error = ''
                        await ws.send_json({'type': 'orientation', 'orientation': self.orientation})
                    elif msg['type'] == 'state':
                        self.state = msg
                    elif msg['type'] == 'error':
                        self.error = msg['error']
                        if self.slot == 0 or msg['error'] in ('invalid_reconnect_token', 'wrong_room_code'):
                            raise ValueError(self.error)
                if ws.close_code == 1001:
                    self.ended = True
                    raise ValueError('房间已关闭')
            finally:
                self.socket = None

    def send(self, message):
        ws = self.socket
        if not ws or ws.closed or not self.slot:
            return
        if message['type'] in ('action', 'input'):
            if self.state is None:
                return
            self.seq += 1
            message = dict(message, seq=self.seq, match_id=self.state['match_id'])
        async def send():
            with contextlib.suppress(aiohttp.ClientError, ConnectionError, RuntimeError):
                await ws.send_json(message)
        asyncio.create_task(send())
        return message.get("seq")

    async def leave(self):
        if self.leave_id is None:
            self.leave_id = secrets.token_hex(16)
        try:
            await self.request('/rooms/leave', {'token': self.token, 'room_id': self.room_id,
                                                'request_id': self.leave_id})
        except (aiohttp.ClientError, ValueError, TimeoutError) as exc:
            self.error = str(exc)
            return False
        self.create_id = self.leave_id = None
        self.reset()
        return True

    def reset(self):
        if self.connection:
            self.connection.cancel()
        self.socket = self.connection = self.state = None
        self.slot = 0
        self.ended = False
        self.error = ''
        self.invite = ''

    async def close(self):
        self.reset()
        if self.host_task:
            self.host_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.host_task
        if self.session:
            await self.session.close()
        if self.host and self.host.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.host.terminate()
            try:
                await asyncio.wait_for(self.host.wait(), 3)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.host.kill()
                await self.host.wait()
