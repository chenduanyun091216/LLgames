"""Two-player authoritative room and restricted aiohttp HTTP/WebSocket transport."""
import asyncio
import contextlib
import ipaddress
import json
import logging
from copy import deepcopy
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web
from online.shared.world import WORLD_SIZES
from online.shared.protocol import decode, ProtocolError, MAX_MESSAGE, VERSION

STATIC_ROOT = Path(__file__).resolve().parents[1] / 'build' / 'web'
ROOM_KEY = web.AppKey('room', object)

@dataclass
class Peer:
    slot: int
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    ws: object = None
    orientation: str = None
    ready: bool = False
    suspended: bool = False
    seq: int = -1
    last_input: float = 0
    queue: object = None
    sender: object = None

class Room:
    def __init__(self, factory=None, code=None):
        self.code = code or secrets.token_hex(3).upper()
        self.factory = factory
        self.players = []
        self.game = None
        self.match_id = secrets.token_hex(16)
        self.task = None
        self.orientation = None
        self.difficulty = 'medium'
        self.failed = False
        self.last_state = None

    def clear_input(self):
        if self.game:
            for p in self.players:
                self.game.set_input(p.slot, 0, 0, False)

    def fail(self):
        if not self.failed:
            logging.getLogger(__name__).exception("Authoritative simulation failed; room paused")
        self.failed = True
        with contextlib.suppress(Exception):
            self.clear_input()

    def pause_reason(self):
        if self.failed:
            return 'server_error'
        if len(self.players) < 2 or any(p.ws is None for p in self.players):
            return 'disconnected'
        if any(p.suspended for p in self.players):
            return 'suspended'
        if self.orientation not in WORLD_SIZES or any(p.orientation != self.orientation for p in self.players):
            return 'orientation_mismatch'
        return None

    def start(self, difficulty):
        if self.factory is None:
            from online.adapters.core_adapter import OnlineGame
            factory = OnlineGame
        else:
            factory = self.factory
        self.game = factory(difficulty=difficulty, orientation=self.orientation)
        self.failed = False
        self.last_state = None
        self.difficulty = difficulty
        self.match_id = secrets.token_hex(16)
        for p in self.players:
            p.last_input = 0
        self.clear_input()

    def snapshot(self):
        empty = {'tick':0, 'phase':'lobby', 'players':[], 'gold':0, 'lives':0, 'world':{}}
        if self.failed:
            state = deepcopy(self.last_state or empty)
        else:
            try:
                state = self.game.snapshot() if self.game else empty
                json.dumps(state, allow_nan=False)
                self.last_state = deepcopy(state)
            except Exception:
                self.fail()
                state = deepcopy(self.last_state or empty)
        state = dict(state)
        game_players = {p['slot']:p for p in state.get('players', [])}
        state['players'] = [dict(game_players.get(p.slot, {'slot':p.slot,'alive':True,'hp':0,'max_hp':0,'shop_open':False}), connected=p.ws is not None, ready=p.ready, orientation=p.orientation) for p in self.players]
        reason = self.pause_reason() or state.get('pause_reason')
        state.update(orientation=self.orientation, world_size=list(WORLD_SIZES[self.orientation]) if self.orientation else None, type='state', version=VERSION, match_id=self.match_id, difficulty=self.difficulty, paused=bool(reason or state.get('paused')), pause_reason=reason)
        return state

    def broadcast(self):
        payload = json.dumps(self.snapshot(), allow_nan=False, separators=(',', ':'))
        for p in self.players:
            if p.ws is not None:
                if p.queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        p.queue.get_nowait()
                p.queue.put_nowait(payload)

    async def run(self):
        next_tick = time.monotonic()
        count = 0
        while True:
            now = time.monotonic()
            if self.game and not self.failed:
                try:
                    for p in self.players:
                        if now - p.last_input > .4:
                            self.game.set_input(p.slot, 0, 0, False)
                    if not self.pause_reason():
                        self.game.step()
                except Exception:
                    self.fail()
            count += 1
            if count % 3 == 0:
                self.broadcast()
            next_tick += 1/60
            if next_tick < now - .1:
                next_tick = now
            await asyncio.sleep(max(0, next_tick - time.monotonic()))

    def handle(self, peer, msg):
        kind = msg['type']
        if kind == 'orientation':
            peer.orientation = msg['orientation']
            self.clear_input()
            return None
        if kind == 'room_orientation':
            if peer.slot != 1:
                return 'host_only'
            if self.game and self.game.snapshot()['phase'] == 'playing':
                return 'match_in_progress'
            if self.orientation != msg['orientation']:
                self.orientation = msg['orientation']
                for p in self.players:
                    p.ready = False
                self.clear_input()
            return None
        if kind == 'ready':
            if self.game and self.game.snapshot()['phase'] == 'playing':
                return 'match_in_progress'
            peer.ready = msg['ready']
            return None
        if kind == 'start':
            if peer.slot != 1:
                return 'host_only'
            if self.game and self.game.snapshot()['phase'] == 'playing':
                return 'match_in_progress'
            if len(self.players) != 2 or any(p.ws is None or not p.ready for p in self.players):
                return 'players_not_ready'
            if self.pause_reason():
                return self.pause_reason()
            self.start(msg['difficulty'])
            return None
        if kind not in ('input', 'action'):
            return 'unexpected_message'
        if msg['match_id'] != self.match_id:
            return 'stale_match'
        if msg['seq'] <= peer.seq:
            return 'stale_sequence'
        peer.seq = msg['seq']
        if kind == 'action' and msg['action'] in ('suspend','resume'):
            peer.suspended = msg['action'] == 'suspend'
            self.clear_input()
            return None
        if self.game is None:
            return 'not_started'
        if kind == 'action' and msg['action'] == 'restart':
            if peer.slot != 1:
                return 'host_only'
            if len(self.players) != 2 or any(p.ws is None or not p.ready for p in self.players):
                return 'players_not_ready'
            if self.pause_reason() not in (None, 'server_error'):
                return self.pause_reason()
            if any(p.orientation != self.orientation or p.suspended for p in self.players):
                return 'players_not_ready'
            self.start(self.difficulty)
            return None
        if self.pause_reason():
            return 'paused'
        if kind == 'input':
            peer.last_input = time.monotonic()
            self.game.set_input(peer.slot, msg['dx'], msg['dy'], msg['shoot'])
            return None
        return self.game.action(peer.slot, msg['action'], msg.get('key'))


