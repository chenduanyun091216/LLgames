"""Shared Pygame entry and room UI for native and browser transports."""
import asyncio
import json
from time import monotonic

import pygame

from game_core import config, menu_ui
from game_core.render import RenderSurface
from game_core.game import BACKGROUND_SCROLL_TICKS, BG_FADE_MS, GameState
from game_core.sounds import advance_music
from .interpolation import PositionBuffer, LocalPrediction


class BrowserTransport:
    def __init__(self, bridge):
        self.bridge = bridge
        self._revision = None
        self._snapshot = None
        self.perf = bool(getattr(bridge, 'perf', False))
        self.decode_ms = 0

    def __getattr__(self, name):
        return getattr(self.bridge, name)

    @property
    def state(self):
        revision = int(self.bridge.stateRevision)
        if revision != self._revision:
            started = monotonic()
            raw = str(self.bridge.state)
            self._snapshot = json.loads(raw) if raw else None
            self._revision = revision
            self.decode_ms = (monotonic() - started) * 1000
        return self._snapshot

    @property
    def address(self):
        return str(self.bridge.address)

    @property
    def ready(self):
        return bool(self.bridge.ready)

    def send(self, message):
        result = self.bridge.send(json.dumps(message))
        return int(result) if result is not None else None

    def prompt_join(self):
        self.bridge.promptJoin()


