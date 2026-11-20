import asyncio
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from online.server.app import HOST_KEY
from online.server.host import create_host
from online.shared.protocol import UNIFIED_VERSION


class UnifiedLANTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = TestClient(TestServer(create_host(Path(self.tmp.name))))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.host = self.client.app[HOST_KEY]
        self.headers = {'Origin': str(self.client.make_url('/')).rstrip('/')}

    async def post(self, path, data):
        return await self.client.post(path, json=data, headers=self.headers)

    async def prepare(self):
        response = await self.post('/rooms', {'request_id': 'a' * 32})
        self.assertEqual(response.status, 200)
        return await response.json()

    async def join(self, room, host=False):
        ws = await self.client.ws_connect('/ws', headers=self.headers)
        hello = dict(type='hello', version=UNIFIED_VERSION, code=room['code'])
        if host:
            hello['host_token'] = room['host_token']
        await ws.send_json(hello)
        result = await ws.receive_json(timeout=2)
        self.assertEqual(result['type'], 'welcome')
        await ws.send_json(dict(type='orientation', orientation='landscape'))
        return ws, result

    async def wait_for(self, predicate):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(.01)
        self.fail('server state did not converge')

    async def start(self, mode, level=1):
        room = await self.prepare()
        p2 = await self.join(room)
        p1 = await self.join(room, host=True)
        self.assertEqual([p1[1]['slot'], p2[1]['slot']], [1, 2])
        settings = dict(type='room_settings', mode=mode, orientation='landscape')
        if mode == 'campaign':
            settings.update(difficulty='medium', start_level=level)
        await p1[0].send_json(settings)
        await self.wait_for(lambda: self.host.room.revision == 1)
        await p2[0].send_json(dict(type='ready', ready=True, settings_revision=0))
        await p1[0].send_json(dict(type='ready', ready=True, settings_revision=1))
        await self.wait_for(lambda: any(p.ready for p in self.host.room.players))
        self.assertFalse(next(p for p in self.host.room.players if p.slot == 2).ready)
        await p2[0].send_json(dict(type='ready', ready=True, settings_revision=1))
        await self.wait_for(lambda: all(p.ready for p in self.host.room.players))
        await p1[0].send_json(dict(type='start', settings_revision=1))
        await self.wait_for(lambda: self.host.room.game is not None)
        return p1, p2

    async def test_creation_retry_and_slot_reservation(self):
        self.assertIsNone(self.host.room)
        room = await self.prepare()
        self.assertEqual(room, await self.prepare())
        response = await self.post('/rooms', {'request_id': 'b' * 32})
        self.assertEqual(response.status, 409)
        _, guest = await self.join(room)
        self.assertEqual(guest['slot'], 2)
        _, owner = await self.join(room, host=True)
        self.assertEqual(owner['slot'], 1)

    async def test_campaign_start_level(self):
        await self.start('campaign', 11)
        self.assertEqual(self.host.room.game.current_level, 11)
        self.assertEqual(self.host.room.snapshot()['start_level'], 11)

    async def test_defeated_campaign_player_can_leave_without_stopping_teammate(self):
        p1, p2 = await self.start('campaign')
        room = self.host.room
        game = room.game
        game.lives = 0
        game.player.gold = 0
        game._damage_target = game.all_players[0]
        game.all_players[0].invincible_until = 0
        game._damage_player(0, 100, 'test')
        response = await self.post('/rooms/leave', dict(
            room_id=p1[1]['room_id'], token=p1[1]['token'], request_id='q' * 32))
        self.assertEqual(response.status, 200)
        tick = game.tick
        await self.wait_for(lambda: game.tick > tick)
        self.assertFalse(room.snapshot()['paused'])
        self.assertTrue(game.all_players[1].alive)

    async def test_infinite_departure_keeps_p2_and_notice(self):
        p1, p2 = await self.start('infinite')
        room = self.host.room
        match = room.match_id
        data = dict(room_id=p1[1]['room_id'], token=p1[1]['token'], request_id='z' * 32)
        for _ in range(2):
            response = await self.post('/rooms/leave', data)
            self.assertEqual(response.status, 200)
        tick = room.game.tick
        await self.wait_for(lambda: room.game.tick > tick)
        state = room.snapshot()
        self.assertEqual(state['match_id'], match)
        self.assertFalse(state['paused'])
        self.assertEqual([p['slot'] for p in state['world']['players']], [2])
        self.assertEqual(len(state['notices']), 1)
        await p2[0].send_json(dict(type='ack_notice', match_id=match, event_id=state['notices'][0]['event_id']))
        await self.wait_for(lambda: not room.notices)

    async def test_independent_continue_and_pause(self):
        p1, p2 = await self.start('infinite')
        room = self.host.room
        game = room.game
        now = game.tick * 1000 // 60
        for player in game.all_players:
            with game._for_player(player):
                game._damage_player(now, 100, '测试阵亡')
        self.assertFalse(game.players)
        self.assertEqual(game.infinite_deaths, 2)
        def action(name, seq):
            return dict(type='action', action=name, seq=seq, match_id=room.match_id)
        await p2[0].send_json(action('pause', 1))
        await self.wait_for(lambda: room.pause_reason() == 'manual_pause')
        await p1[0].send_json(action('continue', 1))
        await self.wait_for(lambda: game.continuing.get(1) == 180)
        await p1[0].send_json(action('continue', 2))
        await asyncio.sleep(.05)
        self.assertEqual(game.continuing[1], 180)
        await p2[0].send_json(action('unpause', 2))
        await self.wait_for(lambda: game.continuing[1] < 180)
        game.continuing[1] = 1
        await self.wait_for(lambda: bool(game.players))
        self.assertEqual([p.slot for p in game.players], [1])

    async def test_shared_view_restores_local_ui_and_disables_level_switch(self):
        from types import SimpleNamespace
        import pygame
        from game_core import config
        from game_core.game import Game
        from online.client.integrated import LAN

        await self.start('campaign', 9)
        room = self.host.room
        size = (1280, 720)
        window = pygame.display.set_mode(size)
        names = ('SCR', 'SCREEN_WIDTH', 'SCREEN_HEIGHT', 'VIEW_SIZE', 'VIEW_OFFSET')
        saved = {name: getattr(config, name) for name in names}
        try:
            config.update_mobile_view(size)
            local = Game(desktop_controls=True)
            sent = []
            client = LAN(SimpleNamespace(slot=2, error='', send=sent.append))
            local_rects = local._hud_controls()
            px, py = local_rects[0].center
            event = pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, touch=False,
                pos=(round(px * config.VIEW_SCALE), round(py * config.VIEW_SCALE)))
            client.battle(local, room.snapshot(), [event], False, None)
            self.assertEqual(config.SCR.get_size(), (960, 540))
            self.assertEqual(client.presentation.view._hud_controls(), local_rects)
            self.assertEqual(client.notice, '仅开局可选关')
            self.assertFalse(any(message['type'] == 'action' for message in sent))
            self.assertEqual(room.game.current_level, 9)
        finally:
            for name, value in saved.items():
                setattr(config, name, value)



