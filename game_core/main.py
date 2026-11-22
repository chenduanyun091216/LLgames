"""PC 和 Web 共用的异步游戏入口。"""
import asyncio
import json
import platform
from time import perf_counter

import pygame

from . import asset_loader, config
from .config import FPS
from .render import RenderSurface


FRAME_TIMING_TOLERANCE = 0.002
STANDARD_BROWSER_RENDER_DENSITY = 1.15
STANDARD_MAX_VIEW = (1800, 960)
HD_MAX_VIEW = (2560, 1200)
BROWSER_QUALITIES = (1.5, 1.75, 2)


def _draw_scaled(window, scaled):
    if config.VIEW_SIZE != window.get_size():
        window.fill(config.OCEAN_DEEP)
    if config.SCR.get_size() == config.VIEW_SIZE:
        window.blit(config.SCR, config.VIEW_OFFSET)
    else:
        if scaled is None or scaled.get_size() != config.VIEW_SIZE:
            scaled = pygame.Surface(config.VIEW_SIZE).convert(config.SCR)
        pygame.transform.smoothscale(config.SCR, config.VIEW_SIZE, scaled)
        window.blit(scaled, config.VIEW_OFFSET)
    return scaled


def _browser_size(viewport, quality):
    short, long = sorted(viewport)
    if short <= 0:
        return viewport
    standard = min(STANDARD_MAX_VIEW[1] / short, STANDARD_MAX_VIEW[0] / long,
                   STANDARD_BROWSER_RENDER_DENSITY)
    hd = min(HD_MAX_VIEW[1] / short, HD_MAX_VIEW[0] / long)
    # Keep the default pixel budget stable; higher resolution is opt-in via HD.
    default_hd = min(1080 / short, HD_MAX_VIEW[0] / long)
    density = {1.5: standard, 1.75: (standard + default_hd) / 2, 2: hd}[quality]
    size = tuple(max(1, round(value * density)) for value in viewport)
    long_pixels = max(size)
    if size[0] * size[1] % 8 and long_pixels >= 8:
        # The bundled SDL canvas backend writes alpha eight pixels at a time
        # only when the complete frame fits that loop.
        density = (long_pixels - long_pixels % 8) / long
        size = tuple(max(1, round(value * density)) for value in viewport)
    return size


def _browser_viewport(window):
    return (int(getattr(window, 'ttgamesViewportWidth', None) or window.innerWidth),
            int(getattr(window, 'ttgamesViewportHeight', None) or window.innerHeight))


def _browser_surfaces(viewport, quality, set_scene_size, display=None):
    render_size = _browser_size(viewport, quality)
    output_size = _browser_size(viewport, 2) if set_scene_size else render_size
    if display is None or display.get_size() != output_size:
        display = pygame.display.set_mode(output_size, pygame.RESIZABLE)
    if set_scene_size:
        set_scene_size(*render_size, *output_size)
    # The visible part of the SDL canvas spans the scene's pixels for input as well.
    config.update_mobile_view(render_size, viewport)
    frame = display if render_size == display.get_size() else display.subsurface(((0, 0), render_size))
    return display, frame