class LAN:
    def __init__(self, transport):
        self.transport = transport
        self.page = 'home'
        self.home_keys = False
        self.text = ''
        self.last_send = 0
        self.last_input = None
        self.settings_sent = False
        self.presentation = None
        self.scene = None
        self.scene_layout = None
        self.positions = PositionBuffer()
        self.prediction = LocalPrediction()
        self.prediction_context = None
        self.render_positions = {}
        self.render_scroll = None
        self.applied = None
        self.leave_task = None
        self.orientation = None
        self.hidden = None
        self.notice = ''
        self.notice_until = 0
        self.seen = set()
        self.exit_confirmation = False
        self.victory_left = None
        self.ui_state = (False, False)
        self.perf_at = self.perf_frame = None
        self.perf_max = [0, 0, 0]
        self.perf_text = ''
        if isinstance(transport, BrowserTransport) and str(transport.resumeCode):
            self.start_room('join', str(transport.resumeCode))

    def message(self, text):
        self.notice = text
        self.notice_until = monotonic() + 4

    def send(self, action, key=None):
        msg = {'type': 'action', 'action': action}
        if key is not None:
            msg['key'] = key
        self.transport.send(msg)

    def home(self):
        self.transport.reset()
        self.page = 'home'
        self.presentation = None
        self.scene = None
        self.scene_layout = None
        self.positions = PositionBuffer()
        self.prediction = LocalPrediction()
        self.prediction_context = None
        self.render_positions = {}
        self.render_scroll = None
        self.applied = None
        self.exit_confirmation = False
        self.victory_left = None
        self.settings_sent = False
        pygame.key.stop_text_input()

    def leave(self):
        if not self.transport.slot:
            self.home()
        elif isinstance(self.transport, BrowserTransport):
            self.transport.leave()
        elif not self.leave_task or self.leave_task.done():
            self.leave_task = asyncio.create_task(self.transport.leave())

    def draw_join_form(self, game, events):
        for event in events:
            if event.type == pygame.TEXTINPUT:
                self.text = (self.text + event.text)[:300]
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.home()
                    return
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif event.key == pygame.K_v and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_GUI):
                    self.text = pygame.scrap.get_text().strip()[:300]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.join_value():
                    self.start_room('join', self.join_value())
                    return

        w, h = config.SCR.get_size()
        panel = pygame.Rect(0, 0, min(w - 32, 360), 192)
        panel.center = (w // 2, h // 2)
        field = pygame.Rect(panel.x + 20, panel.y + 67, panel.w - 40, 42)
        cancel = pygame.Rect(field.x, panel.bottom - 56, (field.w - 10) // 2, 36)
        join = cancel.move(cancel.w + 10, 0)
        value = self.join_value()

        menu_ui.draw_home(game, entrances=True)
        game._draw_scrim(175)
        game._draw_panel(*panel, alpha=250)
        game._draw_text_fit('加入房间', game.font_large, (220, 246, 255),
                            pygame.Rect(field.x, panel.y + 13, field.w, 43), align='center')
        game._draw_panel(*field, accent=(106, 217, 235), fill=(7, 23, 38), alpha=255)
        game._draw_text_fit(self.text or '输入四位房间号', game.font_med,
                            (240, 250, 255) if self.text else (162, 192, 210),
                            field.inflate(-20, -8), align='center')
        game._draw_button('取消', *cancel, color=(61, 94, 118))
        disabled = ((18, 35, 49), (49, 74, 93), (159, 182, 196))
        game._draw_button('加入', *join, palette=None if value else disabled)
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = config.window_to_game(event.pos)
                if cancel.collidepoint(pos):
                    self.home()
                    return
                if value and join.collidepoint(pos):
                    self.start_room('join', value)
                    return
            elif event.type == pygame.MOUSEMOTION:
                game.cursor_pos = config.window_to_game(event.pos)

    def join_value(self):
        value = self.text.strip()
        if (len(value) == 4 and value.isascii() and value.isdigit()
                or '?room=' in value):
            return value
        return ''

    def start_room(self, mode, value=''):
        pygame.key.stop_text_input()
        self.page = 'room'
        self.transport.begin(mode, value)

    def join_form(self):
        self.text = ''
        self.page = 'join'
        if isinstance(self.transport, BrowserTransport):
            self.page = 'room'
            self.transport.prompt_join()
        else:
            pygame.key.start_text_input()

    def lobby(self, game, events, state, direction):
        reset = self.home if not self.transport.slot else self.leave
        rows = []
        error = str(self.transport.error)
        detail = '' if error == 'orientation_mismatch' else error
        if error == 'wrong_room_code':
            detail = '房间不存在，请核对房主提供的房间号或邀请链接'
        if state:
            orientation = state['orientation']
            wrong_direction = [f"P{p['slot']}" for p in state['players']
                               if p['connected'] and p['orientation'] != orientation]
            if orientation and wrong_direction:
                target = '横屏' if orientation == 'landscape' else '竖屏'
                detail = f"请 {'、'.join(wrong_direction)} 切换至{target}（电脑调整窗口，手机旋转屏幕）"

            slot = int(self.transport.slot)
            me = next((p for p in state['players'] if p['slot'] == slot), None)
            host = slot == 1
            def settings(**changes):
                msg = {'type': 'room_settings', 'mode': state['mode'], 'orientation': state['orientation'] or direction}
                msg.update(changes)
                if msg['mode'] == 'campaign':
                    msg.setdefault('difficulty', state['difficulty'])
                    msg.setdefault('start_level', state['start_level'])
                self.transport.send(msg)
            if host and not state['orientation'] and not self.settings_sent:
                settings()
                self.settings_sent = True
            if host:
                rows.append((('战役' if state['mode'] == 'campaign' else '无限模式'),
                             lambda: settings(mode='infinite' if state['mode'] == 'campaign' else 'campaign')))
                rows.append((('竖屏' if state['orientation'] == 'portrait' else '横屏'),
                             lambda: settings(orientation='portrait' if state['orientation'] != 'portrait' else 'landscape')))
                if state['mode'] == 'campaign':
                    levels = len(config.LEVEL_CONFIGS)
                    difficulties = ('easy', 'medium', 'hard')
                    rows.extend([
                        (config.DIFFICULTY_PRESETS[state['difficulty']].name,
                         lambda: settings(difficulty=difficulties[(difficulties.index(state['difficulty']) + 1) % 3])),
                        (f"第 {state['start_level']} 关",
                         lambda: settings(start_level=state['start_level'] % levels + 1)),
                    ])
            if me:
                revision = state['settings_revision']
                rows.append(('取消准备' if me['ready'] else '准备', lambda: self.transport.send(
                    {'type': 'ready', 'ready': not me['ready'], 'settings_revision': revision})))
                if host:
                    start = None if orientation and wrong_direction else lambda: self.transport.send(
                        {'type': 'start', 'settings_revision': revision})
                    rows.append(('开始对局', start))
        rows.append(('返回首页' if not self.transport.slot else '离开房间', reset))
        if state:
            labels = ['P' + str(p['slot']) + (' 已准备' if p['ready'] else ' 等待准备') for p in state['players']]
            detail = (' · '.join(labels) + '　' + detail).strip()
        self.draw_room(game, rows, events, detail or '正在连接房间…', str(self.transport.invite))

    def draw_room(self, game, rows, events, detail, invite):
        rects = menu_ui.room_action_rects(len(rows))
        menu_ui.draw_room(game, rows, rects, detail, invite)
        shortcuts = dict(zip(menu_ui.room_shortcuts(len(rows)), (action for _, action in rows)))
        for event in events:
            pos = None
            if event.type == pygame.KEYDOWN and game.desktop_controls:
                action = shortcuts.get(event.key)
                if action:
                    action()
                    return
            elif event.type == pygame.FINGERDOWN:
                pos = game.mobile_controls.event_position(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not getattr(event, 'touch', False):
                pos = config.window_to_game(event.pos)
            elif event.type == pygame.MOUSEMOTION and not getattr(event, 'touch', False):
                game.cursor_pos = config.window_to_game(event.pos)
            if pos is not None:
                for rect, (_, action) in zip(rects, rows):
                    if action and rect.collidepoint(pos):
                        action()
                        return

    def frame(self, game, events, window, hidden, touch_active):
        if any(event.type == pygame.QUIT for event in events):
            return False
        self.ui_state = (False, False)
        self.drawn_to_window = False
        started = monotonic()
        if isinstance(self.transport, BrowserTransport) and self.transport.perf:
            if self.perf_frame is not None:
                self.perf_max[0] = max(self.perf_max[0], (started - self.perf_frame) * 1000)
            self.perf_frame = started
        self.state = state = self.transport.state
        direction = 'landscape' if config.MOBILE_LANDSCAPE_VIEW else 'portrait'
        away = hidden or (not game.web and not pygame.key.get_focused()
                          and not any(event.type == pygame.WINDOWFOCUSGAINED for event in events))
        if not isinstance(self.transport, BrowserTransport):
            self.transport.orientation = direction
        if self.orientation != direction:
            self.orientation = direction
            self.transport.send({'type': 'orientation', 'orientation': direction})
        if away != self.hidden and state:
            self.hidden = away
            self.send('suspend' if away else 'resume')
        if self.transport.ended:
            self.home()
            self.message('房间已关闭')
            state = None
        if (self.leave_task and self.leave_task.done() and self.leave_task.result()
                or isinstance(self.transport, BrowserTransport) and self.transport.leaveResult):
            self.leave_task = None
            self.home()
            state = None
        if self.page == 'home':
            self.draw_home(game, events, window)
        elif self.page == 'join':
            self.draw_illustrated(window, lambda: self.draw_join_form(game, events))
        elif state and state.get('world'):
            self.battle(game, state, events, away, touch_active, window)
        else:
            self.draw_illustrated(window, lambda: self.lobby(game, events, state, direction))
        return True

    def draw_home(self, game, events, window):
        rects = menu_ui.entrance_rects()
        action = None
        for event in events:
            pos = None
            if event.type == pygame.KEYDOWN:
                action = {pygame.K_RETURN: 'single', pygame.K_KP_ENTER: 'single',
                          pygame.K_k: 'keys'}.get(event.key)
                if game.desktop_controls:
                    action = next((name for name, key in menu_ui.ENTRANCE_SHORTCUTS.items()
                                   if key == event.key), action)
            elif event.type == pygame.FINGERDOWN:
                pos = game.mobile_controls.event_position(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not getattr(event, 'touch', False):
                pos = config.window_to_game(event.pos)
            elif event.type == pygame.MOUSEMOTION and not getattr(event, 'touch', False):
                game.cursor_pos = config.window_to_game(event.pos)
            if pos is not None:
                action = next((key for key, rect in rects.items() if rect.collidepoint(pos)), None)
            if action:
                break

        detail = self.notice if monotonic() < self.notice_until else ''
        if not detail and not isinstance(self.transport, BrowserTransport):
            status = str(self.transport.address)
            if status.startswith('联机'):
                detail = status
        self.draw_illustrated(window, lambda: menu_ui.draw_home(game, entrances=True, detail=detail))

        if action in ('single', 'keys'):
            self.page = 'single'
            self.home_keys = action == 'keys'
            if self.home_keys:
                game.state = GameState.KEY_SETTINGS
        elif action == 'create':
            self.start_room('create')
        elif action == 'join':
            self.join_form()

    def draw_illustrated(self, window, draw):
        from game_core.background import background_art

        scene = config.SCR
        background = background_art(1, config.VIEW_SIZE)
        if background is None or window.get_size() != config.VIEW_SIZE:
            window.fill(config.OCEAN_DEEP)
        if background is not None:
            window.blit(background, config.VIEW_OFFSET)
        config.SCR = RenderSurface(window, scene.get_size(), config.VIEW_SIZE,
                                   config.VIEW_OFFSET, desktop_ui=True)
        try:
            draw()
        finally:
            config.SCR = scene
        self.drawn_to_window = True

    def battle(self, game, state, events, away, touch_active, window=None):
        from online.adapters.presentation import Presentation
        slot = int(self.transport.slot)
        me = next((p for p in state['players'] if p['slot'] == slot), None)
        if me is None:
            self.home()
            return
        size = tuple(state['world_size'])
        local_names = ('SCR', 'SCREEN_WIDTH', 'SCREEN_HEIGHT', 'GAME_AREA_LEFT', 'GAME_AREA_RIGHT',
                       'GAME_AREA_BOTTOM', 'MOBILE_LANDSCAPE_VIEW', 'VIEW_SCALE', 'VIEW_SIZE', 'VIEW_OFFSET',
                       'campaign_time_ms')
        local = {name: getattr(config, name) for name in local_names}
        if self.presentation is None:
            try:
                self.presentation = Presentation(
                    pygame.Surface(size, pygame.SRCALPHA), integrated=True, desktop_controls=game.desktop_controls,
                    web=game.web, mobile_web=game.mobile_web)
            finally:
                for name, value in local.items():
                    setattr(config, name, value)
        presentation = self.presentation
        view = presentation.view
        view.desktop_controls, view.web, view.mobile_web = game.desktop_controls, game.web, game.mobile_web
        view.controls = game.controls
        view.clock = game.clock
        view.lan = self
        local_surface = config.SCR
        layout = None if window is None else (
            window.get_size(), local_surface.get_size(), config.VIEW_SIZE, config.VIEW_OFFSET)
        new_state = self.applied is not state
        now = monotonic() * 1000
        if new_state:
            self.positions.push(state, now)
        positions, scroll = self.positions.sample(now)
        if not game.web:
            scroll = None
        # The controlling player must not inherit the remote interpolation delay.
        for player in state['world']['players']:
            if player['slot'] == slot:
                positions.pop(player['id'], None)
        moving = positions != self.render_positions or scroll != self.render_scroll
        self.render_positions = positions
        self.render_scroll = scroll
        predict = (not state['paused'] and me['alive'] and state['phase'] == 'playing'
                   and state['stage'] != 'transition' and not away and not self.exit_confirmation
                   and me.get('move_speed', 0) > 0 and 'input_seq' in me and 'input_age_ms' in me)
        context = (state['match_id'], state['orientation'], state.get('current_level'), predict)
        if context != self.prediction_context:
            self.prediction = LocalPrediction()
            self.prediction_context = context
        if new_state:
            self.prediction.reconcile((me['x'], me['y']), me.get('input_seq', -1),
                                      me.get('input_age_ms', 0), now / 1000)
        self.predicting = predict and me.get('move_speed', 0) > 0
        self.prediction_speed = me.get('move_speed', 0)
        if new_state or moving or self.predicting or layout is None or layout != self.scene_layout:
            if layout is not None and (self.scene is None or self.scene.get_size() != layout[0]):
                self.scene = pygame.Surface(layout[0]).convert(window)
            target = self.scene if window is not None else local_surface
            draw_started = monotonic()
            self._compose_battle(state, slot, size, local, target, window is not None, new_state)
            self.perf_max[1] = max(self.perf_max[1], (monotonic() - draw_started) * 1000)
            self.applied, self.scene_layout = state, layout
        hud = local_surface
        if window is not None:
            # Positions interpolate between snapshots at the browser render cadence.
            window.blit(self.scene, (0, 0))
            hud = RenderSurface(window, local_surface.get_size(), config.VIEW_SIZE, config.VIEW_OFFSET, desktop_ui=True)
            self.drawn_to_window = True
        view.player_hp, view.max_player_hp = me['hp'], max(1, me['max_hp'])
        view.player.gold = state['gold']
        view.shop_notice = str(self.transport.error)
        view.player.owned_weapons = [p['key'] for p in state['catalog']['weapons'] if p['owned']]
        view.player.owned_characters = [p['key'] for p in state['catalog']['characters'] if p['owned']]
        paused = state['paused'] and state['pause_reason'] != 'revive'
        mode = state['mode']
        view.state = GameState.PLAYING if state['stage'] != 'boss' else GameState.BOSS_FIGHT
        if state['phase'] == 'won':
            view.state = GameState.VICTORY
        elif state['phase'] == 'lost':
            view.state = GameState.GAME_OVER
        elif me['shop_open']:
            view.state = GameState.SHOP
        elif paused and state['pause_reason'] != 'shop':
            view.state = GameState.PAUSED
        elif not me['alive']:
            view.state = (GameState.INFINITE_COUNTDOWN if me['continue_ms'] else
                          GameState.INFINITE_CONTINUE if mode == 'infinite' else GameState.GAME_OVER)
        view.game_over_reason = me.get('defeat_reason') or ''
        view.exit_confirmation = self.exit_confirmation
        config.SCR = hud
        try:
            config.campaign_time_ms = state['world']['time_ms']
            self.ui_state = (view.state in (GameState.PLAYING, GameState.BOSS_FIGHT),
                             view.state == GameState.PAUSED)
            view.draw_local_hud()
            for notice in state.get('notices', []):
                if notice['recipient_slot'] != slot:
                    continue
                key = 'lan-notice:' + state['match_id'] + ':' + notice['event_id'] + ':' + str(slot)
                browser = isinstance(self.transport, BrowserTransport)
                if key not in self.seen and not away and not (browser and self.transport.noticeSeen(key)):
                    self.message('队友已退出，你可以继续游戏')
                    self.seen.add(key)
                    if browser:
                        self.transport.markNotice(key)
                if key in self.seen or browser and self.transport.noticeSeen(key):
                    self.transport.send({'type': 'ack_notice', 'match_id': state['match_id'], 'event_id': notice['event_id']})
            if state['pause_reason'] == 'shop' and not me['shop_open']:
                events = [event for event in events if self.exit_confirmation or
                          event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE]
            view.handle_local_events(events)
            if touch_active is not None:
                view.mobile_controls.release_inactive_touches(touch_active)
            active = view.state in (GameState.PLAYING, GameState.BOSS_FIGHT) and state['stage'] != 'transition' and not paused and not away and not self.exit_confirmation
            if not active:
                view.mobile_controls.reset()
            x, y = view.mobile_controls.axis if active else (0, 0)
            keys = pygame.key.get_pressed()
            if active and not view.mobile_web:
                x = int(view._key_pressed(keys, 'p1_right')) - int(view._key_pressed(keys, 'p1_left'))
                y = int(view._key_pressed(keys, 'p1_down')) - int(view._key_pressed(keys, 'p1_up'))
            current_input = (x, y, bool(active and (
                view._mobile_fire_active() or not view.mobile_web and view._key_pressed(keys, 'p1_shoot'))))
            now = monotonic()
            if not state['paused'] and (current_input != self.last_input and now - self.last_send >= 1 / 60
                                        or now - self.last_send >= .05):
                self.last_send = now
                self.last_input = current_input
                sequence = self.transport.send({'type': 'input', 'dx': x, 'dy': y, 'shoot': current_input[2]})
                self.prediction.sent_input(sequence, now)
            view.draw_local_overlay(me)
            if view.state == GameState.VICTORY and view.victory_end <= config.game_ticks() and self.victory_left != state['match_id']:
                self.victory_left = state['match_id']
                self.leave()
            reason = {'orientation_mismatch': '请将屏幕转至房间方向', 'disconnected': '等待队友重连',
                      'suspended': '等待队友返回游戏', 'shop': '等待开店玩家关闭商店', 'server_error': '联机服务发生错误'}.get(state['pause_reason'], '')
            others = [f"P{p['slot']}  HP {p['hp']}/{p['max_hp']}" for p in state['players'] if p['slot'] != slot]
            error = str(self.transport.error)
            if error == 'paused':
                error = ''
            status = self.notice if monotonic() < self.notice_until else (reason or error or '　'.join(others))
            if isinstance(self.transport, BrowserTransport) and self.transport.perf:
                self.perf_max[2] = max(self.perf_max[2], self.transport.decode_ms)
                now = monotonic()
                if self.perf_at is None or now - self.perf_at >= 1:
                    gap = float(self.transport.maxSnapshotGap)
                    frame, draw, decode = self.perf_max
                    self.perf_text = f'NET3 P{int(self.predicting)} F{frame:.0f} D{draw:.0f} J{decode:.0f} N{gap:.0f}ms'
                    self.perf_at = now
                    self.perf_max = [0, 0, 0]
                status = self.perf_text
            if status:
                _, health, _ = view._hud_controls()
                width = min(320, config.SCREEN_WIDTH - 32)
                rect = pygame.Rect(0, health.top - 46, width, 20)
                rect.centerx = health.centerx
                view._draw_text_fit(status, view.font_tiny, (224, 244, 253), rect, align='center')
        finally:
            config.SCR = local_surface
            config.campaign_time_ms = local['campaign_time_ms']
        advance_music()

    def _compose_battle(self, state, slot, size, local, target, projected, new_state):
        presentation = self.presentation
        view = presentation.view
        local_surface = config.SCR
        view_size = config.VIEW_SIZE if projected else local_surface.get_size()
        offset = config.VIEW_OFFSET if projected else (0, 0)
        rect = pygame.Rect(0, 0, *size).fit(pygame.Rect(offset, view_size))
        world_target = None
        if projected:
            world_target = getattr(self, 'world_target', None)
            if (world_target is None or world_target.get_size() != size
                    or self.projected.get_size() != rect.size):
                self.projected = pygame.Surface(rect.size, pygame.SRCALPHA)
                world_target = self.world_target = RenderSurface(
                    self.projected, size, rect.size, (0, 0), track_damage=True)
        try:
            # Map the local buttons onto the fitted room canvas used by the actors.
            hud_scale = view_size[0] / local_surface.get_width()
            room_scale = rect.w / size[0]
            view._projected_field_badge_obstacles = [
                pygame.Rect(round((button.x * hud_scale + offset[0] - rect.x) / room_scale),
                            round((button.y * hud_scale + offset[1] - rect.y) / room_scale),
                            round(button.w * hud_scale / room_scale), round(button.h * hud_scale / room_scale))
                for button in view._field_badge_obstacles()]
            if new_state:
                presentation.apply(state, slot)
            restored = []
            if self.predicting:
                from online.shared.world import configure_world
                configure_world(presentation.orientation)
                player = view.player
                width = player.rect().w
                left = max(40, config.GAME_AREA_LEFT + width // 2)
                right = min(config.SCREEN_WIDTH - 40, config.GAME_AREA_RIGHT - (width + 1) // 2)
                bottom = player.bottom_limit()
                def clamp(point):
                    return max(left, min(right, point[0])), max(80, min(bottom, point[1]))
                axis = (self.last_input or (0, 0))[:2]
                predicted = self.prediction.advance(monotonic(), axis, self.prediction_speed, clamp)
                if predicted is not None:
                    restored.append((player, player.x, player.y))
                    player.x, player.y = predicted
            for ident, position in self.render_positions.items():
                obj = presentation.objects.get(ident)
                if obj is not None:
                    restored.append((obj, obj.x, obj.y))
                    obj.x, obj.y = position
            try:
                presentation.draw(world_target, clear=world_target is None)
            finally:
                for obj, x, y in restored:
                    obj.x, obj.y = x, y
        finally:
            view._projected_field_badge_obstacles = None
            for name, value in local.items():
                setattr(config, name, value)
        from game_core.background import background_art, draw_scrolling_background_art
        level = view.infinite_background_level if view.infinite_mode else view.current_level
        if target.get_size() != view_size:
            target.fill(config.OCEAN_DEEP)
        boss_background = view.trench_boss_background(view_size)
        subpixel = boss_background is None and self.render_scroll is not None and view._scrolls_background()
        if not (subpixel and draw_scrolling_background_art(
                target, offset, level, view_size, self.render_scroll / BACKGROUND_SCROLL_TICKS)):
            background = None if subpixel else view.scrolling_background(view_size)
            if background is None:
                background = background_art(level, view_size)
            if background is not None:
                target.blit(background, offset)
            else:
                target.fill(config.OCEAN_DEEP)
        if view.bg_transition_prev is not None:
            previous = pygame.transform.smoothscale(view.bg_transition_prev, view_size)
            remaining = (view.bg_transition_until - presentation.time_ms) / BG_FADE_MS
            previous.set_alpha(round(255 * min(1, remaining) ** 3))
            target.blit(previous, offset)
        config.SCR = (RenderSurface(target, local_surface.get_size(), view_size, offset, desktop_ui=True)
                      if world_target is not None else local_surface)
        try:
            for alpha, color in presentation.scrims:
                view._draw_scrim(alpha, color)
        finally:
            config.SCR = local_surface
        if world_target is not None:
            world_target.composite_onto(target, offset=rect.topleft, blit_flags=0)
        else:
            target.blit(pygame.transform.smoothscale(presentation.surface, rect.size), rect)
