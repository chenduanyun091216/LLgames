"""PC 和 Web 共用的异步游戏入口。"""
import asyncio
from functools import lru_cache
import json
import math
import platform
from time import perf_counter, sleep

import pygame

from . import asset_loader, config
from .config import FPS
from .render import RenderSurface, trim_transparent


FRAME_TIMING_TOLERANCE = 0.002
STANDARD_BROWSER_RENDER_DENSITY = 1.15
STANDARD_MAX_VIEW = (1800, 960)
HD_MAX_VIEW = (2560, 1200)
BROWSER_QUALITIES = (1.5, 1.75, 2)


def _load_desktop_level_art(level, size, variant, title_assets, effect_assets):
    from .background import load_panorama

    panorama = load_panorama(level, size, variant)
    images = asset_loader.prepare_images(title_assets, variant)
    for surface, _ in images.values():
        trim_transparent(surface)
    images.update(asset_loader.prepare_images(effect_assets, variant))
    return panorama, images


def _load_browser_level_art(level, size, variant, title_assets, effect_assets):
    from .background import load_panorama, make_background

    panorama = load_panorama(level, size, variant)
    yield panorama
    if panorama is not None:
        make_background(level, art_size=size, scrolling=True)
        yield
    for filename in title_assets:
        image = asset_loader.image_asset(filename)
        if image is not None:
            trim_transparent(image)
        yield
    for filename in effect_assets:
        asset_loader.image_asset(filename)
        yield


class _CampaignPreload:
    def __init__(self, submit):
        self.submit = submit
        self.key = None
        self.task = None
        self.panorama = None
        self.remaining = None

    def advance(self, level, size, *, browser_ready):
        from .abyss_bosses import BOSS_EFFECT_IMAGES
        from .background import make_background
        from .game import level_title_assets

        key = (level, size, asset_loader.image_variant())
        if self.key != key:
            if self.task is not None and not self.task.done():
                return None
            self.key = key
            self.panorama = None
            boss_key = config.BOSS_DEFS[config.LEVEL_CONFIGS[level - 1]['boss_idx']]['key']
            assets = level_title_assets(level), BOSS_EFFECT_IMAGES.get(boss_key, ())
            if self.submit is not None:
                self.task = self.submit(_load_desktop_level_art, *key, *assets)
            else:
                self.remaining = _load_browser_level_art(*key, *assets)
        if self.task is not None and self.task.done():
            self.panorama, images = self.task.result()
            asset_loader.remember_prepared_images(images)
            self.task = None
            if self.panorama is not None:
                make_background(level, art_size=size, scrolling=True)
        if browser_ready and self.remaining is not None:
            try:
                panorama = next(self.remaining)
            except StopIteration:
                self.remaining = None
            else:
                if panorama is not None:
                    self.panorama = panorama
        return self.panorama


def _desktop_skill_art():
    animations = ['player1_fisher_grenade', 'player_radiation_radiation_laser',
                  'player_radiation_dart_shield']
    for key, character in config.CHARACTER_DEFS.items():
        animations.extend(f'player_{key}_{skill.skill_type}' for skill in character.skills)
        animations.extend((f'player_{key}_run', f'player_{key}_back'))
    return ([f'players/player_{key}.png' for key in config.CHARACTER_DEFS]
            + [f'animations/players/anim_{name}.png' for name in animations])


def _new_enemy_action_art(enemies, prepared):
    keys = ({enemy.edef['key'] for enemy in enemies} & config.ENEMY_ACTION_KEYS) - prepared
    prepared.update(keys)
    return [f'animations/enemies/enemy_{key}_action.png' for key in sorted(keys)]


