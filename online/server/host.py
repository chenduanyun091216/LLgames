"""One reserved two-player room behind the unified PC/Web entry points."""
import asyncio
import contextlib
import hashlib
import secrets
import time

from aiohttp import web

from online.shared.protocol import MAX_MESSAGE, UNIFIED_VERSION, ProtocolError, valid_id
from .app import HOST_KEY, Peer, Room, guard, static_file, websocket


class MatchRoom(Room):
    def __init__(self, request_id, now):
        super().__init__()
        self.id = secrets.token_hex(16)
        self.host_token = secrets.token_urlsafe(32)
        self.request_id = request_id
        self.created = now
        self.mode = 'campaign'
        self.start_level = 1
        self.revision = 0
        self.notices = {}

    def snapshot(self):
        state = super().snapshot()
        state.update(version=UNIFIED_VERSION, mode=self.mode, start_level=self.start_level,
                     settings_revision=self.revision, notices=list(self.notices.values()))
        return state

    def start(self, difficulty):
        super().start(difficulty, mode=self.mode, start_level=self.start_level)
        self.notices.clear()

    def handle(self, peer, message):
        kind = message['type']
        if kind == 'room_settings':
            if peer.slot != 1:
                return 'host_only'
            if self.game is not None:
                return 'match_in_progress'
            settings = (message['mode'], message['orientation'],
                        message.get('difficulty', 'hard'), message.get('start_level', 1))
            from game_core.config import LEVEL_CONFIGS
            if not 1 <= settings[3] <= len(LEVEL_CONFIGS):
                return 'invalid_start_level'
            if settings != (self.mode, self.orientation, self.difficulty, self.start_level):
                self.mode, self.orientation, self.difficulty, self.start_level = settings
                self.revision += 1
                for player in self.players:
                    player.ready = False
            return None
        if kind in ('ready', 'start') and message['settings_revision'] != self.revision:
            return 'settings_changed'
        if kind == 'start':
            message = dict(message, difficulty=self.difficulty)
        if (kind == 'action' and message['action'] == 'continue'
                and self.mode == 'infinite' and self.game is not None):
            if message['match_id'] != self.match_id or message['seq'] <= peer.seq:
                return 'stale_action'
            peer.seq = message['seq']
            return self.game.action(peer.slot, 'continue')
        if kind == 'ack_notice':
            event = self.notices.get(peer.slot)
            if event and message['match_id'] == self.match_id and event['event_id'] == message['event_id']:
                del self.notices[peer.slot]
            return None
        return super().handle(peer, message)

    def remove(self, peer):
        if self.game:
            self.game.set_input(peer.slot, 0, 0, False)
            self.game.remove_player(peer.slot)
        self.players.remove(peer)
        self.notices.pop(peer.slot, None)
        if self.game:
            for player in self.players:
                self.notices[player.slot] = {
                    'event_id': secrets.token_hex(16), 'recipient_slot': player.slot,
                }


