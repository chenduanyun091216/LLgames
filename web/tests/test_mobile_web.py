import math
import os
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.game import Game, GameState
from game_core.entities import Bullet, Enemy, GiftBox, SkillProjectile
from game_core.entities import MagneticStorm, SpinningDarts
from game_core import sounds


class MobileWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((480, 850), pygame.RESIZABLE)

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        config.update_mobile_view((480, 850))
        self.game = Game()

    def test_hud_does_not_overlap_touch_buttons(self):
        for size in ((360, 640), (390, 844), (844, 390), (1280, 720)):
            config.update_mobile_view(size)
            for rect in self.game._hud_controls():
                for action, (x, y), radius, _, _ in self.game.mobile_controls._buttons(self.game):
                    nearest_x = max(rect.left, min(x, rect.right))
                    nearest_y = max(rect.top, min(y, rect.bottom))
                    self.assertGreater((x - nearest_x) ** 2 + (y - nearest_y) ** 2,
                                       radius ** 2, (size, action, rect))

    def test_hud_level_buttons_switch_infinite_chapter(self):
        game = self.game
        game._start_infinite_game()
        game._trigger_infinite_boss()
        left, _, right = game._hud_controls()
        self.assertTrue(game._handle_hud_click(right.center))
        self.assertEqual((game.chapter, game.infinite_background_level, game.infinite_boss_index), (2, 2, 1))
        self.assertIsNone(game.boss)
        self.assertEqual(game.state, GameState.PLAYING)
        game._trigger_infinite_boss()
        self.assertEqual(game.boss.bdef['name'], config.BOSS_DEFS[1]['name'])
        self.assertTrue(game._handle_hud_click(left.center))
        self.assertEqual((game.chapter, game.infinite_background_level, game.infinite_boss_index), (1, 1, 0))
        game._handle_hud_click(left.center)
        self.assertEqual(game.chapter, 1)
        game._begin_infinite_run(8)
        game._handle_hud_click(right.center)
        self.assertEqual((game.chapter, game.infinite_background_level, game.infinite_boss_index), (9, 1, 8))

    def test_hud_level_buttons_switch_campaign_level(self):
        game = self.game
        game._start_game('easy')
        _, _, right = game._hud_controls()
        game._handle_hud_click(right.center)
        self.assertEqual(game.current_level, 2)
        self.assertEqual(game.level_enemy_defs, config.get_level_enemy_defs(config.LEVEL_CONFIGS[1]))

    def test_campaign_boss_health_and_final_victory_timeout(self):
        game = self.game
        game._start_game('easy')
        for level, hp in ((7, 118), (8, 131)):
            game.boss = None
            game._start_level(level)
            game._trigger_boss()
            self.assertEqual(game.boss.max_hp, hp)
        with patch('pygame.time.get_ticks', return_value=1000):
            game._kill_boss()
            labels = []
            game.draw(labels)
            self.assertIn('恭喜完成全部关卡！', [row[0] for row in labels])
        with patch('pygame.time.get_ticks', return_value=4999):
            game.update()
            self.assertEqual(game.state, GameState.VICTORY)
        with patch('pygame.time.get_ticks', return_value=5000):
            game.update()
            self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)
        game._start_infinite_game()
        game.infinite_boss_index = 7
        game._trigger_infinite_boss()
        self.assertEqual(game.boss.max_hp, 192)
        game._kill_boss()
        self.assertEqual(game.state, GameState.PLAYING)

    def test_easy_campaign_reduces_late_boss_pressure(self):
        game = self.game
        game._start_game('easy')
        game._start_level(7)
        game._trigger_boss()
        niu = game.boss
        self.assertEqual(niu.attack_interval, 6800)
        niu.laser_active_until = 2000
        self.assertEqual(len(niu.death_laser_rects(1000)), 2)
        niu.laser_active_until = 0
        niu.y = 60
        with patch('pygame.time.get_ticks', return_value=1000), patch('game_core.entities.random.randint', return_value=7000):
            niu.update()
        self.assertEqual(niu.next_death_laser_time, 15000)
        with patch('game_core.special_bosses.random.choice', return_value='axes'):
            game._add_boss_projectiles(niu.attack(1000, game.player.x))
        self.assertEqual([projectile.damage for projectile in game.boss_projectiles], [1, 1])
        game.boss = None
        game._start_level(8)
        game._trigger_boss()
        zong = game.boss
        left, right = zong.hitboxes()
        zong.hit_by('pistol', 1, source='bullet', hit_rect=left)
        zong.hit_by('pistol', 1, source='skill', hit_rect=right)
        self.assertEqual(zong.body_hp, [64.5, 64.5])
        game._start_infinite_game()
        game.infinite_boss_index = 6
        game._trigger_infinite_boss()
        self.assertEqual(len(game.boss.death_laser_xs()), 2)
        self.assertEqual(game.boss.max_hp, 170)

    def test_player_can_reach_bottom_and_fire_without_clipping_the_shot(self):
        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game._start_game('medium')
            hud = game._hud_controls()
            game.player.move(0, 1000)
            self.assertEqual(game.player.rect().bottom, config.SCREEN_HEIGHT - 8)
            self.assertEqual(game._hud_controls(), hud)
            self.assertEqual((hud[1].height, hud[1].bottom), (28, config.SCREEN_HEIGHT - 15))
            self.assertTrue(game.player.rect().colliderect(hud[1]))
            bullet = game.player.shoot(1000)[0]
            bullet.update()
            self.assertFalse(bullet.is_offscreen())
            gap = math.ceil(config.WEAPON_DEFS['pistol'].fire_rate / .70)
            self.assertFalse(game.player.can_shoot(1000 + gap - 1))
            self.assertTrue(game.player.can_shoot(1000 + gap))

    def test_boss_laser_hitboxes_reach_screen_bottom(self):
        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game._start_game('medium')
            for definition in config.BOSS_DEFS:
                boss = game._make_boss(definition)
                boss.y = 55
                boss.laser_active_until = 2000
                if boss.can_laser():
                    boss.entered = True
                    old_x = boss.x
                    with patch('game_core.config.game_ticks', return_value=1000):
                        boss.update()
                    self.assertNotEqual(boss.x, old_x)
                    self.assertTrue(all(rect.bottom == config.SCREEN_HEIGHT
                                        for rect in boss.death_laser_rects(1000)))

    def test_campaign_warning_accounts_for_slow_and_freeze_in_both_orientations(self):
        game = self.game
        for size in ((844, 390), (390, 844)):
            with self.subTest(size=size):
                config.update_mobile_view(size)
                game.reset()
                game._start_game('medium')
                now = 2000
                zone = pygame.Rect(config.GAME_AREA_LEFT, 0, 365, config.SCREEN_HEIGHT)
                normal = game._hazard_warning_ms([zone], now)
                game.player.niu_slow_until = now + 2000
                game.player.niu_freeze_until = now + 500
                slowed = game._hazard_warning_ms([zone], now)
                self.assertIsNotNone(normal)
                self.assertGreater(slowed, normal)
                self.assertEqual(game._hazard_warning_ms([], now), 1000)
                full = pygame.Rect(config.GAME_AREA_LEFT, 0,
                                   config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT,
                                   config.SCREEN_HEIGHT)
                self.assertIsNone(game._hazard_warning_ms([full], now))

    def test_campaign_laser_warning_updates_when_armed(self):
        game = self.game
        game._start_game('medium')
        game._start_level(2)
        game._trigger_boss()
        boss = game.boss
        now = 3000
        boss.entered = True
        boss.y = 60
        boss.next_death_laser_time = now
        game.player.niu_freeze_until = now + 1500
        with patch('pygame.time.get_ticks', return_value=now), patch('game_core.entities.random.random', return_value=0):
            game.update()
        self.assertEqual(boss.laser_warning_start, now)
        self.assertGreater(boss.laser_warning_ms, 1500)
        with patch('pygame.time.get_ticks', return_value=now + 1000):
            boss.update()
        self.assertEqual(boss.laser_active_until, 0)
        with patch('pygame.time.get_ticks', return_value=now + boss.laser_warning_ms):
            boss.update()
        self.assertGreater(boss.laser_active_until, now + boss.laser_warning_ms)

    def test_campaign_niu_vortex_preserves_duration_after_warning_extension(self):
        game = self.game
        game._start_game('hard')
        game._start_level(7)
        game._trigger_boss()
        boss = game.boss
        now = 4000
        game.player.y = config.GAME_AREA_BOTTOM * 0.62
        game.player.niu_freeze_until = now + 1200
        with patch('game_core.special_bosses.random.choice', return_value='vortex'):
            boss.attack(now, game.player.x)
        original_warning = boss.vortex_warning_until
        game._extend_ground_warning(boss, now)
        self.assertGreater(boss.vortex_warning_until, original_warning)
        self.assertEqual(boss.vortex_until - boss.vortex_warning_until, 2600)
        self.assertEqual(boss.vortex_next_tick, boss.vortex_warning_until)
        self.assertEqual(boss.next_hazard_time - boss.vortex_until, 1400)

    def test_infinite_boss_growth_and_death_progress(self):
        game = self.game
        game._start_infinite_game()
        for defeated, hp, interval in ((0, 30, 4400), (8, 36, 4180), (16, 42, 3960),
                                       (48, 66, 3080), (56, 66, 3080)):
            with self.subTest(defeated=defeated):
                game.infinite_boss_index = defeated
                game._trigger_infinite_boss()
                self.assertEqual(game.infinite_boss_index, defeated)
                self.assertEqual(game.boss.max_hp, hp)
                self.assertEqual(game.boss.attack_interval, interval)
                game._kill_boss()
                self.assertEqual(game.infinite_boss_index, defeated + 1)
                game._kill_boss()
                self.assertEqual(game.infinite_boss_index, defeated + 1)

    def test_infinite_density_tracks_bosses_and_ignores_elapsed_time(self):
        game = self.game
        game._start_infinite_game()
        for defeated, expected in ((0, 4), (2, 5), (8, 8), (20, 14), (48, 14)):
            game.infinite_boss_index = defeated
            self.assertEqual(game._infinite_density(10000000), expected)

    def test_campaign_laser_hit_and_shop_return(self):
        game = self.game
        game._start_game('medium')
        game._start_level(2)
        game._trigger_boss()
        boss = game.boss
        game._handle_mobile_action('shop')
        game._handle_shop_click(*game._mobile_shop_rects()['close'].center)
        self.assertEqual(game.state, GameState.BOSS_FIGHT)
        self.assertIs(game.boss, boss)
        boss.entered = True
        boss.speed = 0
        boss.y = 60
        boss.laser_active_until = 3000
        for now in range(1000, 2800, 17):
            with patch('pygame.time.get_ticks', return_value=now):
                game.update()
        self.assertEqual(game.player_hp, 4)

    def test_campaign_leak_and_weapon_damage_share_the_same_health(self):
        game = self.game
        game._start_game('medium')
        game.spawn_enemy()
        first = game.enemies[0]
        self.assertEqual(first.edef['key'], 'lobster')
        first.hit_by('pistol', 2)
        first.hit_by('rifle', 1.35)
        self.assertTrue(first.is_killed('rifle'))
        game.spawn_enemy()
        for enemy in game.enemies[:]:
            self.assertFalse(game._resolve_leak(enemy, 1000))
        self.assertEqual(game.player_hp, 4)
        self.assertEqual(game.leak_count, 2)
        self.assertEqual(game.lives, 3)
        self.assertEqual(game.enemies, [])

    def test_custom_defaults_and_boss_health_multiplier(self):
        game = self.game
        game._start_custom_game()
        self.assertEqual(game.spawn_interval, 2400)
        self.assertEqual(game._bullet_cost('sniper'), 0)
        game._start_level(7)
        game._trigger_boss()
        self.assertEqual(game.boss.max_hp, 156)
        game.reset()
        game.custom_values['boss_hp_mult'] *= 1.2
        game._start_custom_game()
        game._start_level(8)
        game._trigger_boss()
        self.assertEqual(game.boss.max_hp, 209)

    def test_three_lives_then_paid_revive(self):
        game = self.game
        game.player.gold = 100
        for remaining in (2, 1):
            game._player_defeated('测试')
            self.assertEqual(game.lives, remaining)
            self.assertEqual(game.player_hp, game.max_player_hp)
            self.assertEqual(game.player.gold, 100)
        game._player_defeated('测试')
        self.assertEqual(game.state, GameState.PAID_REVIVE)
        game.draw()
        game._handle_click(game._choice_rects()[0].center)
        self.assertEqual(game.player.gold, 15)
        self.assertEqual(game.lives, 1)
        game._player_defeated('测试')
        self.assertEqual(game.state, GameState.GAME_OVER)

    def test_declining_revive_does_not_spend_gold_and_infinite_keeps_continue(self):
        game = self.game
        game.lives = 1
        game.player.gold = 100
        game._player_defeated('测试')
        game._handle_click(game._choice_rects()[1].center)
        self.assertEqual(game.state, GameState.GAME_OVER)
        self.assertEqual(game.player.gold, 100)

        game.infinite_mode = True
        game._player_defeated('测试')
        self.assertEqual(game.state, GameState.INFINITE_CONTINUE)

    def test_terminal_rage_movement_speed_and_expiry(self):
        game = self.game
        player = game.player
        for infinite in (False, True):
            with self.subTest(infinite=infinite):
                game.infinite_mode = infinite
                player.rage_until = 0
                normal_speed = game._player_speed(player, 1000)
                with patch('game_core.config.game_ticks', return_value=1000):
                    game._activate_rage()
                self.assertAlmostEqual(game._player_speed(player, 20999), normal_speed * 1.6)
                self.assertAlmostEqual(game._player_speed(player, 21000), normal_speed)

    def test_web_speed_and_pause_exit(self):
        game = self.game
        for infinite in (True, False):
            game.infinite_mode = infinite
            self.assertAlmostEqual(game._player_speed(game.player, 0), 5.2)
        game.state = GameState.PAUSED
        game.draw()
        game._handle_click(game._choice_rects()[1].center)
        self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)
        self.assertEqual(game.lives, 3)

    def test_touch_generated_mouse_does_not_toggle_auto_fire(self):
        self.game.state = GameState.PLAYING
        center = next(row[1] for row in self.game.mobile_controls._buttons(self.game)
                      if row[0] == 'auto_fire')
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                   pos=center, button=1, touch=True)
        self.game.handle_events([event])
        self.assertTrue(self.game.mobile_controls.auto_fire)

    def test_restart_restores_auto_fire_and_releases_movement(self):
        self.game.mobile_controls.auto_fire = False
        self.game.mobile_controls.axis = (1, 0)
        self.game.reset()
        self.assertTrue(self.game.mobile_controls.auto_fire)
        self.assertEqual(self.game.mobile_controls.axis, (0, 0))

    def test_short_joystick_drag_reaches_full_speed_and_release_stops(self):
        controls = self.game.mobile_controls
        for size in ((844, 390), (480, 850)):
            config.update_mobile_view(size)
            controls.joystick_id = 7
            controls.joystick_origin = (100, 300)
            controls._update_axis((124, 300))
            self.assertEqual(controls.axis, (1, 0))
            before = self.game.player.x
            self.game._move_player_from_controls(self.game.player, {}, pygame.time.get_ticks())
            self.assertGreater(self.game.player.x, before)
            controls.release(7)
            before = self.game.player.x
            self.game._move_player_from_controls(self.game.player, {}, pygame.time.get_ticks())
            self.assertEqual(self.game.player.x, before)

    def test_difficulty_starts_single_player_without_mode_select(self):
        _key, rect = self.game._mobile_difficulty_rects()[0]
        self.game._handle_click(rect.center)
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertEqual(len(self.game.players), 1)
        self.game.draw()

    def test_difficulty_cards_and_custom_button_stay_separate(self):
        for size in ((844, 390), (932, 393), (390, 844)):
            with self.subTest(size=size):
                config.update_mobile_view(size)
                button = self.game._mobile_custom_button()
                cards = [rect for _, rect in self.game._mobile_difficulty_rects()]
                self.assertTrue(all(rect.bottom <= button.top for rect in cards))
                self.assertTrue(all(rect.collidelist(cards[index + 1:]) == -1
                                    for index, rect in enumerate(cards)))

    def test_modal_labels_do_not_reveal_covered_hud(self):
        self.game._start_game('easy')
        self.game.state = GameState.PLAYING
        labels = []
        self.game.draw(labels)
        self.assertTrue(any(row[0] == '射击' for row in labels))
        level_title = config.LEVEL_CONFIGS[0]['title']
        self.assertIn(level_title, {row[0] for row in labels})
        self.game.state = GameState.PAUSED
        labels = []
        self.game.draw(labels)
        self.assertIn('继续游戏', {row[0] for row in labels})
        self.assertNotIn(level_title, {row[0] for row in labels})
        self.assertFalse(any(row[0].startswith('HP') or row[0] == '射击' for row in labels))

    def test_custom_difficulty_controls_fit_portrait_and_update_values(self):
        rows = self.game._mobile_custom_rows()
        actions = self.game._mobile_custom_action_rects()
        self.assertEqual(len(rows), len(self.game.custom_fields))
        self.assertTrue(all(row.bottom < actions['reset'].top for _, row, _, _ in rows))
        key, _row, _minus, plus = rows[0]
        before = self.game.custom_values[key]
        self.game._click_custom_difficulty(*plus.center)
        self.assertNotEqual(self.game.custom_values[key], before)
        self.game.state = GameState.CUSTOM_DIFFICULTY
        self.game.draw()

    def test_mobile_actions_switch_owned_character(self):
        self.game.player.owned_characters.append('ice')
        self.game._handle_mobile_action('character:ice')
        self.assertEqual(self.game.player.character, 'ice')

    def test_mobile_controls_have_attack_and_auto_fire_toggle(self):
        actions = [row[0] for row in self.game.mobile_controls._buttons(self.game)]
        self.assertIn('attack', actions)
        self.assertIn('auto_fire', actions)
        self.assertTrue(self.game.mobile_controls.auto_fire)

    def test_mobile_web_fires_without_attack_touch(self):
        now = pygame.time.get_ticks()
        self.game.last_spawn_time = now
        self.game.spawn_interval = 10**9
        with patch.object(self.game.player, 'can_shoot', return_value=True), \
                patch.object(self.game, '_shoot') as shoot:
            self.game._update_playing(now)
        shoot.assert_called_once_with(now, self.game.player)

    def test_mobile_manual_fire_works_when_auto_fire_is_off(self):
        now = pygame.time.get_ticks()
        self.game._handle_mobile_action('auto_fire')
        self.assertFalse(self.game.mobile_controls.auto_fire)
        self.game.mobile_controls.fingers[7] = 'attack'
        self.game.last_spawn_time = now
        self.game.spawn_interval = 10**9
        with patch.object(self.game.player, 'can_shoot', return_value=True), \
                patch.object(self.game, '_shoot') as shoot:
            self.game._update_playing(now)
        shoot.assert_called_once_with(now, self.game.player)

    def test_touch_can_hold_fire_and_toggle_auto_fire(self):
        controls = self.game.mobile_controls
        buttons = {row[0]: row[1] for row in controls._buttons(self.game)}
        attack_x, attack_y = buttons['attack']
        down = pygame.event.Event(pygame.FINGERDOWN, {
            'finger_id': 11, 'x': attack_x / config.SCREEN_WIDTH,
            'y': attack_y / config.SCREEN_HEIGHT,
        })
        up = pygame.event.Event(pygame.FINGERUP, {
            'finger_id': 11, 'x': attack_x / config.SCREEN_WIDTH,
            'y': attack_y / config.SCREEN_HEIGHT,
        })
        self.assertEqual(controls.handle_touch(down, self.game), 'attack')
        self.assertTrue(controls.is_pressed('attack'))
        controls.handle_touch(up, self.game)
        self.assertFalse(controls.is_pressed('attack'))

        auto_x, auto_y = buttons['auto_fire']
        toggle = pygame.event.Event(pygame.FINGERDOWN, {
            'finger_id': 12, 'x': auto_x / config.SCREEN_WIDTH,
            'y': auto_y / config.SCREEN_HEIGHT,
        })
        self.assertEqual(controls.handle_touch(toggle, self.game), 'auto_fire')
        self.game._handle_mobile_action('auto_fire')
        self.assertFalse(controls.auto_fire)

    def test_mobile_skill_arc_and_buttons_fit_without_overlap(self):
        self.game.player.character = 'radiation'
        for window_size in ((844, 390), (1280, 720), (480, 850), (390, 844)):
            config.update_mobile_view(window_size)
            rows = self.game.mobile_controls._buttons(self.game)
            buttons = {action: (center, radius) for action, center, radius, _label, _color in rows}
            attack_center, attack_radius = buttons['attack']
            auto_center, auto_radius = buttons['auto_fire']
            self.assertLess(auto_center[0], attack_center[0])
            self.assertGreater(auto_center[1], attack_center[1])
            skill1, skill2 = (buttons[action][0] for action in ('skill1', 'skill2'))
            self.assertLess(skill1[0], skill2[0])
            self.assertLess(skill2[0], attack_center[0])
            self.assertLess(skill2[1], skill1[1])
            self.assertLess(skill1[1], attack_center[1])
            self.assertAlmostEqual(pygame.Vector2(attack_center).distance_to(skill1),
                                   pygame.Vector2(attack_center).distance_to(skill2), delta=1)
            self.assertGreater(
                pygame.Vector2(attack_center).distance_to(auto_center),
                attack_radius + auto_radius + 16,
            )
            for action, (center, radius) in buttons.items():
                self.assertGreaterEqual(center[0] - radius, 0, action)
                self.assertLessEqual(center[0] + radius, config.SCREEN_WIDTH, action)
                self.assertGreaterEqual(center[1] - radius, 0, action)
                self.assertLessEqual(center[1] + radius, config.SCREEN_HEIGHT, action)
            for action in ('skill1', 'skill2'):
                center, radius = buttons[action]
                for primary_center, primary_radius in (buttons['attack'], buttons['auto_fire']):
                    self.assertGreater(
                        pygame.Vector2(center).distance_to(primary_center),
                        radius + primary_radius + 16,
                    )
            for index, button in enumerate(rows):
                for other in rows[index + 1:]:
                    distance = pygame.Vector2(button[1]).distance_to(other[1])
                    self.assertGreater(
                        distance, button[2] + other[2] + 16,
                        f'{window_size}: {button[0]} overlaps {other[0]}',
                    )

    def test_campaign_tracks_have_distinct_tempos_and_clean_loop_seams(self):
        lengths = set()
        for level in range(1, 9):
            generator = sounds._music_pcm(level, False, False, 0)
            with self.assertRaises(StopIteration) as finished:
                while True:
                    next(generator)
            pcm = finished.exception.value
            lengths.add(len(pcm))
            self.assertEqual(pcm[:2], b'\0\0')
            self.assertEqual(pcm[-2:], b'\0\0')
        self.assertEqual(len(lengths), 8)

    def test_music_can_start_and_switch_when_effect_channels_are_full(self):
        pygame.mixer.stop()
        pcm = b'\0\0' * sounds.SAMPLE_RATE
        effect = pygame.mixer.Sound(buffer=pcm)

        def track(*args):
            yield
            return pcm

        try:
            with patch.object(sounds, '_pending_music', None), \
                    patch.object(sounds, '_requested_music', None), \
                    patch.object(sounds, '_music_pcm', side_effect=track):
                self.assertTrue(sounds.ensure_audio())
                while effect.play(loops=-1) is not None:
                    pass
                channel = pygame.mixer.Channel(0)
                self.assertIs(channel.get_sound(), None)
                sounds.start_music(1)
                sounds.advance_music()
                previous = channel.get_sound()
                self.assertIsNotNone(previous)
                sounds.start_music(1, boss=True)
                sounds.advance_music()
                self.assertIsNotNone(channel.get_sound())
                self.assertIsNot(channel.get_sound(), previous)
                self.assertEqual(previous.get_num_channels(), 0)
        finally:
            pygame.mixer.stop()

    def test_web_audio_mixer_can_retry_after_initialization_failure(self):
        with patch.object(sounds.pygame.mixer, 'get_init', side_effect=[None, (22050, -16, 1)]), \
                patch.object(sounds.pygame.mixer, 'init') as init_mixer:
            self.assertTrue(sounds.ensure_audio())
        init_mixer.assert_called_once_with(frequency=sounds.SAMPLE_RATE, size=-16, channels=1)

    def test_web_sound_does_not_cache_until_audio_is_available(self):
        key = 'shoot_pistol'
        sounds._sound_cache.pop(key, None)
        with patch.object(sounds, 'ensure_audio', return_value=False):
            self.assertIsNone(sounds.make_sound(key))
        self.assertNotIn(key, sounds._sound_cache)

    def test_mobile_joystick_moves_player_during_boss_fight(self):
        self.game.boss = SimpleNamespace(update=lambda: None, signature=None)
        self.game.mobile_controls.axis = (1.0, 0.0)
        previous_x = self.game.player.x
        now = pygame.time.get_ticks()
        with patch.object(self.game, '_settle_boss_if_killed', return_value=False), \
                patch.object(self.game, '_damage_player_on_contacts', return_value=True):
            self.game._update_boss_fight(now)
        self.assertGreater(self.game.player.x, previous_x)

    def test_touch_joystick_tracks_and_resets_finger(self):
        down = pygame.event.Event(pygame.FINGERDOWN, {'finger_id': 7, 'x': 0.2, 'y': 0.8})
        move = pygame.event.Event(pygame.FINGERMOTION, {'finger_id': 7, 'x': 0.35, 'y': 0.8})
        up = pygame.event.Event(pygame.FINGERUP, {'finger_id': 7, 'x': 0.35, 'y': 0.8})
        self.game.mobile_controls.handle_touch(down, self.game)
        self.game.mobile_controls.handle_touch(move, self.game)
        self.assertGreater(self.game.mobile_controls.axis[0], 0.9)
        self.game.mobile_controls.handle_touch(up, self.game)
        self.assertEqual(self.game.mobile_controls.axis, (0.0, 0.0))

    def test_skill_button_shows_remaining_cooldown(self):
        game = self.game
        game._start_game('easy')
        controls = game.mobile_controls
        game.player.skill_cooldowns['fisher_grenade'] = 3500
        game._ui_labels = []
        with patch('game_core.config.game_ticks', return_value=1000):
            controls.draw(pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), game)
        countdown = next(row for row in game._ui_labels if row[0] == '3s')
        self.assertEqual(countdown[1:3], (16, True))

    def test_weapon_bullets_have_colored_round_heads_and_short_trails(self):
        for weapon, angle in (('pistol', 0), ('rifle', 0), ('sniper', 0), ('shotgun', 0), ('shotgun', 16)):
            with self.subTest(weapon=weapon, angle=angle):
                bullet = Bullet(48, 40, config.WEAPON_DEFS[weapon], weapon, angle=angle)
                surface = pygame.Surface((96, 96), pygame.SRCALPHA)
                bullet.draw(surface)
                self.assertEqual(surface.get_at((48, 40)), (*bullet.color, 255))
                self.assertEqual(surface.get_at((48, 30)).a, 0)
                self.assertTrue(any(0 < surface.get_at((x, 52)).a < 255 for x in range(40, 53)))

    def test_fire_and_ice_projectile_centers_are_opaque(self):
        for kind, ptype in (('fire', 'fireball'), ('ice', 'ice_ball')):
            bullet = Bullet(48, 40, config.WEAPON_DEFS['pistol'], 'pistol')
            bullet.gift_kind = kind
            bullet.radius = 6
            for projectile in (bullet, SkillProjectile(48, 40, 0, 8, ptype)):
                with self.subTest(kind=kind, projectile=type(projectile)):
                    surface = pygame.Surface((96, 96), pygame.SRCALPHA)
                    projectile.draw(surface)
                    self.assertEqual(surface.get_at((48, 40)).a, 255)
                    if projectile is bullet:
                        self.assertEqual(surface.get_at((61, 40)).a, 255)

    def test_background_preparation_reuses_hd_art_for_the_game_surface(self):
        from game_core import background
        logical_size = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        view_size = (logical_size[0] * 2, logical_size[1] * 2)
        art = pygame.Surface(view_size)
        with patch.object(background, '_bg_surf', {}), \
                patch.object(background, 'background_art', return_value=art) as load_art:
            prepared = background.make_background(2, art_size=view_size)
            self.assertEqual(prepared.get_size(), logical_size)
            self.assertIs(background.make_background(2), prepared)
            load_art.assert_called_once_with(2, view_size)

    def test_fire_skill_interleaves_two_long_rockets_and_splash_hits_each_target_once(self):
        game = self.game
        game._start_game('easy')
        game._activate_skill(config.CHARACTER_DEFS['fire'].skills[1], game.player)
        shots = game.skill_projectiles
        self.assertEqual([shot.ptype for shot in shots].count('fireball'), 3)
        rockets = [shot for shot in shots if shot.ptype == 'fire_rocket']
        self.assertEqual([shot.angle for shot in shots if shot.ptype == 'fireball'], [-32, 0, 32])
        self.assertEqual([shot.angle for shot in rockets], [-16, 16])
        self.assertEqual([shot.ptype for shot in sorted(shots, key=lambda shot: shot.angle)],
                         ['fireball', 'fire_rocket', 'fireball', 'fire_rocket', 'fireball'])
        origin = (shots[0].x, shots[0].y)
        for shot in shots:
            for _ in range(20):
                shot.update()
            self.assertAlmostEqual(math.hypot(shot.x - origin[0], shot.y - origin[1]), 160)

        rocket = rockets[0]
        surface = pygame.Surface((96, 96), pygame.SRCALPHA)
        SkillProjectile(48, 48, 0, rocket.speed, 'fire_rocket').draw(surface)
        self.assertGreaterEqual(surface.get_bounding_rect().height, 47)
        direct, nearby, distant = [Enemy(config.ENEMY_DEFS[0]) for _ in range(3)]
        for enemy, offset in zip((direct, nearby, distant), (0, 36, 115)):
            enemy.x = rocket.x + offset
            enemy.y = rocket.y - enemy.h // 2
        game.enemies = [direct, nearby, distant]
        with patch.object(direct, 'hit_by') as direct_hit, \
                patch.object(nearby, 'hit_by') as nearby_hit, \
                patch.object(distant, 'hit_by') as distant_hit:
            game._explode_fire_rocket(rocket, config.game_ticks())
        direct_hit.assert_called_once_with('sniper', rocket.damage)
        nearby_hit.assert_called_once_with('sniper', rocket.damage)
        distant_hit.assert_not_called()
        self.assertEqual(game.explosions[-1].element, 'fire')

    def test_skill_cooldown_ring_tracks_remaining_fraction(self):
        game = self.game
        game._start_game('easy')
        game._start_skill_effect(game.player, 'fisher_grenade', 4000, 0, now=1000)
        for now, fraction in ((2000, 0.75), (4000, 0.25), (5000, 0)):
            with patch('game_core.config.game_ticks', return_value=now), patch('game_core.render.Draw.arc') as arc:
                game.mobile_controls.draw(config.SCR, game)
                if fraction:
                    arc.assert_called_once()
                    _, _, _, start, end, _ = arc.call_args.args
                    self.assertAlmostEqual((end - start) / math.tau, fraction)
                else:
                    arc.assert_not_called()

    def test_element_impacts_draw_distinct_shapes_without_using_randomness(self):
        self.game._spawn_hit_effect(48, 48, (255, 190, 105), element='ice')
        impact = self.game.explosions[-1]
        for _ in range(5):
            impact.update()
        rng = random.getstate()
        rendered = set()
        for element in ('ice', 'water', 'fire', 'radiation'):
            surface = pygame.Surface((96, 96), pygame.SRCALPHA)
            impact.element = element
            impact.draw(surface)
            rendered.add(pygame.image.tostring(surface, 'RGBA'))
        self.assertEqual(len(rendered), 4)
        self.assertEqual(random.getstate(), rng)

    def test_projectile_trails_follow_flight_direction(self):
        from game_core.entities import Bullet, BossProjectile
        player = Bullet(60, 60, config.WEAPON_DEFS['pistol'], 'pistol')
        enemy = BossProjectile(60, 60, 0, 3)
        for projectile, behind, ahead in ((player, (60, 75), (60, 45)),
                                          (enemy, (60, 45), (60, 75))):
            surface = pygame.Surface((120, 120), pygame.SRCALPHA)
            projectile.draw(surface)
            self.assertGreater(surface.get_at(behind).a, 0)
            self.assertEqual(surface.get_at(ahead).a, 0)
        surface = pygame.Surface((120, 120), pygame.SRCALPHA)
        enemy.draw(surface)
        self.assertGreater(surface.get_at((60, 51)).a, surface.get_at((66, 51)).a)
        for projectile in (Bullet(60, 60, config.WEAPON_DEFS['pistol'], 'pistol', angle=90),
                           BossProjectile(60, 60, 90, 3)):
            surface = pygame.Surface((120, 120), pygame.SRCALPHA)
            projectile.draw(surface)
            self.assertGreater(surface.get_at((45, 60)).a, 0)
            self.assertEqual(surface.get_at((75, 60)).a, 0)

    def test_player_bullet_speed_is_reduced(self):
        from game_core.entities import Bullet
        bullet = Bullet(100, 100, config.WEAPON_DEFS['pistol'], 'pistol')
        self.assertEqual(bullet.speed, config.WEAPON_DEFS['pistol'].speed * 0.8)

    def test_weapon_touch_switches_directly_without_stealing_joystick(self):
        game = self.game
        controls = game.mobile_controls
        game._start_game('easy')
        game.player.owned_weapons.append('sniper')
        weapons = {action: (center, radius) for action, center, radius, _, _ in controls._buttons(game)
                   if action.startswith('weapon:')}
        self.assertEqual(list(weapons), ['weapon:pistol', 'weapon:rifle', 'weapon:shotgun', 'weapon:sniper'])
        center, radius = weapons['weapon:sniper']
        stick = (96, config.SCREEN_HEIGHT - 108)
        self.assertGreater(stick[1] - 64 - (center[1] + radius), 24)
        with patch.object(controls, 'event_position', side_effect=[stick, center, center, weapons['weapon:rifle'][0]]):
            controls.handle_touch(pygame.event.Event(pygame.FINGERDOWN, finger_id=1), game)
            self.assertIsNone(controls.handle_touch(pygame.event.Event(pygame.FINGERMOTION, finger_id=1), game))
            with patch('pygame.time.get_ticks', return_value=1000):
                game._handle_mobile_action(controls.handle_touch(
                    pygame.event.Event(pygame.FINGERDOWN, finger_id=2), game))
            self.assertEqual(game.player.current_weapon, 'sniper')
            self.assertEqual(controls.joystick_id, 1)
            with patch('pygame.time.get_ticks', return_value=2000):
                game._handle_mobile_action(controls.handle_touch(
                    pygame.event.Event(pygame.FINGERDOWN, finger_id=3), game))
            self.assertEqual(game.player.current_weapon, 'sniper')

    def test_joystick_reaches_full_speed_within_visible_thumb_travel(self):
        config.update_mobile_view((844, 390))
        controls = self.game.mobile_controls
        controls.joystick_origin = (480, 300)
        controls._update_axis((495, 300))
        self.assertGreaterEqual(controls.axis[0], 0.4)
        controls._update_axis((510, 300))
        self.assertEqual(controls.axis[0], 1.0)

    def test_landscape_gift_boxes_spawn_inside_center_half(self):
        config.update_mobile_view((844, 390))
        left, right = config.SCREEN_WIDTH // 4, config.SCREEN_WIDTH * 3 // 4
        expected_x_bounds = (left + GiftBox.SIZE // 2, right - GiftBox.SIZE // 2)
        with patch('game_core.entities.random.uniform', return_value=config.SCREEN_WIDTH // 2) as choose_x:
            box = GiftBox()
        choose_x.assert_called_once_with(*expected_x_bounds)
        self.assertGreaterEqual(box.rect().left, left)
        self.assertLessEqual(box.rect().right, right)

    def test_second_touch_does_not_take_over_active_joystick(self):
        controls = self.game.mobile_controls
        first_down = pygame.event.Event(pygame.FINGERDOWN, {'finger_id': 7, 'x': 0.4, 'y': 0.9})
        first_move = pygame.event.Event(pygame.FINGERMOTION, {'finger_id': 7, 'x': 0.55, 'y': 0.9})
        second_down = pygame.event.Event(pygame.FINGERDOWN, {'finger_id': 8, 'x': 0.4, 'y': 0.8})
        second_up = pygame.event.Event(pygame.FINGERUP, {'finger_id': 8, 'x': 0.4, 'y': 0.8})
        controls.handle_touch(first_down, self.game)
        controls.handle_touch(first_move, self.game)
        controls.handle_touch(second_down, self.game)
        controls.handle_touch(second_up, self.game)
        self.assertEqual(controls.joystick_id, 7)
        self.assertGreater(controls.axis[0], 0.9)

    def test_window_focus_loss_releases_mobile_inputs(self):
        controls = self.game.mobile_controls
        controls.fingers[7] = 'joystick'
        controls.joystick_id = 7
        controls.joystick_origin = (96, 680)
        controls.axis = (1.0, 0.0)
        event = pygame.event.Event(pygame.WINDOWFOCUSLOST)
        self.game.handle_events([event])
        self.assertEqual(controls.fingers, {})
        self.assertIsNone(controls.joystick_id)
        self.assertEqual(controls.axis, (0.0, 0.0))

    def test_touch_takes_over_synthetic_mouse_joystick(self):
        self.game.state = GameState.PLAYING
        events = [
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': (192, 765), 'button': 1}),
            pygame.event.Event(pygame.MOUSEMOTION, {
                'pos': (264, 765), 'rel': (72, 0), 'buttons': (1, 0, 0),
            }),
            pygame.event.Event(pygame.FINGERDOWN, {'finger_id': 7, 'x': 0.4, 'y': 0.9}),
            pygame.event.Event(pygame.FINGERMOTION, {'finger_id': 7, 'x': 0.55, 'y': 0.9}),
            pygame.event.Event(pygame.FINGERUP, {'finger_id': 7, 'x': 0.55, 'y': 0.9}),
            pygame.event.Event(pygame.MOUSEBUTTONUP, {'pos': (264, 765), 'button': 1}),
        ]
        self.game.handle_events(events)
        self.assertIsNone(self.game.mobile_controls.joystick_id)
        self.assertEqual(self.game.mobile_controls.axis, (0.0, 0.0))

    def test_mouse_release_clears_joystick_after_state_change(self):
        self.game.state = GameState.PLAYING
        controls = self.game.mobile_controls
        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': (192, 765), 'button': 1})
        move = pygame.event.Event(pygame.MOUSEMOTION, {
            'pos': (264, 765), 'rel': (72, 0), 'buttons': (1, 0, 0),
        })
        controls.handle_mouse(down, self.game)
        controls.handle_mouse(move, self.game)
        self.game.state = GameState.PAUSED
        self.game._last_touch_event = pygame.time.get_ticks()
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, {'pos': (264, 765), 'button': 1})
        self.game.handle_events([up])
        self.assertIsNone(controls.joystick_id)
        self.assertEqual(controls.axis, (0.0, 0.0))

    def test_shop_cards_and_close_button_fit_portrait(self):
        self.game.state = GameState.SHOP
        self.game.draw()
        rects = self.game._mobile_shop_rects()
        self.assertTrue(all(
            rect.x >= 0 and rect.y >= 0 and
            rect.right <= config.SCREEN_WIDTH and rect.bottom <= config.SCREEN_HEIGHT
            for rect in rects.values()
        ))
        self.game._handle_shop_click(*rects['close'].center)
        self.assertEqual(self.game.state, GameState.PLAYING)

    def test_landscape_view_keeps_mobile_screens_in_bounds(self):
        config.update_mobile_view((844, 390))
        self.game.resize_view()
        self.assertEqual(config.SCREEN_WIDTH, 960)
        self.assertLess(config.SCREEN_HEIGHT, 500)
        self.game.state = GameState.DIFFICULTY_SELECT
        self.game.draw()
        self.game.state = GameState.CUSTOM_DIFFICULTY
        self.game.draw()
        self.game.state = GameState.SHOP
        self.game.draw()
        self.assertTrue(all(
            rect.bottom <= config.SCREEN_HEIGHT
            for rect in self.game._mobile_shop_rects().values()
        ))

    def test_landscape_confines_player_enemies_and_boss_to_center_half(self):
        config.update_mobile_view((844, 390))
        self.game.resize_view()
        left, right = config.SCREEN_WIDTH // 4, config.SCREEN_WIDTH * 3 // 4

        self.game.player.move(-config.SCREEN_WIDTH, 0)
        player_rect = self.game.player.rect()
        self.assertGreaterEqual(player_rect.left, left)
        self.assertLessEqual(player_rect.right, right)

        enemy = Enemy(config.ENEMY_DEFS[0])
        self.assertGreaterEqual(enemy.rect().left, left)
        self.assertLessEqual(enemy.rect().right, right)

        self.game.difficulty = config.DIFFICULTY_PRESETS['medium']
        boss = self.game._make_boss(config.BOSS_DEFS[5])
        boss.movement_timer = 78.5
        boss._move(1.0)
        self.assertGreaterEqual(boss.rect().left, left)
        self.assertLessEqual(boss.rect().right, right)

    def test_landscape_rotation_repositions_existing_combatants(self):
        enemy = Enemy(config.ENEMY_DEFS[0])
        enemy.x = 80
        self.game.enemies = [enemy]
        self.game.difficulty = config.DIFFICULTY_PRESETS['medium']
        self.game.boss = self.game._make_boss(config.BOSS_DEFS[5])
        self.game.boss.x = 100

        config.update_mobile_view((844, 390))
        self.game.resize_view()
        left, right = config.SCREEN_WIDTH // 4, config.SCREEN_WIDTH * 3 // 4
        self.assertGreaterEqual(enemy.rect().left, left)
        self.assertLessEqual(enemy.rect().right, right)
        self.assertGreaterEqual(self.game.boss.rect().left, left)
        self.assertLessEqual(self.game.boss.rect().right, right)

    def test_landscape_keeps_large_and_growing_monsters_inside_center_half(self):
        config.update_mobile_view((844, 390))
        left, right = config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT

        large_def = next(edef for edef in config.ENEMY_DEFS if edef['is_large'])
        large_enemy = Enemy(large_def)
        self.assertGreaterEqual(large_enemy.rect().left, left)
        self.assertLessEqual(large_enemy.rect().right, right)

        zongzong_def = next(edef for edef in config.ENEMY_DEFS if edef.get('zongzong'))
        zongzong = Enemy(zongzong_def)
        zongzong.x = right - zongzong.w // 2
        zongzong.hit_by('pistol', amount=1000)
        self.assertGreaterEqual(zongzong.rect().left, left)
        self.assertLessEqual(zongzong.rect().right, right)

    def test_radiation_skills_fit_short_landscape_battlefield(self):
        config.update_mobile_view((844, 390))
        center = (config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)
        owner = SimpleNamespace(x=center[0], y=center[1] + self.game.player.SIZE[1] // 2 - 12)
        with patch('game_core.config.game_ticks', return_value=0):
            storm = MagneticStorm(*center)
            shield = SpinningDarts(owner)
            for effect in (storm, shield):
                surface = pygame.Surface(config.SCR.get_size(), pygame.SRCALPHA)
                effect.draw(surface)
                bounds = surface.get_bounding_rect()
                self.assertGreater(bounds.width, 0)
                self.assertLessEqual(bounds.width, 365)
                self.assertLessEqual(bounds.height, config.GAME_AREA_BOTTOM)
        self.assertTrue(storm.contains_point(center[0] + 130, center[1]))
        self.assertFalse(storm.contains_point(center[0] + 150, center[1]))
        first_disc, _ = next(shield.dart_positions(0))
        self.assertTrue(shield.hits(pygame.Rect(*first_disc, 1, 1), 0))
        self.assertFalse(shield.hits(pygame.Rect(first_disc[0] + 28, first_disc[1], 1, 1), 0))

    def test_landscape_magnetic_storm_keeps_pushed_monster_inside_center_half(self):
        config.update_mobile_view((844, 390))
        enemy = Enemy(config.ENEMY_DEFS[0])
        enemy.x = config.GAME_AREA_RIGHT - enemy.w // 2 - 1
        enemy.y = 100
        self.game.enemies = [enemy]
        storm = SimpleNamespace(x=config.GAME_AREA_RIGHT - 10, y=130, radius=100)

        self.game._explode_magnetic_storm(storm)

        self.assertLessEqual(enemy.rect().right, config.GAME_AREA_RIGHT)

    def test_signature_opening_precedes_normal_attack_cooldown(self):
        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            for infinite in (False, True):
                for index in range(6):
                    with self.subTest(size=size, infinite=infinite, boss=index):
                        if infinite:
                            game._start_infinite_game()
                            game.infinite_boss_index = index
                            game._trigger_infinite_boss()
                        else:
                            game._start_game('easy')
                            game._start_level(index + 1)
                            game._trigger_boss()
                        boss = game.boss
                        entrance_ms = math.ceil(math.ceil((60 - boss.y) / 1.5) * 1000 / config.FPS)
                        now = 1000 + entrance_ms
                        boss.y = 59
                        with patch('game_core.config.game_ticks', return_value=now), \
                                patch.object(boss, 'should_attack', return_value=False):
                            game._update_boss_fight(now)
                        self.assertFalse(boss.signature_opening_pending)
                        self.assertIsNotNone(boss.signature)
                        self.assertLessEqual(boss.signature.impact_at - 1000, 5000)
                        game._update_boss_signature(boss.signature.end_at)
                        self.assertFalse(game._try_boss_signature(now + 5000))

    def test_six_bosses_have_animated_attacks_and_two_keep_original_moves(self):
        from game_core.boss_skills import SIGNATURES

        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game._start_game('easy')
            for definition in config.BOSS_DEFS:
                with self.subTest(size=size, boss=definition['key']):
                    boss = game.boss = game._make_boss(definition)
                    boss.y = 55
                    boss.signature_attacks = 3
                    if definition['key'] in ('boss_niu', 'boss_zongzong'):
                        self.assertFalse(game._try_boss_signature(1000))
                        self.assertIsNone(boss.signature)
                        continue
                    self.assertTrue(game._try_boss_signature(1000))
                    signature = boss.signature
                    self.assertEqual(signature.name, SIGNATURES[definition['key']][0])
                    self.assertGreaterEqual(signature.impact_at, 2200)
                    surface = pygame.Surface(config.SCR.get_size(), pygame.SRCALPHA)
                    for age in (-200, 240):
                        surface.fill((0, 0, 0, 0))
                        signature.move(boss, signature.impact_at + age)
                        signature.draw(surface, boss, signature.impact_at + age)
                        signature.draw_bite(surface, boss)
                        self.assertTrue(surface.get_bounding_rect())
                    game._update_boss_signature(signature.end_at)
                    self.assertIsNone(boss.signature)

    def test_tridents_use_distinct_transparent_sprites(self):
        from game_core.boss_skills import _trident_image

        gold, red = (_trident_image(color) for color in (False, True))
        for sprite in (gold, red):
            self.assertIsNotNone(sprite)
            self.assertGreater(sprite.get_height(), sprite.get_width())
            self.assertLess(sprite.get_at((0, 0)).a, 255)
        self.assertNotEqual(pygame.image.tostring(gold, 'RGBA'), pygame.image.tostring(red, 'RGBA'))

    def test_claws_bubbles_and_tridents_damage_at_their_visible_impact(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        for boss_index, age, shapes in ((0, 300, '_claws'), (1, 860, '_bubbles'),
                                        (3, 120, '_tridents')):
            with self.subTest(boss_index=boss_index):
                boss = game._make_boss(config.BOSS_DEFS[boss_index])
                boss.y = 55
                attack = BossSignature(boss, game.player, 1000, 1000)
                x, y, _ = getattr(attack, shapes)(age)[0]
                if boss_index == 3:
                    y += 17
                rect = pygame.Rect(round(x), round(y), 1, 1)
                self.assertFalse(attack.hit(boss, rect, attack.impact_at - 1))
                if boss_index == 1:
                    self.assertFalse(attack.hit(boss, rect, attack.impact_at + age - 1))
                self.assertTrue(attack.hit(boss, rect, attack.impact_at + age))
                self.assertFalse(attack.hit(boss, rect, attack.impact_at + age + 1))
                if boss_index == 0:
                    self.assertGreater(attack._claws(990)[0][1] - 145, config.SCREEN_HEIGHT)

    def test_boss_fire_burns_for_four_seconds_with_one_hit_per_second(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[4])
        attack = BossSignature(boss, game.player, 1000, 1000)
        x, y, _ = attack.fire_patches[0]
        inside = pygame.Rect(round(x), round(y), 1, 1)
        outside = pygame.Rect(0, 0, 1, 1)
        self.assertEqual(len(attack.fire_patches), 3)
        self.assertEqual(attack.end_at - attack.impact_at, 4000)
        self.assertFalse(attack.hit(boss, inside, 1999))
        for now in range(2000, 6000, 1000):
            self.assertFalse(attack.hit(boss, outside, now))
            self.assertTrue(attack.hit(boss, inside, now))
            self.assertFalse(attack.hit(boss, inside, now + 100))
        self.assertFalse(attack.hit(boss, inside, 6000))
        delayed = BossSignature(boss, game.player, 1000, 1000)
        x, y, _ = delayed.fire_patches[0]
        inside = pygame.Rect(round(x), round(y), 1, 1)
        self.assertTrue(delayed.hit(boss, inside, 2999))
        self.assertFalse(delayed.hit(boss, inside, 3000))

    def test_octopus_lashes_three_times_and_abyss_bite_is_lethal(self):
        from game_core.boss_skills import BossSignature, LASH_MS

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[2])
        boss.y = 55
        attack = BossSignature(boss, game.player, 1000, 1000)
        for lash in range(3):
            age = 240 + lash * LASH_MS
            x, y, _ = next(attack._tentacles(boss, age))[-1]
            rect = pygame.Rect(round(x), round(y), 1, 1)
            self.assertTrue(attack.hit(boss, rect, attack.impact_at + age))
            self.assertFalse(attack.hit(boss, rect, attack.impact_at + age))
        self.assertFalse(attack.hit(boss, rect, attack.end_at))

        boss = game.boss = game._make_boss(config.BOSS_DEFS[5])
        boss.x, boss.y = game.player.x, 55
        original = boss.x, boss.y
        boss.signature = attack = BossSignature(boss, game.player, 1000, 1000)
        with patch.object(game, '_player_is_invincible', return_value=False), \
                patch.object(game, '_damage_player', return_value=True) as damage:
            for now in range(2000, 3400, 17):
                if game._update_boss_signature(now):
                    break
            damage.assert_called_once_with(now, game.player_hp, '被深渊封潮击败！')
        self.assertGreater(boss.y, original[1])
        game._update_boss_signature(attack.end_at)
        self.assertEqual((boss.x, boss.y), original)
        self.assertIsNone(boss.signature)
        boss.signature = BossSignature(boss, game.player, 1000, 1000)
        game.player.move(110, 0)
        with patch.object(game, '_player_is_invincible', return_value=False), \
                patch.object(game, '_damage_player') as damage:
            for now in range(2000, boss.signature.end_at, 17):
                game._update_boss_signature(now)
            damage.assert_not_called()

    def test_abyss_bite_exits_below_and_returns_from_above(self):
        from game_core.boss_skills import BossSignature, CHASE_MS

        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game._start_game('medium')
            boss = game.boss = game._make_boss(config.BOSS_DEFS[5])
            boss.y = 55
            origin = (boss.x, boss.y)
            boss.signature = attack = BossSignature(boss, game.player, 1000, 1000)
            attack.move(boss, attack.impact_at)
            reentry = attack.impact_at + CHASE_MS
            attack.move(boss, reentry - 16)
            self.assertGreater(boss.y - boss.h * .22, config.SCREEN_HEIGHT)
            attack.move(boss, reentry)
            self.assertLess(boss.rect().bottom, 0)
            self.assertFalse(attack.chasing)
            self.assertFalse(attack.hit(boss, boss.rect(), reentry))
            attack.move(boss, reentry + 350)
            self.assertGreater(boss.rect().bottom, 0)
            self.assertLess(boss.y, origin[1])
            game._update_boss_signature(attack.end_at)
            self.assertEqual((boss.x, boss.y), origin)

    def test_boss_name_and_hp_use_visible_hd_labels(self):
        game = self.game
        game._start_game('medium')
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game.resize_view()
            for level in (2, 8):
                game._start_level(level)
                game._trigger_boss()
                labels = []
                game.draw(labels)
                name = game.boss.name if level == 2 else '小粽粽 × 2'
                hp = f'{int(game.boss.hp)} / {int(game.boss.max_hp)}'
                name_rect, hp_rect = (pygame.Rect(next(label[4:8] for label in labels if label[0] == text))
                                      for text in (name, hp))
                self.assertTrue(pygame.Rect(0, 0, config.SCREEN_WIDTH, 48).contains(name_rect))
                self.assertTrue(pygame.Rect(0, 0, config.SCREEN_WIDTH, 48).contains(hp_rect))
                self.assertLessEqual(name_rect.bottom, hp_rect.top)

    def test_hd_controls_match_native_at_one_to_one_scale(self):
        from game_core.render import RenderSurface

        self.game._start_game('medium')
        for size in ((480, 850), (844, 390)):
            config.update_mobile_view(size)
            self.game.resize_view()
            logical_size = config.SCR.get_size()
            expected = pygame.Surface(logical_size, pygame.SRCALPHA)
            actual = expected.copy()
            controls = self.game.mobile_controls
            controls.joystick_origin = (55, config.SCREEN_HEIGHT - 60)
            controls.axis = (-0.8, 0.6)
            controls.draw(expected, self.game)
            controls.draw(RenderSurface(actual, logical_size, logical_size, (0, 0)), self.game)
            self.assertEqual(pygame.image.tobytes(actual, 'RGBA'), pygame.image.tobytes(expected, 'RGBA'))

    def test_hd_battle_draws_at_physical_resolution_without_moving_hitboxes(self):
        from game_core.render import RenderSurface, Draw

        self.game._start_game('medium')
        for size in ((780, 1688), (1688, 780)):
            config.update_mobile_view(size)
            self.game.resize_view()
            for level in (2, 7, 8):
                self.game._start_level(level)
                self.game._trigger_boss()
                self.game.boss.y = 55
                self.game.boss_projectiles.extend(self.game.boss.attack(1000, self.game.player.x))
                scene = config.SCR
                target = pygame.Surface(size, pygame.SRCALPHA)
                config.SCR = RenderSurface(target, scene.get_size(), config.VIEW_SIZE,
                                           config.VIEW_OFFSET, track_damage=True)
                hitbox = self.game.boss.rect()
                try:
                    self.game.draw([], draw_background=False)
                    Draw.circle(config.SCR, (255, 255, 255), (30, 30), 10)
                    self.assertEqual(target.get_at(config.SCR.point((30, 30))), (255, 255, 255, 255))
                    self.assertEqual(self.game.boss.rect(), hitbox)
                    actual = pygame.Surface(size)
                    actual.fill((15, 40, 80))
                    expected = actual.copy()
                    expected.blit(target, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
                    config.SCR.composite_onto(actual)
                    self.assertEqual(pygame.image.tobytes(actual, 'RGB'),
                                     pygame.image.tobytes(expected, 'RGB'))
                    self.assertFalse(target.get_bounding_rect())
                    background = pygame.Surface(size)
                    background.fill((15, 40, 80))
                    config.SCR.restore_background(actual, background)
                    self.assertEqual(pygame.image.tobytes(actual, 'RGB'),
                                     pygame.image.tobytes(background, 'RGB'))
                finally:
                    config.SCR = scene

    def test_hd_projectiles_and_skills_render_without_changing_hitboxes(self):
        from game_core.entities import BossProjectile, Bullet, FireWall, IceFloor, MagneticStorm, RadiationLaser
        from game_core.render import RenderSurface
        from game_core.special_bosses import CrescentWave, ReturningAxe, ZongBomb

        for size in ((780, 1688), (1688, 780)):
            config.update_mobile_view(size)
            self.game._start_game('medium')
            boss = self.game._make_boss(config.BOSS_DEFS[6])
            x, y = config.SCREEN_WIDTH // 2, config.GAME_AREA_BOTTOM // 2
            boss.x, boss.y = x, y
            effects = [
                Bullet(x, y, config.WEAPON_DEFS['pistol'], 'pistol'), BossProjectile(x, y, 15, 3),
                FireWall(x, y), IceFloor(x, y), MagneticStorm(x, y), RadiationLaser(self.game.player),
                CrescentWave(x, y, 70), ReturningAxe(boss, 1, x, True), ZongBomb(x, y, 0, 3, bomb=True),
            ]
            target = pygame.Surface(size, pygame.SRCALPHA)
            surface = RenderSurface(target, config.SCR.get_size(), config.VIEW_SIZE, config.VIEW_OFFSET)
            for effect in effects:
                with self.subTest(size=size, effect=type(effect).__name__):
                    target.fill((0, 0, 0, 0))
                    rect = effect.rect() if hasattr(effect, 'rect') else None
                    effect.draw(surface)
                    self.assertTrue(target.get_bounding_rect())
                    if rect is not None:
                        self.assertEqual(effect.rect(), rect)

    def test_portrait_keeps_full_width_gameplay_bounds(self):
        self.assertEqual((config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT),
                         (0, config.SCREEN_WIDTH))

    def test_landscape_scales_player_enemies_and_bosses_with_collision_boxes(self):
        config.update_mobile_view((844, 390))
        self.game.difficulty = config.DIFFICULTY_PRESETS['medium']
        enemy_def = next(edef for edef in config.ENEMY_DEFS
                         if not edef['is_large'] and not edef.get('zongzong'))
        enemy = Enemy(enemy_def)
        regular_boss = self.game._make_boss(config.BOSS_DEFS[5])
        zong_boss = self.game._make_boss(config.BOSS_DEFS[7])
        self.game.enemies = [enemy]
        self.game.boss = zong_boss
        self.game.resize_view()

        self.assertEqual(self.game.player.rect().size, (36, 42))
        self.assertEqual(enemy.rect().size, (41, 36))
        self.assertLess(enemy.surface.get_width(), enemy.base_surface_size[0])
        self.assertEqual(regular_boss.rect().size, (86, 77))
        self.assertEqual(zong_boss.w, 61)
        self.assertAlmostEqual(abs(zong_boss.body_x(1) - zong_boss.x), 52.8)
        self.assertLess(zong_boss.rect().width, 180)
        zong_boss.movement_timer = 78.5
        zong_boss._move(1.0)
        self.assertGreaterEqual(zong_boss.rect().left, config.GAME_AREA_LEFT)
        self.assertLessEqual(zong_boss.rect().right, config.GAME_AREA_RIGHT)
        self.game.player.draw(config.SCR)
        zong_boss.draw(config.SCR)

        config.update_mobile_view((480, 850))
        self.game.resize_view()
        self.assertEqual(self.game.player.rect().size, (45, 53))
        self.assertEqual((enemy.w, enemy.h), (51, 45))
        self.assertLess(enemy.surface.get_width(), enemy.base_surface_size[0])
        self.assertEqual((zong_boss.w, zong_boss.h), (102, 94))
        self.assertEqual(abs(zong_boss.body_x(1) - zong_boss.x), 88)


if __name__ == '__main__':
    unittest.main()
