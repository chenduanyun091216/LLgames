"""Strict, small wire protocol. Clients never supply authoritative state."""
import json
import math

VERSION = 1
UNIFIED_VERSION = 2
COOP_MODES = {'run_gun': '横版突围', 'boss_duel': '今天我当 Boss', 'sub_courier': '双人潜艇快递', 'tide_race': '潮汐竞速'}
EXTRA_MODES = {'boss_duel': 1, 'sub_courier': 1, 'tide_race': 1}
BOSS_IDS = ('whale', 'mecha', 'orochi')
CAST_ACTIONS = ('cast_1', 'cast_2', 'cast_3')
DUEL_RESULT_ACTIONS = ('result_seen', 'rematch_ready', 'back_lobby')
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
            'mode_caps': ({'type','modes'}, set()),
            'mode_input': ({'type','seq','match_id','epoch','x','y','held'}, {'aim'}),
            'mode_action': ({'type','seq','match_id','epoch','action'}, {'target'}),
            'hello': ({'type', 'version', 'code'}, {'token', 'host_token', 'extra_modes'}),
            'room_settings': ({'type', 'mode', 'orientation'}, {'difficulty', 'start_level', 'mode_options'}),
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
        if 'extra_modes' in msg:
            modes = msg['extra_modes']
            if not isinstance(modes, dict) or len(modes) > 8 or any(
                    not k.isascii() or len(k) > 24 or type(v) is not int or v < 1 for k, v in modes.items()):
                raise ProtocolError('invalid_modes')
    if version == UNIFIED_VERSION and kind in ('ready', 'start'):
        if type(msg['settings_revision']) is not int or msg['settings_revision'] < 0:
            raise ProtocolError('invalid_settings_revision')
    if kind == 'room_settings':
        if msg['orientation'] not in ('landscape', 'portrait') or msg['mode'] not in ('campaign', 'infinite', *COOP_MODES):
            raise ProtocolError('invalid_settings')
        if msg['mode'] == 'campaign':
            if msg.get('difficulty') not in ('easy', 'medium', 'hard') or type(msg.get('start_level')) is not int:
                raise ProtocolError('invalid_campaign_settings')
        elif 'difficulty' in msg or 'start_level' in msg:
            raise ProtocolError('invalid_infinite_settings')
        if msg['mode'] == 'boss_duel':
            options = msg.get('mode_options')
            if not isinstance(options, dict) or set(options) != {'boss'} or options['boss'] not in BOSS_IDS:
                raise ProtocolError('invalid_boss_settings')
        elif msg['mode'] == 'sub_courier':
            options = msg.get('mode_options')
            if not isinstance(options, dict) or options.keys() != {'order'} or options['order'] not in ('jelly', 'express', 'calf'):
                raise ProtocolError('invalid_order')
        elif msg['mode'] == 'tide_race':
            from game_core.modes.tide_race import TRACK_IDS
            options = msg.get('mode_options')
            if not isinstance(options, dict) or options.keys() != {'track'} or options['track'] not in TRACK_IDS:
                raise ProtocolError('invalid_track')
        elif 'mode_options' in msg:
            raise ProtocolError('unexpected_mode_options')
    if kind == 'ack_notice' and not all(valid_id(msg[key]) for key in ('event_id', 'match_id')):
        raise ProtocolError('invalid_notice')
    if kind == 'ready' and type(msg['ready']) is not bool:
        raise ProtocolError('invalid_ready')
    if kind == 'start' and version == VERSION and msg['difficulty'] not in ('easy','medium','hard'):
        raise ProtocolError('invalid_difficulty')
    if kind == 'mode_caps':
        ids = msg['modes']
        if not isinstance(ids,list) or len(ids)>8 or any(not isinstance(i,str) or i not in COOP_MODES for i in ids):
            raise ProtocolError('invalid_modes')
    if kind in ('mode_input','mode_action'):
        if type(msg['epoch']) is not int or msg['epoch'] < 0:
            raise ProtocolError('invalid_epoch')
        if kind == 'mode_input' and (type(msg['held']) is not int or not 0 <= msg['held'] <= 15 or
                any(type(msg[k]) not in (int,float) or not -1 <= msg[k] <= 1 for k in ('x','y'))):
            raise ProtocolError('invalid_mode_input')
        if 'aim' in msg and (not isinstance(msg['aim'],list) or len(msg['aim'])!=2 or
                any(type(n) is not int or n not in (-1,0,1) for n in msg['aim']) or not any(msg['aim'])):
            raise ProtocolError('invalid_aim')
        if kind == 'mode_action':
            action = msg['action']
            if action not in ('jump', 'continue_solo', 'end_run', 'skill1', 'skill2', 'weapon', 'hero',
                              'launch', 'dash', 'round_ready', *CAST_ACTIONS, *DUEL_RESULT_ACTIONS,
                              'power_next', 'station_next', 'deliver', 'swap_request',
                              'signal_dive', 'signal_slow', 'signal_cargo', 'signal_dock'):
                raise ProtocolError('invalid_mode_action')
            target = msg.get('target')
            if action in CAST_ACTIONS:
                if not isinstance(target, list) or len(target) != 2 or any(
                        type(n) is not int or not 0 <= n <= 1000 for n in target):
                    raise ProtocolError('invalid_target')
            elif 'target' in msg:
                raise ProtocolError('unexpected_target')
    if kind in ('input', 'action','mode_input','mode_action'):
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