class Host:
    version = UNIFIED_VERSION

    def __init__(self, static_root, clock=time.monotonic, reservation=60, reconnect=120):
        self.static_root = static_root.resolve()
        self.clock = clock
        self.reservation = reservation
        self.reconnect = reconnect
        self.room = None
        self.public_url = ''
        self.attempts = {}
        self.receipts = {}

    def limited(self, address):
        now = self.clock()
        self.attempts = {key: value for key, value in self.attempts.items() if now - value[0] < 10}
        start, count = self.attempts.get(address, (now, 0))
        self.attempts[address] = start, count + 1
        return count >= 30

    def admit(self, hello):
        room = self.room
        if room is None or not secrets.compare_digest(room.code, hello['code']):
            raise ProtocolError('wrong_room_code')
        token = hello.get('token')
        host_token = hello.get('host_token')
        if token:
            peer = next((p for p in room.players if secrets.compare_digest(p.token, token)), None)
            if peer is None:
                raise ProtocolError('invalid_reconnect_token')
        else:
            slot = 1 if host_token else 2
            if host_token and (room.host_token is None or not secrets.compare_digest(room.host_token, host_token)):
                raise ProtocolError('invalid_host_token')
            peer = next((p for p in room.players if p.slot == slot), None)
            if (slot == 2 and (peer is not None or room.game is not None)):
                raise ProtocolError('room_full')
            if peer is None:
                peer = Peer(slot)
                room.players.append(peer)
        if peer.ws is not None:
            raise ProtocolError('already_connected')
        return room, peer

    async def dispose(self, room):
        if self.room is room:
            self.room = None
        room.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await room.task
        for peer in room.players:
            if peer.ws is not None:
                await peer.ws.close(code=1001, message=b'Room closed')

    async def remove(self, room, peer):
        if (room.game and (room.mode == 'infinite' or
                           not room.game.all_players[peer.slot - 1].alive)
                or not room.game and peer.slot == 2):
            room.remove(peer)
            if room.players:
                room.broadcast()
                return
        await self.dispose(room)

    async def maintain(self):
        while True:
            await asyncio.sleep(.25)
            now = self.clock()
            self.receipts = {key: at for key, at in self.receipts.items() if now - at < self.reconnect}
            room = self.room
            if room is None:
                continue
            if room.host_token is not None and now - room.created >= self.reservation:
                await self.dispose(room)
                continue
            for peer in tuple(room.players):
                if peer.dropped_at is not None and now - peer.dropped_at >= self.reconnect:
                    await self.remove(room, peer)
                    if self.room is not room:
                        break


def create_host(static_root, **options):
    host = Host(static_root, **options)
    app = web.Application(middlewares=[guard], client_max_size=MAX_MESSAGE)
    app[HOST_KEY] = host

    async def lifecycle(_):
        task = asyncio.create_task(host.maintain())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if host.room:
            await host.dispose(host.room)

    async def health(_):
        index = host.static_root / 'index.html'
        return web.json_response({'version': UNIFIED_VERSION, 'ready': index.is_file(),
                                  'build': hashlib.sha256(index.read_bytes()).hexdigest()[:16] if index.is_file() else None,
                                  'url': host.public_url})

    async def create(request):
        if host.limited(request.remote):
            return web.json_response({'error': 'rate_limit'}, status=429)
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return web.json_response({'error': 'invalid_json'}, status=400)
        request_id = body.get('request_id') if isinstance(body, dict) else None
        if not valid_id(request_id):
            return web.json_response({'error': 'invalid_request_id'}, status=400)
        room = host.room
        if room is None:
            room = host.room = MatchRoom(request_id, host.clock())
            room.task = asyncio.create_task(room.run())
        elif room.request_id != request_id or room.host_token is None:
            return web.json_response({'error': 'room_in_use'}, status=409)
        base = host.public_url or f'{request.scheme}://{request.host}/'
        return web.json_response({'room_id': room.id, 'code': room.code, 'host_token': room.host_token,
                                  'invite_url': f'{base}?room={room.code}'})

    async def leave(request):
        if host.limited(request.remote):
            return web.json_response({'error': 'rate_limit'}, status=429)
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return web.json_response({'error': 'invalid_json'}, status=400)
        if not isinstance(body, dict) or not all(valid_id(body.get(k)) for k in ('token', 'request_id', 'room_id')):
            return web.json_response({'error': 'invalid_request'}, status=400)
        key = (body['room_id'], body['token'], body['request_id'])
        if key in host.receipts:
            return web.json_response({'left': True})
        room = host.room
        peer = next((p for p in room.players if secrets.compare_digest(p.token, body['token'])), None) if room and room.id == body['room_id'] else None
        if peer is None:
            return web.json_response({'error': 'invalid_reconnect_token'}, status=403)
        host.receipts[key] = host.clock()
        await host.remove(room, peer)
        if peer.ws is not None:
            await peer.ws.close()
        return web.json_response({'left': True})

    async def join(request):
        if host.limited(request.remote):
            return web.json_response({'error': 'rate_limit'}, status=429)
        return await websocket(request)

    app.cleanup_ctx.append(lifecycle)
    app.router.add_get('/health', health)
    app.router.add_post('/rooms', create)
    app.router.add_post('/rooms/leave', leave)
    app.router.add_get('/ws', join)
    app.router.add_get('/{path:.*}', static_file)
    return app
