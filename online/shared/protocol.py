"""Strict, small wire protocol. Clients never supply authoritative state."""
import json
import math

VERSION = 1
UNIFIED_VERSION = 2
MAX_MESSAGE = 2048
ACTIONS = frozenset(('skill1', 'skill2', 'laser', 'dart', 'shop_open', 'shop_close', 'revive', 'weapon', 'character', 'restart', 'suspend', 'resume', 'pause', 'unpause', 'continue', 'rage', 'upgrade', 'add_gold'))

class ProtocolError(ValueError):
    pass

def decode(raw, version=VERSION):
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
    specs = {'orientation': ({'type','orientation'}, set()), 'room_orientation': ({'type','orientation'}, set()), 'hello': ({'type','version','code'}, {'token'}), 'ready': ({'type','ready'}, set()), 'start': ({'type','difficulty'}, set()), 'input': ({'type','seq','match_id','dx','dy','shoot'}, set()), 'action': ({'type','seq','match_id','action'}, {'key'})}
    if version == UNIFIED_VERSION:
        specs.update({
            'hello': ({'type', 'version', 'code'}, {'token', 'host_token'}),
            'room_settings': ({'type', 'mode', 'orientation'}, {'difficulty', 'start_level'}),
            'ready': ({'type', 'ready', 'settings_revision'}, set()),
            'start': ({'type', 'settings_revision'}, set()),
            'ack_notice': ({'type', 'event_id', 'match_id'}, set()),
        })
        del specs['room_orientation']
    if not isinstance(kind, str) or kind not in specs:
        raise ProtocolError('unknown_type')
    required, optional = specs[kind]
    if not required <= msg.keys() or msg.keys() - required - optional:
        raise ProtocolError('invalid_fields')
    if kind in ('orientation', 'room_orientation') and msg['orientation'] not in ('landscape', 'portrait'):
        raise ProtocolError('invalid_orientation')
    if kind == 'hello':
        if type(msg['version']) is not int or msg['version'] != version:
            raise ProtocolError('unsupported_version')
        if not isinstance(msg['code'], str) or len(msg['code']) != 4 or not msg['code'].isascii() or not msg['code'].isdigit():
            raise ProtocolError('invalid_code')
        if 'token' in msg and (not isinstance(msg['token'], str) or len(msg['token']) > 128 or not msg['token'].isascii()):
            raise ProtocolError('invalid_token')
        if 'host_token' in msg and ('token' in msg or not valid_id(msg['host_token'])):
            raise ProtocolError('invalid_host_token')
    if version == UNIFIED_VERSION and kind in ('ready', 'start'):
        if type(msg['settings_revision']) is not int or msg['settings_revision'] < 0:
            raise ProtocolError('invalid_settings_revision')
    if kind == 'room_settings':
        if msg['orientation'] not in ('landscape', 'portrait') or msg['mode'] not in ('campaign', 'infinite'):
            raise ProtocolError('invalid_settings')
        if msg['mode'] == 'campaign':
            if msg.get('difficulty') not in ('easy', 'medium', 'hard') or type(msg.get('start_level')) is not int:
                raise ProtocolError('invalid_campaign_settings')
        elif 'difficulty' in msg or 'start_level' in msg:
            raise ProtocolError('invalid_infinite_settings')
    if kind == 'ack_notice' and not all(valid_id(msg[key]) for key in ('event_id', 'match_id')):
        raise ProtocolError('invalid_notice')
    if kind == 'ready' and type(msg['ready']) is not bool:
        raise ProtocolError('invalid_ready')
    if kind == 'start' and version == VERSION and msg['difficulty'] not in ('easy','medium','hard'):
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
        if 'key' in msg and msg['action'] not in ('weapon', 'character', 'upgrade'):
            raise ProtocolError('unexpected_key')
    return msg


def valid_id(value):
    return isinstance(value, str) and 20 <= len(value) <= 128 and all(
        c.isascii() and (c.isalnum() or c in "-_") for c in value)
