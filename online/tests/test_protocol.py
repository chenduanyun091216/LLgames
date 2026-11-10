import json
import unittest
from online.shared.protocol import decode, ProtocolError
from online.server.app import allowed_host

class ProtocolTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(decode('{"type":"hello","version":1,"code":"ABC"}')['version'], 1)
        decode(json.dumps(dict(type='input',seq=1,match_id='a',dx=0.3,dy=-1,shoot=False)))

    def test_invalid(self):
        messages = [None, '[]', '{"type":"ready","ready":1}', '{"type":"hello","version":2,"code":"ABC"}', '{"type":"ready","ready":true,"slot":1}', '{"type":"ready","ready":true,"ready":false}', '{"type":"hello","version":true,"code":"a"}']
        for axis in [True, float('nan'), float('inf'), 2, '0', 10**1000]:
            messages.append(json.dumps(dict(type='input',seq=1,match_id='a',dx=axis,dy=0,shoot=False)))
        for raw in messages:
            with self.subTest(raw=str(raw)[:80]), self.assertRaises(ProtocolError):
                decode(raw)

    def test_hosts(self):
        for host in ['localhost:80', '127.0.0.1:123', '192.168.1.10:8765', '[::1]:80', '10.0.0.5']:
            self.assertTrue(allowed_host(host), host)
        for host in ['evil.com', '127.0.0.1.evil.com', '8.8.8.8', '0.0.0.0', 'localhost@evil.com', '127.0.0.1/foo', '127.0.0.1:bad']:
            self.assertFalse(allowed_host(host), host)