async def main(transport=None):
    pygame.init()
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
    except Exception:
        pass
    browser_window = getattr(platform, 'window', None)
    viewport = None
    hide_startup = browser_window is None and pygame.display.get_driver() == 'windows'
    if browser_window is not None:
        quality = getattr(browser_window, 'ttgamesRenderDensity', 1.75)
        set_scene_size = getattr(browser_window, 'ttgamesSetSceneSize', None)
        asset_loader.web_hd_assets = quality != 1.5
        viewport = tuple(max(1, value) for value in _browser_viewport(browser_window))
        display, window = _browser_surfaces(viewport, quality, set_scene_size)
        show_resolutions = getattr(browser_window, 'ttgamesShowResolutions', None)
        if show_resolutions:
            show_resolutions(*(value for q in BROWSER_QUALITIES for value in _browser_size(viewport, q)))
    else:
        flags = pygame.RESIZABLE | (pygame.HIDDEN if hide_startup else 0)
        display = window = pygame.display.set_mode((960, 720), flags)
    pygame.display.set_caption('海洋生物入侵 - Ocean Invaders')
    native_window = None
    fullscreen = False
    if browser_window is None:
        from pygame._sdl2 import Window
        # Let the window manager fit the frame to the usable desktop area.
        native_window = Window.from_display_module()
        native_window.title = '海洋生物入侵 - Ocean Invaders · F11 全屏/窗口'
        if hide_startup:
            # On Windows, maximizing a hidden SDL window can show it before it has pixels.
            native_window.opacity = 0
            native_window.show()
        native_window.maximize()
        pygame.event.pump()
        pygame.key.stop_text_input()
        config.update_mobile_view(window.get_size())

    from .game import Game, GameState
    from .asset_loader import image_asset
    from .background import background_art, clear_background_cache, make_background, scrolling_background_art
    from .boss_skills import SKILL_IMAGES
    from .sounds import advance_music, make_sound, start_music

    start_music()
    mobile_web = browser_window is not None and bool(browser_window.matchMedia('(pointer: coarse)').matches)
    game = Game(desktop_controls=browser_window is None, scroll_campaign_backgrounds=True,
                web=browser_window is not None, mobile_web=mobile_web, campaign_ending=True)
    lan = None
    web_transport = getattr(browser_window, 'ttgamesLAN', None)
    if transport is not None or web_transport is not None:
        from online.client.integrated import BrowserTransport, LAN
        lan = LAN(transport if transport is not None else BrowserTransport(web_transport))
        game.on_return_home = lan.home
    for filename in SKILL_IMAGES:
        image_asset(filename)
    for sound in ('boss_appear', 'boss_hit', 'kill', 'level_up', 'player_hit'):
        make_sound(sound)
    warmed_background = None
    warmed_panorama = None
    warmed_boss = None
    running = True
    draw_ui = getattr(browser_window, 'ttgamesDrawUI', None)
    record_frame = getattr(browser_window, 'ttgamesRecordFrame', None)
    fill_safe_area = getattr(browser_window, 'ttgamesFillSafeArea', None)
    touch_active = getattr(browser_window, 'ttgamesTouchActive', None)
    previous_ui = None
    fps_started = None
    fps_frames = 0
    displayed_fps = None
    show_timings = browser_window is not None and 'perf=1' in str(browser_window.location.search)[1:].split('&')
    update_seconds = draw_seconds = compose_seconds = submit_seconds = 0.0
    timing_label = ''
    scaled = None
    foreground = None
    rendered = None
    previous_background = None
    resize_events = (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED)
    step = 1 / FPS
    update_tolerance = FRAME_TIMING_TOLERANCE if browser_window is not None else 0.0
    campaign_seconds = 0.0
    accumulator = 0.0
    previous_frame = perf_counter()
    was_hidden = False
    advancing_states = (GameState.PLAYING, GameState.BOSS_FIGHT,
                        GameState.LEVEL_TRANSITION, GameState.VICTORY)
    cutscene_states = (GameState.OPENING, GameState.ENDING)

    def present_frame():
        nonlocal hide_startup
        if window is not display:
            # Browser filtering can sample one texel beyond the visible scene.
            width, height = window.get_size()
            display.blit(display, (width, 0), (width - 1, 0, 1, height))
            display.blit(display, (0, height), (0, height - 1, width + 1, 1))
        pygame.display.flip()
        if hide_startup:
            native_window.opacity = 1
            hide_startup = False

    def advance_frame_music(frame_started):
        if browser_window is None:
            advance_music()
            return
        # Reserve time for the browser to present the submitted frame.
        remaining = step - (perf_counter() - frame_started) - 0.001
        advance_music(max(0.00025, min(0.004, remaining)))

    while running:
        # Pygbag already resumes this coroutine once per requestAnimationFrame.
        frame_time = perf_counter()
        elapsed = min(frame_time - previous_frame, 4 * step)
        previous_frame = frame_time
        hidden = bool(browser_window.document.hidden) if browser_window is not None else False
        if was_hidden:
            elapsed = 0
        was_hidden = hidden
        previous_area = (config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT, config.GAME_AREA_BOTTOM)
        resized = False
        events = pygame.event.get()
        if native_window is not None:
            for event in events:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11 and not getattr(event, 'repeat', False):
                    if fullscreen:
                        native_window.set_windowed()
                    else:
                        native_window.set_fullscreen(desktop=True)
                    fullscreen = not fullscreen
                    pygame.event.pump()
                    resized = True
            events = [event for event in events if not (event.type == pygame.KEYDOWN and event.key == pygame.K_F11)]
        if browser_window is not None:
            new_quality = getattr(browser_window, 'ttgamesRenderDensity', 1.75)
            new_viewport = _browser_viewport(browser_window)
            if min(new_viewport) > 0 and (new_viewport != viewport or new_quality != quality):
                quality = new_quality
                hd_assets = quality != 1.5
                if hd_assets != asset_loader.web_hd_assets:
                    asset_loader.web_hd_assets = hd_assets
                    clear_background_cache()
                    game.bg = game._load_bg()
                    warmed_background = warmed_panorama = warmed_boss = None
                layout_changed = new_viewport != viewport
                viewport = new_viewport
                display, window = _browser_surfaces(viewport, quality, set_scene_size, display)
                if layout_changed:
                    if show_resolutions:
                        show_resolutions(*(value for q in BROWSER_QUALITIES for value in _browser_size(viewport, q)))
                    game.resize_view(previous_area)
                resized = True
        elif resized or any(event.type in resize_events for event in events):
            config.update_mobile_view(window.get_size())
            game.resize_view(previous_area)
            resized = True
        if lan is not None and lan.page != 'single':
            if browser_window is not None:
                lan.browser_viewport = viewport if draw_ui else None
                lan.render_density = quality
            running = lan.frame(game, events, window, hidden, touch_active)
            if not lan.drawn_to_window:
                scaled = _draw_scaled(window, scaled)
            previous_background = None
            present_frame()
            if browser_window is not None:
                lan.record_rendered_frame(perf_counter(), reset=hidden or resized)
            if fill_safe_area:
                fill_safe_area()
            if draw_ui:
                lan_ui = (lan.ui_labels, config.SCREEN_WIDTH, config.SCREEN_HEIGHT,
                          *lan.ui_state, '', lan.page == 'home')
                if previous_ui != lan_ui:
                    draw_ui(json.dumps(lan.ui_labels, separators=(",", ":")), *lan_ui[1:])
                    previous_ui = lan_ui
            if record_frame:
                record_frame('lan' if lan.ui_state[0] else 'idle', resized)
            if not hidden:
                advance_frame_music(frame_time)
            game.clock.tick(0 if browser_window is not None else FPS)
            await asyncio.sleep(0)
            continue
        was_advancing = game.state in advancing_states
        if lan is not None and game.state == GameState.MENU and any(
                e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
            lan.home()
            continue
        running = game.handle_events(events)
        if not running:
            break
        if lan is not None and lan.home_keys and game.state == GameState.MENU:
            lan.home_keys = False
            lan.home()
            continue
        if touch_active is not None:
            game.mobile_controls.release_inactive_touches(touch_active)
        if game.state in cutscene_states:
            accumulator = 0.0
            game.update()
        elif game.web_level_intro_active():
            if config.campaign_time_ms is None and game.difficulty is not None:
                campaign_seconds = pygame.time.get_ticks() / 1000
                config.campaign_time_ms = round(campaign_seconds * 1000)
            accumulator = 0.0
        elif game.exit_confirmation:
            accumulator = 0.0
        elif game.difficulty is None:
            config.campaign_time_ms = None
            accumulator = 0.0
            game.update()
        else:
            if config.campaign_time_ms is None:
                campaign_seconds = pygame.time.get_ticks() / 1000
                config.campaign_time_ms = round(campaign_seconds * 1000)
            if not hidden and not resized and was_advancing and game.state in advancing_states:
                accumulator += elapsed
                while (accumulator + update_tolerance >= step and game.state in advancing_states
                       and not game.web_level_intro_active()):
                    accumulator -= step
                    campaign_seconds += step
                    config.campaign_time_ms = round(campaign_seconds * 1000)
                    game.update()
            else:
                accumulator = 0.0
                if not hidden and game.state == GameState.INFINITE_COUNTDOWN:
                    game.update()
        if game.state == GameState.MENU:
            start_music()
        if game.state in cutscene_states:
            if game.state == GameState.OPENING:
                game.draw_opening(window)
            else:
                game.draw_ending(window)
            if game.state in cutscene_states:
                previous_background = None
                present_frame()
                if fill_safe_area:
                    fill_safe_area()
                cutscene = 'opening' if game.state == GameState.OPENING else 'ending'
                cutscene_ui = ([], config.SCREEN_WIDTH, config.SCREEN_HEIGHT, False, False, cutscene)
                if draw_ui and cutscene_ui != previous_ui:
                    draw_ui('[]', *cutscene_ui[1:])
                    previous_ui = cutscene_ui
                if game.state == GameState.OPENING:
                    advance_music()
                game.clock.tick(0 if browser_window is not None else FPS)
                await asyncio.sleep(0)
                continue
        if show_timings:
            draw_started = perf_counter()
        labels = [] if draw_ui else None
        level = game.infinite_background_level if game.infinite_mode else game.current_level
        use_hd = game.state in (GameState.MENU, GameState.DIFFICULTY_SELECT, GameState.PLAYING,
                                GameState.BOSS_FIGHT, GameState.LEVEL_TRANSITION)
        scene = config.SCR
        try:
            if use_hd or browser_window is None:
                if foreground is None or foreground.get_size() != window.get_size():
                    foreground = pygame.Surface(window.get_size(), pygame.SRCALPHA)
                    rendered = None
                if rendered is None or resized:
                    rendered = RenderSurface(foreground, scene.get_size(), config.VIEW_SIZE,
                                             config.VIEW_OFFSET, track_damage=True, desktop_ui=browser_window is None)
                    previous_background = None
                config.SCR = rendered
                background = game.scrolling_background(config.VIEW_SIZE)
                if background is None:
                    background = background_art(level, config.VIEW_SIZE)
                game.draw(labels, draw_background=background is None)
                if show_timings:
                    compose_started = perf_counter()
                if background is not None and background is previous_background:
                    rendered.restore_background(window, background, config.OCEAN_DEEP)
                elif background is not None:
                    if config.VIEW_SIZE != window.get_size():
                        window.fill(config.OCEAN_DEEP)
                    window.blit(background, config.VIEW_OFFSET)
                else:
                    window.fill(config.OCEAN_DEEP)
                rendered.composite_onto(window)
                previous_background = background
            else:
                previous_background = None
                game.draw(labels)
                if show_timings:
                    compose_started = perf_counter()
                scaled = _draw_scaled(window, scaled)
        finally:
            config.SCR = scene
        if show_timings:
            submit_started = perf_counter()
        present_frame()
        if fill_safe_area:
            fill_safe_area()
        if draw_ui:
            in_battle = (game.state in (GameState.PLAYING, GameState.BOSS_FIGHT)
                         and not game.web_level_intro_active())
            if in_battle and not hidden:
                submitted_at = perf_counter()
                if fps_started is None or resized:
                    fps_started = submitted_at
                    fps_frames = 0
                    update_seconds = draw_seconds = compose_seconds = submit_seconds = 0.0
                else:
                    fps_frames += 1
                    if show_timings:
                        update_seconds += draw_started - frame_time
                        draw_seconds += compose_started - draw_started
                        compose_seconds += submit_started - compose_started
                        submit_seconds += submitted_at - submit_started
                    sample_duration = submitted_at - fps_started
                    if sample_duration >= 1:
                        displayed_fps = round(fps_frames / sample_duration)
                        if show_timings:
                            per_frame = 1000 / fps_frames
                            timing_label = (f'更新 {update_seconds * per_frame:.1f} · '
                                            f'绘制 {draw_seconds * per_frame:.1f} · '
                                            f'合成 {compose_seconds * per_frame:.1f} · '
                                            f'提交 {submit_seconds * per_frame:.1f} ms')
                            update_seconds = draw_seconds = compose_seconds = submit_seconds = 0.0
                        fps_started = submitted_at
                        fps_frames = 0
                fps_label = 'FPS --' if displayed_fps is None else f'FPS {displayed_fps}'
                diagnostics_y = game.hud_diagnostics_y
                labels.append((fps_label, 10, False, (180, 220, 232), *game.hud_fps_rect, 'right'))
                if timing_label:
                    labels.append((timing_label, 10, False, (180, 220, 232), 17, diagnostics_y + 14, 285, 13, 'left'))
                    sizes = f'场景 {window.get_width()}×{window.get_height()} · 输出 {display.get_width()}×{display.get_height()}'
                    labels.append((sizes, 10, False, (180, 220, 232), 17, diagnostics_y + 28, 245, 13, 'left'))
            else:
                fps_started = None
                fps_frames = 0
                displayed_fps = None
                update_seconds = draw_seconds = compose_seconds = submit_seconds = 0.0
                timing_label = ''
            paused = game.state == GameState.PAUSED and not game.exit_confirmation
            home = lan is None and game.state == GameState.MENU
            frame = (labels, config.SCREEN_WIDTH, config.SCREEN_HEIGHT, in_battle, paused, '', home)
            if frame != previous_ui:
                draw_ui(json.dumps(labels, separators=(",", ":")), *frame[1:])
                previous_ui = frame
        level_count = len(config.INFINITE_BOSS_HP if game.infinite_mode else config.LEVEL_CONFIGS)
        next_index = level % level_count
        next_level = next_index + 1
        background_key = (next_level, scene.get_size(), config.VIEW_SIZE)
        warm_campaign = game.state == GameState.LEVEL_TRANSITION
        warm_infinite = (game.infinite_mode and use_hd and game.bg_transition_prev is None)
        warm_scroll = browser_window is not None and warm_campaign and not game.infinite_mode
        if (not hidden and game.difficulty and background_key != warmed_background
                and (warm_campaign or warm_infinite)):
            make_background(next_level, art_size=None if warm_scroll else config.VIEW_SIZE)
            warmed_background = background_key
        elif not hidden and warm_scroll and warmed_panorama != background_key:
            # A scrolling level uses a display-size panorama, not the static backdrop.
            scrolling_background_art(next_level, config.VIEW_SIZE, 0)
            warmed_panorama = background_key
        elif (not hidden and warm_campaign and warmed_boss != next_level
              and config.LEVEL_CONFIGS[next_index].get('boss_on_start')):
            boss = config.BOSS_DEFS[config.LEVEL_CONFIGS[next_index]['boss_idx']]
            image_asset(f'bosses/{boss.get("sprite_key", boss["key"])}.png')
            warmed_boss = next_level
        else:
            advance_frame_music(frame_time)
        game.clock.tick(0 if browser_window is not None else FPS)
        if record_frame:
            record_frame('single' if game.state in advancing_states else 'idle', resized)
        await asyncio.sleep(0)

