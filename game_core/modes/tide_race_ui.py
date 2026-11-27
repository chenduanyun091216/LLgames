"""The local race session and input shared with the room client."""
from functools import lru_cache
from math import hypot
import platform

import pygame

from .. import config, sounds
from .tide_race import Race, VIEW, clamp
from .tide_race_art import draw_race, field_rect, fmt
from .tide_records import Ghost, RaceRecords

TOUCH = (
    ('方向', (33, 414, 98, 98)), ('潜 K', (758, 451, 82, 60)),
    ('跃 J', (854, 426, 74, 67)), ('暂停', (858, 121, 70, 35)),
)
PORTRAIT_TOUCH = (
    ('方向', (38, 568, 140, 140)), ('潜 K', (650, 582, 124, 108)),
    ('跃 J', (800, 560, 124, 108)), ('暂停', (836, 117, 100, 51)),
)


def touch_layout(target):
    view = field_rect(target)
    return PORTRAIT_TOUCH if target.get_height()-view.bottom >= view.w*.18 else TOUCH
DRIVE_KEYS = {pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d, pygame.K_UP,
              pygame.K_w, pygame.K_DOWN, pygame.K_s, pygame.K_j, pygame.K_k}


class RaceControls:
    def __init__(self):
        self.keys = set()
        self.fingers = {}
        self.axes = (0, 0)

    def clear(self):
        self.keys.clear()
        self.fingers.clear()
        self.axes = (0, 0)

    def release_inactive(self):
        window = getattr(platform, 'window', None)
        active = getattr(window, 'ttgamesTouchActive', None)
        if active is not None:
            for finger in tuple(self.fingers):
                if finger != 'mouse' and not active(finger):
                    if self.fingers.pop(finger) == '方向':
                        self.axes = (0, 0)

    def event(self, e, point, layout=TOUCH):
        if e.type == pygame.KEYDOWN:
            if e.key in DRIVE_KEYS:
                fresh = e.key not in self.keys and not getattr(e, 'repeat', False)
                self.keys.add(e.key)
                return 'launch' if fresh and e.key == pygame.K_j else None
            if e.key in (pygame.K_p, pygame.K_ESCAPE):
                return 'pause'
        if e.type == pygame.KEYUP:
            self.keys.discard(e.key)
        finger = getattr(e, 'finger_id', 'mouse')
        if e.type in (pygame.FINGERUP, pygame.MOUSEBUTTONUP):
            if self.fingers.pop(finger, None) == '方向':
                self.axes = (0, 0)
        if point is None:
            return
        if e.type in (pygame.FINGERDOWN, pygame.MOUSEBUTTONDOWN):
            for name, box in layout:
                if pygame.Rect(box).collidepoint(point):
                    if name == '方向' and name in self.fingers.values():
                        return
                    self.fingers[finger] = name
                    if name == '跃 J':
                        return 'launch'
                    if name == '暂停':
                        return 'pause'
                    break
        if self.fingers.get(finger) == '方向':
            jx, jy, width, height = layout[0][1]
            x, y = point[0]-jx-width/2, point[1]-jy-height/2
            distance = hypot(x, y)
            if distance > 5:
                scale = clamp((distance-5)/(width*.36),0,1)/distance
                self.axes = (x*scale,y*scale)
            else:
                self.axes = (0,0)

    def state(self):
        x = int(bool(self.keys & {pygame.K_d, pygame.K_RIGHT})) - int(bool(self.keys & {pygame.K_a, pygame.K_LEFT}))
        y = int(bool(self.keys & {pygame.K_s, pygame.K_DOWN})) - int(bool(self.keys & {pygame.K_w, pygame.K_UP}))
        return (x or self.axes[0], y or self.axes[1],
                2 if pygame.K_k in self.keys or '潜 K' in self.fingers.values() else 0)


def event_point(event, target):
    if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
        width, height = pygame.display.get_surface().get_size()
        pos = width*event.x, height*event.y
    elif (event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION)
          and not getattr(event, 'touch', False)):
        pos = event.pos
    else:
        return None
    # Pointer conversion below uses the same window viewport offset as the direct draw.
    r = field_rect(target)
    w, h = config.VIEW_SIZE
    gw, gh = config.SCR.get_size()
    x, y = config.window_to_game(pos)
    return ((x*w/gw-r.x)*VIEW[0]/r.w, (y*h/gh-r.y)*VIEW[1]/r.h)


@lru_cache(maxsize=3)
def combo_sound(combo):
    samples = sounds._snd_coin()
    ratio = 1 + .19 * (combo-1)
    return pygame.mixer.Sound(buffer=sounds._pack([samples[int(i*ratio)] for i in range(int(len(samples)/ratio))]))


def play_combo(combo):
    if combo and pygame.mixer.get_init():
        combo_sound(combo).play()


def overlay_buttons(labels, focus):
    width = min(140, (472-12*(len(labels)-1))/len(labels))
    return [(name, (480+(i-len(labels)/2)*(width+12)+6, 351, width, 36), i==focus)
            for i, name in enumerate(labels)]


def menu_pick(e, point, buttons, focus):
    if e.type == pygame.KEYDOWN:
        if e.key in (pygame.K_LEFT,pygame.K_a):
            focus = (focus-1)%len(buttons)
        if e.key in (pygame.K_RIGHT,pygame.K_d):
            focus = (focus+1)%len(buttons)
        if e.key in (pygame.K_RETURN,pygame.K_KP_ENTER,pygame.K_SPACE):
            return focus, focus
    elif e.type in (pygame.FINGERDOWN,pygame.MOUSEBUTTONDOWN) and point is not None:
        for i, (_, rect, _) in enumerate(buttons):
            if pygame.Rect(rect).collidepoint(point):
                return i, i
    return focus, None


