"""Race snapshots are drawn from each driver's own camera."""
from time import monotonic

import pygame

from game_core import config
from game_core.modes.tide_race import content
from game_core.modes.tide_race_art import draw_race
from game_core.modes.tide_race_ui import (RaceControls, event_point, menu_pick,
                                        overlay_buttons, play_combo, result_lines, touch_layout)


class TideRaceView:
    def __init__(self):
        self.controls = RaceControls()
        self.context = None
        self.action_clock = 0
        self.last_input = None
        self.last_combo = 0
        self.focus = 0
        self.confirm = False
        self.next_ack = 0
        self.previous_frame = self.current_frame = None
        self.received_at = 0

    def frame(self, lan, game, state, events, away, window):
        world = state['world']
        slot = int(lan.transport.slot)
        me = next(r for r in world['racers'] if r['slot'] == slot)
        can_drive = me['finish_tick'] is None and world['result'] is None
        target = window.subsurface((config.VIEW_OFFSET, config.VIEW_SIZE))
        layout = touch_layout(target)
        context = (state['match_id'], world['epoch'])
        if context != self.context:
            self.controls.clear()
            self.last_input = None
            self.last_combo = me['combo_until']
            if self.context is None or context[0] != self.context[0]:
                self.focus = 0
                self.confirm = False
            self.context = context
            self.next_ack = 0
            self.previous_frame = self.current_frame = None
        if state['paused'] or away:
            self.controls.clear()
            self.last_input = None

        def action(name):
            lan.transport.send(dict(type='mode_action', epoch=world['epoch'], action=name))

        overlay = None
        terminal = world['result']
        if terminal:
            tied = sum(r['rank'] == 1 for r in terminal) == 2
            winner = terminal[0]['slot']
            title = '并列' if tied else f'P{winner} 获胜'
            detail = result_lines(world)
            if world['rematch']:
                detail.append('已选择再赛 '+ '、'.join(f'P{i}' for i in world['rematch']))
            if world['back_lobby']:
                detail.append('等待双方查看结果')
            options = ('再来一局','回房间','离开房间') if len(state['players']) == 2 else ('离开房间',)
            commands = ('rematch_ready','back_lobby','leave') if len(options)==3 else ('leave',)
            overlay = title, detail, overlay_buttons(options, self.focus % len(options))
        elif self.confirm:
            commands = ('cancel','leave')
            overlay = '离开房间？', ('未冲线离开按弃赛处理',), overlay_buttons(('返回比赛','离开房间'),self.focus)
        elif state['paused'] and can_drive:
            commands = ('unpause','exit')
            labels = ('继续','离开…')
            if game.desktop_controls:
                commands += ('quality',)
                labels += (f'画质 {game.desktop_quality}K',)
            reason = {'disconnected':'等待选手重连','suspended':'等待选手返回',
                      'orientation_mismatch':'请两位选手切到同一方向','server_error':'服务器暂停'}
            overlay = '比赛暂停', (reason.get(state['pause_reason'],'P 继续比赛'),), overlay_buttons(labels,self.focus)

        for e in events:
            if away:
                continue
            point = event_point(e, target)
            if overlay:
                self.focus, index = menu_pick(e, point, overlay[2], self.focus % len(commands))
                command = commands[index] if index is not None else None
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        command = 'leave' if terminal else 'cancel' if self.confirm else 'exit'
                    elif e.key == pygame.K_p and not terminal and not self.confirm:
                        command = 'unpause'
                if command == 'leave':
                    lan.leave()
                    return
                if command == 'cancel':
                    self.confirm = False
                    if can_drive:
                        lan.send('unpause')
                elif command == 'exit':
                    self.confirm = True
                    self.focus = 0
                    if can_drive:
                        lan.send('pause')
                elif command == 'unpause':
                    lan.send('unpause')
                elif command == 'quality':
                    game.desktop_quality = 4 if game.desktop_quality == 2 else 2
                elif command:
                    action(command)
            else:
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    self.confirm = True
                    self.focus = 0
                    if can_drive:
                        lan.send('pause')
                    break
                if not can_drive:
                    if e.type in (pygame.FINGERDOWN,pygame.MOUSEBUTTONDOWN) and point and pygame.Rect(805,121,123,35).collidepoint(point):
                        self.confirm = True
                        self.focus = 0
                    continue
                command = self.controls.event(e, point, layout)
                if command == 'pause':
                    lan.send('pause')
                elif command == 'launch' and world['race_phase'] == 'racing':
                    action('launch')
        if can_drive and not away and not state['paused'] and not self.confirm:
            self.controls.release_inactive()
            inputs = self.controls.state()
            now = monotonic()
            if inputs != self.last_input or now-self.action_clock >= .05:
                lan.transport.send(dict(type='mode_input',epoch=world['epoch'],x=inputs[0],y=inputs[1],held=inputs[2]))
                self.last_input, self.action_clock = inputs, now
        if me['combo_until'] != self.last_combo:
            play_combo(me['combo'])
            self.last_combo = me['combo_until']
        buttons = layout if game.mobile_web and can_drive and not overlay else ()
        if not can_drive and not terminal and not overlay:
            buttons = (('离开…',(805,121,123,35)),)
        visual = self.interpolate(world, state['paused'] or away)
        draw_race(target,visual,content()['tracks'][world['track_id']],slot,controls=buttons,overlay=overlay)
        lan.drawn_to_window = True
        lan.ui_state = (True, False)
        if terminal and slot in world['result_pending'] and monotonic() >= self.next_ack:
            action('result_seen')
            self.next_ack = monotonic() + .25

    def interpolate(self, world, paused):
        now = monotonic()
        if paused or world['race_phase'] != 'racing':
            self.previous_frame = self.current_frame = None
            return world
        if self.current_frame is None or self.current_frame['tick'] != world['tick']:
            self.previous_frame, self.current_frame = self.current_frame, world
            self.received_at = now
        previous = self.previous_frame
        if previous is None or not 0 < world['tick']-previous['tick'] <= 4:
            return world
        fraction = min(1, (now-self.received_at)*30)
        racers = []
        for before, current in zip(previous['racers'], world['racers']):
            if (before['branch'] == current['branch'] and current['pose'] != 'reset'
                    and not current['freeze'] and current['finish_tick'] is None
                    and abs(current['x']-before['x']) <= 32):
                current = dict(current, x=before['x']+(current['x']-before['x'])*fraction,
                               y=before['y']+(current['y']-before['y'])*fraction)
            racers.append(current)
        return dict(world, racers=racers,
                    visual_clock=previous['clock']+(world['clock']-previous['clock'])*fraction)