class LobbyOrientationTests(unittest.TestCase):
    def test_lobby_explains_orientation_and_starts_after_rotation(self):
        for mode in ('campaign', 'infinite'):
            with self.subTest(mode=mode):
                self.check_orientation_blocks_start(mode)

    def check_orientation_blocks_start(self, mode):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from online.client.integrated import LAN
        from online.server.app import Peer
        from online.server.host import MatchRoom

        room = MatchRoom('a' * 32, 0)
        room.mode, room.orientation = mode, 'landscape'
        owner = Peer(slot=1, ws=object(), ready=True, orientation='landscape')
        guest = Peer(slot=2, ws=object(), ready=True, orientation='portrait')
        room.players = [owner, guest]
        transport = SimpleNamespace(slot=1, error='orientation_mismatch', invite='', send=Mock())
        ui = LAN(transport)
        ui.draw_room = Mock()
        ui.lobby(None, [], room.snapshot(), 'landscape')
        _, rows, _, detail, _ = ui.draw_room.call_args.args
        self.assertIn(('开始对局', None), rows)
        self.assertIn('请 P2 切换至横屏', detail)
        self.assertNotIn('orientation_mismatch', detail)
        self.assertEqual(room.handle(owner, {'type': 'start', 'settings_revision': 0}),
                         'orientation_mismatch')

        room.handle(guest, {'type': 'orientation', 'orientation': 'landscape'})
        ui.lobby(None, [], room.snapshot(), 'landscape')
        _, rows, _, detail, _ = ui.draw_room.call_args.args
        self.assertNotIn('orientation_mismatch', detail)
        self.assertIn('P2 已准备', detail)
        dict(rows)['开始对局']()
        self.assertIsNone(room.handle(owner, transport.send.call_args.args[0]))
        self.assertIsNotNone(room.game)