def result_lines(state):
    names = {'departed':'弃赛', 'timeout':'超时', 'won_by_forfeit':'对手弃赛'}
    return [f'P{r["slot"]}　'+(fmt(r['finish_tick']-state['start_tick']) if r['finish_tick'] is not None
                            else names.get(r['status'], '未完赛')) for r in state['result']]


class TideRaceMode:
    def __init__(self, track, game, change_track, *, show_tip, session):
        self.track_id, self.game, self.change_track = track, game, change_track
        self.race = Race(track)
        self.records = RaceRecords(self.race, session=session)
        self.controls = RaceControls()
        self.screen = 'ready'
        self.focus = 0
        self.accumulator = 0
        self.pending = False
        self.show_ghost = True
        self.show_tip = show_tip
        self.ghost = None
        self.ghost_source = None

    def reset_input(self):
        self.controls.clear()
        self.race.racers[1].launch_until = -1
        self.pending = False
        self.accumulator = 0

    def set_screen(self, screen):
        self.screen, self.focus = screen, 0
        self.reset_input()

    def overlay(self):
        if self.screen == 'ready':
            return (self.race.track['name'], ('方向键或 A/D 调速　J 跃　K 潜',
                    '蓝色鱼群处向下或按潜，进入水下捷径', f'个人最佳 {fmt(self.records.best[0] if self.records.best else None)}'),
                    overlay_buttons(('开始', '换赛道', '返回大厅'), self.focus))
        if self.screen == 'paused':
            labels = ['继续', '航迹 '+('开' if self.show_ghost else '关'), '退出']
            if self.game.desktop_controls:
                labels.append(f'画质 {self.game.desktop_quality}K')
            return ('已暂停', ('比赛和航迹已停下',), overlay_buttons(labels, self.focus))
        if self.screen == 'exit':
            return ('退出比赛？', ('当前比赛进度将丢失',), overlay_buttons(('继续比赛', '返回大厅'), self.focus))
        if self.screen == 'result':
            racer = self.race.racers[1]
            detail = [f'用时 {fmt(racer.finish_tick-self.race.start_tick)}' if racer.finish_tick is not None else '超时',
                      f'个人最佳 {fmt(self.records.best[0] if self.records.best else None)}']
            if self.records.error:
                detail.append('本次记录仅在当前会话有效')
            return ('顺利冲线' if racer.finish_tick is not None else '比赛结束', detail,
                    overlay_buttons(('再跑一次','换赛道','返回大厅'),self.focus))
        return None

    def choose(self, index):
        if self.screen in ('ready','result'):
            if index == 0:
                self.race = Race(self.track_id)
                self.set_screen('playing')
            else:
                self.records.close()
                if index == 1:
                    self.change_track()
                    return True
                return False
        elif self.screen == 'paused':
            if index == 1:
                self.show_ghost = not self.show_ghost
            elif index == 3:
                self.game.desktop_quality = 4 if self.game.desktop_quality == 2 else 2
            else:
                self.set_screen('playing' if index == 0 else 'exit')
        elif self.screen == 'exit':
            if index == 1:
                self.records.close()
                return False
            self.set_screen('playing')
        return True

    def frame(self, events, elapsed, suspended, font, target):
        if self.records.browser is not None:
            self.records.refresh()
        race = self.race
        layout = touch_layout(target)
        if suspended:
            self.reset_input()
            elapsed = 0
        for e in events:
            if e.type == pygame.WINDOWFOCUSLOST:
                if self.screen == 'playing':
                    self.set_screen('paused')
                continue
            if suspended:
                continue
            point = event_point(e, target)
            overlay = self.overlay()
            if overlay:
                self.focus, index = menu_pick(e, point, overlay[2], self.focus)
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    index = 2 if self.screen in ('ready','result') else 0
                if e.type == pygame.KEYDOWN and e.key == pygame.K_p and self.screen == 'paused':
                    index = 0
                if index is not None:
                    if not self.choose(index):
                        return False
                    elapsed = 0
                    break
            else:
                action = self.controls.event(e, point, layout)
                if action == 'pause':
                    self.set_screen('paused')
                    break
                if action == 'launch' and race.phase == 'racing':
                    self.pending = True
                if e.type == pygame.KEYDOWN and e.key == pygame.K_g and not getattr(e, 'repeat', False):
                    self.show_ghost = not self.show_ghost
        race = self.race
        if self.screen == 'playing':
            self.controls.release_inactive()
            self.accumulator += min(elapsed,4/60)
            while self.accumulator+1e-10 >= 1/60 and not race.result:
                racer = race.racers[1]
                before = racer.combo_until
                race.step({1:self.controls.state()}, (1,) if self.pending else ())
                self.pending = False
                self.accumulator -= 1/60
                if racer.combo_until != before:
                    play_combo(racer.combo)
            if race.result:
                self.records.save(race)
                self.set_screen('result')
        best = self.records.best
        if best and best is not self.ghost_source:
            self.ghost_source = best
            self.ghost = Ghost(best[1])
        draw_race(target,race.snapshot(),race.track,best=best[0] if best else None,
                  ghost=self.ghost.at(race.clock) if self.ghost and self.show_ghost and self.screen!='result' else None,
                  tip=self.show_tip and not best and self.screen=='playing',
                  controls=layout if self.game.mobile_web and self.screen=='playing' else (),overlay=self.overlay())
        return True
