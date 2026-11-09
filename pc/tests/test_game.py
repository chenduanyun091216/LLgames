import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game, GameState
from game_core.render import RenderSurface
from run_pc import main


class DesktopGameTests(unittest.TestCase):
    def test_desktop_shortcuts_match_battle_keycaps_and_pause_actions(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((960, 540))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)

        def press(key):
            event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0)
            self.assertTrue(game.handle_events([event]))

        press(pygame.K_4)
        self.assertTrue(game.infinite_mode)
        press(pygame.K_F2)
        self.assertEqual(game.player.current_weapon, 'rifle')
        press(pygame.K_1)
        self.assertEqual(game.player.character, 'ice')
        auto_fire = game.mobile_controls.auto_fire
        press(pygame.K_t)
        self.assertNotEqual(game.mobile_controls.auto_fire, auto_fire)

        with patch.object(game, '_draw_keycap', wraps=game._draw_keycap) as draw_keycap:
            game.draw()
        drawn_keys = {call.args[0] for call in draw_keycap.call_args_list}
        self.assertTrue({pygame.K_F2, pygame.K_1, pygame.K_t, pygame.K_b, pygame.K_h} <= drawn_keys)

        press(pygame.K_b)
        self.assertEqual(game.state, GameState.SHOP)
        press(pygame.K_b)
        self.assertEqual(game.state, GameState.PLAYING)
        press(pygame.K_h)
        self.assertEqual(game.state, GameState.PAUSED)
        press(pygame.K_RETURN)
        self.assertEqual(game.state, GameState.PLAYING)
        press(pygame.K_h)
        press(pygame.K_n)
        self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)

    def test_infinite_fps_is_inside_status_panel_beside_elapsed_time(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((960, 540))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)
        game._begin_infinite_run()

        with patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as draw_text:
            game.draw()
        fps = next(call for call in draw_text.call_args_list if call.args[0].startswith('FPS '))
        elapsed = next(call for call in draw_text.call_args_list if call.args[0].startswith('用时 '))
        fps_rect, elapsed_rect = fps.args[3], elapsed.args[3]
        self.assertTrue(pygame.Rect(8, 8, 162, 110).contains(fps_rect))
        self.assertEqual(fps_rect.centery, elapsed_rect.centery)
        self.assertGreater(fps_rect.left, elapsed_rect.right)
        self.assertEqual(fps.kwargs['align'], 'right')

    def test_desktop_battle_controls_draw_and_respond_to_mouse(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        window = pygame.display.set_mode((960, 540))
        config.update_mobile_view(window.get_size())
        game = Game(desktop_controls=True)
        game._start_game('medium')

        with patch.object(game.mobile_controls, 'draw', wraps=game.mobile_controls.draw) as draw, \
                patch.object(game, '_draw_button', wraps=game._draw_button) as draw_button:
            game.draw()
        draw.assert_called_once()
        self.assertEqual(draw_button.call_args_list[0].args[0], '-')

        def click(position, event_type=pygame.MOUSEBUTTONDOWN):
            x, y = position
            sx = config.VIEW_SIZE[0] / config.SCREEN_WIDTH
            sy = config.VIEW_SIZE[1] / config.SCREEN_HEIGHT
            pos = (round(x * sx + config.VIEW_OFFSET[0]), round(y * sy + config.VIEW_OFFSET[1]))
            game.handle_events([pygame.event.Event(event_type, button=1, pos=pos)])

        buttons = {action: center for action, center, *_ in game.mobile_controls._buttons(game)}
        self.assertTrue({'attack', 'skill1', 'skill2', 'laser', 'dart'}.isdisjoint(buttons))
        game.desktop_controls = False
        web_buttons = {action: center for action, center, *_ in game.mobile_controls._buttons(game)}
        game.desktop_controls = True
        for prefix in ('weapon:', 'character:'):
            desktop = [center for action, center in buttons.items() if action.startswith(prefix)]
            web = [center for action, center in web_buttons.items() if action.startswith(prefix)]
            self.assertEqual(len(desktop), 4)
            self.assertEqual(len({x for x, _ in desktop}), 1)
            self.assertEqual(len({x for x, _ in web}), 2)
            self.assertLess(desktop[1][1] - desktop[0][1], web[2][1] - web[0][1])
        left, health, right = game._hud_controls()
        click(right.center)
        self.assertEqual(game.current_level, 2)
        click(left.center)
        self.assertEqual(game.current_level, 1)
        click(health.center)
        self.assertGreater(game.player.rage_until, config.game_ticks())

        joystick = (40, config.SCREEN_HEIGHT - 70)
        click(joystick)
        click((joystick[0] + 30, joystick[1]), pygame.MOUSEMOTION)
        self.assertEqual(game.mobile_controls.axis, (0.0, 0.0))
        click(joystick, pygame.MOUSEBUTTONUP)
        self.assertEqual(game.mobile_controls.axis, (0.0, 0.0))

        self.assertFalse(game._mobile_fire_active())
        click(buttons['auto_fire'])
        self.assertTrue(game._mobile_fire_active())
        click(buttons['shop'])
        self.assertEqual(game.state, GameState.SHOP)
        click(game._mobile_shop_rects()['close'].center)
        self.assertEqual(game.state, GameState.PLAYING)
        click(buttons['pause'])
        self.assertEqual(game.state, GameState.PAUSED)
        click(game._choice_rects()[0].center)
        self.assertEqual(game.state, GameState.PLAYING)
        game.player.owned_weapons.append('rifle')
        game.last_switch_time = -10000
        click(buttons['weapon:rifle'])
        self.assertEqual(game.player.current_weapon, 'rifle')

    def test_desktop_skill_status_tracks_cooldown_and_character(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((960, 540))
        config.update_mobile_view((960, 540))
        game = Game(desktop_controls=True)
        game._start_game('medium')

        def labels_at(now):
            with patch.object(config, 'game_ticks', return_value=now), \
                    patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as draw_text:
                game.draw()
            return [call.args[0] for call in draw_text.call_args_list]

        self.assertIn('就绪', labels_at(1000))
        with patch.object(config, 'game_ticks', return_value=1000):
            game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k, mod=0)])
        end = game.player.skill_cooldowns['fisher_grenade']
        self.assertIn('1s', labels_at(end - 500))
        self.assertIn('就绪', labels_at(end))

        game.player.character = 'radiation'
        labels = labels_at(end)
        self.assertNotIn('手榴弹', labels)
        self.assertTrue({'闪电链', '磁暴', '辐射激光', '飞镖'}.issubset(labels))

    def test_keyboard_moves_and_fires_in_campaign_and_boss_fight(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((960, 540))
        config.update_mobile_view((960, 540))
        game = Game(desktop_controls=True)
        game._start_game('medium')
        for boss_fight in (False, True):
            with self.subTest(boss_fight=boss_fight):
                if boss_fight:
                    game._start_level(6)
                    self.assertEqual(game.state, GameState.BOSS_FIGHT)
                now = config.game_ticks() + 1000
                update = game._update_boss_fight if boss_fight else game._update_playing
                x, y = game.player.x, game.player.y
                with patch('pygame.key.get_pressed', return_value={pygame.K_w: True, pygame.K_a: True}), \
                        patch.object(game, '_shoot') as shoot:
                    update(now)
                    shoot.assert_not_called()
                self.assertLess(game.player.x, x)
                self.assertLess(game.player.y, y)
                x, y = game.player.x, game.player.y
                with patch('pygame.key.get_pressed', return_value={
                        pygame.K_j: True, pygame.K_s: True, pygame.K_d: True}), \
                        patch.object(game, '_shoot') as shoot:
                    update(now)
                    shoot.assert_called_once_with(now, game.player)
                self.assertGreater(game.player.x, x)
                self.assertGreater(game.player.y, y)

        game.player.character = 'radiation'
        game.handle_events([
            pygame.event.Event(pygame.KEYDOWN, key=key, mod=0)
            for key in (pygame.K_k, pygame.K_l, pygame.K_r)
        ])
        self.assertTrue(game.lightnings)
        self.assertTrue(game.magnetic_storms)
        self.assertTrue(game.dart_shields)

    def test_desktop_entry_starts_web_campaign_with_one_player(self):
        frames = []
        draw = Game.draw
        flip = pygame.display.flip

        def record_frame(game, *args, **kwargs):
            frames.append((game.state, len(game.players), game.desktop_controls))
            if game.state == GameState.DIFFICULTY_SELECT:
                self.assertIsInstance(config.SCR, RenderSurface)
            return draw(game, *args, **kwargs)

        def check_menu_frame():
            if frames[-1][0] == GameState.DIFFICULTY_SELECT:
                self.assertEqual(config.SCR.get_masks()[-1], 0)
                window = pygame.display.get_surface()
                # The white title must survive composition onto the native window.
                x, y = config.VIEW_OFFSET
                w = config.VIEW_SIZE[0]
                title = window.subsurface((x + w // 3, y + round(74 * config.VIEW_SCALE),
                                           w // 3, round(54 * config.VIEW_SCALE)))
                self.assertTrue(pygame.mask.from_threshold(title, (255, 255, 255), (15, 15, 15)).count())
            flip()

        events = [
            [],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0)],
            [pygame.event.Event(pygame.QUIT)],
        ]
        with patch.object(config, 'campaign_time_ms', None), \
                patch.object(Game, 'draw', record_frame), \
                patch('pygame.display.flip', side_effect=check_menu_frame), \
                patch('pygame.event.get', side_effect=events):
            main()

        self.assertEqual(frames[0][0], GameState.DIFFICULTY_SELECT)
        self.assertEqual(frames[1], (GameState.PLAYING, 1, True))
