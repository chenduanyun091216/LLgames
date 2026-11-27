"""Shared Pygame entry and room UI for native and browser transports."""
import asyncio
import json
from time import monotonic

import pygame

from game_core import config, menu_ui
from game_core.render import RenderSurface
from game_core.game import BACKGROUND_SCROLL_TICKS, BG_FADE_MS, GameState
from game_core.sounds import start_music
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
    def game_url(self):
        return str(self.bridge.gameUrl)

    @property
    def setup_url(self):
        return str(self.bridge.setupUrl)

    def open_home_link(self, url):
        self.bridge.openHomeLink(url)

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
        self.caps_sent = False
        self.side_view = None
        self.duel_view = None
        self.courier_view = None
        self.duel_picker = False
        self.requested_mode = None
        self.presentation = None
        self.scene = None
        self.scene_layout = None
        self.scene_labels = ()
        self.browser_viewport = None
        self.render_density = 1.75
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
        self.ui_labels = ()
        self.displayed_fps = 0
        self._fps_started = None
        self._fps_frames = 0
        self.perf_at = self.perf_frame = None
        self.perf_max = [0, 0, 0]
        self.perf_text = ''
        if isinstance(transport, BrowserTransport) and str(transport.resumeCode):
            self.start_room('join', str(transport.resumeCode))

    def close_courier_view(self):
        if self.courier_view is not None:
            self.courier_view.silence()
            self.courier_view = None

    def message(self, text):
        self.notice = text
        self.notice_until = monotonic() + 4

    def send(self, action, key=None):
        msg = {'type': 'action', 'action': action}
        if key is not None:
            msg['key'] = key
        self.transport.send(msg)

    def home(self):
        self.close_courier_view()
        self.transport.reset()
        self.caps_sent = False
        self.side_view = None
        self.duel_view = None
        self.duel_picker = False
        self.requested_mode = None
        self.page = 'home'
        self.presentation = None
        self.scene = None
        self.scene_layout = None
        self.scene_labels = ()
        self.last_input = None
        self.last_send = 0
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
        briefing = ()
        error = str(self.transport.error)
        detail = '' if error == 'orientation_mismatch' else error
        if error == 'update_required':
            detail = '请更新游戏后重连，原席位暂时保留'
        elif error == 'wrong_room_code':
            detail = '房间不存在，请核对房主提供的房间号或邀请链接'
        elif error == 'room_in_use':
            detail = '已有房间。加入请输入房主的四位房间号，重新创建需等原房间关闭。'
            rows.append(('重新创建', lambda: self.start_room('create')))
        elif error == 'update_required':
            detail = '请更新游戏后重连'
        if not state and not self.transport.slot and error in ('room_in_use', 'wrong_room_code'):
            rows.append(('输入房间号', self.join_form))
        if state:
            if 'extra_modes' in state and not self.caps_sent:
                self.transport.send({'type':'mode_caps','modes':[m for m in state['extra_modes'] if m=='run_gun']})
                self.caps_sent = True
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
                elif msg['mode'] == 'boss_duel':
                    msg.setdefault('mode_options', state['mode_options'] if state['mode'] == 'boss_duel'
                                   else {'boss': 'whale'})
                elif msg['mode'] == 'sub_courier':
                    msg.setdefault('mode_options', state['mode_options'] if state['mode'] == 'sub_courier'
                                   else {'order': 'jelly'})
                elif msg['mode'] == 'tide_race':
                    msg.setdefault('mode_options', state.get('mode_options') if state['mode'] == 'tide_race' else {'track': 'lighthouse'})
                self.transport.send(msg)
            if host and not state['orientation'] and not self.settings_sent:
                settings()
                self.settings_sent = True
            if host:
                from online.shared.protocol import COOP_MODES
                names = {'campaign':'战役','infinite':'无限模式', **COOP_MODES}
                modes = ['campaign','infinite',*state.get('available_modes',[])]
                requested=getattr(self,'requested_mode',None)
                if requested in modes and orientation:
                    self.requested_mode=None
                    settings(mode=requested)
                elif requested == 'boss_duel' and len(state['players']) == 2 and not detail:
                    detail = '请两位玩家使用支持 Boss 对决的版本'
                if requested == 'sub_courier' and not detail:
                    detail = ('等待搭档加入后选单' if len(state['players']) < 2 else
                              '请两位玩家使用支持潜艇快递的版本')
                if requested == 'tide_race' and not detail:
                    detail = ('等待对手加入后选赛道' if len(state['players']) < 2 else
                              '请两位玩家使用支持潮汐竞速的版本')
                if state['mode'] not in modes:
                    modes.append(state['mode'])
                rows.append((names[state['mode']],lambda: settings(mode=modes[(modes.index(state['mode'])+1)%len(modes)] if state['mode'] in modes else 'campaign')))
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
                if state['mode'] == 'boss_duel':
                    from game_core.modes.boss_duel import BOSSES
                    boss = state['mode_options']['boss']
                    if self.duel_picker:
                        from .duel_art import boss_cards
                        boss_cards(game, events, boss,
                                   lambda choice: settings(mode_options={'boss': choice}) if choice else None,
                                   lambda: setattr(self, 'duel_picker', False))
                        return
                    rows.append((BOSSES[boss]['name'], lambda: setattr(self, 'duel_picker', True)))
            elif state['mode'] == 'boss_duel':
                from game_core.modes.boss_duel import BOSSES
                detail = 'Boss 对决 · ' + BOSSES[state['mode_options']['boss']]['name'] + '　' + detail
            if state['mode'] == 'sub_courier':
                from game_core.modes.sub_courier import ORDERS
                order = state['mode_options']['order']
                cargo = ORDERS[order]
                order_ids = tuple(ORDERS)
                if host:
                    rows.append((cargo['name'], lambda: settings(mode_options={
                        'order': order_ids[(order_ids.index(order) + 1) % len(order_ids)]})))
                route = ' → '.join(label for _, label in cargo['landmarks'])
                role = '舵手 · 驾驶和慢靠' if host else '轮机员 · 压载、修理和签收'
                briefing = (f"{cargo['name']} · {cargo['route']} · {cargo['estimate']}",
                            f"{role}｜{route}", cargo['brief'])
            if state['mode'] == 'tide_race':
                from game_core.modes.tide_race import TRACK_IDS, content
                track = state['mode_options']['track']
                title = content()['tracks'][track]['name']
                if host:
                    rows.append((title, lambda: settings(mode_options={
                        'track': TRACK_IDS[(TRACK_IDS.index(track)+1)%len(TRACK_IDS)]})))
                else:
                    detail = '潮汐竞速 · ' + title + '　' + detail
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
            address = str(getattr(self.transport, 'address', ''))
            if not detail and self.transport.slot == 1 and address.startswith('联机证书'):
                detail = address
            detail = (' · '.join(labels) + '　' + detail).strip()
        self.draw_room(game, rows, events, detail or '正在连接房间…', str(self.transport.invite), briefing=briefing)

    def draw_room(self, game, rows, events, detail, invite, *, briefing=()):
        rects = menu_ui.room_action_rects(len(rows))
        menu_ui.draw_room(game, rows, rects, detail, invite, briefing=briefing)
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
        self.ui_labels = ()
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
        if self.page in ('home', 'join') or not (state and state.get('world')):
            start_music()
        if self.page == 'home':
            self.draw_home(game, events, window)
        elif self.page == 'join':
            self.draw_illustrated(window, lambda: self.draw_join_form(game, events))
        elif state and state.get('world'):
            if state['world'].get('mode') == 'sub_courier':
                from .sub_courier_view import CourierView
                if self.courier_view is None:
                    self.courier_view = CourierView()
                self.courier_view.frame(self, game, state, events, away, window, touch_active)
            elif state['world'].get('mode') == 'boss_duel':
                from .duel_view import DuelView
                if self.duel_view is None:
                    self.duel_view = DuelView()
                self.duel_view.frame(self, game, state, events, away, window, touch_active)
            elif state['world'].get('mode') == 'tide_race':
                from .tide_race_view import TideRaceView
                if getattr(self, 'tide_race_view', None) is None:
                    self.tide_race_view = TideRaceView()
                self.tide_race_view.frame(self, game, state, events, away, window)
            elif state['world'].get('kind')=='run_gun':
                from online.client.side_view import SideView
                if self.side_view is None:
                    self.side_view=SideView()
                self.side_view.frame(self,game,state,events,away,window)
            else:
                self.battle(game, state, events, away, touch_active, window)
        else:
            self.duel_view = None
            self.tide_race_view = None
            self.close_courier_view()
            self.draw_illustrated(window, lambda: self.lobby(game, events, state, direction))
        return True

    def record_rendered_frame(self, now, *, reset=False):
        if reset or not self.ui_state[0]:
            self._fps_started = None
            self._fps_frames = self.displayed_fps = 0
        elif self._fps_started is None:
            self._fps_started = now
        else:
            self._fps_frames += 1
            elapsed = now - self._fps_started
            if elapsed >= 1:
                self.displayed_fps = round(self._fps_frames / elapsed)
                self._fps_started = now
                self._fps_frames = 0

    def draw_home(self, game, events, window):
        requested = str(getattr(self.transport.bridge, 'requestedMode', '')) if isinstance(self.transport, BrowserTransport) else ''
        if requested in ('run_gun', 'boss_duel', 'sub_courier', 'tide_race'):
            self.transport.bridge.requestedMode = ''
            self.page = 'single'
            game._activate_home_action('modes')
            getattr(game.side_game, requested)()
            return
        rects = menu_ui.entrance_rects()
        links = [(label, url) for label, url in (
            ('证书安装', getattr(self.transport, 'setup_url', '')),
            ('下载游戏', getattr(self.transport, 'game_url', '')),
        ) if url]
        if links:
            rects.update(zip((url for _, url in links), menu_ui.home_link_rects(len(links))))
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
        self.draw_illustrated(window, lambda: menu_ui.draw_home(game, entrances=True, detail=detail,
                                                               links=links))

        if action == 'modes':
            self.page = 'single'
            game._activate_home_action('modes')
        elif action in ('single', 'keys'):
            self.page = 'single'
            self.home_keys = action == 'keys'
            if self.home_keys:
                game.state = GameState.KEY_SETTINGS
        elif action == 'create':
            self.start_room('create')
        elif action == 'join':
            self.join_form()
        elif action:
            self.transport.open_home_link(action)

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
        new_state = self.applied is not state
        if new_state:
            try:
                presentation.apply(state, slot)
            finally:
                for name, value in local.items():
                    setattr(config, name, value)
        view.desktop_controls, view.web, view.mobile_web = game.desktop_controls, game.web, game.mobile_web
        view.desktop_quality = game.desktop_quality
        view.controls = game.controls
        view.clock = game.clock
        view.lan = self
        local_surface = config.SCR
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
        config.campaign_time_ms = presentation.time_ms
        try:
            active, current_input = self._battle_input(view, state, me, events, away, touch_active)
            game.desktop_quality = view.desktop_quality
            view.exit_confirmation = self.exit_confirmation
            now = monotonic()
            self._update_battle_prediction(state, me, now, active, new_state, current_input)
            self._draw_battle_world(state, me['slot'], size, local, window, new_state, now,
                                    current_input[:2], active)
            self.ui_state = (view.state in (GameState.PLAYING, GameState.BOSS_FIGHT),
                             view.state == GameState.PAUSED and not self.exit_confirmation)
            if active and self.browser_viewport is not None and window is not None:
                self.ui_labels = list(self.ui_labels)
                view._ui_labels = self.ui_labels
            view.draw_local_hud(self.displayed_fps if isinstance(self.transport, BrowserTransport) else None)
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
            view._ui_labels = None
            config.SCR = local_surface
            config.campaign_time_ms = local['campaign_time_ms']

    def _battle_input(self, view, state, me, events, away, touch_active):
        if state['pause_reason'] == 'shop' and not me['shop_open']:
            events = [event for event in events if self.exit_confirmation or
                      event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE]
        view.handle_local_events(events)
        if touch_active is not None:
            view.mobile_controls.release_inactive_touches(touch_active)
        active = (view.state in (GameState.PLAYING, GameState.BOSS_FIGHT) and state['stage'] != 'transition'
                  and not state['paused'] and not away and not self.exit_confirmation
                  and (not isinstance(self.transport, BrowserTransport) or self.transport.ready))
        if not active:
            view.mobile_controls.reset()
            return False, (0, 0, False)
        x, y = view.mobile_controls.axis
        shoot = view._mobile_fire_active()
        if not view.mobile_web:
            keys = pygame.key.get_pressed()
            dx = int(view._key_pressed(keys, 'p1_right')) - int(view._key_pressed(keys, 'p1_left'))
            dy = int(view._key_pressed(keys, 'p1_down')) - int(view._key_pressed(keys, 'p1_up'))
            if dx or dy:
                x, y = dx, dy
            shoot = shoot or view._key_pressed(keys, 'p1_shoot')
        return True, (x, y, bool(shoot))

    def _update_battle_prediction(self, state, me, now, active, new_state, current_input):
        self.prediction_speed = me.get('move_speed', 0)
        self.predicting = (active and self.prediction_speed > 0
                           and 'input_seq' in me and 'input_age_ms' in me)
        context = (state['match_id'], state['orientation'], state.get('current_level'), self.predicting)
        context_changed = context != self.prediction_context
        if context_changed:
            self.prediction = LocalPrediction()
            self.prediction_context = context
        if self.predicting and (new_state or context_changed):
            self.prediction.reconcile((me['x'], me['y']), me['input_seq'], me['input_age_ms'], now)
        age = now - self.last_send
        # Small refresh jitters should still allow one input change per 60 Hz frame.
        if not state['paused'] and (age >= .05 or (age >= 1 / 60 - .002 and current_input != self.last_input)):
            self.last_send = now
            self.last_input = current_input
            x, y, shoot = current_input
            sequence = self.transport.send({'type': 'input', 'dx': x, 'dy': y, 'shoot': shoot})
            self.prediction.sent_input(sequence, now)

    def _draw_battle_world(self, state, slot, size, local, window, new_state, now, axis, active):
        view = self.presentation.view
        local_surface = config.SCR
        stamp = now * 1000
        if new_state:
            self.positions.push(state, stamp)
        positions, scroll = self.positions.sample(stamp)
        if not view.web:
            scroll = None
        # Local movement is predicted immediately, while remote objects use the buffer.
        for player in state['world']['players']:
            if player['slot'] == slot:
                positions.pop(player['id'], None)
        moving = positions != self.render_positions or scroll != self.render_scroll
        self.render_positions, self.render_scroll = positions, scroll
        show_labels = active and self.browser_viewport is not None and window is not None
        direct = window is not None and view.web and self.predicting
        layout = None if window is None else (window.get_size(), local_surface.get_size(), config.VIEW_SIZE,
                                              config.VIEW_OFFSET, show_labels, self.browser_viewport,
                                              self.render_density, view.actor_scale_percent)
        if new_state or moving or self.predicting or layout is None or layout != self.scene_layout:
            if window is None:
                target = local_surface
            elif direct:
                target = window
            else:
                if self.scene is None or self.scene.get_size() != layout[0]:
                    self.scene = pygame.Surface(layout[0]).convert(window)
                target = self.scene
            draw_started = monotonic()
            self._compose_battle(size, local, target, window is not None, axis, now, show_labels)
            self.perf_max[1] = max(self.perf_max[1], (monotonic() - draw_started) * 1000)
            self.applied = state
            self.scene_layout = None if direct else layout
        self.ui_labels = self.scene_labels if show_labels else ()
        if window is not None:
            if not direct:
                window.blit(self.scene, (0, 0))
            config.SCR = RenderSurface(window, local_surface.get_size(), config.VIEW_SIZE, config.VIEW_OFFSET,
                                       desktop_ui=True, blit_flags=pygame.BLEND_ALPHA_SDL2 if view.web else 0)
            self.drawn_to_window = True

    def _compose_battle(self, size, local, target, projected, axis, now, show_labels):
        presentation = self.presentation
        view = presentation.view
        local_surface = config.SCR
        view_size = config.VIEW_SIZE if projected else local_surface.get_size()
        offset = config.VIEW_OFFSET if projected else (0, 0)
        rect = pygame.Rect(0, 0, *size).fit(pygame.Rect(offset, view_size))
        # Keep the complete room; compensate object sizes for its letterboxing.
        view.presentation_scale = (view_size[0] / local_surface.get_width()) / (rect.w / size[0])
        local_landscape = local['MOBILE_LANDSCAPE_VIEW']
        room_landscape = presentation.orientation == 'landscape'
        entity_scale = lambda landscape: (config.MOBILE_LANDSCAPE_ENTITY_SCALE if landscape
                                           else config.MOBILE_PORTRAIT_ENTITY_SCALE)
        boss_scale = lambda landscape: (config.MOBILE_LANDSCAPE_BOSS_SCALE if landscape
                                         else config.MOBILE_PORTRAIT_ENTITY_SCALE)
        view.presentation_actor_scale = entity_scale(local_landscape) / entity_scale(room_landscape)
        view.presentation_boss_scale = boss_scale(local_landscape) / boss_scale(room_landscape)
        labels = [] if show_labels else None
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
            if self.browser_viewport is not None:
                css_scale = min(pixels / extent for pixels, extent in zip(self.browser_viewport, size))
                # Keep the base 16 px status font legible when the room is letterboxed on a phone.
                view._water_status_scale = max(1, min(1.75, 12 / (16 * css_scale)))
            view._projected_field_badge_obstacles = [
                pygame.Rect(round((button.x * hud_scale + offset[0] - rect.x) / room_scale),
                            round((button.y * hud_scale + offset[1] - rect.y) / room_scale),
                            round(button.w * hud_scale / room_scale), round(button.h * hud_scale / room_scale))
                for button in view._field_badge_obstacles()]
            restored = []
            restored_previous = []
            restored_trails = []
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
                predicted = self.prediction.advance(now, axis, self.prediction_speed, clamp)
                if predicted is not None:
                    restored.append((player, player.x, player.y))
                    player.x, player.y = predicted
            for ident, position in self.render_positions.items():
                obj = presentation.objects.get(ident)
                if obj is not None and position != (obj.x, obj.y):
                    restored.append((obj, obj.x, obj.y))
                    dx, dy = position[0] - obj.x, position[1] - obj.y
                    # Keep projectile geometry in the same frame as the interpolated head.
                    if hasattr(obj, 'prev_x') and hasattr(obj, 'prev_y'):
                        restored_previous.append((obj, obj.prev_x, obj.prev_y))
                        obj.prev_x += dx
                        obj.prev_y += dy
                    for attr in ('sniper_trail', 'missile_trail'):
                        trail = getattr(obj, attr, None)
                        if trail:
                            restored_trails.append((obj, attr, trail))
                            setattr(obj, attr, [(x + dx, y + dy) for x, y in trail])
                    obj.x, obj.y = position
            try:
                presentation.draw(world_target, clear=world_target is None, ui_labels=labels)
            finally:
                for obj, x, y in restored:
                    obj.x, obj.y = x, y
                for obj, x, y in restored_previous:
                    obj.prev_x, obj.prev_y = x, y
                for obj, attr, trail in restored_trails:
                    setattr(obj, attr, trail)
        finally:
            view._projected_field_badge_obstacles = None
            for name, value in local.items():
                setattr(config, name, value)
            config.campaign_time_ms = presentation.time_ms
        self.scene_labels = ()
        if labels:
            ui_x = local_surface.get_width() / target.get_width()
            ui_y = local_surface.get_height() / target.get_height()
            self.scene_labels = tuple(
                (text, font_size * room_scale * ui_y, bold, color,
                 (rect.x + x * room_scale) * ui_x, (rect.y + y * room_scale) * ui_y,
                 w * room_scale * ui_x, h * room_scale * ui_y, align)
                for text, font_size, bold, color, x, y, w, h, align in labels)
        from game_core.background import background_art, draw_scrolling_background_art, scrolling_background_art
        level = view.infinite_background_level if view.infinite_mode else view.current_level
        if target.get_size() != view_size:
            target.fill(config.OCEAN_DEEP)
        background = view.trench_boss_background(view_size)
        scrolling = background is None and self.render_scroll is not None and view._scrolls_background()
        progress = self.render_scroll / BACKGROUND_SCROLL_TICKS if scrolling else None
        subpixel = scrolling and self.render_density == 2
        if not (subpixel and draw_scrolling_background_art(
                target, offset, level, view_size, progress)):
            if background is None:
                background = (scrolling_background_art(level, view_size, progress) if scrolling
                              else view.scrolling_background(view_size))
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
            world_target.composite_onto(target, offset=rect.topleft,
                                        blit_flags=pygame.BLEND_ALPHA_SDL2 if view.web else 0)
        else:
            target.blit(pygame.transform.smoothscale(presentation.surface, rect.size), rect)
