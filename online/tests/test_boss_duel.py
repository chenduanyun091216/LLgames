"""Rule and live-room regressions for the asymmetric arena."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from game_core.modes.boss_duel import (
    BOSSES, HERO_SPEED, LIMIT, BossDuel, compare, hits, make_cast, safe_route, shapes,
)
from online.server.app import HOST_KEY
from online.server.host import create_host
from online.shared.protocol import ProtocolError, decode


def enter(duel):
    for _ in range(240):
        duel.step()


def cast(duel, slot, index, target):
    duel.mode_input(slot, dict(type='mode_action', action=f'cast_{index}', target=target))
    duel.step()


class DuelRules(unittest.TestCase):
    def test_all_bosses_complete_two_rounds_from_initial_inputs(self):
        for name in BOSSES:
            with self.subTest(boss=name):
                duel = BossDuel(name)
                for slot in (2, 1):
                    enter(duel)
                    # The hero fires from the original spawn while the boss
                    # deliberately targets a flank. Both reset on the next round.
                    duel.set_input(slot, 0, 0, True)
                    cast(duel, 3-slot, 1, [120, 775])
                    for _ in range(LIMIT):
                        duel.step()
                        if duel.stage != 'combat':
                            break
                    row = duel.results[-1]
                    self.assertEqual((row['slot'], row['damage'], row['hp']), (slot, 150, 5))
                    if slot == 2:
                        for seat in (1, 2):
                            duel.mode_input(seat, dict(type='mode_action', action='round_ready'))
                        duel.step()
                self.assertEqual(duel.result['metric'], 'draw')

    def test_all_nine_locked_at_each_side(self):
        for name in BOSSES:
            for index in range(1, 4):
                for x in (0, 1000):
                    with self.subTest(boss=name, index=index, side=x):
                        duel = BossDuel(name)
                        enter(duel)
                        cast(duel, 1, index, [x, 790])
                        (attack,) = duel.casts
                        encoded = json.dumps(attack, sort_keys=True)
                        self.assertTrue(shapes(attack, duel.clock, preview=True))
                        duel.set_input(1, 1 if x == 0 else -1, 0, False)
                        while duel.clock <= attack['active_tick']:
                            duel.step()
                        self.assertNotEqual(duel.position[0], 400)
                        self.assertEqual(json.dumps(duel.casts[0], sort_keys=True), encoded)
                        self.assertTrue(duel.snapshot()['world']['active_shapes'][0]['shapes'])
                        while duel.casts:
                            duel.step()
                        self.assertLessEqual(5-duel.hero_hp, 1)
                        self.assertFalse(duel.snapshot()['world']['active_shapes'])

    def test_walkable_moon_gap_at_both_extremes(self):
        for x, target, expected, direction in ((18, 1000, (212, 324), 1), (782, 0, (476, 588), -1)):
            duel = BossDuel()
            enter(duel)
            duel.hero = (x, 170)
            duel.next_dash = 500
            cast(duel, 1, 3, [target, 315])
            (attack,) = duel.casts
            self.assertEqual(attack['safe'], expected)
            while duel.clock < attack['start_tick'] + 12:
                duel.step()
            duel.set_input(2, direction, 0, False)
            for _ in range(60):
                duel.step()
            self.assertEqual(duel.hero[0], x+60*direction*HERO_SPEED)
            duel.set_input(2, 0, 0, False)
            while duel.casts:
                duel.step()
            self.assertEqual(duel.hero_hp, 5)

    def test_overlap_requires_a_route_through_both_timelines(self):
        duel = BossDuel()
        enter(duel)
        hero = (400, 180)
        first = make_cast(1, 2, duel.skills[2], (400, 112), (400, 180), hero, 60)
        second = make_cast(2, 0, duel.skills[0], (400, 112), (400, 180), hero, 84)
        self.assertTrue(safe_route(hero, [first, second], 84))
        # If a group is already hitting the hero now, adding a second may not
        # claim there is a damage-free escape during the reaction window.
        second['active_tick'] = 84
        self.assertTrue(hits(shapes(second, 84)[0], hero))
        self.assertFalse(safe_route(hero, [first, second], 84))

    def test_feedback_and_simultaneous_finish(self):
        duel = BossDuel()
        enter(duel)
        cast(duel, 2, 1, [500, 600])
        self.assertEqual(duel.feedback[2][1], 'role')
        cast(duel, 1, 1, [500, 600])
        energy = duel.energy
        cast(duel, 1, 1, [700, 600])
        self.assertEqual(duel.feedback[1][1], 'cooldown')
        self.assertEqual(duel.energy, energy+8)
        duel.energy = 0
        while duel.clock < duel.next_cast:
            duel.step()
        cast(duel, 1, 3, [500, 600])
        self.assertEqual(duel.feedback[1][1], 'energy')
        duel.clock = duel.casts[0]['active_tick']
        duel.hero_hp = duel.boss_hp = 1
        duel.shots = [(400, 135)]
        duel.step()
        self.assertEqual((duel.hero_hp, duel.boss_hp, duel.stage), (0, 0, 'swap'))
        self.assertTrue(duel.results[0]['defeated'])
        for slot in (1, 2):
            duel.mode_input(slot, dict(type='mode_action', action='round_ready'))
        duel.step()
        self.assertEqual((duel.boss_slot, duel.hero_slot, duel.clock, duel.boss_hp, duel.energy),
                         (2, 1, 0, 150, 70*60))
        self.assertEqual((duel.casts, duel.shots, duel.cooldowns), ([], [], [0, 0, 0]))

    def test_ranking(self):
        def score(slot, time, damage, hp=2, defeated=False):
            return dict(slot=slot, survival_tick=time, damage=damage, hp=hp, defeated=defeated,
                        defeat_tick=time if defeated else None)
        self.assertEqual(compare(score(1, 53*60, 97), score(2, 68*60, 80)), (2, 'survival_tick'))
        self.assertEqual(compare(score(1, LIMIT, 112), score(2, LIMIT, 95)), (1, 'damage'))
        self.assertEqual(compare(score(1, 51*60, 150, defeated=True), score(2, 49*60, 150, defeated=True)),
                         (2, 'defeat_tick'))
        self.assertEqual(compare(score(1, LIMIT, 110), score(2, 51*60, 150, defeated=True)), (2, 'defeated'))
        self.assertEqual(compare(score(1, LIMIT, 100), score(2, LIMIT, 100, hp=1)), (1, 'hp'))
        self.assertEqual(compare(score(1, LIMIT, 100), score(2, LIMIT, 100)), (None, 'draw'))

    def test_target_is_required_only_on_cast_and_bounded(self):
        payload = dict(type='mode_action', action='cast_1', seq=1, match_id='match', epoch=1)
        for fields in ({}, {'target': [1001, 20]}, {'target': [True, 3]},
                       {'action':'dash', 'target': [0, 0]}):
            with self.assertRaises(ProtocolError):
                decode(json.dumps(dict(payload, **fields)), 2)
        self.assertEqual(decode(json.dumps(dict(payload, target=[0, 1000])), 2)['target'], [0, 1000])


class DuelRoom(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.client = TestClient(TestServer(create_host(Path(tmp.name))))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {'Origin': str(self.client.make_url('/')).rstrip('/')}
        self.host = self.client.app[HOST_KEY]

    async def join(self, slot, token=None, version=1):
        ws = await self.client.ws_connect('/ws', headers=self.headers)
        hello = dict(type='hello', version=2, code=self.reservation['code'])
        if version:
            hello['extra_modes'] = {'boss_duel':version}
        if token:
            hello['token'] = token
        elif slot == 1:
            hello['host_token'] = self.reservation['host_token']
        await ws.send_json(hello)
        welcome = await ws.receive_json(timeout=2)
        if welcome['type'] == 'welcome':
            await ws.send_json(dict(type='orientation', orientation='landscape'))
        return ws, welcome

    async def until(self, ws, predicate, kind='state'):
        async with asyncio.timeout(3):
            while True:
                msg = await ws.receive_json()
                if msg['type'] == kind and predicate(msg):
                    return msg

    async def start(self, name):
        response = await self.client.post('/rooms', json={'request_id':'a'*32}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.reservation = await response.json()
        a, self.owner = await self.join(1)
        b, self.guest = await self.join(2)
        await a.send_json(dict(type='room_settings', mode='boss_duel', orientation='landscape',
                               mode_options={'boss':name}))
        s = await self.until(a, lambda s: s['mode'] == 'boss_duel')
        revision = s['settings_revision']
        for ws in (a, b):
            await ws.send_json(dict(type='ready', ready=True, settings_revision=revision))
        await self.until(a, lambda s: len(s['players']) == 2 and all(p['ready'] for p in s['players']))
        await a.send_json(dict(type='start', settings_revision=revision))
        await self.until(a, lambda s: s['phase'] == 'playing')
        return a, b, self.host.room

    async def message(self, ws, room, seq, action, target=None, epoch=None):
        msg = dict(type='mode_action', seq=seq, action=action, match_id=room.match_id,
                   epoch=room.game.epoch if epoch is None else epoch)
        if target is not None:
            msg['target'] = target
        await ws.send_json(msg)

    async def test_two_rounds_stale_input_and_rematch_for_each_boss(self):
        for boss in BOSSES:
            a, b, room = await self.start(boss)
            game = room.game
            game.remaining = 1
            await self.until(a, lambda s: s['world']['phase'] == 'combat')
            game.clock = 60
            await self.message(a, room, 1, 'cast_1', [100, 800])
            first = await self.until(a, lambda s: s['world'].get('pending_casts'))
            second = await self.until(b, lambda s: s['world'].get('pending_casts'))
            self.assertEqual(first['world']['pending_casts'], second['world']['pending_casts'])
            game.clock = LIMIT - 1
            await self.until(a, lambda s: s['world']['phase'] == 'swap')
            epoch = game.epoch
            await self.message(a, room, 2, 'round_ready')
            await self.message(b, room, 1, 'round_ready')
            state = await self.until(a, lambda s: s['world']['round_id'] == 2)
            self.assertFalse(state['world']['pending_casts'])
            self.assertEqual(state['world']['role_by_slot'], {'1':'hero', '2':'boss'})
            await self.message(a, room, 3, 'cast_1', [900, 800], epoch)
            await self.until(a, lambda s: s['error'] == 'stale_mode_input', 'error')
            game.remaining = 1
            await self.until(a, lambda s: s['world']['phase'] == 'combat')
            game.clock = LIMIT - 1
            state = await self.until(a, lambda s: s['world']['phase'] == 'result')
            self.assertEqual(state['world']['result']['metric'], 'draw')
            before = state['match_id']
            await self.message(a, room, 4, 'result_seen')
            await self.message(b, room, 2, 'result_seen')
            await self.message(a, room, 5, 'rematch_ready')
            await self.message(b, room, 3, 'rematch_ready')
            after = await self.until(a, lambda s: s['match_id'] != before)
            self.assertEqual(after['world']['content_id'], boss)
            await a.close()
            await b.close()
            await self.host.dispose(room)

    async def test_reconnect_restores_warning_and_leave_awards_one_result(self):
        a, b, room = await self.start('whale')
        game = room.game
        game.remaining = 1
        await self.until(a, lambda s: s['world']['phase'] == 'combat')
        game.clock = 60
        await self.message(a, room, 1, 'cast_1', [200, 800])
        original = await self.until(a, lambda s: s['world'].get('pending_casts'))
        await b.close()
        frozen = await self.until(a, lambda s: s['pause_reason'] == 'disconnected')
        await asyncio.sleep(.08)
        self.assertEqual(frozen['world']['clock'], game.clock)
        bad, reply = await self.join(2, self.guest['token'], version=0)
        self.assertEqual(reply['error'], 'update_required')
        await bad.close()
        b, _ = await self.join(2, self.guest['token'])
        resumed = await self.until(b, lambda s: not s['paused'])
        self.assertEqual(original['world']['pending_casts'], resumed['world']['pending_casts'])
        game.clock = LIMIT - 1
        await self.until(b, lambda s: s['world']['phase'] == 'swap')
        data = dict(room_id=self.owner['room_id'], token=self.owner['token'], request_id='c'*32)
        for _ in range(2):
            response = await self.client.post('/rooms/leave', json=data, headers=self.headers)
            self.assertEqual(response.status, 200)
        finish = await self.until(b, lambda s: s['world']['phase'] == 'result')
        self.assertEqual(finish['world']['result']['winner'], 2)
        self.assertEqual(finish['world']['result']['metric'], 'forfeit')
        self.assertEqual(len(finish['world']['result']['rounds']), 1)
