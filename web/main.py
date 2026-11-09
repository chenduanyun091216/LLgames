"""Pygbag 专用异步入口；桌面版继续使用 main.py。"""
import asyncio
import json
import platform
from time import perf_counter

import pygame

from . import config
from .config import FPS
from .render import RenderSurface


FRAME_TIMING_TOLERANCE = 0.002
DEFAULT_BROWSER_RENDER_DENSITY = 1.5


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


def _browser_size(window, viewport):
    density = getattr(window, 'ttgamesRenderDensity', None)
    if density not in (1, 1.5, 2):
        density = DEFAULT_BROWSER_RENDER_DENSITY
    return tuple(round(value * density) for value in viewport)


def _browser_frame_deadline(now, deadline, step):
    # Keep the cadence anchored when a browser callback arrives slightly early.
    if now < deadline - FRAME_TIMING_TOLERANCE:
        return None
    slots = max(1, int((now - deadline + FRAME_TIMING_TOLERANCE) / step) + 1)
    return deadline + slots * step


async def main():
    pygame.init()
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
    except Exception:
        pass
    browser_window = getattr(platform, 'window', None)
    viewport = None
    if browser_window is not None:
        viewport = (max(1, int(browser_window.innerWidth)), max(1, int(browser_window.innerHeight)))
        window_size = _browser_size(browser_window, viewport)
    else:
        try:
            window_size = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            window_size = (960, 720)
    window = pygame.display.set_mode(window_size, pygame.RESIZABLE)
    pygame.display.set_caption('海洋生物入侵 - Ocean Invaders')
    config.update_mobile_view(window.get_size(), viewport)

    from .game import Game, GameState
    from .asset_loader import image_asset
    from .background import background_art, make_background
    from .boss_skills import SKILL_IMAGES
    from .sounds import advance_music, make_sound, start_music

    start_music()
    game = Game()
    for filename in SKILL_IMAGES:
        image_asset(filename)
    for sound in ('boss_appear', 'kill', 'level_up'):
        make_sound(sound)
    warmed_background = None
    warmed_boss = None
    running = True
    draw_ui = getattr(browser_window, 'ttgamesDrawUI', None)
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
    next_frame = perf_counter()
    resize_events = (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED)
    step = 1 / FPS
    update_tolerance = FRAME_TIMING_TOLERANCE if browser_window is not None else 0.0
    campaign_seconds = 0.0
    accumulator = 0.0
    previous_frame = perf_counter()
    was_hidden = False
    advancing_states = (GameState.PLAYING, GameState.BOSS_FIGHT,
                        GameState.LEVEL_TRANSITION, GameState.VICTORY)

    while running:
        if browser_window is not None:
            now = perf_counter()
            deadline = _browser_frame_deadline(now, next_frame, step)
            if deadline is None:
                await asyncio.sleep(0)
                continue
            next_frame = deadline
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
        if browser_window is not None:
            new_viewport = (int(browser_window.innerWidth), int(browser_window.innerHeight))
            size = _browser_size(browser_window, new_viewport)
            if min(size) > 0 and (size != window_size or new_viewport != viewport):
                layout_changed = new_viewport != viewport
                viewport = new_viewport
                window_size = size
                window = pygame.display.set_mode(size, pygame.RESIZABLE)
                config.update_mobile_view(window.get_size(), viewport)
                if layout_changed:
                    game.resize_view(previous_area)
                resized = True
        elif any(event.type in resize_events for event in events):
            config.update_mobile_view(window.get_size())
            game.resize_view(previous_area)
            resized = True
        was_advancing = game.state in advancing_states
        running = game.handle_events(events)
        if game.difficulty is None:
            config.campaign_time_ms = None
            accumulator = 0.0
            game.update()
        else:
            if config.campaign_time_ms is None:
                campaign_seconds = pygame.time.get_ticks() / 1000
                config.campaign_time_ms = round(campaign_seconds * 1000)
            if not hidden and not resized and was_advancing and game.state in advancing_states:
                accumulator += elapsed
                while accumulator + update_tolerance >= step and game.state in advancing_states:
                    accumulator -= step
                    campaign_seconds += step
                    config.campaign_time_ms = round(campaign_seconds * 1000)
                    game.update()
            else:
                accumulator = 0.0
                if not hidden and game.state == GameState.INFINITE_COUNTDOWN:
                    game.update()
        if show_timings:
            draw_started = perf_counter()
        labels = [] if draw_ui else None
        level = game.infinite_background_level if game.infinite_mode else game.current_level
        use_hd = browser_window is not None and game.state in (GameState.PLAYING, GameState.BOSS_FIGHT)
        scene = config.SCR
        try:
            if use_hd:
                if foreground is None or foreground.get_size() != window.get_size():
                    foreground = pygame.Surface(window.get_size(), pygame.SRCALPHA)
                    rendered = None
                if rendered is None or resized:
                    rendered = RenderSurface(foreground, scene.get_size(), config.VIEW_SIZE,
                                             config.VIEW_OFFSET, track_damage=True)
                    previous_background = None
                config.SCR = rendered
                background = background_art(level, config.VIEW_SIZE)
                game.draw(labels, draw_background=background is None)
                if show_timings:
                    compose_started = perf_counter()
                if background is not None and background is previous_background and config.VIEW_OFFSET == (0, 0):
                    rendered.restore_background(window, background)
                elif background is not None:
                    if config.VIEW_SIZE != window.get_size():
                        window.fill(config.OCEAN_DEEP)
                    window.blit(background, config.VIEW_OFFSET)
                else:
                    window.fill(config.OCEAN_DEEP)
                rendered.composite_onto(window)
                previous_background = background if config.VIEW_SIZE == window.get_size() else None
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
        pygame.display.flip()
        if draw_ui:
            in_battle = game.state in (GameState.PLAYING, GameState.BOSS_FIGHT)
            if in_battle and not hidden:
                submitted_at = perf_counter()
                if fps_started is None:
                    fps_started = submitted_at
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
                labels.append((fps_label, 10, False, (180, 220, 232), 17, 97, 65, 13, 'left'))
                if timing_label:
                    labels.append((timing_label, 10, False, (180, 220, 232), 17, 111, 285, 13, 'left'))
            else:
                fps_started = None
                fps_frames = 0
                displayed_fps = None
                update_seconds = draw_seconds = compose_seconds = submit_seconds = 0.0
                timing_label = ''
            frame = (labels, config.SCREEN_WIDTH, config.SCREEN_HEIGHT, in_battle, game.state == GameState.PAUSED)
            if frame != previous_ui:
                draw_ui(json.dumps(labels, separators=(",", ":")), *frame[1:])
                previous_ui = frame
        next_index = level % len(config.LEVEL_CONFIGS)
        next_level = next_index + 1
        background_key = (next_level, scene.get_size(), config.VIEW_SIZE)
        # Let the victory cue play before decoding the next stage behind the clear panel.
        warm_campaign = (game.state == GameState.LEVEL_TRANSITION
                         and game.level_transition_end - config.game_ticks() <= 1100)
        warm_infinite = (game.infinite_mode and use_hd and game.bg_transition_prev is None)
        if (not hidden and game.difficulty and background_key != warmed_background
                and (warm_campaign or warm_infinite)):
            art_size = config.VIEW_SIZE if browser_window is not None else None
            make_background(next_level, art_size=art_size)
            warmed_background = background_key
        elif (not hidden and warm_campaign and warmed_boss != next_level
              and config.LEVEL_CONFIGS[next_index].get('boss_on_start')):
            boss = config.BOSS_DEFS[config.LEVEL_CONFIGS[next_index]['boss_idx']]
            image_asset(f'{boss.get("sprite_key", boss["key"])}.png')
            warmed_boss = next_level
        else:
            if browser_window is not None:
                # Keep track generation from consuming the next display slot.
                remaining = step - (perf_counter() - frame_time) - 0.001
                advance_music(max(0.00025, min(0.004, remaining)))
            else:
                advance_music()
        game.clock.tick(0 if browser_window is not None else FPS)
        await asyncio.sleep(0)

