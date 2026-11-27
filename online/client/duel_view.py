"""Controls and snapshot routing for the authoritative Boss Duel."""
from time import monotonic

import pygame

from game_core import config
from game_core.modes.boss_duel import HEIGHT, WIDTH, clip, unit
from game_core.sounds import play_sound
from .duel_art import DESKTOP_CONTROLS, HUD_HEIGHT, TOUCH_CONTROLS, Painter, draw_scene, fit

SOUNDS = {'shot': 'shoot_pistol', 'hit': 'boss_hit', 'hurt': 'player_hit', 'dash': 'dart_cast',
          'start': 'boss_appear', 'swap': 'coin', 'result': 'level_up'}
BOSS_SOUNDS = {'whale': ('water_cast', 'laser_hit'), 'mecha': ('laser', 'grenade'),
               'orochi': ('storm', 'orochi_thunder')}
ARENA = pygame.Rect(0, 0, WIDTH, HEIGHT)


def pointer_down(event):
    return event.type == pygame.FINGERDOWN or (event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1 and not getattr(event, 'touch', False))


def event_pos(game, event):
    if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
        return game.mobile_controls.event_position(event)
    return config.window_to_game(event.pos)


class DuelView:
    def __init__(self):
        self.context = self.round = self.match = self.last_input = None
        self.seen = self.sent = 0
        self.last_frame = monotonic()
        self.keys = set()
        self.blocked = set()
        self.fingers = {}
        self.stick = (0, 0)
        self.aim = [400., 270.]
        self.auto = self.confirm_leave = False

    def controls(self, stage, boss, touch, solo):
        if self.confirm_leave:
            return {'leave': pygame.Rect(216, 322, 168, 39), 'cancel': pygame.Rect(416, 322, 168, 39)}
        if stage == 'result':
            if solo:
                return {'exit': pygame.Rect(306, 404, 188, 39)}
            return {name: pygame.Rect(142+i*182, 404, 151, 39)
                    for i, name in enumerate(('rematch_ready', 'back_lobby', 'exit'))}
        buttons = {'pause': pygame.Rect(704, -48, 81, 36), 'exit': pygame.Rect(15, -48, 81, 36)}
        if stage == 'swap':
            buttons['round_ready'] = pygame.Rect(303, 365, 194, 41)
        if touch and stage == 'combat':
            buttons['move'] = pygame.Rect(12, 545, 164, 91)
            if boss:
                buttons['aim'] = pygame.Rect(184, 585, 222, 50)
            names = ('cast_1', 'cast_2', 'cast_3') if boss else ('shoot', 'dash', 'auto')
            for i, name in enumerate(names):
                buttons[name] = pygame.Rect(418+i*124, 552, 117, 76)
        return buttons

    def clear(self):
        self.blocked.update(self.keys)
        self.keys.clear()
        self.fingers.clear()
        self.stick = (0, 0)
        self.last_input = None

    def frame(self, lan, game, state, events, away, window, touch_active=None):
        world = state['world']
        slot = int(lan.transport.slot)
        if not any(p['slot'] == slot for p in state['players']):
            return
        boss = world['role_by_slot'].get(str(slot), world['role_by_slot'].get(slot)) == 'boss'
        match, epoch, stage = state['match_id'], world['epoch'], world['phase']
        connected = getattr(lan.transport, 'ready', True)
        paused = state['paused'] or not connected
        if self.context != (match, epoch) or paused or away:
            self.clear()
        self.context = match, epoch
        if self.round != (match, world['round_id']):
            self.round = match, world['round_id']
            self.aim = [400., 270.]
            self.auto = self.confirm_leave = False
        if stage == 'result':
            self.confirm_leave = False
        now = monotonic()
        dt = min(.05, now-self.last_frame)
        self.last_frame = now
        touch = game.mobile_web
        height = HUD_HEIGHT + HEIGHT + (TOUCH_CONTROLS if touch else DESKTOP_CONTROLS)
        logic = fit(config.SCR.get_rect(), height)
        solo = len(state['players']) == 1
        buttons = self.controls(stage, boss, touch, solo)
        occupied = stage == 'combat' and not paused and not away and not self.confirm_leave

        def send(name, target=None):
            msg = dict(type='mode_action', action=name, epoch=epoch)
            if target is not None:
                msg['target'] = target
            lan.transport.send(msg)

        def accept(name):
            if away or not name:
                return
            if name == 'pause':
                lan.send('unpause' if paused else 'pause')
                self.clear()
            elif name == 'exit':
                if stage == 'result':
                    lan.leave()
                else:
                    self.confirm_leave = True
                    self.clear()
            elif name == 'leave':
                lan.leave()
            elif name == 'cancel':
                self.confirm_leave = False
            elif name in ('rematch_ready', 'back_lobby') or (name == 'round_ready' and not paused):
                send(name)
            elif occupied and not self.confirm_leave:
                if name == 'auto':
                    self.auto = not self.auto
                elif name.startswith('cast_'):
                    send(name, [round(self.aim[0]*1000/WIDTH), round(self.aim[1]*1000/HEIGHT)])
                elif name == 'dash':
                    send(name)

        def point(event):
            x, y = event_pos(game, event)
            return (x-logic.x)*WIDTH/logic.w, (y-logic.y)*WIDTH/logic.w-HUD_HEIGHT

        def aim_at(x, y):
            self.aim = [0 if x < 3 else WIDTH if x > WIDTH-3 else x,
                        0 if y < 3 else HEIGHT if y > HEIGHT-3 else y]

        def arrows(negative, positive):
            return int(positive in self.keys)-int(negative in self.keys)

        if occupied and boss:
            dx, dy = unit(arrows(pygame.K_LEFT, pygame.K_RIGHT), arrows(pygame.K_UP, pygame.K_DOWN))
            self.aim = [clip(self.aim[0]+dx*365*dt, 0, WIDTH), clip(self.aim[1]+dy*365*dt, 0, HEIGHT)]
        for event in events:
            if event.type == pygame.KEYUP:
                self.keys.discard(event.key)
                self.blocked.discard(event.key)
            elif event.type == pygame.KEYDOWN:
                key = event.key
                if key in self.keys or key in self.blocked or getattr(event, 'repeat', False):
                    continue
                if occupied:
                    self.keys.add(key)
                if key == pygame.K_ESCAPE:
                    accept('cancel' if self.confirm_leave else 'exit')
                elif key == pygame.K_RETURN:
                    if self.confirm_leave:
                        accept('leave')
                    elif stage == 'swap':
                        accept('round_ready')
                    elif stage == 'result':
                        accept('exit' if solo else 'rematch_ready')
                elif key == pygame.K_b and stage == 'result' and not solo:
                    accept('back_lobby')
                elif key == pygame.K_p and stage != 'result':
                    accept('pause')
                elif occupied:
                    accept(({pygame.K_j:'cast_1', pygame.K_k:'cast_2', pygame.K_l:'cast_3'}.get(key)
                            if boss else 'dash' if key == pygame.K_k else None))
            elif pointer_down(event):
                pos = point(event)
                name = next((key for key, rect in buttons.items() if rect.collidepoint(pos)), None)
                finger_id = getattr(event, 'finger_id', 'mouse')
                if name in ('aim', 'move', 'shoot'):
                    if occupied and not any(f[0] == name for f in self.fingers.values()):
                        self.fingers[finger_id] = name, pos
                elif name:
                    accept(name)
                elif occupied and boss and ARENA.inflate(8, 8).collidepoint(pos):
                    aim_at(*pos)
                    self.fingers[finger_id] = 'field', pos
            elif event.type in (pygame.FINGERMOTION, pygame.MOUSEMOTION) and occupied:
                if event.type == pygame.MOUSEMOTION and getattr(event, 'touch', False):
                    continue
                finger_id = getattr(event, 'finger_id', 'mouse')
                name, previous = self.fingers.get(finger_id, (None, None))
                x, y = point(event)
                if name == 'move':
                    dx, dy = x-previous[0], y-previous[1]
                    scale = max(26, (dx*dx+dy*dy)**.5)
                    self.stick = dx/scale, dy/scale
                elif boss and name == 'aim':
                    self.aim = [clip(self.aim[0]+3.7*(x-previous[0]), 0, WIDTH),
                                clip(self.aim[1]+3.7*(y-previous[1]), 0, HEIGHT)]
                    self.fingers[finger_id] = name, (x, y)
                elif boss and (name == 'field' or name is None and event.type == pygame.MOUSEMOTION):
                    aim_at(x, y)
            elif event.type in (pygame.FINGERUP, pygame.MOUSEBUTTONUP):
                name, _ = self.fingers.pop(getattr(event, 'finger_id', 'mouse'), (None, None))
                if name == 'move':
                    self.stick = (0, 0)

        if touch_active is not None:
            for ident, (name, _) in tuple(self.fingers.items()):
                if ident != 'mouse' and not touch_active(ident):
                    del self.fingers[ident]
                    if name == 'move':
                        self.stick = (0, 0)

        dx, dy = arrows(pygame.K_a, pygame.K_d), arrows(pygame.K_w, pygame.K_s)
        if not boss:
            dx = dx or arrows(pygame.K_LEFT, pygame.K_RIGHT)
            dy = dy or arrows(pygame.K_UP, pygame.K_DOWN)
        shoot = not boss and (self.auto or pygame.K_j in self.keys or
                              any(f[0] == 'shoot' for f in self.fingers.values()))
        inputs = (dx or self.stick[0], dy or self.stick[1], int(shoot)) if occupied and not self.confirm_leave else (0, 0, 0)
        if not paused and not away and stage == 'combat' and (inputs != self.last_input or now-self.sent >= .05):
            lan.transport.send(dict(type='mode_input', epoch=epoch, x=inputs[0], y=inputs[1], held=inputs[2]))
            self.last_input, self.sent = inputs, now

        pending_audio = world['events']
        if self.match != match:
            self.match = match
            self.seen = pending_audio[-1][0] if world['tick'] > 10 and pending_audio else 0
        for ident, name in pending_audio:
            if ident > self.seen:
                warning, impact = BOSS_SOUNDS[world['content_id']]
                if not away and connected:
                    play_sound(warning if name == 'warning' else impact if name == 'impact' else SOUNDS[name])
                self.seen = ident

        target = window.subsurface((config.VIEW_OFFSET, config.VIEW_SIZE))
        viewport = fit(target.get_rect(), height)
        target.fill((4, 16, 27))
        buttons = self.controls(stage, boss, touch, solo)
        draw_scene(Painter(target.subsurface(viewport), HUD_HEIGHT), state, world, slot, boss, touch, self, buttons, paused)
        if world.get('result') and slot in world['result_pending'] and now-self.sent >= .1:
            send('result_seen')
            self.sent = now
        lan.drawn_to_window = True
