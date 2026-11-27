"""Local Pygame input and presentation for both submarine stations."""
from time import monotonic

import pygame

from game_core import config
from game_core.modes.sub_courier import SIGNALS
from game_core.sounds import make_sound, play_sound, stop_music
from . import sub_courier_art as art

PAUSE = {'disconnected': '等待搭档重连', 'suspended': '搭档切到后台，航行已暂停',
         'orientation_mismatch': '请恢复与房主一致的屏幕方向', 'manual_pause': '航行已暂停',
         'server_error': '航行暂停，房间模拟异常'}


class CourierView:
    def __init__(self):
        self.context = None
        self.role = None
        self.keys = set()
        self.fingers = {}
        self.stick = (0, 0)
        self.signal_menu = False
        self.last_input = None
        self.sent = 0.
        self.last_event = 0
        self.seen = None
        self.flow_channel = None
        self.exit_prompt = False
        self.tutorials = set()
        self.tutorial = ('', 0)

    def silence(self):
        if self.flow_channel:
            self.flow_channel.fadeout(160)
            self.flow_channel = None

    def clear(self):
        self.keys.clear()
        self.fingers.clear()
        self.stick = (0, 0)
        self.signal_menu = False
        self.last_input = None
        self.exit_prompt = False

    def controls(self, width, height, role, state):
        def buttons(specs, y, start=12, available=None):
            gap = ((width - start - 12) if available is None else available) // len(specs)
            return [(key, label, pygame.Rect(start + i * gap, y, gap - 5, 40))
                    for i, (key, label) in enumerate(specs)]

        y = height - 52
        if state['world']['result']:
            specs = [('leave', '返回首页')]
            if len(state['players']) == 2:
                specs = [('rematch_ready', '换岗重送'), ('back_lobby', '回房选单'), ('leave', '离开')]
            return buttons(specs, y)
        if self.exit_prompt:
            return buttons([('leave', '确认离开'), ('cancel', '返回航行')], y)
        if self.signal_menu:
            return buttons([*SIGNALS.items(), ('signals', '返回')], y)
        local = next((p for p in state['players'] if p['slot'] == state.get('local_slot')), {})
        shared = [('swap_request', '换岗'), ('signals', '信号'),
                  ('pause', '继续' if local.get('manual_pause') else '暂停'), ('exit', '离开')]
        if width == 520:
            if role == 'helm':
                return ([('stick', '', pygame.Rect(34, 505, 142, 142))] +
                        buttons([('slow', '慢靠')], 560, start=278) + buttons(shared, y))
            return (buttons([('up', '减压载'), ('down', '加压载')], 535) +
                    buttons([('power_next', '动力'), ('station_next', '选设备'),
                             ('operate', '交货' if state['world']['station'] == 2 else '操作')], 602) +
                    buttons(shared, y))
        if role == 'helm':
            return ([('stick', '', pygame.Rect(32, 457, 70, 70))] +
                    buttons([('slow', '慢靠'), *shared], y, start=125))
        return buttons([('up', '减压载'), ('down', '加压载'), ('power_next', '动力'),
                        ('station_next', '选设备'),
                        ('operate', '交货' if state['world']['station'] == 2 else '操作'), *shared], y)

    @staticmethod
    def axes(point, rect):
        return tuple(max(-1., min(1., (a-b) / (rect.width * .37))) for a, b in zip(point, rect.center))

    def instruction(self, w, role, tick):
        if w['loading_ticks']:
            return f"装货中 · {art.ORDERS[w['content_id']]['name']}正在入舱"
        if role == 'helm':
            if w['content_id'] == 'express' and 2800 <= w['x'] < 5550 and w['runtime']['gate_ticks']:
                return f"短闸开启 · 剩余 {w['runtime']['gate_ticks']/60:.1f} 秒"
            if w['content_id'] == 'express' and 2800 <= w['x'] < 4030 and not w['runtime']['gate_attempted']:
                key, hint = 'gate', '短闸走下层等待区 · 请轮机员加压载；安全航道在上层'
            elif w['content_id'] == 'calf' and any(a-400 <= w['x'] < b for a,b in art.ORDERS['calf']['quiet']):
                key, hint = 'quiet', '静音区 · 请轮机员切换静音或关机顺流'
            elif w['dock_ticks'] or w['x'] > art.ORDERS[w['content_id']]['length'] - 300:
                key, hint = 'dock', '慢靠 J · 停稳后请轮机员签收'
            elif w['content_id'] == 'jelly' and 1050 <= w['x'] < 2490:
                key, hint = 'dive', '限高洞在前 · 用信号请轮机员加压载下潜'
            else:
                key, hint = 'helm', '方向键 / WASD 驾驶 · J 慢靠 · Tab 发信号'
        elif w['station'] == 2 or w['dock_ticks']:
            key, hint = 'deliver', art.dock_status(w)
        elif w['leak']:
            key, hint = 'leak', 'K 选泵 · 按住 E 两秒修漏'
        elif w['cargo']['loose']:
            key, hint = 'rack', 'K 选货架 · 按住 E 一秒锁紧'
        else:
            key, hint = 'engineer', '↑↓ 压载 · J 动力 · K 选设备 · E 操作'
        if key not in self.tutorials:
            self.tutorials.add(key)
            self.tutorial = (hint, tick + 300)
        if tick < self.tutorial[1]:
            return self.tutorial[0]
        return ('方向键 / WASD 驾驶 · J 慢靠 · L 换岗 · Tab 信号' if role == 'helm' else
                '↑↓ 压载 · J 动力 · K 选设备 · E 操作 · L 换岗 · Tab 信号')

    def frame(self, lan, game, state, events, away, window, touch_active=None):
        w = state['world']
        slot = int(lan.transport.slot)
        state = dict(state, local_slot=slot)
        role = w['role_by_slot'][str(slot)]
        result = w['result']
        context = (state['match_id'], w['epoch'], state['paused'], away, config.VIEW_SIZE)
        recent = w['runtime']['events']
        if context != self.context:
            new_match = self.context is None or context[0] != self.context[0]
            if new_match:
                stop_music(150)
                self.tutorials.clear()
                self.tutorial = ('', 0)
            if role != self.role:
                self.tutorials.discard(role)
                self.tutorial = ('', 0)
                self.role = role
            self.clear()
            if new_match or state['pause_reason'] == 'disconnected':
                self.last_event = recent[-1][0] if recent else 0
            self.context = context

        def action(name):
            lan.transport.send(dict(type='mode_action', epoch=w['epoch'], action=name))

        portrait = state['orientation'] == 'portrait'
        width, height = (520, 780) if portrait else (960, 540)
        target = window.subsurface((config.VIEW_OFFSET, config.VIEW_SIZE))
        bounds = art.viewport(target, portrait)
        paused = state['paused'] or away
        controls = self.controls(width, height, role, state)
        if result and (state['match_id'], w['epoch']) != self.seen and not away:
            action('result_seen')
            self.seen = (state['match_id'], w['epoch'])

        def invoke(name):
            if name == 'leave':
                self.silence()
                lan.leave()
            elif name == 'exit':
                self.exit_prompt = not self.exit_prompt
                self.signal_menu = False
            elif name == 'cancel':
                self.exit_prompt = False
            elif name == 'pause':
                local = next(p for p in state['players'] if p['slot'] == slot)
                lan.send('unpause' if local.get('manual_pause') else 'pause')
            elif name == 'signals' and not paused:
                self.signal_menu = not self.signal_menu
            elif result:
                action(name)
            elif not paused:
                if name == 'operate':
                    if role == 'engineer' and w['station'] == 2:
                        action('deliver')
                elif name not in ('stick', 'up', 'down', 'slow'):
                    action(name)
                    if name in SIGNALS:
                        self.signal_menu = False

        for event in events:
            if away:
                break
            if event.type == pygame.KEYUP:
                self.keys.discard(event.key)
            elif event.type == pygame.KEYDOWN and not getattr(event, 'repeat', False):
                if not paused and not result and not self.exit_prompt:
                    self.keys.add(event.key)
                commands = {pygame.K_l: 'swap_request', pygame.K_TAB: 'signals', pygame.K_p: 'pause',
                            pygame.K_ESCAPE: 'leave' if result or self.exit_prompt else 'exit',
                            **({pygame.K_j: 'power_next', pygame.K_k: 'station_next', pygame.K_e: 'operate'}
                               if role == 'engineer' else {})}
                if result:
                    commands = {pygame.K_ESCAPE: 'leave', pygame.K_RETURN: 'back_lobby' if len(state['players']) == 2 else 'leave',
                                **({pygame.K_r: 'rematch_ready'} if len(state['players']) == 2 else {})}
                elif self.signal_menu:
                    commands.update(zip((pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4), SIGNALS))
                if event.key in commands:
                    invoke(commands[event.key])
            elif event.type in (pygame.FINGERUP, pygame.MOUSEBUTTONUP):
                if not getattr(event, 'touch', False):
                    self.fingers.pop(getattr(event, 'finger_id', 'mouse'), None)
            elif event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION):
                if getattr(event, 'touch', False) or getattr(event, 'button', 1) != 1:
                    continue
                finger = getattr(event, 'finger_id', 'mouse')
                pos = (game.mobile_controls.event_position(event) if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION)
                       else config.window_to_game(event.pos))
                px = pos[0] * target.get_width() / config.SCREEN_WIDTH
                py = pos[1] * target.get_height() / config.SCREEN_HEIGHT
                point = ((px - bounds.x) * width / bounds.w, (py - bounds.y) * height / bounds.h)
                if event.type in (pygame.FINGERMOTION, pygame.MOUSEMOTION):
                    if self.fingers.get(finger) == 'stick':
                        stick = next((r for key, _, r in controls if key == 'stick'), None)
                        if stick:
                            self.stick = self.axes(point, stick)
                else:
                    for key, _, rect in controls:
                        if rect.collidepoint(point):
                            if key == 'stick' and 'stick' in self.fingers.values():
                                break
                            if not paused and key in ('stick', 'up', 'down', 'slow', 'operate'):
                                self.fingers[finger] = key
                            if key == 'stick':
                                self.stick = self.axes(point, rect)
                            invoke(key)
                            break

        if touch_active is not None:
            for finger in tuple(self.fingers):
                if finger != 'mouse' and not touch_active(finger):
                    del self.fingers[finger]
        active = dict.fromkeys(self.fingers.values(), True)
        if 'stick' in active:
            active['stick'] = self.stick
        if not paused and not result:
            dx, dy = active.get('stick', (0, 0))
            keys = self.keys
            x = int(bool(keys & {pygame.K_RIGHT, pygame.K_d})) - int(bool(keys & {pygame.K_LEFT, pygame.K_a}))
            down, up = ({pygame.K_DOWN, pygame.K_s}, {pygame.K_UP, pygame.K_w}) if role == 'helm' else ({pygame.K_DOWN}, {pygame.K_UP})
            y = int(bool(keys & down) or 'down' in active) - int(bool(keys & up) or 'up' in active)
            held = int(pygame.K_j in keys or 'slow' in active) if role == 'helm' else 4 * int(pygame.K_e in keys or 'operate' in active)
            inputs = (x or dx, y or dy, held) if not self.exit_prompt else (0, 0, 0)
            if inputs != self.last_input or monotonic() - self.sent >= .05:
                lan.transport.send(dict(type='mode_input', epoch=w['epoch'], x=inputs[0], y=inputs[1], held=inputs[2]))
                self.last_input, self.sent = inputs, monotonic()
        if not state['paused'] and not away:
            for event_id, cue in recent:
                if event_id > self.last_event:
                    play_sound('courier_' + cue)
                    self.last_event = event_id
        if not paused and not result and any(w['runtime']['flow']):
            if self.flow_channel is None:
                sound = make_sound('courier_flow')
                if sound:
                    self.flow_channel = sound.play(loops=-1, fade_ms=180)
        else:
            self.silence()

        status = PAUSE.get(state['pause_reason'], '') if not result else ''
        if result and w.get('back_lobby'):
            status = '回房意向已提交，等待搭档查看结果'
        elif result and slot in w.get('rematch', ()):
            status = '已选择换岗重送，等待搭档'
        elif not status and self.exit_prompt:
            status = '主动离开将中止当前订单'
        elif not status and not result:
            status = self.instruction(w, role, state['tick'])
        if w['runtime']['swap'] or w['slot_signals'].get(str(slot)):
            if not paused and not result:
                status = ''
        art.draw(target, portrait, w, role, state, self.controls(width, height, role, state), active, status, slot)
        lan.drawn_to_window = True