class IntegratedShopTests(unittest.TestCase):
    def test_shop_purchase_and_opener_closes_both_at_display_resolution(self):
        from types import SimpleNamespace

        import pygame

        from game_core import config
        from game_core.game import Game, GameState
        from online.client.integrated import LAN
        from online.server.app import Peer
        from online.server.host import MatchRoom

        pygame.init()
        window = pygame.display.set_mode((780, 1688))
        room = MatchRoom('a' * 32, 0)
        room.orientation = 'portrait'
        room.players = [Peer(slot=slot, ws=object(), orientation='portrait') for slot in (1, 2)]
        room.start('medium')
        room.game.player.gold = 1000
        config.update_mobile_view(window.get_size(), (390, 844))
        game = Game(web=True, mobile_web=True)
        game.clock = SimpleNamespace(get_fps=lambda: 54.6)
        seq = {1: 0, 2: 0}
        errors = []
        def send(slot, message):
            if message['type'] in ('input', 'action'):
                seq[slot] += 1
                error = room.handle(room.players[slot - 1], dict(
                    message, match_id=room.match_id, seq=seq[slot]))
                if error:
                    errors.append(error)
        clients = [LAN(SimpleNamespace(slot=slot, error='', send=lambda message, slot=slot: send(slot, message)))
                   for slot in (1, 2)]
        clients[0].send('shop_open')

        def draw(client, action=None):
            config.update_mobile_view(window.get_size(), (390, 844))
            events = []
            if action is not None:
                rect = client.presentation.view._mobile_shop_rects()[action]
                x, y = rect.center
                pos = (round(x * config.VIEW_SCALE + config.VIEW_OFFSET[0]),
                       round(y * config.VIEW_SCALE + config.VIEW_OFFSET[1]))
                if client.transport.slot == 2:
                    width, height = window.get_size()
                    events = [pygame.event.Event(pygame.FINGERDOWN, finger_id=1,
                                                 x=pos[0] / width, y=pos[1] / height)]
                else:
                    events = [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)]
            client.battle(game, room.snapshot(), events, False, None, window)
            return client.presentation.view.state

        self.assertEqual(draw(clients[0]), GameState.SHOP)
        self.assertEqual(draw(clients[1]), GameState.SHOP)
        draw(clients[0], 'weapon:rifle')
        self.assertEqual(room.game.player.current_weapon, 'rifle')
        room.players[0].suspended = True
        draw(clients[0], 'close')
        self.assertFalse(any(p.shop_open for p in room.game.all_players))
        self.assertEqual(room.snapshot()['pause_reason'], 'suspended')
        room.players[0].suspended = False
        self.assertFalse(room.snapshot()['paused'])
        self.assertEqual(draw(clients[0]), GameState.PLAYING)
        previous_tick = room.game.tick
        room.game.step()
        self.assertEqual(room.game.tick, previous_tick + 1)
        from unittest.mock import patch
        view = clients[1].presentation.view
        with patch.object(view, '_draw_text_fit', wraps=view._draw_text_fit) as draw_text:
            self.assertEqual(draw(clients[1]), GameState.PLAYING)
        self.assertIn('FPS 55', [call.args[0] for call in draw_text.call_args_list if call.args])
        self.assertTrue(clients[1].drawn_to_window)
        self.assertGreater(clients[1].projected.get_width(), 480)
        self.assertEqual(errors, [])


