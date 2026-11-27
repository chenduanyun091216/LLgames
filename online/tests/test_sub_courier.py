import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from game_core.modes.sub_courier import ORDERS, SubCourier
from online.server.host import create_host
from online.server.app import HOST_KEY
from online.shared.protocol import ProtocolError, UNIFIED_VERSION, decode


class CourierSimulationTests(unittest.TestCase):
    def test_dock_strict_speed_last_tick_and_failure_precedence(self):
        for order, route in ORDERS.items():
            for speed, hull, outcome in ((12, 100, '已签收'), (15, 100, '订单超时'), (12, 0, '船体损毁')):
                with self.subTest(order=order, speed=speed, hull=hull):
                    sub = SubCourier(order)
                    sub.loading_ticks = 0
                    sub.remaining_ticks = 1
                    sub.x, sub.y = route['length'], 230
                    self.assertEqual(sub.flow(), (0, 0))
                    sub.vx = speed
                    sub.inputs = {1: (speed / 108, 0, 0)}
                    sub.station, sub.dock_ticks, sub.hull = 2, 59, hull
                    sub.actions = [(2, 'deliver')]
                    sub.step()
                    self.assertEqual(sub.result['reason'], outcome)
                    self.assertEqual(sub.dock_ticks, 0 if speed == 15 else 60)
                    result = sub.result
                    sub.step()
                    self.assertIs(sub.result, result)

    def test_collision_stays_single_then_pump_repairs_second_impact(self):
        sub = SubCourier()
        sub.loading_ticks = 0
        sub.power = 2
        sub.x, sub.y, sub.vx = 1749.9, 230, 70
        sub.inputs[1] = (1, 0, 0)
        for _ in range(120):
            sub.step()
        self.assertEqual(sub.hull, 85)
        self.assertEqual(sub.integrity, 95)
        sub.inputs[1] = (-1, 0, 0)
        for _ in range(120):
            sub.step()
        sub.inputs[1] = (1, 0, 0)
        for _ in range(310):
            sub.step()
        self.assertTrue(sub.leak)
        self.assertEqual(sub.records[1]['impacts'], 2)
        sub.inputs[2] = (0, 0, 4)
        for _ in range(120):
            sub.step()
        self.assertFalse(sub.leak)
        self.assertEqual(sub.records[2]['repairs'], 1)
        hull = sub.hull
        for _ in range(60):
            sub.step()
        self.assertEqual(sub.hull, hull)

    def test_whale_collision_crossing_threshold_is_immediate_even_with_silent_power(self):
        sub = SubCourier('calf')
        sub.loading_ticks = 0
        sub.x, sub.y, sub.vx = 2649.9, 350, 70
        sub.power, sub.wake = 2, 85
        sub.step()
        self.assertEqual(sub.result['reason'], '幼鲸惊醒')

    def test_swap_boundary_discards_old_commands_and_request_expires(self):
        sub = SubCourier()
        sub.loading_ticks = 0
        sub.actions = [(2, 'power_next'), (1, 'swap_request'), (2, 'swap_request')]
        sub.inputs[2] = (0, 1, 4)
        sub.step()
        self.assertEqual(sub.slots(), (2, 1))
        self.assertEqual((sub.epoch, sub.power, sub.ballast), (1, 0, 50))
        sub.actions = [(2, 'swap_request')]
        for _ in range(182):
            sub.step()
        self.assertIsNone(sub.swap)
        self.assertEqual(sub.slots(), (2, 1))
        self.assertEqual(sub.world()['runtime']['swap'], '换岗请求已超时')

    def test_all_routes_are_navigable_including_both_express_branches(self):
        for order, shortcut in (('jelly', False), ('express', False), ('express', True), ('calf', False)):
            with self.subTest(order=order, shortcut=shortcut):
                sub = self.navigate(order, shortcut)
                self.assertEqual(sub.result['stars'], 3)
                self.assertEqual(sub.result['shortcut'], shortcut)
                self.assertEqual(sub.hull, 100)
                self.assertEqual(sub.dock_ticks, 60)

    @staticmethod
    def navigate(order, shortcut):
        sub = SubCourier(order)
        sub.loading_ticks = 0
        sub.power = 1

        def axis(value):
            return min(1, max(-1, value))

        while not sub.result:
            x, y = sub.x, sub.y
            goal_y, target_ballast = 230, 50
            if order == 'jelly':
                if 1110 < x < 2540:
                    goal_y = 338
                elif 4270 < x < 4860:
                    goal_y = 249
                if 1100 < x < 1500:
                    target_ballast = 78
            elif shortcut:
                if 2750 < x < 5570:
                    goal_y = 362
                if 2800 < x < 3750 and not sub.gate_attempted:
                    target_ballast = 68 if x < 3450 else 80
            elif order == 'calf':
                sub.power = 3 if any(a <= x < b for a, b in sub.route['quiet']) else 1

            _, flow_y = sub.flow()
            vertical = (goal_y - y) * 2 - flow_y
            if sub.power == 3:
                target_ballast = 50 + 35 * axis(vertical / (1.1 * 35))
            elevator = axis((vertical - (sub.ballast - 50) * 1.1) / 26)
            distance = sub.route['length'] - x
            forward = distance > -3 and not (shortcut and x > 3590 and not sub.gate_attempted)
            sub.station = 1 if sub.loose else 2
            sub.inputs = {
                1: (int(forward), elevator, int(distance < 208)),
                2: (0, axis((target_ballast - sub.ballast) * 2), 4 if sub.loose else 0),
            }
            if sub.dock_ticks >= 59:
                sub.actions = [(2, 'deliver')]
            sub.step()
        return sub

    def test_unknown_and_cross_mode_options_rejected(self):
        message = dict(type='room_settings', mode='sub_courier', orientation='landscape')
        for options in (None, {'order': 'bad'}, {'order': 'jelly', 'extra': 1}):
            with self.assertRaises(ProtocolError):
                decode(json.dumps(dict(message, mode_options=options)), UNIFIED_VERSION)
        self.assertEqual(decode(json.dumps(dict(message, mode_options={'order': 'calf'})),
                                UNIFIED_VERSION)['mode_options'], {'order': 'calf'})


class CourierSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.client = TestClient(TestServer(create_host(Path(directory.name))))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.origin = {'Origin': str(self.client.make_url('/')).rstrip('/')}
        response = await self.client.post('/rooms', json={'request_id': 'a' * 32}, headers=self.origin)
        self.room_info = await response.json()
        self.room = self.client.app[HOST_KEY].room
        self.seq = {}

    async def connect(self, auth=None):
        ws = await self.client.ws_connect('/ws', headers=self.origin)
        await ws.send_json(dict(type='hello', version=UNIFIED_VERSION, code=self.room_info['code'],
                                extra_modes={'sub_courier': 1}, **(auth or {})))
        welcome = await ws.receive_json(timeout=2)
        self.assertEqual(welcome['type'], 'welcome')
        await ws.send_json(dict(type='orientation', orientation='landscape'))
        self.seq[ws] = 0
        return ws, welcome['token']

    async def state(self, ws, condition):
        async with asyncio.timeout(4):
            while True:
                state = await ws.receive_json()
                if state['type'] == 'state' and condition(state):
                    return state

    async def send(self, ws, action=None, **fields):
        self.seq[ws] += 1
        fields.setdefault('epoch', self.room.game.epoch)
        fields.update(match_id=self.room.match_id, seq=self.seq[ws])
        if action:
            fields.update(type='mode_action', action=action)
        else:
            fields.update(type='mode_input')
        await ws.send_json(fields)

    async def start(self):
        p1, _ = await self.connect({'host_token': self.room_info['host_token']})
        p2, token = await self.connect()
        await self.state(p1, lambda s: 'sub_courier' in s['available_modes'])
        await p1.send_json(dict(type='room_settings', mode='sub_courier', orientation='landscape',
                                mode_options={'order': 'jelly'}))
        setting = await self.state(p2, lambda s: s['mode'] == 'sub_courier')
        revision = setting['settings_revision']
        for ws in (p1, p2):
            await ws.send_json(dict(type='ready', ready=True, settings_revision=revision))
        await self.state(p1, lambda s: not s['paused'] and all(p['ready'] for p in s['players']))
        await p1.send_json(dict(type='start', settings_revision=revision))
        initial = await self.state(p2, lambda s: bool(s['world']))
        self.assertEqual(initial['world']['role_by_slot'], {'1': 'helm', '2': 'engineer'})
        self.assertEqual([a['id'] for a in initial['world']['actors']], ['submarine'])
        await self.state(p1, lambda s: s['world'].get('phase') == 'playing')
        return p1, p2, token

    async def test_input_swap_reconnect_and_departure(self):
        p1, p2, token = await self.start()
        await self.send(p2, 'power_next')
        await self.send(p1, x=1, y=0, held=0)
        await self.send(p2, x=0, y=1, held=0)
        moved = await self.state(p2, lambda s: s['world']['ballast'] > 51 and s['world']['x'] > 65)
        self.assertEqual(moved['world']['power'], 1)
        epoch = moved['world']['epoch']
        await self.send(p1, 'swap_request')
        await self.send(p2, 'swap_request')
        changed = await self.state(p1, lambda s: s['world']['epoch'] > epoch)
        self.assertEqual(changed['world']['role_by_slot'], {'1': 'engineer', '2': 'helm'})
        ballast = changed['world']['ballast']
        await self.send(p2, epoch=epoch, x=0, y=1, held=4)
        await self.state(p1, lambda s: s['tick'] > changed['tick'] + 5)
        self.assertAlmostEqual(self.room.game.ballast, ballast)
        await p2.close()
        paused = await self.state(p1, lambda s: s['pause_reason'] == 'disconnected')
        await asyncio.sleep(.08)
        world = json.loads(json.dumps(self.room.game.world()))
        for key in ('x', 'y', 'cargo', 'remaining_ticks', 'role_by_slot', 'dock_ticks'):
            self.assertEqual(paused['world'][key], world[key])
        p2, token = await self.connect({'token': token})
        resumed = await self.state(p2, lambda s: not s['paused'] and s['tick'] > paused['tick'])
        self.assertEqual(resumed['world']['role_by_slot'], {'1': 'engineer', '2': 'helm'})
        response = await self.client.post('/rooms/leave', headers=self.origin, json={
            'room_id': self.room.id, 'token': token, 'request_id': 'b' * 32})
        self.assertEqual(response.status, 200)
        gone = await self.state(p1, lambda s: bool(s['world'].get('result')))
        self.assertEqual(gone['world']['result']['reason'], '搭档离开，订单中止')

    async def test_result_votes_switch_roles_and_return_to_order_selection(self):
        p1, p2, _ = await self.start()
        self.room.game.finish('订单超时')
        await self.state(p1, lambda s: bool(s['world'].get('result')))
        old = self.room.match_id
        for ws in (p1, p2):
            await self.send(ws, 'result_seen')
            await self.send(ws, 'rematch_ready')
        rematch = await self.state(p1, lambda s: s['match_id'] != old)
        self.assertEqual(rematch['world']['role_by_slot'], {'1': 'engineer', '2': 'helm'})
        self.room.game.finish('订单超时')
        await self.state(p2, lambda s: bool(s['world'].get('result')))
        await self.send(p1, 'result_seen')
        await self.send(p1, 'back_lobby')
        await self.send(p2, 'result_seen')
        lobby = await self.state(p2, lambda s: s['phase'] == 'lobby')
        self.assertEqual(lobby['mode_options'], {'order': 'jelly'})
        self.assertFalse(any(p['ready'] for p in lobby['players']))
