import asyncio
import errno
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp

from online.client.native import NativeTransport
from online.shared.protocol import UNIFIED_VERSION


class NativeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_click_waits_for_local_host_even_after_cancel_and_retry(self):
        for mode, value in [('create', ''), ('join', '1234')]:
            transport = NativeTransport()
            ready = asyncio.Event()
            async def start():
                await ready.wait()
                transport.origin = 'https://127.0.0.1:8001'
            transport.host_task = asyncio.create_task(start())
            with patch.object(transport, 'request', new_callable=AsyncMock, return_value={
                    'code': '1234', 'host_token': 'owner', 'invite_url': 'invite'}) as request, \
                    patch.object(transport, 'receive', new_callable=AsyncMock) as receive:
                transport.begin(mode, value)
                await asyncio.sleep(0)
                self.assertFalse(transport.connection.done())
                transport.begin(mode, value)
                ready.set()
                await asyncio.wait_for(transport.connection, 2)
                receive.assert_awaited_once()
                self.assertEqual(request.await_count, int(mode == 'create'))

    async def test_pc_reuses_host_bound_to_its_wifi_address(self):
        transport = NativeTransport()
        with patch('web.run_web.lan_addresses', return_value=['172.20.10.4']), \
                patch.object(transport, 'use_local_host', new_callable=AsyncMock,
                             side_effect=[False, True]) as probe, \
                patch('online.client.native.asyncio.create_subprocess_exec', new_callable=AsyncMock) as spawn:
            await transport.start_host()
        self.assertEqual([call.args[0] for call in probe.await_args_list],
                         ['https://127.0.0.1:8001', 'https://172.20.10.4:8001'])
        spawn.assert_not_awaited()

    def connector_error(self, error):
        key = SimpleNamespace(host='127.0.0.1', port=8001, ssl=True)
        return aiohttp.ClientConnectorError(key, error)

    async def test_windows_refusal_starts_local_service(self):
        error = OSError(errno.EINVAL, '远程计算机拒绝网络连接。')
        error.winerror = 1225
        response = Mock()
        response.ok = True
        response.json = AsyncMock(return_value={
            'version': UNIFIED_VERSION, 'ready': True,
            'url': 'https://192.168.1.2:8001/',
            'setup_url': 'http://192.168.1.2:8123/',
            'lan_warning': '联机证书未覆盖 192.168.1.2',
        })
        probe = AsyncMock()
        probe.__aenter__.side_effect = [self.connector_error(error), response]
        session = Mock()
        session.get.return_value = probe
        process = Mock()
        process.stdout.readline = AsyncMock(return_value=b'{"port": 8001}\n')
        transport = NativeTransport()
        with patch('web.run_web.lan_addresses', return_value=[]), \
                patch.object(transport, 'http', return_value=session), \
                patch('online.client.native.asyncio.create_subprocess_exec',
                      new_callable=AsyncMock, return_value=process) as spawn:
            await transport.start_host()
        spawn.assert_awaited_once()
        self.assertEqual(transport.origin, 'https://127.0.0.1:8001')
        self.assertEqual(transport.address, '联机证书未覆盖 192.168.1.2')
        self.assertEqual(transport.game_url, 'https://192.168.1.2:8001/')
        self.assertEqual(transport.setup_url, 'http://192.168.1.2:8123/')

    async def test_standard_refusal_means_service_is_absent(self):
        probe = AsyncMock()
        probe.__aenter__.side_effect = self.connector_error(
            ConnectionRefusedError(errno.ECONNREFUSED, 'Connection refused'))
        session = Mock()
        session.get.return_value = probe
        transport = NativeTransport()
        with patch.object(transport, 'http', return_value=session):
            self.assertFalse(await transport.use_local_host('https://127.0.0.1:8001'))

    async def test_other_connection_errors_are_not_treated_as_absent_service(self):
        error = self.connector_error(PermissionError(errno.EACCES, 'Permission denied'))
        probe = AsyncMock()
        probe.__aenter__.side_effect = error
        session = Mock()
        session.get.return_value = probe
        transport = NativeTransport()
        with patch.object(transport, 'http', return_value=session):
            with self.assertRaises(aiohttp.ClientConnectorError):
                await transport.use_local_host('https://127.0.0.1:8001')
