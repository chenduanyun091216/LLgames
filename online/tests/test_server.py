import asyncio
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from aiohttp.test_utils import TestServer, TestClient
from online.server.app import create_app, ROOM_KEY

class FakeGame:
    def __init__(self,difficulty='medium'):
        self.tick=0
        self.inputs={}
        self.actions=[]
    def set_input(self,slot,dx,dy,shoot):
        self.inputs[slot]=(dx,dy,shoot)
    def action(self,slot,action,key=None):
        self.actions.append((slot,action,key))
    def step(self):
        self.tick+=1
    def snapshot(self):
        return dict(tick=self.tick,phase='playing',players=[dict(slot=s,hp=100,max_hp=100,alive=True,shop_open=False) for s in (1,2)],gold=0,lives=3,world={})

class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client=TestClient(TestServer(create_app(FakeGame, code='ABC123')))
        await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
        self.room=self.client.app[ROOM_KEY]
        self.sockets=[]
    async def asyncTearDown(self):
        for ws in self.sockets:
            await ws.close()
        await self.client.close()
    async def receive(self, ws, kind):
        for _ in range(100):
            msg=await ws.receive_json(timeout=2)
            if msg['type']==kind:
                return msg
        self.fail('message not received')
    async def join(self, token=None, code='ABC123'):
        ws=await self.client.ws_connect('/ws', origin=self.origin)
        self.sockets.append(ws)
        msg=dict(type='hello',version=1,code=code)
        if token:
            msg['token']=token
        await ws.send_json(msg)
        return ws, await ws.receive_json(timeout=2)
    async def start(self):
        a,wa=await self.join()
        b,wb=await self.join()
        await a.send_json(dict(type='ready',ready=True))
        await b.send_json(dict(type='ready',ready=True))
        await asyncio.sleep(.03)
        await a.send_json(dict(type='start',difficulty='medium'))
        await asyncio.sleep(.04)
        self.assertIsNotNone(self.room.game)
        return a,b,wa,wb
    async def test_origin_static_and_host(self):
        for headers in [{'Origin':'https://evil.example'}, {'Origin':self.origin,'Host':'evil.example'}, {}]:
            response=await self.client.get('/ws',headers=headers)
            self.assertEqual(response.status,403)
        response=await self.client.get('/online/server/app.py')
        self.assertEqual(response.status,404)
        response=await self.client.get('/../server/app.py')
        self.assertEqual(response.status,404)
    async def test_slots_reconnect_disconnect_pause(self):
        a,b,wa,wb=await self.start()
        extra,error=await self.join()
        self.assertEqual(error['error'],'room_full')
        duplicate,error=await self.join(wa['token'])
        self.assertEqual(error['error'],'already_connected')
        self.assertIs(self.room.players[0].ws is not None,True)
        await a.send_json(dict(type='input',seq=1,match_id=self.room.match_id,dx=1,dy=0,shoot=True))
        await asyncio.sleep(.03)
        self.assertEqual(self.room.game.inputs[1],(1,0,True))
        await a.close()
        await asyncio.sleep(.03)
        tick=self.room.game.tick
        await asyncio.sleep(.06)
        self.assertEqual(self.room.game.tick,tick)
        self.assertEqual(self.room.game.inputs[1],(0,0,False))
        new,welcome=await self.join(wa['token'])
        self.assertEqual(welcome['slot'],1)
        self.assertEqual(welcome['token'],wa['token'])
        await asyncio.sleep(.04)
        self.assertGreater(self.room.game.tick,tick)
    async def test_authority_sequence_timeout_suspend(self):
        a,b,wa,wb=await self.start()
        mid=self.room.match_id
        await b.send_json(dict(type='action',seq=1,match_id=mid,action='restart'))
        self.assertEqual((await self.receive(b,'error'))['error'],'host_only')
        await a.send_json(dict(type='input',seq=1,match_id=mid,dx=1,dy=0,shoot=True))
        await asyncio.sleep(.03)
        await a.send_json(dict(type='input',seq=1,match_id=mid,dx=-1,dy=0,shoot=True))
        self.assertEqual((await self.receive(a,'error'))['error'],'stale_sequence')
        await asyncio.sleep(.43)
        self.assertEqual(self.room.game.inputs[1],(0,0,False))
        await a.send_json(dict(type='action',seq=2,match_id=mid,action='suspend'))
        await asyncio.sleep(.03)
        tick=self.room.game.tick
        await asyncio.sleep(.06)
        self.assertEqual(tick,self.room.game.tick)
        self.assertEqual(self.room.snapshot()['pause_reason'],'suspended')
        await a.send_json(dict(type='action',seq=3,match_id=mid,action='resume'))
        await asyncio.sleep(.04)
        self.assertGreater(self.room.game.tick,tick)
        await a.send_json(dict(type='input',seq=4,match_id='old',dx=0,dy=0,shoot=False))
        self.assertEqual((await self.receive(a,'error'))['error'],'stale_match')
    async def test_runtime_failure_pauses_and_reports(self):
        a,b,wa,wb=await self.start()
        def fail():
            raise RuntimeError('private diagnostic not sent to browsers')
        with self.assertLogs('online.server.app',level='ERROR'):
            self.room.game.step=fail
            await asyncio.sleep(.06)
        self.assertTrue(self.room.failed)
        self.assertFalse(self.room.task.done())
        state=self.room.snapshot()
        self.assertTrue(state['paused'])
        self.assertEqual(state['pause_reason'],'server_error')
        self.assertNotIn('private diagnostic',str(state))
        await a.send_json(dict(type='action',seq=1,match_id=self.room.match_id,action='restart'))
        await asyncio.sleep(.05)
        self.assertFalse(self.room.failed)

    async def test_snapshot_failure_is_contained(self):
        a,b,wa,wb=await self.start()
        previous=self.room.snapshot()
        def fail():
            raise ValueError('bad visual entity')
        self.room.game.snapshot=fail
        with self.assertLogs('online.server.app',level='ERROR'):
            state=self.room.snapshot()
        self.assertEqual(state['tick'],previous['tick'])
        self.assertEqual(state['pause_reason'],'server_error')
        await asyncio.sleep(.06)
        self.assertFalse(self.room.task.done())

    async def test_static_isolation_headers(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root=Path(directory)
            (root/'index.html').write_text('<!doctype html><title>Test</title>')
            with patch('online.server.app.STATIC_ROOT',root):
                response=await self.client.get('/')
                await response.read()
        self.assertEqual(response.status,200)
        for key,value in [('Cross-Origin-Opener-Policy','same-origin'),('Cross-Origin-Embedder-Policy','require-corp'),('Cross-Origin-Resource-Policy','same-origin')]:
            self.assertEqual(response.headers[key],value)

    async def test_stale_frame_queue_is_bounded(self):
        a,b,wa,wb=await self.start()
        peer=self.room.players[0]
        peer.sender.cancel()
        try:
            await peer.sender
        except asyncio.CancelledError:
            pass
        for _ in range(100):
            self.room.broadcast()
        self.assertEqual(peer.queue.qsize(),1)
        tick=self.room.game.tick
        await asyncio.sleep(.06)
        self.assertGreater(self.room.game.tick,tick)
        await b.send_json(dict(type='action',seq=1,match_id=self.room.match_id,action='laser'))
        await asyncio.sleep(.03)
        self.assertIn((2,'laser',None),self.room.game.actions)

    async def test_malformed_and_wrong_code(self):
        a,msg=await self.join(code='wrong')
        self.assertEqual(msg['error'],'wrong_room_code')
        a,wa=await self.join()
        await a.send_json(dict(type='ready',ready=True,slot=1))
        self.assertEqual((await self.receive(a,'error'))['error'],'invalid_fields')


class RealAdapterTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end protocol boundary against the actual legacy-core adapter."""
    asyncTearDown = ServerTests.asyncTearDown
    receive = ServerTests.receive
    join = ServerTests.join
    start = ServerTests.start

    async def asyncSetUp(self):
        from online.adapters.core_adapter import OnlineGame
        self.client=TestClient(TestServer(create_app(OnlineGame, code='ABC123')))
        await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
        self.room=self.client.app[ROOM_KEY]
        self.sockets=[]

    async def test_slot_movement_and_serialized_snapshot(self):
        a,b,wa,wb=await self.start()
        self.assertEqual((wa['slot'],wb['slot']),(1,2))
        game=self.room.game
        x1,x2=game.all_players[0].x,game.all_players[1].x
        mid=self.room.match_id
        await a.send_json(dict(type='input',seq=1,match_id=mid,dx=-1,dy=0,shoot=False))
        await b.send_json(dict(type='input',seq=1,match_id=mid,dx=1,dy=0,shoot=False))
        await asyncio.sleep(.10)
        self.assertLess(game.all_players[0].x,x1)
        self.assertGreater(game.all_players[1].x,x2)
        state=await self.receive(a,'state')
        while state['phase'] != 'playing':
            state=await self.receive(a,'state')
        self.assertEqual([p['slot'] for p in state['players']],[1,2])
        self.assertGreater(state['players'][0]['hp'],0)
        self.assertIn('world',state)
