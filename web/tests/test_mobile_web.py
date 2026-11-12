import math
import os
import random
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config, menu_ui
from game_core.game import Game, GameState
from game_core.entities import Bullet, Enemy, GiftBox, SkillProjectile
from game_core.entities import MagneticStorm, RadiationLaser, SpinningDarts
from game_core.render import RenderSurface
from game_core.special_bosses import ReturningAxe
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

    def test_pause_settings_change_actor_size_without_moving_hitboxes(self):
        self.addCleanup(sounds.set_music_volume_percent, sounds.music_volume_percent())
        for desktop in (False, True):
            game = Game(web=not desktop, desktop_controls=desktop)
            game._begin_infinite_run(7)
            game._trigger_infinite_boss()
            game.enemies = [Enemy(config.ENEMY_DEFS[0])]
            game._handle_mobile_action('pause')
            (quieter, louder), (zoom_out, zoom_in) = game._pause_settings_rects()
            hitboxes = game.player.rect(), game.enemies[0].rect(), game.boss.rect()

            def click(rect):
                if desktop:
                    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=rect.center, button=1)
                else:
                    event = pygame.event.Event(pygame.FINGERDOWN, finger_id=7,
                                               x=rect.centerx / 480, y=rect.centery / 850)
                game.handle_events([event])

            sounds.set_music_volume_percent(80)
            click(quieter)
            self.assertEqual(sounds.music_volume_percent(), 70)
            click(louder)
            self.assertEqual(sounds.music_volume_percent(), 80)
            sounds.set_music_volume_percent(0)
            click(quieter)
            self.assertEqual(sounds.music_volume_percent(), 0)
            sounds.set_music_volume_percent(100)
            click(louder)
            self.assertEqual(sounds.music_volume_percent(), 100)
            widths = []
            with patch.object(config, 'game_ticks', return_value=1000):
                for expected in (95, 90, 85, 85):
                    click(zoom_out)
                    self.assertEqual(game.actor_scale_percent, expected)
                for expected in range(85, 116, 5):
                    if expected > 85:
                        click(zoom_in)
                    self.assertEqual(game.actor_scale_percent, expected)
                    with patch('game_core.entities.blit_lit_sprite') as blit:
                        game.draw(draw_background=False)
                    widths.append([call.args[1].get_width() for call in blit.call_args_list])
                    self.assertEqual((game.player.rect(), game.enemies[0].rect(), game.boss.rect()), hitboxes)
                    self.assertEqual(game.state, GameState.PAUSED)
                click(zoom_in)
                self.assertEqual(game.actor_scale_percent, 115)
            self.assertEqual(len(widths[0]), 3)
            self.assertTrue(all(small < normal < large for small, normal, large in zip(widths[0], widths[3], widths[-1])))

    def test_web_level_title_is_centered_and_blocks_input_for_three_seconds(self):
        game = Game(web=True)
        with patch('pygame.time.get_ticks', return_value=1000) as clock:
            game._start_game('easy')
            for size in ((390, 844), (844, 390)):
                config.update_mobile_view(size)
                with patch.object(game, '_draw_panel') as panel, patch.object(game, '_draw_game') as battle:
                    game.draw(draw_background=False)
                battle.assert_not_called()
                rect = pygame.Rect(*panel.call_args.args)
                self.assertEqual(rect.center, (config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2))
            event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k, mod=0)
            with patch.object(game, '_handle_keydown') as keydown:
                clock.return_value = 3999
                self.assertTrue(game.web_level_intro_active())
                game.handle_events([event])
                keydown.assert_not_called()
                clock.return_value = 4000
                self.assertFalse(game.web_level_intro_active())
                game.handle_events([event])
                keydown.assert_called_once_with(event)

    def test_web_skill_buttons_keep_icons_during_cooldown(self):
        game = Game(web=True)
        game.player.character = 'radiation'
        controls = game.mobile_controls
        with patch.object(config, 'game_ticks', return_value=1000), \
                patch.object(controls, '_skill_timing', return_value=(2000, 1000)), \
                patch.object(game, '_draw_text_fit') as labels, \
                patch('game_core.mobile_controls.Draw.lines') as icons:
            controls.draw(config.SCR, game)
        self.assertGreaterEqual(icons.call_count, 4)
        drawn = {call.args[0] for call in labels.call_args_list}
        self.assertTrue(drawn.isdisjoint({'闪电链', '磁暴', '激光', '飞镖', '1s'}))

    def test_web_home_scrim_preserves_the_background(self):
        game = Game(web=True)
        pixels = pygame.Surface((720, 405), pygame.SRCALPHA)
        with patch.object(config, 'SCR', RenderSurface(pixels, (960, 540), pixels.get_size(), (0, 0))):
            game.draw(draw_background=False)
        self.assertGreater(pixels.get_at((0, 0)).a, 0)
        self.assertLess(pixels.get_at((0, 0)).a, 255)

    def test_mobile_web_restores_sprite_size_without_changing_hitboxes(self):
        for size in ((390, 844), (844, 390)):
            config.update_mobile_view(size)
            game = Game(web=True, mobile_web=True)
            game._start_game('easy')
            game.player.character = 'water'
            octopus = Enemy(next(enemy for enemy in config.ENEMY_DEFS if enemy['key'] == 'octopus'))
            game.enemies = [octopus]
            hitboxes = game.player.rect(), octopus.rect()
            with patch('game_core.entities.blit_lit_sprite') as blit:
                game._draw_game()
                mobile_sizes = [call.args[1].get_size() for call in blit.call_args_list]
                blit.reset_mock()
                game.mobile_web = False
                game._draw_game()
                desktop_sizes = [call.args[1].get_size() for call in blit.call_args_list]
            self.assertEqual(len(mobile_sizes), 2)
            for mobile, desktop in zip(mobile_sizes, desktop_sizes):
                self.assertGreater(mobile[0], desktop[0])
                self.assertGreater(mobile[1], desktop[1])
            self.assertEqual((game.player.rect(), octopus.rect()), hitboxes)

    def test_hud_does_not_overlap_touch_buttons(self):
        for size in ((360, 640), (390, 844), (844, 390), (1280, 720)):
            config.update_mobile_view(size)
            for rect in self.game._hud_controls():
                for action, (x, y), radius, _, _ in self.game.mobile_controls._buttons(self.game):
                    nearest_x = max(rect.left, min(x, rect.right))
                    nearest_y = max(rect.top, min(y, rect.bottom))
                    self.assertGreater((x - nearest_x) ** 2 + (y - nearest_y) ** 2,
                                       radius ** 2, (size, action, rect))

    def test_radiation_laser_has_a_narrower_hitbox(self):
        laser = RadiationLaser(self.game.player)
        self.assertEqual(laser.beam_width(), int(self.game.player.SIZE[0] * 0.28))
        self.assertEqual(laser.rect().width, laser.beam_width() + 20)
        self.assertAlmostEqual(laser.rect().centerx, self.game.player.x, delta=1)

    def test_radiation_laser_hits_each_monster_but_plays_one_impact_sound(self):
        game = self.game
        game._start_game('easy')
        now = config.game_ticks()
        laser = RadiationLaser(game.player)
        game.radiation_lasers = [laser]
        game.enemies = [Enemy(config.ENEMY_DEFS[0]) for _ in range(2)]
        for enemy, y in zip(game.enemies, (100, 160)):
            enemy.x, enemy.y = laser.rect().centerx, y
            enemy.max_hp = 10
        with patch('game_core.game.play_sound') as sound:
            game._update_radiation_lasers(now)
        sound.assert_called_once_with('laser_hit')
        self.assertEqual([effect.element for effect in game.explosions], ['radiation', 'radiation'])

    def test_radiation_laser_rolls_one_animated_muzzle_effect_per_cast(self):
        game = self.game
        player = game.player
        player.character = 'radiation'
        player.x, player.y = 100, 110
        previews = set()
        for index in range(4):
            now = 1000 + index * 10000
            with patch.object(config, 'game_ticks', return_value=now) as clock, \
                    patch('game_core.game.random.randrange', return_value=index) as roll:
                game._activate_radiation_laser(player)
                laser, = game.radiation_lasers
                self.assertEqual(laser.muzzle_effect, index)
                clock.return_value = now + 180
                game._activate_radiation_laser(player)
                self.assertIs(game.radiation_lasers[0], laser)
                roll.assert_called_once()
                surface = pygame.Surface((200, 160), pygame.SRCALPHA)
                laser._draw_muzzle(surface, (100, 77), now + 180)
                first = pygame.image.tobytes(surface, 'RGBA')
                surface.fill((0, 0, 0, 0))
                laser._draw_muzzle(surface, (100, 77), now + 260)
                self.assertNotEqual(first, pygame.image.tobytes(surface, 'RGBA'))
                previews.add(first)
            game.radiation_lasers.clear()
        self.assertEqual(len(previews), 4)

    def test_gift_hud_shows_active_effects_and_hides_expired_ones(self):
        game = self.game
        with patch.object(config, 'campaign_time_ms', 1000):
            game._begin_infinite_run()
            for kind in ('fire', 'ice', 'haste', 'lightning', 'heal'):
                box = GiftBox(240)
                box.kind = kind
                game._open_gift_box(box, 1000)
                if kind == 'fire':
                    labels = []
                    game.draw(labels)
                    self.assertIn('火弹 10s', {label[0] for label in labels})
            with patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as draw_text:
                game.draw()
        labels = {call.args[0] for call in draw_text.call_args_list}
        self.assertTrue({'冰弹 10s', '极速 10s', '闪电 9s'} <= labels)
        self.assertNotIn('火弹 10s', labels)

        with patch.object(config, 'campaign_time_ms', 11000):
            with patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as draw_text:
                game.draw()
        self.assertFalse(any(call.args[0].startswith(('冰弹 ', '极速 ', '闪电 '))
                             for call in draw_text.call_args_list))

    def test_sniper_missiles_prioritize_and_open_the_nearest_visible_gift(self):
        game = self.game
        game._start_game('easy')
        enemy = Enemy(config.ENEMY_DEFS[0])
        enemy.x, enemy.y = 220, 290
        game.enemies = [enemy]
        for flag in ('sniper_missile', 'sniper_submissile'):
            with self.subTest(flag=flag):
                missile = Bullet(240, 350, config.WEAPON_DEFS['sniper'], 'sniper')
                setattr(missile, flag, True)
                near, far = GiftBox(300), GiftBox(110)
                near.y = far.y = 270
                near.kind = 'haste'
                game.gift_boxes = [far, near]
                game.bullets = [missile]
                game._advance_bullet(missile, 1000)
                self.assertEqual(missile.angle, 7)
                missile.x, missile.y = near.x, near.y
                self.assertTrue(game._handle_bullet_gift_hit(missile, 1000))
                self.assertEqual(game.gift_boxes, [far])
                self.assertFalse(game.bullets)
                self.assertGreater(game.player.gift_speed_until, 1000)
                far.y = -GiftBox.SIZE
                missile.x, missile.y, missile.angle = 240, 350, 0
                game._advance_bullet(missile, 1000)
                self.assertLess(missile.angle, 0)

    def test_gift_lightning_waits_for_a_visible_nearby_target_and_hits_after_travel(self):
        game = self.game
        game._start_game('medium')
        enemy = Enemy(config.ENEMY_DEFS[0])
        enemy.x, enemy.y = config.SCREEN_WIDTH // 2, -1
        game.enemies = [enemy]
        with patch.object(config, 'campaign_time_ms', 1000):
            box = GiftBox(enemy.x)
            box.kind = 'lightning'
            game._open_gift_box(box, 1000)
            game._maybe_fire_gift_lightning(1000)
            self.assertFalse(game.lightnings)
            self.assertEqual(game.gift_lightning_remaining, 2)
            enemy.y = config.SCREEN_HEIGHT // 2 - 100
            game._maybe_fire_gift_lightning(1000)
        bolt = game.lightnings[0]
        with patch.object(enemy, 'hit_by', wraps=enemy.hit_by) as hit:
            with patch.object(config, 'campaign_time_ms', 1040):
                game._update_lightnings(1040)
                bolt.draw(config.SCR)
                hit.assert_not_called()
            with patch.object(config, 'campaign_time_ms', 1055):
                game._update_lightnings(1055)
                game._update_lightnings(1055)
                hit.assert_called_once_with('sniper', 3)

    def test_infinite_continue_clears_score_and_keeps_elapsed_time(self):
        game = self.game
        with patch.object(config, 'campaign_time_ms', 1000):
            game._begin_infinite_run()
        with patch.object(config, 'campaign_time_ms', 66000):
            game.score = 320
            game._player_defeated('测试')
            self.assertEqual(game.score, 320)
            game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_y, mod=0)])
            self.assertEqual(game.state, GameState.INFINITE_COUNTDOWN)
            self.assertEqual(game.score, 0)
            with patch.object(game, '_draw_text_fit', wraps=game._draw_text_fit) as draw_text:
                game.draw()
            self.assertIn('用时 01:05', {call.args[0] for call in draw_text.call_args_list})
            with patch.object(pygame.time, 'get_ticks', return_value=game.infinite_countdown_end):
                game.update()
            self.assertEqual(game.state, GameState.PLAYING)
            self.assertEqual(game.score, 0)

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
        self.assertEqual((game.chapter, game.infinite_background_level, game.infinite_boss_index), (9, 9, 8))

    def test_campaign_enemy_gold_requires_coin_pickup(self):
        game = self.game
        with patch.object(config, 'campaign_time_ms', 1000):
            for boss_fight in (False, True):
                with self.subTest(boss_fight=boss_fight):
                    game._start_game('medium')
                    if boss_fight:
                        game._trigger_boss()
                    starting_gold = game.player.gold
                    enemy = Enemy(config.ENEMY_DEFS[0])
                    enemy.x, enemy.y = game.player.x, 100
                    game.enemies.append(enemy)
                    game._kill_enemy(enemy)

                    self.assertEqual(game.player.gold, starting_gold)
                    self.assertEqual(sum(coin.value for coin in game.coins), enemy.gold_value)
                    game.update()
                    self.assertEqual(game.player.gold, starting_gold)

                    for coin in game.coins:
                        coin.x, coin.y = game.player.rect().center
                    game.update()
                    self.assertEqual(game.player.gold, starting_gold + enemy.gold_value)
                    self.assertFalse(game.coins)

    def test_infinite_enemy_coins_fund_weapon_upgrades(self):
        for boss_fight in (False, True):
            with self.subTest(boss_fight=boss_fight), patch.object(config, 'campaign_time_ms', 1000):
                game = Game(web=True)
                game._begin_infinite_run()
                if boss_fight:
                    game._trigger_infinite_boss()
                enemy = Enemy(config.ENEMY_DEFS[0])
                enemy.x, enemy.y = game.player.x, 100
                game.enemies.append(enemy)
                cost = game._weapon_upgrade_cost('rifle')
                starting_gold = cost - enemy.gold_value
                game.player.gold = starting_gold
                game._kill_enemy(enemy)
                game.update()
                self.assertEqual(game.player.gold, starting_gold)
                self.assertEqual(sum(coin.value for coin in game.coins), enemy.gold_value)
                for coin in game.coins:
                    coin.x, coin.y = game.player.rect().center
                game.update()
                game.update()
                self.assertEqual(game.player.gold, cost)
                self.assertFalse(game.coins)
                game._open_shop()
                game._handle_click(game._mobile_shop_rects()['upgrade:rifle'].center)
                self.assertEqual(game.player.gold, 0)
                self.assertEqual(game.player.weapon_upgrades['rifle'], 1)

    def test_campaign_boss_credits_gold_directly_and_advances_level(self):
        game = self.game
        with patch.object(config, 'campaign_time_ms', 1000):
            game._start_game('medium')
            game._trigger_boss()
            starting_gold = game.player.gold
            game.boss.hp = 0
            self.assertTrue(game._settle_boss_if_killed())
            self.assertEqual(game.player.gold, starting_gold + config.CAMPAIGN_REWARDS[0])
            self.assertFalse(game.coins)
            self.assertEqual(game.state, GameState.LEVEL_TRANSITION)
        previous_background = game.bg
        with patch.object(config, 'campaign_time_ms', game.level_transition_end):
            game.update()
            self.assertIsNot(game.bg, previous_background)
            self.assertIsNotNone(game.bg_transition_prev)
            game.draw()
            self.assertEqual(game.bg_transition_prev.get_alpha(), 255)
        self.assertEqual(game.current_level, 2)
        with patch.object(config, 'campaign_time_ms', game.bg_transition_until):
            game.draw()
            self.assertIsNone(game.bg_transition_prev)

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
        for level, hp in ((7, 118), (8, 128), (9, 132), (10, 136), (11, 148)):
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
            self.assertEqual(game.state, GameState.MENU)
        game._start_infinite_game()
        game.infinite_boss_index = 7
        game._trigger_infinite_boss()
        self.assertEqual(game.boss.max_hp, 184)
        game._kill_boss()
        self.assertEqual(game.state, GameState.PLAYING)

    def test_campaign_victory_totals_include_failed_attempts(self):
        game = self.game
        with patch.object(config, 'campaign_time_ms', 1000):
            game._start_game('easy', len(config.LEVEL_CONFIGS))
            enemy = Enemy(config.ENEMY_DEFS[0])
            game.enemies.append(enemy)
            game._kill_enemy(enemy)
            game.lives = 1
            game._player_defeated('测试')
            game._retry_level()
            self.assertEqual(game.kill_count, 0)
            enemy = Enemy(config.ENEMY_DEFS[0])
            game.enemies.append(enemy)
            game._kill_enemy(enemy)
        with patch.object(config, 'campaign_time_ms', 66000):
            game._trigger_boss()
            game._kill_boss()
        for size in ((390, 844), (844, 390), (960, 720)):
            with self.subTest(size=size), patch.object(config, 'campaign_time_ms', 68000):
                config.update_mobile_view(size)
                labels = []
                game.draw(labels)
                texts = [row[0] for row in labels]
                viewport = pygame.Rect(0, 0, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
                for label, value in (('总共耗时', '01:05'), ('总共消灭怪物', '2'),
                                     ('死亡次数', '1'), ('重启次数', '1'),
                                     ('击败首领', '1'), ('剩余金币', str(game.player.gold))):
                    index = texts.index(label)
                    self.assertEqual(texts[index + 1], value)
                    self.assertTrue(viewport.contains(pygame.Rect(labels[index][4:8])))
                    self.assertTrue(viewport.contains(pygame.Rect(labels[index + 1][4:8])))
                self.assertIn('从第 11 关开始', texts)
        game._start_game('easy')
        self.assertEqual((game.campaign_enemies_defeated, game.campaign_bosses_defeated,
                          game.campaign_deaths, game.campaign_restarts), (0, 0, 0, 0))

    def test_easy_campaign_reduces_late_boss_pressure(self):
        game = self.game
        game._start_game('easy')
        game._start_level(7)
        game._trigger_boss()
        niu = game.boss
        self.assertEqual(niu.attack_interval, 6800)
        niu.laser_active_until = 2000
        self.assertFalse(niu.death_laser_rects(1000))
        niu.laser_active_until = 0
        niu.y = 60
        with patch('pygame.time.get_ticks', return_value=1000), patch('game_core.entities.random.randint', return_value=7000):
            niu.update()
        self.assertEqual(niu.next_death_laser_time, 0)
        with patch('game_core.special_bosses.random.choice', return_value='axes'):
            game._add_boss_projectiles(niu.attack(1000, game.player.x))
        self.assertEqual([projectile.damage for projectile in game.boss_projectiles], [1, 1])
        game.boss = None
        game._start_level(8)
        game._trigger_boss()
        zong = game.boss
        zong.y = Enemy.ENTRY_DAMAGE_Y
        left, right = zong.hitboxes()
        zong.hit_by('pistol', 1, source='bullet', hit_rect=left)
        zong.hit_by('pistol', 1, source='skill', hit_rect=right)
        self.assertEqual(zong.body_hp, [63, 63])
        game._start_infinite_game()
        game.infinite_boss_index = 6
        game._trigger_infinite_boss()
        self.assertFalse(game.boss.can_laser())
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
            gap = 400
            self.assertFalse(game.player.can_shoot(1000 + gap - 1))
            self.assertTrue(game.player.can_shoot(1000 + gap))

    def test_enemy_can_take_damage_as_soon_as_it_is_visible(self):
        enemy = Enemy(config.ENEMY_DEFS[0])
        enemy.hit_by('pistol')
        self.assertFalse(enemy.hits)
        enemy.update()
        self.assertLess(enemy.y, 0)
        self.assertFalse(self.game._show_immune(enemy))
        enemy.hit_by('pistol')
        self.assertEqual(enemy.hits['pistol'], 0.5)

    def test_boss_laser_leaves_room_at_both_edges(self):
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            self.game._start_game('medium')
            for level, definition in enumerate(config.BOSS_DEFS, 1):
                boss = self.game._make_boss({**definition, 'campaign_tier': 1,
                                             'campaign_level': level})
                if not boss.can_laser():
                    continue
                boss.entered = True
                boss.y = 60
                boss.laser_active_until = 2000
                for direction in (-1, 1):
                    boss.movement_timer = direction * math.pi / 0.04
                    with patch('game_core.config.game_ticks', return_value=1000):
                        boss.update()
                    width = self.game.player.rect().w
                    for rect in boss.death_laser_rects(1000):
                        self.assertGreaterEqual(rect.left - config.GAME_AREA_LEFT, math.ceil(width * 1.5))
                        self.assertGreaterEqual(config.GAME_AREA_RIGHT - rect.right, math.ceil(width * 1.5))

    def test_laser_boss_turns_away_from_edge_without_waiting(self):
        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game._start_game('medium')
            for direction in (-1, 1):
                boss = game._make_boss({**config.BOSS_DEFS[1], 'campaign_tier': 1, 'campaign_level': 2})
                boss.entered = True
                boss.y = 60
                boss.laser_active_until = 5000
                boss.movement_timer = direction * math.pi / .04
                with patch('game_core.config.game_ticks', return_value=1000):
                    boss.update()
                    boundary_x = boss.x
                    for _ in range(5):
                        boss.update()
                self.assertGreater((boundary_x - boss.x) * direction, 0)
                for rect in boss.death_laser_rects(1000):
                    self.assertGreaterEqual(rect.left - config.GAME_AREA_LEFT, math.ceil(game.player.rect().w * 1.5))
                    self.assertGreaterEqual(config.GAME_AREA_RIGHT - rect.right, math.ceil(game.player.rect().w * 1.5))

    def test_boss_moves_during_laser_warning(self):
        game = self.game
        game._start_game('medium')
        game._start_level(3)
        game._trigger_boss()
        boss = game.boss
        boss.entered = True
        boss.y = 60
        boss.laser_warning_start = 1000
        boss.laser_warning_ms = 500
        with patch('game_core.config.game_ticks', return_value=1100):
            boss.update()
        self.assertNotEqual(boss.x, config.SCREEN_WIDTH // 2)
        self.assertEqual(boss.laser_active_until, 0)

    def test_laser_preparation_and_firing_use_same_movement_speed(self):
        game = self.game
        game._start_game('medium')
        game._start_level(3)
        game._trigger_boss()
        boss = game.boss
        boss.entered = True
        boss.y = 60
        boss.laser_warning_start = 1000
        boss.laser_warning_ms = 1500
        with patch('game_core.config.game_ticks', return_value=1200):
            before = boss.movement_timer
            boss.update()
            preparing = boss.movement_timer - before
        boss.laser_warning_start = 0
        boss.laser_active_until = 4000
        with patch('game_core.config.game_ticks', return_value=2600):
            before = boss.movement_timer
            boss.update()
            firing = boss.movement_timer - before
        self.assertAlmostEqual(preparing, boss.speed * .5)
        self.assertAlmostEqual(preparing, firing)

    def test_big_fireball_fan_starts_separated(self):
        game = self.game
        game._start_game('medium')
        game._start_level(3)
        game._trigger_boss()
        boss = game.boss
        boss.y = 60
        with patch('game_core.entities.random.random', return_value=0):
            shots = boss.attack(1000, game.player.x)
        self.assertEqual(len(shots), 3)
        self.assertTrue(all(shot.big_fireball for shot in shots))
        for left, right in zip(shots, shots[1:]):
            self.assertGreaterEqual(right.x - left.x, left.r + right.r)

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
        self.assertEqual(boss.laser_warning_ms, 1500)
        with patch('pygame.time.get_ticks', return_value=now + boss.laser_warning_ms - 1):
            boss.update()
        self.assertEqual(boss.laser_active_until, 0)
        fired_at = now + boss.laser_warning_ms
        with patch('pygame.time.get_ticks', return_value=fired_at):
            boss.update()
        self.assertEqual(boss.laser_active_until, fired_at + 2000)
        before = boss.death_laser_rects(fired_at)[0]
        with patch('pygame.time.get_ticks', return_value=fired_at + 16):
            boss.update()
            boss.draw(config.SCR)
        after = boss.death_laser_rects(fired_at + 16)[0]
        self.assertNotEqual(after.centerx, before.centerx)
        self.assertEqual(after.centerx, round(boss.death_laser_xs()[0]))
        self.assertEqual(after.bottom, config.SCREEN_HEIGHT)
        self.assertTrue(boss.death_laser_rects(fired_at + 1999))
        self.assertFalse(boss.death_laser_rects(fired_at + 2000))

    def test_niu_moves_at_patrol_speed_while_swinging_axe_down(self):
        game = self.game
        game._start_game('hard')
        game._start_level(7)
        game._trigger_boss()
        boss = game.boss
        boss.entered = True
        boss.y = 60
        with patch.object(config, 'game_ticks', return_value=1900):
            for phase, direction in ((0, 1), (157, -1)):
                with self.subTest(direction=direction):
                    boss.axe_slam_start = None
                    boss.movement_timer = phase
                    boss._move(0)
                    start_x = boss.x
                    boss.update()
                    patrol_step = boss.x - start_x

                    boss.movement_timer = phase
                    boss.x = start_x
                    boss.axe_slam_start = 1000
                    before = boss.axe_slam_rect(1900)
                    boss.update()
                    after = boss.axe_slam_rect(1900)
                    self.assertGreater(patrol_step * direction, 0)
                    self.assertAlmostEqual(boss.x - start_x, patrol_step)
                    self.assertGreater((after.centerx - before.centerx) * direction, 0)

    def test_niu_axe_slam_has_warning_damage_and_recovery(self):
        game = self.game
        game._start_game('hard')
        game._start_level(7)
        game._trigger_boss()
        boss = game.boss
        now = 4000
        boss.y = 60
        with patch('game_core.special_bosses.random.choice', return_value='slam'), \
                patch.object(config, 'game_ticks', return_value=now):
            shots = boss.attack(now, game.player.x)
        self.assertEqual(shots, [])
        self.assertIsNone(boss.axe_slam_rect(now + 799))
        first = boss.axe_slam_rect(now + 900)
        later = boss.axe_slam_rect(now + 1100)
        self.assertGreater(later.bottom, first.bottom)
        self.assertGreater(later.bottom, config.GAME_AREA_BOTTOM)
        self.assertIsNone(boss.axe_slam_rect(now + 1500))
        self.assertIsNotNone(boss.axe_slam_rect(now + 2400))
        self.assertIsNotNone(boss.axe_slam_rect(now + 3900))
        self.assertIsNone(boss.axe_slam_rect(now + 4500))
        self.assertGreaterEqual(boss.next_hazard_time, now + 4500)
        game.player.x = boss.x
        game.player.y = game.player.bottom_limit()
        game.player_invincible_until = 0
        hp = game.player_hp
        with patch('game_core.game.play_sound') as sound:
            game._update_special_boss_hazards(now + 1100)
            game._update_special_boss_hazards(now + 1101)
            self.assertEqual(sum(call.args == ('niu_axe_impact',) for call in sound.call_args_list), 1)
        self.assertEqual(boss.axe_slam_impact, (later.centerx, later.bottom, now + 1100))
        self.assertEqual(game.player_hp, hp - 1)
        game.player_invincible_until = 0
        game._update_special_boss_hazards(now + 1200)
        self.assertEqual(game.player_hp, hp - 1)
        for strike in (2600, 4100):
            game.player_invincible_until = 0
            game._update_special_boss_hazards(now + strike)
        self.assertEqual(game.player_hp, hp - 3)

    def test_niu_flying_axes_can_hit_at_the_bottom_in_both_orientations(self):
        game = self.game
        for size in ((844, 390), (390, 844)):
            with self.subTest(size=size):
                config.update_mobile_view(size)
                game._start_game('hard')
                game._start_level(7)
                game._trigger_boss()
                boss = game.boss
                boss.y = 60
                game.player.x = config.SCREEN_WIDTH // 2
                game.player.y = game.player.bottom_limit()
                with patch('game_core.special_bosses.random.choice', return_value='axes'):
                    axes = boss.attack(1000, game.player.x)
                for axe in axes:
                    with patch.object(config, 'game_ticks', return_value=axe.spawn_time + axe.OUTBOUND_MS - 1):
                        axe.update()
                    self.assertIs(game._hit_by_projectile(axe), game.player)

    def test_niu_flying_axe_has_no_landing_circle(self):
        from game_core.render import Draw

        game = self.game
        game._start_game('hard')
        game._start_level(7)
        game._trigger_boss()
        axe = ReturningAxe(game.boss, 1, game.player.x, red=True)
        game.warned_boss_shots = [axe]
        with patch.object(Draw, 'circle', wraps=Draw.circle) as circle:
            game.draw()
        center = (int(axe.target_x), axe.landing_y)
        self.assertFalse(
            any(call.args[2:4] == (center, axe.explode_radius) for call in circle.call_args_list))

    def test_immune_axe_contact_does_not_delay_damage_after_invincibility(self):
        game = self.game
        game._start_game('hard')
        game._start_level(7)
        game._trigger_boss()
        axe = ReturningAxe(game.boss, 1, game.player.x, red=False)
        axe.x = axe.prev_x = game.player.x
        axe.y = axe.prev_y = game.player.y
        game.boss_projectiles = [axe]
        game.last_spawn_time = 1500
        game.player_invincible_until = 1500
        hp = game.player_hp

        with patch.object(game.boss, 'update'), patch.object(axe, 'update'):
            game._update_boss_fight(1400)
            self.assertEqual(game.player_hp, hp)
            game._update_boss_fight(1500)
            self.assertEqual(game.player_hp, hp - 1)
            game._update_boss_fight(2200)
            self.assertEqual(game.player_hp, hp - 1)

    def test_enemy_bomb_hit_sound_requires_player_damage(self):
        game = self.game
        game._start_game('hard')
        hp = game.player_hp
        bomb = SimpleNamespace(y=game.player.y, explode_radius=55, damage=1)
        for offset, invincible, hit in ((200, False, False), (0, True, False), (0, False, True)):
            with self.subTest(offset=offset, invincible=invincible):
                bomb.x = game.player.x + offset
                game.player_invincible_until = 1501 if invincible else 0
                with patch('game_core.game.play_sound') as sound:
                    game._explode_enemy_bomb(bomb, 1500)
                self.assertEqual(game.player_hp, hp - int(hit))
                if hit:
                    sound.assert_called_once_with('player_hit')
                    self.assertEqual(game.player_hit_impact[1], game.player.rect().center)
                else:
                    sound.assert_not_called()
                    self.assertIsNone(game.player_hit_impact)

    def test_infinite_boss_growth_and_death_progress(self):
        game = self.game
        game._start_infinite_game()
        cycle = len(config.BOSS_DEFS)
        for defeated, hp, interval in ((0, 30, 4400), (cycle - 1, 220, 3600),
                                       (cycle, 36, 4180), (2 * cycle, 42, 3960),
                                       (6 * cycle, 66, 3080), (7 * cycle, 66, 3080)):
            with self.subTest(defeated=defeated):
                game.chapter = defeated + 1
                game.infinite_background_level = defeated % cycle + 1
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
        for defeated, expected in ((0, 4), (2, 4), (3, 5), (8, 6), (20, 10), (48, 12)):
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
        with patch.object(game, '_try_boss_signature', return_value=False):
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
        self.assertEqual(first.damage_taken, 0)
        first.y = Enemy.ENTRY_END_Y
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
        self.assertEqual(game.boss.max_hp, 202)

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
        self.assertEqual(game.player.gold, 25)
        self.assertEqual(game.lives, 1)
        game._player_defeated('测试')
        self.assertEqual(game.state, GameState.GAME_OVER)

    def test_respawn_centers_player_and_starts_protection_after_countdown(self):
        game = self.game
        for infinite in (False, True):
            with self.subTest(infinite=infinite):
                game.infinite_mode = infinite
                game.player.x, game.player.y = 100, 100
                game.lives = 2
                game._player_defeated('测试')
                if infinite:
                    game._continue_infinite()
                self.assertEqual(game.state, GameState.INFINITE_COUNTDOWN)
                self.assertEqual((game.player.x, game.player.y),
                                 (config.SCREEN_WIDTH // 2, config.GAME_AREA_BOTTOM - 14))
                with patch.object(pygame.time, 'get_ticks', return_value=game.infinite_countdown_end), \
                        patch.object(config, 'game_ticks', return_value=10000):
                    game.update()
                self.assertTrue(game._player_is_invincible(11499))
                self.assertFalse(game._player_is_invincible(11500))

    def test_paid_revive_limits_by_difficulty(self):
        game = self.game
        for difficulty, limit, cost in (('easy', 5, 50), ('medium', 4, 75), ('hard', 3, 100)):
            with self.subTest(difficulty=difficulty):
                game._start_game(difficulty)
                game.lives = 1
                game.player.gold = 500
                for purchase in range(1, limit + 1):
                    game._player_defeated('测试')
                    self.assertEqual(game.state, GameState.PAID_REVIVE)
                    game._paid_revive()
                    self.assertEqual(game.player.gold, 500 - purchase * cost)
                    self.assertEqual(game.lives, 1)
                game._player_defeated('测试')
                self.assertEqual(game.state, GameState.GAME_OVER)

    def test_retry_restores_level_start_after_paid_revive(self):
        game = self.game
        game._start_game('medium')
        game.player.gold = 120
        game.player.owned_weapons.append('rifle')
        game.player.current_weapon = 'rifle'
        game.player.owned_characters.append('water')
        game.try_switch_character('water')
        game.lives = 2
        game.revive_count = 1
        game.player_hp = 3
        game.kill_count = 12
        with patch('game_core.config.game_ticks', return_value=1000):
            game.player.water_boost_until = 5000
            game.player.skill_cooldowns['water_heal'] = 7000
            game._start_level(2)
        game.player.gold = 300
        game.player.owned_weapons.append('shotgun')
        game.player.owned_characters.append('ice')
        game.try_switch_character('ice')
        game.kill_count = 20
        game.lives = 1
        for _ in range(3):
            game._player_defeated('测试')
            game._paid_revive()
        game._player_defeated('测试')
        self.assertEqual(game.state, GameState.GAME_OVER)
        with patch('game_core.config.game_ticks', return_value=10000):
            game._handle_click(game._game_over_choice_rects()[0].center)
        self.assertEqual(game.state, GameState.PLAYING)
        self.assertEqual(game.current_level, 2)
        self.assertEqual((game.lives, game.player_hp, game.player.gold, game.kill_count), (3, 3, 120, 12))
        self.assertEqual(game.player.owned_weapons, ['pistol', 'rifle'])
        self.assertEqual(game.player.current_weapon, 'rifle')
        self.assertEqual(game.player.owned_characters, ['water'])
        self.assertEqual(game.player.character, 'water')
        self.assertEqual(game.player.water_boost_until, 14000)
        self.assertEqual(game.player.skill_cooldowns['water_heal'], 16000)
        self.assertEqual(game.revive_count, 0)
        self.assertEqual(game._paid_revives_remaining(), 4)

    def test_retry_boss_start_level_can_be_repeated_and_exit(self):
        game = self.game
        game._start_game('medium')
        game.player.gold = 10
        game.lives = 1
        game._start_level(6)
        with patch.object(game, '_level_title_ticks', return_value=game.level_title_until):
            game.update()
        self.assertEqual(game.state, GameState.BOSS_FIGHT)
        for _ in range(2):
            game.lives = 1
            game._player_defeated('测试')
            self.assertEqual(game.state, GameState.GAME_OVER)
            game._handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertIsNone(game.boss)
            with patch.object(game, '_level_title_ticks', return_value=game.level_title_until):
                game.update()
            self.assertEqual(game.state, GameState.BOSS_FIGHT)
            self.assertEqual(game.current_level, 6)
            self.assertEqual(game.lives, 3)
            self.assertIsNotNone(game.boss)
        game.lives = 1
        game._player_defeated('测试')
        game._handle_click(game._game_over_choice_rects()[1].center)
        self.assertEqual(game.state, GameState.MENU)
        self.assertIsNone(game.level_checkpoint)

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
        game._start_game('hard')
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
        cancel, confirm = game._choice_rects()

        def tap(rect):
            event = pygame.event.Event(pygame.FINGERDOWN, finger_id=7,
                                       x=rect.centerx / 480, y=rect.centery / 850)
            self.assertTrue(game.handle_events([event]))

        tap(confirm)
        self.assertTrue(game.exit_confirmation)
        game.handle_events([pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=confirm.center,
                                               button=1, touch=True)])
        self.assertTrue(game.exit_confirmation)
        game.draw()
        tap(cancel)
        self.assertFalse(game.exit_confirmation)
        self.assertEqual(game.state, GameState.PAUSED)
        tap(confirm)
        tap(confirm)
        self.assertFalse(game.exit_confirmation)
        self.assertEqual(game.state, GameState.MENU)
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

    def test_home_difficulty_opens_campaign_with_first_level_selected(self):
        game = self.game
        self.assertEqual(game.state, GameState.MENU)
        with patch.object(game, 'web', True):
            for key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                game._handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
                self.assertEqual(game.state, GameState.MENU)
        game.selected_level = 9
        game._handle_click(game._mobile_menu_rects()['medium'].center)
        self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)
        self.assertEqual(game.selected_difficulty, 'medium')
        self.assertEqual(game.selected_level, 1)
        rects = game._campaign_rects()
        self.assertEqual(set(rects) - {f'level:{i}' for i in range(1, 12)}, {'home', 'detail', 'start'})
        game._handle_click(rects['level:9'].center)
        self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)
        game._handle_click(rects['start'].center)
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertEqual(game.current_level, 9)
        self.assertEqual(game.difficulty.name, '中等')
        self.assertEqual(len(self.game.players), 1)
        self.game.draw()

    def test_battle_shop_skill_preview_and_purchase(self):
        game = self.game
        game._handle_click(game._mobile_menu_rects()['easy'].center)
        game._handle_click(game._campaign_rects()['start'].center)
        game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0)])
        game._handle_mobile_action('shop')
        game.player.gold = 40
        rects = game._mobile_shop_rects()
        self.assertEqual(sum(key.startswith('weapon:') for key in rects), 4)
        self.assertEqual(sum(key.startswith('character:') for key in rects), 4)
        self.assertLess(rects['weapon:pistol'].bottom, rects['character:ice'].top)
        game._handle_click(game._mobile_shop_rects()['skills:fire'].center)
        self.assertEqual(game.shop_character, 'fire')
        self.assertEqual(game.player.gold, 40)
        self.assertIsNone(game.player.character)
        game._handle_click(game._mobile_shop_rects()['character:fire'].center)
        self.assertEqual(game.player.gold, 14)
        self.assertEqual(game.player.character, 'fire')
        self.assertEqual(game.state, GameState.SHOP)
        game._handle_click(game._mobile_shop_rects()['close'].center)
        self.assertEqual(game.state, GameState.PLAYING)
        self.assertEqual(game.player.character, 'fire')
        self.assertEqual(game.player.gold, 14)

    def test_home_title_and_bosses_animate_independently_of_team(self):
        pixels = pygame.Surface((960, 1700), pygame.SRCALPHA)
        target = RenderSurface(pixels, (480, 850), pixels.get_size(), (0, 0))
        sprite = pygame.Surface((10, 10))
        with patch.object(self.game, 'title_image', object()), \
                patch.object(self.game, '_draw_scrim'), \
                patch.object(self.game, '_draw_text_fit'), \
                patch.object(menu_ui, '_panel'), \
                patch.object(config, 'SCR', target), \
                patch.object(target, 'blit_pixels', wraps=target.blit_pixels) as blit, \
                patch.object(menu_ui, '_boss_art', return_value=sprite), \
                patch.object(menu_ui, '_art') as art, \
                patch('pygame.time.get_ticks', return_value=0) as clock:
            poster_frames, other_art, team_frames = [], [], []
            for time in (0, 1800, 3600, 5400, 7200):
                clock.return_value = time
                blit.reset_mock()
                art.reset_mock()
                menu_ui.draw_home(self.game)
                blit.assert_called_once()
                image, position = blit.call_args.args
                poster_frames.append(image.get_rect(topleft=position))
                other_art.append([call.args[1] for call in art.call_args_list])
                team_frames.append([call.args[0] for call in art.call_args_list[1:]])

        resting, growing, expanded, shrinking, returned = poster_frames
        self.assertEqual(expanded.w, target.length(round(menu_ui._home_boxes()[1].w * 0.88)))
        self.assertAlmostEqual(resting.w / expanded.w, 0.90, delta=1 / expanded.w)
        self.assertLess(resting.w, growing.w)
        self.assertLess(growing.w, expanded.w)
        self.assertEqual(growing, shrinking)
        self.assertEqual(resting, returned)
        self.assertTrue(all(rect.center == expanded.center for rect in poster_frames))
        self.assertGreater(other_art[2][0].y, other_art[0][0].y)
        self.assertEqual(other_art[0][1:], other_art[2][1:])
        self.assertEqual(len(team_frames[0]), 5)
        for first, later in zip(team_frames[0], team_frames[2]):
            self.assertIsNotNone(first)
            self.assertIsNotNone(later)
            self.assertNotEqual(pygame.image.tobytes(first, 'RGBA'), pygame.image.tobytes(later, 'RGBA'))
        team_top = min(rect.top for rect in other_art[2][1:])
        self.assertLess(expanded.bottom, target.point((0, team_top))[1])

    def test_home_buttons_fit_portrait_and_landscape(self):
        for size in ((844, 390), (932, 393), (390, 844)):
            with self.subTest(size=size):
                config.update_mobile_view(size)
                rects = self.game._mobile_menu_rects()
                cards = list(rects.values())
                self.assertEqual(len({rect.top for rect in cards}),
                                 1 if config.MOBILE_LANDSCAPE_VIEW else 3)
                self.assertEqual((min(rect.left for rect in cards) + max(rect.right for rect in cards)) // 2,
                                 config.SCREEN_WIDTH // 2)
                bounds = pygame.Rect(0, 0, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
                self.assertTrue(all(bounds.contains(rect) for rect in cards))
                self.assertTrue(all(rect.collidelist(cards[index + 1:]) == -1
                                    for index, rect in enumerate(cards)))

    def test_keyboard_home_settings_custom_campaign_and_endless(self):
        game = self.game

        def press(key):
            game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=key, mod=0)])

        press(pygame.K_3)
        self.assertEqual(game.selected_difficulty, 'hard')
        self.assertEqual(game.selected_level, 1)
        press(pygame.K_DOWN)
        press(pygame.K_RIGHT)
        self.assertEqual(game.selected_level, 5)
        press(pygame.K_a)
        press(pygame.K_w)
        self.assertEqual(game.selected_level, 1)
        press(pygame.K_d)
        press(pygame.K_s)
        self.assertEqual(game.selected_level, 5)
        press(pygame.K_b)
        self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)
        press(pygame.K_ESCAPE)
        press(pygame.K_k)
        self.assertEqual(game.state, GameState.KEY_SETTINGS)
        press(pygame.K_DOWN)
        press(pygame.K_RETURN)
        press(pygame.K_f)
        self.assertEqual(game.controls['p1_right'], pygame.K_f)
        press(pygame.K_ESCAPE)
        self.assertEqual(game.state, GameState.MENU)
        press(pygame.K_c)
        self.assertEqual(game.state, GameState.CUSTOM_DIFFICULTY)
        press(pygame.K_RIGHT)
        press(pygame.K_RETURN)
        self.assertEqual(game.state, GameState.DIFFICULTY_SELECT)
        self.assertEqual(game.selected_level, 1)
        press(pygame.K_RETURN)
        self.assertEqual(game.current_level, 1)
        self.assertEqual(game.difficulty.name, '自定义')
        self.assertEqual(game.difficulty.spawn_interval_start, 2500)
        game.reset()
        press(pygame.K_4)
        self.assertTrue(game.infinite_mode)

    def test_bottom_hp_label_renders_at_web_canvas_resolution(self):
        game = Game(web=True)
        game._start_game('easy')
        for size in ((390, 844), (844, 390)):
            with self.subTest(size=size):
                config.update_mobile_view(size)
                logical = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
                pixels = tuple(round(dimension * 1.5) for dimension in logical)
                target = RenderSurface(pygame.Surface(pixels), logical, pixels, (0, 0))
                game._ui_labels = []
                with patch.object(config, 'SCR', target), patch.object(
                    game, '_desktop_font', wraps=game._desktop_font
                ) as font:
                    game._draw_hud()
                font.assert_any_call(target.length(16), False)
                self.assertFalse(any(row[0].startswith('HP ') for row in game._ui_labels))

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

    def test_chapter_titles_draw_enemy_art_in_portrait_and_landscape(self):
        game = self.game
        for size in ((390, 844), (844, 390)):
            config.update_mobile_view(size)
            target = pygame.Surface(size)
            config.SCR = RenderSurface(target, (config.SCREEN_WIDTH, config.SCREEN_HEIGHT),
                                       config.VIEW_SIZE, config.VIEW_OFFSET)
            for level in range(1, len(config.LEVEL_CONFIGS) + 1):
                with self.subTest(size=size, level=level), \
                        patch.object(config, 'game_ticks', return_value=1000), \
                        patch.object(config.SCR, 'blit', wraps=config.SCR.blit) as blit, \
                        patch.object(game, '_draw_panel', wraps=game._draw_panel) as panel:
                    game.current_level = level
                    game.level_title_until = 2200
                    game._ui_labels = []
                    game._draw_level_title()
                    labels = [label[0] for label in game._ui_labels]
                    self.assertIn(f'第{level}关', labels)
                    self.assertIn(config.LEVEL_CONFIGS[level - 1]['title'], labels)
                    boss = config.BOSS_DEFS[config.LEVEL_CONFIGS[level - 1]['boss_idx']]
                    self.assertIn(boss['name'], labels)
                    self.assertRegex(boss['name'], r'^[\u4e00-\u9fff]{4}·[\u4e00-\u9fff]{2}$')
                    icons = blit.call_args_list
                    self.assertEqual(len(icons), 1 if level == 11 else 4)
                    if level == 11:
                        self.assertIn('直接挑战', labels)
                    self.assertTrue(all(icon.kwargs['logical_size'][0] <= 30 for icon in icons[:-1]))
                    plaque = pygame.Rect(*panel.call_args.args)
                    boss_rect = pygame.Rect(icons[-1].args[1], icons[-1].kwargs['logical_size'])
                    self.assertGreater(max(boss_rect.size), 48)
                    self.assertLess(boss_rect.top, plaque.top)
                    self.assertGreater(boss_rect.bottom, plaque.top)
                    for row in game._ui_labels:
                        self.assertFalse(boss_rect.colliderect(pygame.Rect(row[4:8])))
                    for action, (x, y), radius, _, _ in game.mobile_controls._buttons(game):
                        if action.startswith('character:'):
                            button = pygame.Rect(x - radius, y - radius, 2 * radius, 2 * radius)
                            self.assertFalse(plaque.colliderect(button))

    def test_infinite_title_uses_background_level_and_expires(self):
        game = self.game
        game.infinite_mode = True
        game.chapter = 20
        game.infinite_background_level = 9
        game.level_title_until = 2200
        game._ui_labels = []
        with patch.object(config, 'game_ticks', return_value=2199):
            game._draw_level_title()
        self.assertEqual([label[0] for label in game._ui_labels], ['第20章', '机房重地', '机械蜥蜴·熔芯'])
        game._ui_labels.clear()
        with patch.object(config, 'game_ticks', return_value=2200):
            game._draw_level_title()
        self.assertEqual(game._ui_labels, [])

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

    def test_campaign_tracks_match_menu_level_and_keep_clean_loop_seams(self):
        lengths = set()
        tracks = [(level, False, False, 0) for level in range(9)]
        tracks += [(5, True, False, 0), (2, True, True, 1)]
        for level, boss, infinite, variant in tracks:
            generator = sounds._music_pcm(level, boss, infinite, variant)
            with self.assertRaises(StopIteration) as finished:
                while True:
                    next(generator)
            pcm = finished.exception.value
            samples = struct.iter_unpack('<h', pcm)
            rms = math.sqrt(sum(sample * sample for sample, in samples) / (len(pcm) // 2))
            if level == 0:
                menu_rms = rms
            else:
                self.assertAlmostEqual(rms, menu_rms, delta=1)
                if not boss:
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
                volume = .72 * sounds.music_volume_percent() / 100
                self.assertAlmostEqual(previous.get_volume(), volume, delta=.01)
                sounds.start_music(1, boss=True)
                sounds.advance_music()
                self.assertIsNotNone(channel.get_sound())
                self.assertIsNot(channel.get_sound(), previous)
                self.assertAlmostEqual(channel.get_sound().get_volume(), volume, delta=.01)
                self.assertEqual(previous.get_num_channels(), 0)
        finally:
            pygame.mixer.stop()

    def test_first_level_restores_menu_volume_after_opening_fade(self):
        pcm = b'\0\0' * sounds.SAMPLE_RATE

        def track(*args):
            yield
            return pcm

        self.assertTrue(sounds.ensure_audio())
        self.addCleanup(sounds.stop_music)
        sounds.stop_music()
        channel = pygame.mixer.Channel(0)
        with patch.object(sounds, '_music_pcm', side_effect=track):
            sounds.start_music()
            sounds.advance_music()
            pygame.time.wait(100)
            menu_volume = channel.get_volume()
            sounds.set_music_volume(.13)
            sounds.stop_music(fade_ms=300)
            sounds.start_music(1)
            sounds.advance_music()
            pygame.time.wait(400)
            self.assertTrue(channel.get_busy())
            self.assertEqual(channel.get_volume(), menu_volume)

    def test_music_volume_preserves_effects_and_survives_track_changes(self):
        pcm = b'\0\0' * sounds.SAMPLE_RATE
        self.assertTrue(sounds.ensure_audio())
        self.addCleanup(sounds.set_music_volume_percent, sounds.music_volume_percent())
        sounds.set_music_volume_percent(80)
        self.addCleanup(sounds.stop_music)
        sounds.stop_music()
        effect = pygame.mixer.Sound(buffer=pcm)
        effect_channel = effect.play(loops=-1)
        self.addCleanup(effect_channel.stop)
        music_channel = pygame.mixer.Channel(0)
        def track(*args):
            yield
            return pcm

        with patch.object(sounds, '_music_pcm', side_effect=track):
            sounds.start_music()
            sounds.advance_music()
            self.assertAlmostEqual(music_channel.get_sound().get_volume(), .72 * .8, delta=.01)
            sounds.set_music_volume_percent(40)
            pygame.time.wait(65)
            self.assertAlmostEqual(music_channel.get_sound().get_volume(), .72 * .4, delta=.01)
            sounds.stop_music()
            sounds.start_music(1, boss=True)
            sounds.advance_music()
            pygame.time.wait(65)
            self.assertAlmostEqual(music_channel.get_sound().get_volume(), .72 * .4, delta=.01)
            self.assertTrue(effect_channel.get_busy())
            self.assertEqual(effect_channel.get_volume(), 1)
            sounds.set_music_volume_percent(90)
            self.assertAlmostEqual(music_channel.get_sound().get_volume(), .72 * .9, delta=.01)

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
            self.assertAlmostEqual(math.hypot(shot.x - origin[0], shot.y - origin[1]), 140)

        rocket = rockets[0]
        surface = pygame.Surface((96, 96), pygame.SRCALPHA)
        SkillProjectile(48, 48, 0, rocket.speed, 'fire_rocket').draw(surface)
        self.assertGreaterEqual(surface.get_bounding_rect().height, 75)
        surface.fill((0, 0, 0, 0))
        SkillProjectile(48, 48, 0, shots[0].speed, 'fireball').draw(surface)
        self.assertLessEqual(surface.get_bounding_rect().width, 42)
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
        self.assertEqual(len(game.explosions), 3)  # One blast and two target impacts.

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

    def test_joystick_reverses_after_a_short_drag_back_from_full_tilt(self):
        game = self.game
        game.state = GameState.PLAYING
        controls = game.mobile_controls
        for size in ((844, 390), (390, 844)):
            with self.subTest(size=size), patch.object(controls, '_window_size', return_value=size):
                config.update_mobile_view(size)
                controls.reset()
                game.player.x = config.SCREEN_WIDTH // 2

                def touch(event_type, x):
                    event = pygame.event.Event(event_type, finger_id=7, x=x / size[0], y=0.9)
                    game.handle_events([event])

                touch(pygame.FINGERDOWN, 110)
                touch(pygame.FINGERMOTION, 210)
                game._move_player_from_controls(game.player, {}, pygame.time.get_ticks())
                self.assertGreater(game.player.x, config.SCREEN_WIDTH // 2)

                x = game.player.x
                touch(pygame.FINGERMOTION, 182)
                game._move_player_from_controls(game.player, {}, pygame.time.get_ticks())
                self.assertLess(game.player.x, x)

                touch(pygame.FINGERUP, 182)
                x = game.player.x
                game._move_player_from_controls(game.player, {}, pygame.time.get_ticks())
                self.assertEqual(game.player.x, x)

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

    def test_browser_touch_state_recovers_a_missing_fingerup(self):
        controls = self.game.mobile_controls
        controls.handle_touch(pygame.event.Event(pygame.FINGERDOWN, finger_id=7, x=.4, y=.9), self.game)
        controls.handle_touch(pygame.event.Event(pygame.FINGERMOTION, finger_id=7, x=.55, y=.9), self.game)
        controls.fingers[8] = 'attack'
        controls.release_inactive_touches({8}.__contains__)
        self.assertEqual(controls.fingers, {8: 'attack'})
        self.assertIsNone(controls.joystick_id)
        self.assertEqual(controls.axis, (0.0, 0.0))
        controls.handle_touch(pygame.event.Event(pygame.FINGERDOWN, finger_id=9, x=.4, y=.9), self.game)
        self.assertEqual(controls.joystick_id, 9)

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
        zongzong.y = Enemy.ENTRY_DAMAGE_Y
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
        self.assertTrue(storm.contains_point(center[0] + 124, center[1]))
        self.assertFalse(storm.contains_point(center[0] + 125, center[1]))
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

    def test_niu_opening_random_skill_starts_at_three_seconds(self):
        game = self.game
        for infinite in (False, True):
            for skill in ('axes', 'slam', 'lightning'):
                with self.subTest(infinite=infinite, skill=skill):
                    if infinite:
                        game._start_infinite_game()
                        game.infinite_boss_index = 6
                        game._trigger_infinite_boss()
                    else:
                        game._start_game('easy')
                        game._start_level(7)
                        game._trigger_boss()
                    boss = game.boss
                    boss.entered = True
                    boss.y = 60
                    boss.fight_start_time = 1000
                    boss.last_attack_time = 1000
                    boss.attack_interval = 20000
                    game.last_spawn_time = 4000
                    with patch.object(boss, 'update'), patch.object(game, '_maybe_spawn_gift'), \
                            patch('game_core.special_bosses.random.choice', return_value=skill), \
                            patch.object(config, 'game_ticks', return_value=3999):
                        game._update_boss_fight(3999)
                        self.assertIsNone(boss.last_pattern)
                    with patch.object(boss, 'update'), patch.object(game, '_maybe_spawn_gift'), \
                            patch('game_core.special_bosses.random.choice', return_value=skill), \
                            patch.object(config, 'game_ticks', return_value=4000):
                        game._update_boss_fight(4000)
                    self.assertEqual(boss.last_pattern, skill)
                    self.assertEqual(boss.last_attack_time, 4000)
                    self.assertFalse(boss.opening_skill_pending)
                    if skill == 'lightning':
                        self.assertEqual(boss.lightning_warning_until, 4000)
                        self.assertGreater(boss.lightning_until, 4000)
                    elif skill == 'slam':
                        self.assertEqual(boss.axe_slam_start, 4000)
                    else:
                        self.assertEqual(len(game.boss_projectiles), 2)
                    with patch.object(boss, 'update'), patch.object(game, '_maybe_spawn_gift'), \
                            patch.object(boss, 'attack', wraps=boss.attack) as attack, \
                            patch.object(config, 'game_ticks', return_value=4001):
                        game._update_boss_fight(4001)
                        attack.assert_not_called()
                    if skill == 'axes':
                        self.assertFalse(boss.should_attack(23999))
                        self.assertTrue(boss.should_attack(24000))

    def test_signature_opening_starts_three_seconds_after_entry(self):
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
                        self.assertTrue(boss.signature_opening_pending)
                        self.assertIsNone(boss.signature)
                        with patch('game_core.config.game_ticks', return_value=now + 2999), \
                                patch.object(boss, 'should_attack', return_value=False):
                            game._update_boss_fight(now + 2999)
                        self.assertIsNone(boss.signature)
                        with patch('game_core.config.game_ticks', return_value=now + 3000), \
                                patch.object(boss, 'should_attack', return_value=False):
                            game._update_boss_fight(now + 3000)
                        self.assertFalse(boss.signature_opening_pending)
                        self.assertEqual(boss.signature.impact_at, now + 3000)
                        opening = boss.signature
                        due = (opening.end_at if opening.key == 'boss' else now + 3000) + 10000
                        with patch.object(boss, 'should_attack', return_value=False), \
                                patch('game_core.entities.random.random', return_value=1):
                            game._update_boss_fight(opening.end_at)
                            game._update_boss_fight(due - 1)
                            self.assertIsNone(boss.signature)
                            if opening.key == 'boss_crab':
                                game.enemies[:] = [enemy for enemy in game.enemies if enemy.chase_color is None]
                            attack_time = boss.last_attack_time
                            laser_time = boss.next_death_laser_time
                            game._update_boss_fight(due)
                        self.assertIsNotNone(boss.signature)
                        self.assertIsNot(boss.signature, opening)
                        self.assertEqual(boss.signature.impact_at, due)
                        self.assertEqual(boss.last_attack_time, attack_time)
                        self.assertEqual(boss.next_death_laser_time, laser_time)

    def test_early_bosses_cast_one_extra_signature_below_half_health(self):
        game = self.game
        for level in range(1, 7):
            with self.subTest(level=level):
                game._start_game('easy', level)
                game._trigger_boss()
                boss = game.boss
                self.assertTrue(game._try_boss_signature(3000, opening=True))
                opening = boss.signature
                boss.hp = boss.max_hp / 2 - 1
                self.assertFalse(game._try_boss_signature(3001))
                game._update_boss_signature(opening.end_at)
                boss.hp = boss.max_hp / 2
                self.assertFalse(game._try_boss_signature(opening.end_at + 1))
                boss.hp -= 1
                self.assertTrue(game._try_boss_signature(opening.end_at + 1))
                extra = boss.signature
                game._update_boss_signature(extra.end_at)
                self.assertFalse(game._try_boss_signature(extra.end_at + 1))

    def test_animated_boss_signatures_exclude_bosses_with_custom_skills(self):
        from game_core.boss_skills import SIGNATURES

        game = self.game
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game._start_game('easy')
            for definition in config.BOSS_DEFS:
                with self.subTest(size=size, boss=definition['key']):
                    boss = game.boss = game._make_boss(definition)
                    boss.y = 55
                    if definition['key'] in ('boss_niu', 'boss_zongzong', 'boss_orochi',
                                              'boss_mecha_lizard', 'boss_ancient_whale'):
                        self.assertFalse(game._try_boss_signature(1000))
                        self.assertIsNone(boss.signature)
                        continue
                    self.assertTrue(game._try_boss_signature(1000, opening=True))
                    signature = boss.signature
                    self.assertEqual(signature.name, SIGNATURES[definition['key']][0])
                    self.assertEqual(signature.impact_at, 1000)
                    surface = pygame.Surface(config.SCR.get_size(), pygame.SRCALPHA)
                    for age in ((600,) if signature.key == 'boss' else (0, 240)):
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

    def test_claws_damage_at_their_visible_impact(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        for boss_index, age, shapes in ((0, 300, '_claws'),):
            with self.subTest(boss_index=boss_index):
                boss = game._make_boss(config.BOSS_DEFS[boss_index])
                boss.y = 55
                attack = BossSignature(boss, game.player, 1000, 1000)
                x, y, _ = getattr(attack, shapes)(age)[0]
                rect = pygame.Rect(round(x), round(y), 1, 1)
                self.assertFalse(attack.hit(boss, rect, attack.impact_at - 1))
                if boss_index == 1:
                    self.assertFalse(attack.hit(boss, rect, attack.impact_at + age - 1))
                self.assertTrue(attack.hit(boss, rect, attack.impact_at + age))
                self.assertFalse(attack.hit(boss, rect, attack.impact_at + age + 1))
                if boss_index == 0:
                    self.assertGreater(attack._claws(990)[0][1] - 145, config.SCREEN_HEIGHT)

    def test_lobster_claws_drop_left_then_right(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[0])
        boss.y = 55
        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        left, right = attack._claws(300)
        self.assertGreater(right[0] - left[0], 60)
        self.assertGreater(left[1], right[1])

        x, y, _ = attack._claws(540)[1]
        self.assertAlmostEqual(y, left[1])
        rect = pygame.Rect(round(x), round(y), 1, 1)
        self.assertFalse(attack.hit(boss, rect, attack.impact_at + 300))
        self.assertTrue(attack.hit(boss, rect, attack.impact_at + 540))
        self.assertGreater(attack.end_at, attack.impact_at + 1230)

    def test_lobster_claw_arm_hits_during_drop(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[0])
        boss.y = 55
        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        x, y, _ = attack._claws(400)[0]
        arm = pygame.Rect(round(x), round(y - 80), 1, 1)
        self.assertFalse(attack.hit(boss, arm.move(-25, 0), 1400))
        self.assertTrue(attack.hit(boss, arm, 1400))
        self.assertFalse(attack.hit(boss, arm, 1400))

    def test_crab_bubbles_launch_from_boss_and_pop_independently(self):
        game = self.game
        game._start_game('medium')
        game._start_level(2)
        game._trigger_boss()
        game.boss.y = 55
        game._try_boss_signature(1000, opening=True)
        signature = game.boss.signature
        start = signature._bubbles(0)
        end = signature._bubbles(860)
        self.assertTrue(all(abs(x - game.boss.x) < game.boss.w for x, y, r in start))
        self.assertTrue(all(y > start[i][1] for i, (x, y, r) in enumerate(end)))
        self.assertTrue(all(abs(y - config.SCREEN_HEIGHT / 2) < 1 for x, y, r in end))
        x, y, _ = signature._bubbles(400)[0]
        self.assertTrue(game._hit_crab_bubble(pygame.Rect(round(x), round(y), 1, 1), 1400))
        self.assertEqual(len(game.enemies), 1)
        self.assertAlmostEqual(game.enemies[0].x, x)
        self.assertFalse(game._hit_crab_bubble(pygame.Rect(round(x), round(y), 1, 1), 1400))
        game._update_boss_signature(1860)
        self.assertEqual(len(game.enemies), 2)
        game._update_boss_signature(1861)
        self.assertEqual(len(game.enemies), 2)

    def test_crab_bubbles_release_two_matching_chasers_once(self):
        from game_core.boss_skills import CRAB_BUBBLE_COLORS

        game = self.game
        game._start_game('medium')
        game._start_level(2)
        game._trigger_boss()
        self.assertTrue(game._try_boss_signature(1000, opening=True))
        game._update_boss_signature(1859)
        self.assertFalse(game.enemies)
        game._update_boss_signature(1860)
        game._update_boss_signature(1861)
        self.assertEqual(tuple(crab.chase_color for crab in game.enemies), CRAB_BUBBLE_COLORS)
        crab, partner = game.enemies
        for summon in (crab, partner):
            self.assertAlmostEqual(summon.speed, 1.9 * .70)
        self.assertEqual(crab.max_hp, game.boss.max_hp * .20)
        game.player.x = crab.x + 60
        game.player.y = crab.y - 60
        x, y = crab.x, crab.y
        for _ in range(20):
            crab.update(game.player)
            partner.update(game.player)
            self.assertGreaterEqual(partner.rect().left, crab.rect().right)
        self.assertGreater(crab.x, x)
        self.assertLess(crab.y, y)
        self.assertFalse(game._enemy_can_attack(crab, 99999))
        game._kill_enemy(crab)
        self.assertEqual(len(game.enemies), 1)

    def test_shark_throws_three_tridents_at_the_players_current_lane(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[3])
        boss.y = 55
        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        for age, lane in ((0, 130), (220, 240), (440, 350)):
            game.player.x = lane
            if age:
                attack.move(boss, 1000 + age - 1, game.player)
                self.assertEqual(len(attack._tridents(age - 1)), age // 220)
            attack.move(boss, 1000 + age, game.player)
            index, x, y = attack._tridents(age)[-1]
            self.assertEqual((index, x), (age // 220, game.player.rect().centerx))
            target = pygame.Rect(round(x), round(y + 21), 1, 1)
            self.assertTrue(attack.hit(boss, target, 1000 + age))
            self.assertFalse(attack.hit(boss, target, 1000 + age))
        attack.move(boss, 1660, game.player)
        self.assertEqual(len(attack._tridents(660)), 3)

    def test_shark_trident_shaft_can_hit_once(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[3])
        boss.y = 120
        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        attack.move(boss, 1000, game.player)
        _, x, y = attack._tridents(100)[0]
        shaft = pygame.Rect(round(x), round(y - 35), 1, 1)
        self.assertFalse(attack.hit(boss, shaft.move(15, 0), 1100))
        self.assertTrue(attack.hit(boss, shaft, 1100))
        self.assertFalse(attack.hit(boss, shaft, 1100))

    def test_dragon_sprays_downward_homing_fireballs_that_burst_near_player(self):
        game = self.game
        game._start_game('medium')
        game._start_level(5)
        game._trigger_boss()
        game.boss.y = 60
        self.assertTrue(game._try_boss_signature(1000, opening=True))
        for now in range(1000, 5001, 100):
            with patch.object(config, 'campaign_time_ms', now):
                game._update_boss_signature(now)
        self.assertEqual([shot.spawn_time for shot in game.boss_projectiles],
                         list(range(1000, 5000, 400)))
        shot = game.boss_projectiles[0]
        x, y = shot.x, shot.y
        with patch.object(config, 'campaign_time_ms', 1400):
            shot.update(x + 80, y - 20)
            self.assertGreater(shot.x, x)
            self.assertGreater(shot.y - y, 2 * (shot.x - x))
            self.assertTrue(shot.alive)
            shot.update(shot.x + 20, shot.y + 15)
            self.assertFalse(shot.alive)
            self.assertTrue(shot.bomb)

    def test_octopus_lash_hits_between_tentacle_joints(self):
        from game_core.boss_skills import BossSignature

        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[2])
        boss.y = 55
        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        points = next(attack._tentacles(boss, 300))
        a, b = points[-2:]
        target = pygame.Rect(round((a[0] + b[0]) / 2), round((a[1] + b[1]) / 2), 1, 1)
        self.assertTrue(attack.hit(boss, target, 1300))
        self.assertFalse(attack.hit(boss, target, 1300))

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

        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        start_y = boss.y + boss.h * .58
        attack.target_x, attack.target_y = boss.x + boss.w, start_y
        for age in (LASH_MS / 4, LASH_MS / 2):
            for side, points in zip((-1, 1), attack._tentacles(boss, age)):
                start, tip = points[0], points[-1]
                path_length = sum(math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]))
                self.assertAlmostEqual(start[0], boss.x + side * boss.w * .18)
                self.assertAlmostEqual(start[1], boss.y + boss.h * .54)
                root_offset = math.hypot(boss.w * .14, boss.h * .04)
                self.assertAlmostEqual(path_length, config.SCREEN_HEIGHT - start_y, delta=root_offset)
                self.assertLess(math.dist(start[:2], tip[:2]), path_length)
                self.assertGreater(tip[0] - start[0], abs(tip[1] - start[1]))
        target = pygame.Rect(round(attack.target_x), round(start_y), 1, 1)
        self.assertTrue(attack.hit(boss, target, 1000 + LASH_MS // 2))

        boss = game.boss = game._make_boss(config.BOSS_DEFS[5])
        boss.x, boss.y = game.player.x, 55
        original = boss.x, boss.y
        boss.signature = attack = BossSignature(boss, game.player, 1000, 1000)
        with patch.object(game, '_player_is_invincible', return_value=False), \
                patch.object(game, '_damage_player', return_value=True) as damage:
            for now in range(2000, 3400, 17):
                if game._update_boss_signature(now):
                    break
            damage.assert_called_once_with(now, game.player_hp, '被深渊封潮击败！', hit_feedback=True)
        self.assertGreater(boss.y, original[1])
        game._update_boss_signature(attack.end_at)
        self.assertEqual((boss.x, boss.y), original)
        self.assertIsNone(boss.signature)
        boss.signature = BossSignature(boss, game.player, 1000, 1000)
        game.player.move(110, 0)
        with patch.object(game, '_player_is_invincible', return_value=False), \
                patch.object(game, '_damage_player') as damage:
            for now in range(2000, 2000 + 1520 + 2000, 17):
                game._update_boss_signature(now)
            damage.assert_not_called()

    def test_abyss_dive_starts_at_current_position_and_moves_toward_target(self):
        from game_core.boss_skills import BossSignature, CHASE_MS

        self.assertEqual(CHASE_MS, round(1520 / 1.15))
        game = self.game
        game._start_game('medium')
        boss = game._make_boss(config.BOSS_DEFS[5])
        boss.x, boss.y = 100, 55
        game.player.x = 300
        attack = BossSignature(boss, game.player, 1000, 0, campaign=True)
        origin = boss.x, boss.y
        attack.move(boss, 1000, game.player)
        self.assertEqual((boss.x, boss.y), origin)
        attack.move(boss, 1000 + CHASE_MS // 2, game.player)
        self.assertAlmostEqual(boss.x, (origin[0] + attack.target_x) / 2)
        self.assertGreater(boss.y, origin[1])
        attack.move(boss, 1000 + CHASE_MS, game.player)
        self.assertAlmostEqual(boss.x, attack.target_x)

    def test_abyss_bite_waits_below_even_when_it_misses(self):
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
            self.assertGreater(boss.rect().top, config.SCREEN_HEIGHT)
            self.assertFalse(attack.chasing)
            self.assertFalse(attack.hit(boss, boss.rect(), reentry))
            attack.move(boss, reentry + 1999)
            self.assertGreater(boss.rect().top, config.SCREEN_HEIGHT)
            attack.move(boss, reentry + 2350)
            self.assertLess(boss.y, config.SCREEN_HEIGHT)
            self.assertGreater(boss.y, origin[1])
            game._update_boss_signature(attack.end_at)
            self.assertEqual((boss.x, boss.y), origin)

    def test_campaign_abyss_dives_then_surfaces_after_two_seconds(self):
        from game_core.boss_skills import BITE_REPEAT_MS, CHASE_MS

        game = self.game
        game._start_game('medium')
        game._start_level(6)
        game._trigger_boss()
        boss = game.boss
        boss.y = 60
        self.assertTrue(game._try_boss_signature(1000, opening=True))
        attack = boss.signature
        first = attack.impact_at
        second = first + BITE_REPEAT_MS
        for start in (first, second):
            if start == second:
                game.player.move(80, 0)
                attack.move(boss, second - 1, game.player)
                self.assertFalse(attack.chasing)
                self.assertGreater(boss.rect().top, config.SCREEN_HEIGHT)
                self.assertIsNone(attack.second_target_x)
            attack.move(boss, start, game.player)
            if start == first:
                self.assertEqual(boss.y, 60)
            else:
                self.assertGreater(boss.y - boss.h * .22, config.SCREEN_HEIGHT)
            if start == second:
                self.assertEqual(boss.x, game.player.rect().centerx)
            for now in range(start, start + CHASE_MS, 16):
                attack.move(boss, now, game.player)
                if attack.hit(boss, game.player.rect(), now):
                    if start == first:
                        game._damage_player(now, game.player_hp, '测试首次撕咬')
                        self.assertEqual(game.state, GameState.INFINITE_COUNTDOWN)
                        self.assertIs(boss.signature, attack)
                    break
            else:
                self.fail('The bite missed a stationary target')
        game._update_boss_signature(attack.end_at)
        self.assertEqual(boss.y, 60)

    def test_boss_name_and_hp_use_visible_hd_labels(self):
        game = self.game
        game._start_game('medium')
        for size in ((844, 390), (390, 844)):
            config.update_mobile_view(size)
            game.resize_view()
            for level in (2, 8):
                game._start_level(level)
                game._trigger_boss()
                game.level_title_until = 0
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
