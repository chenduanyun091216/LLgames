"""Strict, small wire protocol. Clients never supply authoritative state."""
import json
import math

VERSION = 1
MAX_MESSAGE = 2048
ACTIONS = frozenset(('skill1', 'skill2', 'laser', 'dart', 'shop_open', 'shop_close', 'revive', 'weapon', 'character', 'restart', 'suspend', 'resume'))

class ProtocolError(ValueError):
    pass

def decode(raw):
    if not isinstance(raw, str) or len(raw.encode('utf8')) > MAX_MESSAGE:
        raise ProtocolError('message_too_large_or_binary')
    try:
        def pairs(items):
            out = {}
            for k, v in items:
                if k in out:
                    raise ProtocolError('duplicate_field')
                out[k] = v
            return out
        msg = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError('nonfinite_number')))
    except (ValueError, TypeError, RecursionError) as e:
        raise ProtocolError('invalid_json') from e
    if not isinstance(msg, dict):
        raise ProtocolError('expected_object')
    kind = msg.get('type')
    specs = {'hello': ({'type','version','code'}, {'token'}), 'ready': ({'type','ready'}, set()), 'start': ({'type','difficulty'}, set()), 'input': ({'type','seq','match_id','dx','dy','shoot'}, set()), 'action': ({'type','seq','match_id','action'}, {'key'})}
    if not isinstance(kind, str) or kind not in specs:
        raise ProtocolError('unknown_type')
    required, optional = specs[kind]
    if not required <= msg.keys() or msg.keys() - required - optional:
        raise ProtocolError('invalid_fields')
    if kind == 'hello':
        if type(msg['version']) is not int or msg['version'] != VERSION:
            raise ProtocolError('unsupported_version')
        if not isinstance(msg['code'], str) or len(msg['code']) > 32 or not msg['code'].isascii():
            raise ProtocolError('invalid_code')
        if 'token' in msg and (not isinstance(msg['token'], str) or len(msg['token']) > 128 or not msg['token'].isascii()):
            raise ProtocolError('invalid_token')
    if kind == 'ready' and type(msg['ready']) is not bool:
        raise ProtocolError('invalid_ready')
    if kind == 'start' and msg['difficulty'] not in ('easy','medium','hard'):
        raise ProtocolError('invalid_difficulty')
    if kind in ('input', 'action'):
        if type(msg['seq']) is not int or not 0 <= msg['seq'] < 2**53:
            raise ProtocolError('invalid_sequence')
        if not isinstance(msg['match_id'], str) or len(msg['match_id']) > 64:
            raise ProtocolError('invalid_match_id')
    if kind == 'input':
        for axis in ('dx', 'dy'):
            v = msg[axis]
            if type(v) not in (int,float) or not -1 <= v <= 1 or not math.isfinite(v):
                raise ProtocolError('invalid_axis')
        if type(msg['shoot']) is not bool:
            raise ProtocolError('invalid_shoot')
    if kind == 'action':
        if not isinstance(msg['action'], str) or msg['action'] not in ACTIONS:
            raise ProtocolError('invalid_action')
        if 'key' in msg and (not isinstance(msg['key'], str) or not 1 <= len(msg['key']) <= 32):
            raise ProtocolError('invalid_key')
        if 'key' in msg and msg['action'] not in ('weapon', 'character'):
            raise ProtocolError('unexpected_key')
    return msg