def allowed_host(host):
    try:
        parsed = urlsplit('//' + host)
        name = parsed.hostname
        _ = parsed.port
        if parsed.username or parsed.password or parsed.path or not name:
            return False
        if name == 'localhost':
            return True
        ip = ipaddress.ip_address(name)
        return ip.is_loopback or (ip.is_private and not ip.is_unspecified and not ip.is_multicast and not ip.is_reserved)
    except ValueError:
        return False

@web.middleware
async def guard(request, handler):
    if not allowed_host(request.host):
        raise web.HTTPForbidden(text='Host must be a loopback or private LAN IP')
    origin = request.headers.get('Origin')
    if request.path == '/ws' and origin != f'{request.scheme}://{request.host}':
        raise web.HTTPForbidden(text='Same-origin browser connection required')
    response = await handler(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response

async def send_states(peer):
    ws, queue = peer.ws, peer.queue
    try:
        while True:
            payload = await queue.get()
            await asyncio.wait_for(ws.send_str(payload), 2)
    except (TimeoutError, ConnectionError, RuntimeError):
        await ws.close()

async def websocket(request):
    room = request.app[ROOM_KEY]
    ws = web.WebSocketResponse(max_msg_size=MAX_MESSAGE, heartbeat=10, receive_timeout=30, compress=False)
    await ws.prepare(request)
    peer = None
    async def error(message):
        await asyncio.wait_for(ws.send_json({'type':'error','error':message}), 2)
    try:
        first = await asyncio.wait_for(ws.receive(), 5)
        hello = decode(first.data if first.type == WSMsgType.TEXT else None)
        if hello['type'] != 'hello':
            raise ProtocolError('hello_required')
        if not secrets.compare_digest(hello['code'], room.code):
            raise ProtocolError('wrong_room_code')
        token = hello.get('token')
        if token:
            peer = next((p for p in room.players if secrets.compare_digest(p.token, token)), None)
            if peer is None:
                raise ProtocolError('invalid_reconnect_token')
            if peer.ws is not None:
                peer = None
                raise ProtocolError('already_connected')
        else:
            if len(room.players) >= 2:
                raise ProtocolError('room_full')
            peer = Peer(len(room.players) + 1)
            room.players.append(peer)
        peer.ws, peer.seq, peer.suspended = ws, -1, False
        peer.orientation = None
        peer.last_input = 0
        peer.queue = asyncio.Queue(maxsize=1)
        await ws.send_json({'type':'welcome','version':VERSION,'slot':peer.slot,'token':peer.token,'match_id':room.match_id})
        peer.sender = asyncio.create_task(send_states(peer))
        room.clear_input()
        room.broadcast()
        credit, last = 120., time.monotonic()
        async for incoming in ws:
            if incoming.type != WSMsgType.TEXT:
                break
            now = time.monotonic()
            credit = min(120, credit + (now-last)*90) - 1
            last = now
            if credit < 0:
                raise ProtocolError('rate_limit')
            msg = decode(incoming.data)
            try:
                problem = room.handle(peer, msg)
            except Exception:
                room.fail()
                problem = 'server_error'
            if problem:
                await error(problem)
    except (ProtocolError, TimeoutError) as exc:
        with contextlib.suppress(ConnectionError, TimeoutError, RuntimeError):
            await error(str(exc) or 'timeout')
    finally:
        if peer is not None and peer.ws is ws:
            peer.ws = None
            if peer.sender:
                peer.sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await peer.sender
            room.clear_input()
            room.broadcast()
        await ws.close()
    return ws

async def static_file(request):
    rel = request.match_info.get('path', '') or 'index.html'
    target = (STATIC_ROOT / rel).resolve()
    if not target.is_relative_to(STATIC_ROOT.resolve()) or not target.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(target)

async def lifecycle(app):
    room = app[ROOM_KEY]
    room.task = asyncio.create_task(room.run())
    yield
    room.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await room.task
    for peer in room.players:
        if peer.ws is not None:
            await peer.ws.close(code=1001, message=b'Server stopping')

def create_app(factory=None, code=None):
    app = web.Application(middlewares=[guard], client_max_size=MAX_MESSAGE)
    app[ROOM_KEY] = Room(factory=factory, code=code)
    app.cleanup_ctx.append(lifecycle)
    app.router.add_get('/ws', websocket)
    app.router.add_get('/{path:.*}', static_file)
    return app
