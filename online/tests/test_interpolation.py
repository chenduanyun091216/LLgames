import unittest
from online.client.interpolation import PositionBuffer


def snapshot(t, match='one', paused=False):
    return {'match_id': match, 'orientation': 'landscape', 'phase': 'playing',
            'paused': paused, 'world': {'time_ms': t, 'game': {'current_level': 1, 'background_scroll_ticks': t * .06},
            'objects': [{'id': 1, 'fields': {'x': t * .1, 'y': 30}}]}}


class InterpolationTests(unittest.TestCase):
    def test_periodic_network_jitter_has_no_freeze_after_warmup(self):
        buffer = PositionBuffer()
        # Ordered WebSocket delivery: a delayed packet holds following packets.
        arrivals = []
        previous = 0
        for i in range(600):
            stamp = i * 1000 / 30
            latency = 75 if i % 30 == 0 else (i % 4) * 5
            previous = max(previous, stamp + latency)
            arrivals.append((previous, snapshot(stamp)))
        index = 0
        positions = []
        scrolls = []
        raw = []
        latest = 0
        for frame in range(1150):
            now = frame * 1000 / 60
            while index < len(arrivals) and arrivals[index][0] <= now:
                state = arrivals[index][1]
                buffer.push(state, now)
                latest = state['world']['time_ms'] * .1
                index += 1
            if now > 500:
                frame, scroll = buffer.sample(now)
                positions.append(frame[1][0])
                scrolls.append(scroll)
                raw.append(latest)
        deltas = [b-a for a,b in zip(positions, positions[1:])]
        self.assertTrue(all(1.5 < d < 1.9 for d in deltas), (min(deltas), max(deltas)))
        for first, last in zip(scrolls, scrolls[1:]):
            self.assertAlmostEqual(last - first, 1)
        self.assertGreater(sum(a == b for a,b in zip(raw, raw[1:])), 400)
        self.assertLessEqual(len(buffer.frames), 12)

    def test_long_outage_holds_and_reconnect_resets(self):
        buffer = PositionBuffer()
        buffer.push(snapshot(0), 0)
        buffer.push(snapshot(100), 100)
        self.assertEqual(buffer.sample(1000), ({1: (10, 30)}, 6))
        buffer.push(snapshot(1000), 1000)
        self.assertEqual(buffer.sample(1000), ({1: (100, 30)}, 60))
        buffer.push(snapshot(0, match='two'), 1010)
        self.assertEqual(buffer.sample(1010), ({1: (0, 30)}, 0))

    def test_pause_and_teleport_do_not_sweep(self):
        buffer = PositionBuffer()
        buffer.push(snapshot(0), 0)
        state = snapshot(33)
        state['world']['objects'][0]['fields']['x'] = 500
        buffer.push(state, 33)
        self.assertEqual(buffer.sample(116)[0][1][0], 500)
        buffer.push(snapshot(33, paused=True), 120)
        positions, scroll = buffer.sample(120)
        self.assertAlmostEqual(positions[1][0], 3.3)
        self.assertAlmostEqual(scroll, 33 * .06)
        self.assertEqual(buffer.sample(200)[1], scroll)

    def test_rolling_background_does_not_interpolate_across_a_level_change(self):
        for level_key in ('current_level', 'infinite_background_level'):
            with self.subTest(level_key=level_key):
                buffer = PositionBuffer()
                before, after = snapshot(100), snapshot(133)
                before['world']['game'][level_key] = 1
                after['world']['game'][level_key] = 2
                after['world']['game']['background_scroll_ticks'] = 7
                buffer.push(before, 100)
                buffer.push(after, 133)
                self.assertEqual(buffer.sample(133)[1], 7)

    def test_real_battle_renders_between_packets_without_changing_authority(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import pygame
        from game_core import config
        from game_core.background import draw_scrolling_background_art
        from game_core.entities import BossProjectile, Bullet
        from game_core.game import BACKGROUND_SCROLL_TICKS, Game
        from online.adapters.core_adapter import OnlineGame
        from online.adapters.presentation import Presentation
        from online.client.integrated import LAN
        pygame.init()
        window = pygame.display.set_mode((450, 970))
        host = OnlineGame(orientation='portrait')
        shot = BossProjectile(180, 160, 0, 3)
        host.enemy_projectiles = [shot]
        missile = Bullet(200, 320, config.WEAPON_DEFS['sniper'], 'sniper')
        missile.sniper_submissile = True
        host.bullets = [missile]
        config.update_mobile_view(window.get_size(), (390, 844))
        game = Game(web=True, mobile_web=True)
        sent = []
        client = LAN(SimpleNamespace(slot=1, error='', send=sent.append))
        client.render_density = 2
        drawn = []
        shot_motion = []
        missile_tail = []
        local_drawn = []
        original_draw = Presentation.draw
        def capture(presentation, *args, **kwargs):
            original_draw(presentation, *args, **kwargs)
            drawn.append(presentation.view.all_players[1].x)
            local_drawn.append(presentation.view.player.x)
            shown_shot = presentation.view.enemy_projectiles[0]
            shot_motion.append(shown_shot.y - shown_shot.prev_y)
            shown_missile = presentation.view.bullets[0]
            missile_tail.append(shown_missile.sniper_trail[-1][1] - shown_missile.y)
        with (patch.object(Presentation, 'draw', capture),
              patch('game_core.background.draw_scrolling_background_art', wraps=draw_scrolling_background_art) as background):
            for stamp in (0, 33, 67, 100, 133):
                host.background_scroll_ticks = round(stamp * .06)
                host.player.x = 100 + stamp * .1
                host.all_players[1].x = 100 + stamp * .1
                shot.y = 160 + stamp * .18
                shot.prev_y = shot.y - shot.speed
                missile.y = 320 - stamp * .42
                missile.sniper_trail = [(missile.x, missile.y + offset) for offset in (16, 9)]
                state = dict(host.snapshot(), match_id='one', mode='campaign')
                state['world']['time_ms'] = stamp
                with patch('online.client.integrated.monotonic', return_value=stamp / 1000):
                    client.battle(game, state, [], False, None, window)
            before = drawn[-1]
            with patch('online.client.integrated.monotonic', return_value=.150):
                client.battle(game, state, [], False, None, window)
            self.assertGreater(drawn[-1], before)
            self.assertAlmostEqual(drawn[-1], 105)
            self.assertAlmostEqual(shot_motion[-1], shot.speed)
            self.assertAlmostEqual(missile_tail[-1], 9)
            shown_shot = client.presentation.view.enemy_projectiles[0]
            self.assertEqual((shown_shot.y, shown_shot.prev_y), (shot.y, shot.prev_y))
            expected_scroll = 2 + (50 - 33) / (67 - 33) * 2
            self.assertAlmostEqual(background.call_args.args[-1] * BACKGROUND_SCROLL_TICKS, expected_scroll)
            self.assertEqual(client.presentation.view.background_scroll_ticks, 8)
            self.assertAlmostEqual(client.presentation.view.all_players[0].x, 113.3)
            self.assertNotIn(state["world"]["players"][0]["id"], client.render_positions)

            state['paused'] = False
            state['stage'] = 'playing'
            state['phase'] = 'playing'
            client.presentation.view.mobile_controls.axis = (1, 0)
            with patch('online.client.integrated.monotonic', return_value=.170):
                client.battle(game, state, [], False, None, window)
            self.assertEqual(sent[-1]['dx'], 1)
            client.presentation.view.mobile_controls.axis = (0, 0)
            with patch('online.client.integrated.monotonic', return_value=.190):
                client.battle(game, state, [], False, None, window)
            self.assertEqual(sent[-1]['dx'], 0)

            state = dict(state)
            state['players'][0].update(input_seq=-1, input_age_ms=0, move_speed=300)
            with patch('online.client.integrated.monotonic', return_value=.200):
                client.battle(game, state, [], False, None, window)
            client.presentation.view.mobile_controls.axis = (1, 0)
            with patch('online.client.integrated.monotonic', return_value=.200 + 1/60):
                client.battle(game, state, [], False, None, window)
            self.assertAlmostEqual(local_drawn[-1] - local_drawn[-2], 5)
            client.presentation.view.mobile_controls.axis = (0, 0)
            with patch('online.client.integrated.monotonic', return_value=.200 + 2/60):
                client.battle(game, state, [], False, None, window)
            self.assertEqual(local_drawn[-1], local_drawn[-2])
            self.assertAlmostEqual(client.presentation.view.player.x, 113.3)

    def test_web_water_badges_keep_their_css_size_and_do_not_overlap(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import pygame

        from game_core import config
        from game_core.game import Game
        from game_core.main import BROWSER_QUALITIES, _browser_size
        from online.adapters.core_adapter import OnlineGame
        from online.client.integrated import LAN

        pygame.init()
        host = OnlineGame(orientation='landscape')
        host.level_title_until = host.level_fade_in_until = 0
        for player in host.all_players:
            player.x, player.y = 450, 500
            player.water_boost_until = player.water_haste_until = config.game_ticks() + 4000
        state = dict(host.snapshot(), match_id='buffs', mode='campaign')
        viewport = (844, 390)
        client = LAN(SimpleNamespace(slot=1, error='', send=lambda message: None))
        client.browser_viewport = viewport
        game = Game(web=True, mobile_web=True)
        for quality in BROWSER_QUALITIES:
            with self.subTest(quality=quality):
                window = pygame.display.set_mode(_browser_size(viewport, quality))
                config.update_mobile_view(window.get_size(), viewport)
                client.render_density = quality
                with patch('game_core.background.draw_scrolling_background_art', return_value=False) as blend:
                    client.battle(game, state, [], False, None, window)
                    self.assertEqual(blend.called, quality == 2)
                buffs = [label for label in client.ui_labels if label[0].startswith(('水增益', '水急速'))]
                self.assertEqual(len(buffs), 4)
                self.assertTrue(any(label[0].startswith('FPS ') for label in client.ui_labels))
                self.assertTrue(any(label[0].startswith('第 1 关') for label in client.ui_labels))
                rectangles = []
                for _, size, bold, _, x, y, width, height, align in buffs:
                    self.assertAlmostEqual(size * viewport[1] / config.SCREEN_HEIGHT, 12, delta=.25)
                    self.assertTrue(bold)
                    self.assertEqual(align, 'center')
                    rect = pygame.Rect(x, y, width, height)
                    self.assertEqual(rect.collidelist(rectangles), -1)
                    rectangles.append(rect)
        paused = dict(state, paused=True, pause_reason='manual_pause')
        client.battle(game, paused, [], False, None, window)
        self.assertEqual(client.ui_labels, ())