@lru_cache(maxsize=1)
def _shaded_level_background(background):
    image = background.copy()
    shade = pygame.Surface(image.get_size(), pygame.SRCALPHA)
    shade.fill((2, 16, 25, 100))
    image.blit(shade, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
    return image


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


def _desktop_render_size(view, quality):
    long, short = (3840, 2160) if quality == 4 else (2560, 1440)
    limit = (long, short) if view[0] >= view[1] else (short, long)
    scale = min(1, limit[0] / view[0], limit[1] / view[1])
    return tuple(max(1, round(length * scale)) for length in view)


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


async def main(transport=None, *, open_desktop_presenter=None, submit_preload=None):
    pygame.init()
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
    except Exception:
        pass
    browser_window = getattr(platform, 'window', None)
    asset_loader.pc_4k_assets = False
    viewport = None
    presenter = None
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
        asset_loader.web_hd_assets = False
        quality = 2
        flags = pygame.RESIZABLE | (pygame.HIDDEN if hide_startup else 0)
        if open_desktop_presenter is not None:
            presenter = open_desktop_presenter(flags)
        display = window = (pygame.display.get_surface() if presenter is not None else
                            pygame.display.set_mode((960, 720), flags))
    pygame.display.set_caption('海洋生物入侵 - Ocean Invaders')
    native_window = None
    fullscreen = False
    if browser_window is None:
        from pygame._sdl2 import Window
        # Let the window manager fit the frame to the usable desktop area.
        native_window = presenter.window if presenter is not None else Window.from_display_module()
        native_window.title = '海洋生物入侵 - Ocean Invaders · F11 全屏/窗口'
        if hide_startup:
            # On Windows, maximizing a hidden SDL window can show it before it has pixels.
            native_window.opacity = 0
            native_window.show()
        native_window.maximize()
        pygame.event.pump()
        pygame.key.stop_text_input()
        config.update_mobile_view(native_window.size if presenter is not None else window.get_size())
        native_view = config.VIEW_SIZE

    from .game import Game, GameState
    from .asset_loader import image_asset
    from .background import background_art, clear_background_cache, make_background
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
        game.arcade_lan = lan
    for filename in SKILL_IMAGES:
        image_asset(filename)
    for sound in ('boss_appear', 'boss_hit', 'kill', 'level_up', 'player_hit', 'fire_cast', 'ice_cast',
                  'water_cast', 'grenade', 'lightning', 'storm', 'laser', 'laser_hit', 'dart_cast', 'dart_burst'):
        make_sound(sound)
    campaign_preload = _CampaignPreload(submit_preload)
    combat_preload = None
    combat_variant = None
    prepared_enemy_actions = set()
    warmed_background = None
    running = True
    draw_ui = getattr(browser_window, 'ttgamesDrawUI', None)
    record_frame = getattr(browser_window, 'ttgamesRecordFrame', None)
    safe_area = None
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

    def present_frame(*, layers_drawn=False):
        nonlocal hide_startup
        if presenter is not None:
            presenter.present(window, pygame.Rect(config.VIEW_OFFSET, config.VIEW_SIZE),
                              pygame.Rect(config.VIEW_OFFSET, native_view), layers_drawn=layers_drawn)
        elif browser_window is None and window is not display:
            source = window.subsurface((config.VIEW_OFFSET, config.VIEW_SIZE))
            output = display.subsurface((config.VIEW_OFFSET, native_view))
            pygame.transform.smoothscale(source, native_view, output)
        elif window is not display:
            # Browser filtering can sample one texel beyond the visible scene.
            width, height = window.get_size()
            display.blit(display, (width, 0), (width - 1, 0, 1, height))
            display.blit(display, (0, height), (0, height - 1, width + 1, 1))
        if presenter is None:
            pygame.display.flip()
        if hide_startup:
            native_window.opacity = 1
            hide_startup = False

    def advance_frame_music(frame_started):
        # Synthesize music in the time left before the next frame.
        remaining = step - (perf_counter() - frame_started) - 0.001
        advance_music(max(0.00025, min(0.004, remaining)))

    def limit_frame_rate(frame_started):
        if presenter is not None:
            remaining = step - (perf_counter() - frame_started)
            if remaining > 0:
                sleep(remaining)
            game.clock.tick(0)
        else:
            game.clock.tick(0 if browser_window is not None else FPS)

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
            if presenter is not None and any(event.type == pygame.RENDER_DEVICE_RESET for event in events):
                presenter.reset_textures()
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
                hd_changed = hd_assets != asset_loader.web_hd_assets
                if hd_changed:
                    asset_loader.web_hd_assets = hd_assets
                    clear_background_cache()
                    warmed_background = None
                layout_changed = new_viewport != viewport
                viewport = new_viewport
                display, window = _browser_surfaces(viewport, quality, set_scene_size, display)
                if layout_changed:
                    if show_resolutions:
                        show_resolutions(*(value for q in BROWSER_QUALITIES for value in _browser_size(viewport, q)))
                    game.resize_view(previous_area)
                elif hd_changed:
                    game.bg = game._load_bg()
                resized = True
            new_safe_area = getattr(browser_window, 'ttgamesSafeArea', None) or '0,0,0,0'
            if resized or new_safe_area != safe_area:
                safe_area = new_safe_area
                left, top, right, bottom = map(int, str(safe_area).split(','))
                x_scale = config.SCREEN_WIDTH / viewport[0]
                y_scale = config.SCREEN_HEIGHT / viewport[1]
                config.WEB_SAFE_INSETS = (math.ceil(left * x_scale), math.ceil(top * y_scale),
                                          math.ceil(right * x_scale), math.ceil(bottom * y_scale))
        elif resized or any(event.type in resize_events for event in events):
            display = pygame.display.get_surface()
            config.update_mobile_view(native_window.size if presenter is not None else display.get_size())
            native_view = config.VIEW_SIZE
            resized = True
        if native_window is not None:
            quality_changed = quality != game.desktop_quality
            quality = game.desktop_quality
            # Keep window input in display pixels while drawing into the selected pixel budget.
            config.VIEW_SIZE = _desktop_render_size(native_view, quality)
            if quality_changed:
                asset_loader.pc_4k_assets = quality == 4
                clear_background_cache()
                game.title_image = image_asset('ui/title.png')
                warmed_background = None
            if resized:
                game.resize_view(previous_area)
            elif quality_changed:
                game.bg = game._load_bg()
            if quality_changed:
                resized = True
            if presenter is None and config.VIEW_SIZE == native_view:
                window = display
            else:
                width, height = config.VIEW_SIZE
                frame_size = width, height + config.VIEW_OFFSET[1]
                if window is display or window.get_size() != frame_size:
                    window = pygame.Surface(frame_size).convert(display)
        if submit_preload is not None and not hidden:
            variant = asset_loader.image_variant()
            if combat_preload is not None and combat_preload.done():
                images = combat_preload.result()
                if combat_variant == variant:
                    asset_loader.remember_prepared_images(images)
                combat_preload = None
            if combat_preload is None:
                if combat_variant != variant:
                    combat_variant = variant
                    prepared_enemy_actions.clear()
                    images = _desktop_skill_art()
                else:
                    images = []
                images.extend(_new_enemy_action_art(game.enemies, prepared_enemy_actions))
                if images:
                    combat_preload = submit_preload(asset_loader.prepare_images, images, variant)
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
            limit_frame_rate(frame_time)
            await asyncio.sleep(0)
            continue
        side_game = getattr(game, 'side_game', None)
        if side_game is not None:
            if any(event.type == pygame.QUIT for event in events):
                break
            if not side_game.frame(events, elapsed, hidden or resized, game.font_small,
                                   window.subsurface((config.VIEW_OFFSET, config.VIEW_SIZE))):
                game.side_game = None
                accumulator = 0.0
                game.mobile_controls.reset()
            if draw_ui:
                race_view = getattr(side_game.active, 'race', None) is not None
                arcade_ui = ([], config.SCREEN_WIDTH, config.SCREEN_HEIGHT, race_view, False, "", False)
                if previous_ui != arcade_ui:
                    draw_ui("[]",*arcade_ui[1:])
                    previous_ui=arcade_ui
            if not side_game.direct:
                scaled = _draw_scaled(window, scaled)
            present_frame()
            limit_frame_rate(frame_time)
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
                cutscene = 'opening' if game.state == GameState.OPENING else 'ending'
                cutscene_ui = ([], config.SCREEN_WIDTH, config.SCREEN_HEIGHT, False, False, cutscene)
                if draw_ui and cutscene_ui != previous_ui:
                    draw_ui('[]', *cutscene_ui[1:])
                    previous_ui = cutscene_ui
                if game.state == GameState.OPENING:
                    advance_frame_music(frame_time)
                limit_frame_rate(frame_time)
                await asyncio.sleep(0)
                continue
        if show_timings:
            draw_started = perf_counter()
        labels = [] if draw_ui else None
        level = game.infinite_background_level if game.infinite_mode else game.current_level
        use_hd = game.state in (GameState.MENU, GameState.DIFFICULTY_SELECT, GameState.PLAYING,
                                GameState.BOSS_FIGHT, GameState.LEVEL_TRANSITION)
        scene = config.SCR
        layers_drawn = False
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
                defer_fade = not game.exit_confirmation
                fade = game.level_fade_alpha() if defer_fade else 0
                intro_shade = (100 if presenter is not None and background is not None
                               and game.campaign_boss_intro_active() else 0)
                web_intro = (browser_window is not None and background is not None
                             and game.web_level_intro_active())
                if web_intro:
                    background = _shaded_level_background(background)
                game.draw(labels, draw_background=background is None, draw_level_fade=not defer_fade,
                          draw_intro_scrim=not (intro_shade or web_intro))
                if show_timings:
                    compose_started = perf_counter()
                if presenter is not None:
                    layers_drawn = presenter.draw_layers(background, rendered,
                                                         pygame.Rect(config.VIEW_OFFSET, config.VIEW_SIZE),
                                                         pygame.Rect(config.VIEW_OFFSET, native_view),
                                                         fade=fade, shade=intro_shade)
                if not layers_drawn:
                    if background is not None and background is previous_background:
                        rendered.restore_background(window, background, config.OCEAN_DEEP)
                    elif background is not None:
                        if config.VIEW_SIZE != window.get_size():
                            window.fill(config.OCEAN_DEEP)
                        window.blit(background, config.VIEW_OFFSET)
                    else:
                        window.fill(config.OCEAN_DEEP)
                    if intro_shade:
                        config.SCR = RenderSurface(window, scene.get_size(), config.VIEW_SIZE, config.VIEW_OFFSET)
                        game._draw_scrim(intro_shade)
                    blit_flags = 0 if native_window is not None and quality == 4 else pygame.BLEND_ALPHA_SDL2
                    rendered.composite_onto(window, blit_flags=blit_flags)
                    if fade:
                        brightness = 255 - fade
                        window.fill((brightness,) * 3, pygame.Rect(config.VIEW_OFFSET, config.VIEW_SIZE),
                                    special_flags=pygame.BLEND_RGB_MULT)
                previous_background = None if layers_drawn or fade or intro_shade else background
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
        present_frame(layers_drawn=layers_drawn)
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
        if not hidden and game.difficulty and game.state in advancing_states:
            if game.infinite_mode and use_hd and game.bg_transition_prev is None:
                next_level = level % len(config.INFINITE_BOSS_HP) + 1
                background_key = (next_level, scene.get_size(), config.VIEW_SIZE)
                if background_key != warmed_background:
                    make_background(next_level, art_size=config.VIEW_SIZE)
                    warmed_background = background_key
            elif not game.infinite_mode and level < len(config.LEVEL_CONFIGS):
                if game.web_level_intro_active():
                    # Let the new level card finish fading in before loading ahead.
                    browser_ready = game.level_title_until - game._level_title_ticks() < 2000
                else:
                    browser_ready = (game.state == GameState.LEVEL_TRANSITION
                                     or perf_counter() - frame_time < step / 2)
                panorama = campaign_preload.advance(level + 1, config.VIEW_SIZE, browser_ready=browser_ready)
                if presenter is not None and panorama is not None:
                    presenter.prepare_background(panorama)
        advance_frame_music(frame_time)
        limit_frame_rate(frame_time)
        if record_frame:
            record_frame('single' if game.state in advancing_states else 'idle', resized)
        await asyncio.sleep(0)

