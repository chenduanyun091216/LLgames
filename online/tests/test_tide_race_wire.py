import asyncio
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from game_core.modes.tide_race import COUNTDOWN, wave
from online.server.app import HOST_KEY
from online.server.host import create_host


class TideRaceWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_authoritative_result_survives_finished_driver_leaving(self):
        async with TestClient(TestServer(create_host(Path(__file__).parent))) as client:
            origin = {'Origin': str(client.make_url('/')).rstrip('/')}
            health = await (await client.get('/health')).json()
            self.assertEqual(health['extra_modes']['tide_race'],1)
            req = await client.post('/rooms', json={'request_id':'0'*32}, headers=origin)
            created = await req.json()
            sockets, welcome = [], []
            for i in (1,2):
                ws = await client.ws_connect('/ws', headers=origin)
                hello = dict(type='hello',version=2,code=created['code'],extra_modes={'tide_race':1})
                if i == 1:
                    hello['host_token'] = created['host_token']
                await ws.send_json(hello)
                welcome.append(await ws.receive_json(timeout=2))
                self.assertEqual(welcome[-1]['slot'],i)
                await ws.send_json(dict(type='orientation',orientation='landscape'))
                sockets.append(ws)
            p1, p2 = sockets

            async def state(socket, condition):
                async with asyncio.timeout(3):
                    while True:
                        value = await socket.receive_json()
                        self.assertNotEqual(value['type'], 'error', value)
                        if value['type']=='state' and condition(value):
                            return value

            room = client.app[HOST_KEY].room
            await state(p1, lambda s: 'tide_race' in s['available_modes'])
            await p1.send_json(dict(type='room_settings',mode='tide_race',orientation='landscape',mode_options={'track':'reef'}))
            lobby = await state(p2, lambda s: s['mode']=='tide_race')
            self.assertEqual(lobby['mode_options'],{'track':'reef'})
            for socket in sockets:
                await socket.send_json(dict(type='ready',ready=True,settings_revision=lobby['settings_revision']))
            await state(p1, lambda s: all(p['ready'] for p in s['players']))
            await p1.send_json(dict(type='start',settings_revision=lobby['settings_revision']))
            first = await state(p1, lambda s: s['world'].get('mode')=='tide_race')
            race = room.game.race
            # Place both drivers near the last gate so the WebSocket test stays short.
            race.tick = COUNTDOWN + 6000
            race.phase = 'racing'
            for r in race.racers.values():
                r.x = race.track['length']-(1 if r.slot==1 else 145)
                r.y = wave(race.track,r.x,race.clock)[0]
                r.gates = [1700,3300,5300]
                r.joined = True
            await p2.send_json(dict(type='mode_input',seq=1,match_id=first['match_id'],
                                    epoch=first['world']['epoch'],x=1,y=0,held=0))
            sealed = await state(p2, lambda s: s['world'].get('racers') and s['world']['racers'][0]['finish_tick'] is not None)
            completed_tick = sealed['world']['racers'][0]['finish_tick']
            await p1.close()
            continued = await state(p2, lambda s: not s['players'][0]['connected']
                                    and s['tick']>sealed['tick'])
            self.assertFalse(continued['paused'])
            self.assertEqual(continued['world']['epoch'],first['world']['epoch'])

            # Reconnect the watching seat and observe the same final payload on both sockets.
            p1 = await client.ws_connect('/ws',headers=origin)
            await p1.send_json(dict(type='hello',version=2,code=created['code'],
                                     token=welcome[0]['token'],extra_modes={'tide_race':1}))
            self.assertEqual((await p1.receive_json(timeout=2))['slot'],1)
            a,b = await asyncio.gather(*(state(ws,lambda s: s['world'].get('result')) for ws in (p1,p2)))
            self.assertEqual(a['world']['result'],b['world']['result'])
            self.assertEqual(a['world']['result_id'],b['world']['result_id'])
            self.assertEqual(b['world']['result'][0]['finish_tick'],completed_tick)
            self.assertEqual([r['status'] for r in b['world']['result']],['finished','finished'])
            await p1.send_json(dict(type='orientation',orientation='landscape'))
            for ws in (p1,p2):
                for seq,action in enumerate(('result_seen','rematch_ready'),2):
                    await ws.send_json(dict(type='mode_action',seq=seq,action=action,
                                            match_id=b['match_id'],epoch=b['world']['epoch']))
            rematch=await state(p2,lambda s:s['match_id']!=b['match_id'])
            self.assertEqual(rematch['world']['track_id'],'reef')
            ack = await client.post('/rooms/leave', headers=origin, json={
                'room_id':created['room_id'],'token':welcome[0]['token'],'request_id':'a'*32})
            self.assertEqual(ack.status,200)
            forfeited = await state(p2,lambda s: s['match_id']==rematch['match_id'] and s['world'].get('result'))
            self.assertEqual([(r['slot'],r['status']) for r in forfeited['world']['result']],
                             [(2,'won_by_forfeit'),(1,'departed')])
            await p1.close()
            await p2.close()