class IntegratedPauseTests(unittest.TestCase):
    def test_reuses_composed_world_until_snapshot_or_layout_changes(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import pygame

        from game_core import config
        from game_core.game import Game
        from online.adapters.core_adapter import OnlineGame
        from online.adapters.presentation import Presentation
        from online.client.integrated import LAN

        pygame.init()
        window = pygame.display.set_mode((450, 970))
        host = OnlineGame(orientation='portrait')
        state = dict(host.snapshot(), match_id='one', mode='campaign')
        config.update_mobile_view(window.get_size(), (390, 844))
        game = Game(web=True, mobile_web=True)
        client = LAN(SimpleNamespace(slot=1, error='', send=lambda message: None))

        with patch.object(Presentation, 'draw', autospec=True, side_effect=Presentation.draw) as draw:
            client.battle(game, state, [], False, None, window)
            expected = pygame.image.tobytes(window, 'RGB')
            window.fill('red')
            view = client.presentation.view
            event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
            with patch.object(view, 'handle_local_events') as handle:
                client.battle(game, state, [event], False, None, window)
                handle.assert_called_once_with([event])
            self.assertEqual(draw.call_count, 1)
            self.assertEqual(pygame.image.tobytes(window, 'RGB'), expected)

            host.step()
            state = dict(host.snapshot(), match_id='one', mode='campaign')
            config.update_mobile_view(window.get_size(), (390, 844))
            client.battle(game, state, [], False, None, window)
            self.assertEqual(draw.call_count, 2)

            window = pygame.display.set_mode((420, 910))
            config.update_mobile_view(window.get_size(), (390, 844))
            client.battle(game, state, [], False, None, window)
            self.assertEqual(draw.call_count, 3)

    def test_repeated_world_draw_does_not_render_local_pause_or_exit_overlay(self):
        from unittest.mock import patch

        import pygame

        from game_core.game import GameState
        from online.adapters.core_adapter import OnlineGame
        from online.adapters.presentation import Presentation

        game = OnlineGame()
        snapshot = game.snapshot()
        presentation = Presentation(pygame.Surface(game.world_size, pygame.SRCALPHA), integrated=True)
        presentation.apply(snapshot)
        view = presentation.view
        for exit_confirmation in (False, True):
            view.state = GameState.PAUSED
            view.exit_confirmation = exit_confirmation
            with patch.object(view, '_draw_pause_overlay', wraps=view._draw_pause_overlay) as overlay:
                presentation.draw()
                presentation.draw()
            overlay.assert_not_called()
            self.assertEqual(view.state, GameState.PAUSED)
            self.assertEqual(view.exit_confirmation, exit_confirmation)
            with patch.object(view, '_draw_pause_overlay', wraps=view._draw_pause_overlay) as overlay:
                view.draw_local_overlay({})
            overlay.assert_called_once_with(shade=82)


class IllustratedHomeTests(unittest.TestCase):
    def test_pc_join_dialog_submits_four_digits_and_preserves_leading_zero(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        import pygame

        from game_core import config
        from game_core.game import Game
        from online.client.integrated import LAN

        pygame.init()
        window = pygame.display.set_mode((1280, 720))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)
        transport = SimpleNamespace(state=None, ended=False, error='', send=Mock(), begin=Mock(), reset=Mock())
        client = LAN(transport)
        client.join_form()
        enter = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_KP_ENTER)
        for text in ('01', '23'):
            client.frame(game, [pygame.event.Event(pygame.TEXTINPUT, text=text), enter],
                         window, False, False)
            if text == '01':
                self.assertEqual(client.page, 'join')
                self.assertTrue(client.drawn_to_window)
                transport.begin.assert_not_called()
        transport.begin.assert_called_once_with('join', '0123')
        self.assertEqual(client.page, 'room')

    def test_home_buttons_match_layout_and_dispatch_actions(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        import pygame

        from game_core import config, menu_ui
        from game_core.game import Game, GameState
        from online.client.integrated import LAN

        pygame.init()
        for size in ((1280, 720), (390, 844)):
            with self.subTest(size=size):
                web = size[0] < size[1]
                window = pygame.display.set_mode(size)
                config.update_mobile_view(size)
                game = Game(desktop_controls=not web, web=web, mobile_web=web)
                transport = SimpleNamespace(address='', begin=Mock(), reset=Mock())
                layout = menu_ui.entrance_rects()
                self.assertEqual(len({layout[key].width for key in ('single', 'create', 'join')}), 1)
                self.assertEqual(layout['keys'].width, layout['keys'].height)
                self.assertEqual(layout['keys'].left - layout['join'].right, 8)
                self.assertEqual(layout['join'].top, layout['keys'].top)
                _, poster, row = menu_ui._home_boxes(entrances=True)
                self.assertLess(poster.bottom, row.top)
                self.assertTrue(config.SCR.get_rect().contains(layout['keys']))
                for action in layout:
                    client = LAN(transport)
                    x, y = layout[action].center
                    if web:
                        event = pygame.event.Event(pygame.FINGERDOWN, finger_id=1,
                                                   x=x * config.VIEW_SCALE / size[0],
                                                   y=y * config.VIEW_SCALE / size[1])
                    else:
                        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                   pos=(round(x * config.VIEW_SCALE), round(y * config.VIEW_SCALE)))
                    client.draw_home(game, [event], window)
                    self.assertTrue(client.drawn_to_window)
                    if action == 'single':
                        self.assertEqual(client.page, 'single')
                        self.assertEqual(game.state, GameState.MENU)
                        game.on_return_home = client.home
                        single = game._mobile_menu_rects()
                        room = menu_ui.room_action_rects(7)
                        self.assertEqual({rect.centery for rect in
                                          (*layout.values(), *single.values(), *room)},
                                         {layout['single'].centery})
                        x, y = single['back'].center
                        if web:
                            back_event = pygame.event.Event(pygame.FINGERDOWN, finger_id=2,
                                                           x=x / config.SCREEN_WIDTH, y=y / config.SCREEN_HEIGHT)
                        else:
                            back_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                           pos=(round(x * config.VIEW_SCALE), round(y * config.VIEW_SCALE)))
                        self.assertTrue(game.handle_events([back_event]))
                        self.assertEqual(client.page, 'home')
                    elif action == 'create':
                        self.assertEqual(client.page, 'room')
                        transport.begin.assert_called_once_with('create', '')
                    elif action == 'join':
                        self.assertEqual(client.page, 'join')
                    else:
                        self.assertTrue(client.home_keys)
                        self.assertEqual(game.state, GameState.KEY_SETTINGS)

    def test_pc_lobby_shortcuts_dispatch_only_enabled_buttons(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        import pygame

        from online.client.integrated import LAN

        client = LAN(SimpleNamespace())
        game = SimpleNamespace(desktop_controls=True)
        actions = [Mock() for _ in range(7)]
        rows = [(str(index), action) for index, action in enumerate(actions)]
        keys = (*range(pygame.K_1, pygame.K_7), pygame.K_ESCAPE)
        with patch('game_core.menu_ui.draw_room'):
            for key in keys:
                client.draw_room(game, rows, [pygame.event.Event(pygame.KEYDOWN, key=key)], '', '')
            rows[5] = ('开始对局', None)
            client.draw_room(game, rows, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_6)], '', '')
        for action in actions:
            action.assert_called_once_with()


class SnapshotCadenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_room_sends_thirty_snapshots_per_sixty_simulation_steps(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from online.server.app import Room

        room = Room(code='0123')
        room.game = Mock()
        room.pause_reason = Mock(return_value=None)
        steps_at_broadcast = []
        room.broadcast = Mock(side_effect=lambda: steps_at_broadcast.append(room.game.step.call_count))
        now = 0

        async def advance(delay):
            nonlocal now
            now += delay
            if room.game.step.call_count == 60:
                raise asyncio.CancelledError

        with patch('online.server.app.time', SimpleNamespace(monotonic=lambda: now)), \
                patch('online.server.app.asyncio', SimpleNamespace(sleep=advance)), \
                self.assertRaises(asyncio.CancelledError):
            await room.run()

        self.assertAlmostEqual(now, 1)
        self.assertEqual(steps_at_broadcast, list(range(2, 61, 2)))
