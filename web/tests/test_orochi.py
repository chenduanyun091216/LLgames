import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from game_core import config
from game_core.game import Game, GameState
from game_core.orochi import OrochiBoss


class OrochiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def setUp(self):
        clock = patch.object(config, 'campaign_time_ms', 1000)
        clock.start()
        self.addCleanup(clock.stop)
        game = Game()
        game.difficulty = config.DIFFICULTY_PRESETS['medium']
        game._start_level(11)
        self.assertEqual(game.state, GameState.BOSS_FIGHT)
        self.assertIsInstance(game.boss, OrochiBoss)
        self.game = game
        self.boss = game.boss
        self.boss.y = 60
        self.boss.entered = True

    def tick(self, age):
        config.campaign_time_ms = 1000 + age
        self.boss.update()

    def start(self, skill):
        self.boss._start_skill(skill, 1000)

    def test_eight_homing_shots_at_200_ms_intervals(self):
        self.start('volley')
        for i in range(8):
            self.tick(i * 200)
            self.assertEqual(len(self.boss.shots), i + 1)
            shot = self.boss.shots[-1]
            self.assertTrue(shot.homing)
            self.assertEqual(shot.color, self.boss.FIRE_COLORS[i % 2])
            self.tick(i * 200 + 199)
            self.assertEqual(len(self.boss.shots), i + 1)

    def test_eight_paired_impacts(self):
        self.start('slam')
        for i in range(8):
            self.tick(i * self.boss.SLAM_ROUND + self.boss.SLAM_IMPACT)
            self.assertEqual(len(self.boss.impacts), (i + 1) * 2)
        self.tick(8 * self.boss.SLAM_ROUND)
        self.assertIsNone(self.boss.skill)

    def test_split_heads_form_a_row_then_randomly_dive_and_return(self):
        self.start('split')
        positions = self.boss.split_positions()
        self.assertEqual([round(x) for x, y in positions], [round(self.boss._lane_x(i)) for i in range(8)])
        self.assertEqual(len({y for x, y in positions}), 1)
        self.assertGreater(self.boss._snake_rect(*positions[0]).w, 34)
        with patch('game_core.orochi.random.choice', return_value=3):
            self.tick(1000)
        self.tick(1100)
        self.assertGreater(self.boss.split_positions()[3][1], positions[3][1])
        self.assertEqual(self.boss.split_positions()[2], positions[2])

    def test_diving_head_exits_screen_before_returning_to_row(self):
        self.start('split')
        with patch('game_core.orochi.random.choice', return_value=3):
            self.tick(700)
        for age in range(800, 1500, 100):
            self.tick(age)
        x, y = self.boss.split_positions()[3]
        self.assertGreater(y, config.SCREEN_HEIGHT)
        self.assertLess(self.boss._snake_rect(x, y).top, config.SCREEN_HEIGHT)
        self.tick(1500)
        x, y = self.boss.split_positions()[3]
        self.assertEqual((x, y), (self.boss._lane_x(3), 150))
        self.assertIsNone(self.boss.split_dive)

    def test_split_heads_track_charge_once_and_regroup_only_after_all_are_defeated(self):
        self.start('split')
        self.assertEqual(self.boss.split_hp, [self.boss.max_hp * .03] * 8)
        self.boss.update(100, 300)
        self.tick(1000)
        config.campaign_time_ms = 2000
        first = self.boss._snake_rect(*self.boss.split_positions()[0])
        self.boss.hit_by('sniper', self.boss.head_max_hp * .8, hit_rect=first)
        self.assertTrue(self.boss.split_charged[0])
        self.assertGreater(self.boss.split_charge_until[0], config.game_ticks())
        self.tick(10000)
        self.assertEqual(self.boss.skill, 'split')
        for i in range(8):
            x, y = self.boss.split_positions()[i]
            self.boss.hit_by('sniper', self.boss.head_max_hp * 2, hit_rect=self.boss._snake_rect(x, y))
        self.assertTrue(self.boss.split_regroup_at)
        self.assertEqual(self.boss.skill, 'split')
        self.tick(11000)
        self.assertIsNone(self.boss.skill)

    def test_orochi_hazards_and_fireballs_deal_two_damage(self):
        self.start('volley')
        self.tick(0)
        self.assertEqual(self.boss.shots[0].damage, 2)
        self.start('laser')
        self.game.player_invincible_until = 0
        self.game.player_hp = 5
        with patch.object(self.boss, 'hazard_hits', return_value=True):
            self.game._update_special_boss_hazards(2000)
        self.assertEqual(self.game.player_hp, 3)

    def test_head_hits_show_feedback_without_changing_body_health(self):
        for skill in ('split', 'storm'):
            self.start(skill)
            rect = self.boss.hitboxes()[0]
            previous_hp = self.boss.hp
            self.boss.hit_by('pistol', 1, hit_rect=rect)
            self.assertEqual(self.boss.hp, previous_hp)
            self.assertTrue(self.boss.hit_flashes)
            self.assertTrue(rect.collidepoint(self.boss.hit_flashes[-1][:2]))
            self.boss.hit_flashes.clear()

    def test_lightning_hits_visible_split_head(self):
        from game_core.entities import Lightning
        self.start('split')
        head = self.boss.hitboxes()[0]
        bolt = Lightning(*head.center, [self.boss], 1)
        bolt.spawn_time = 900
        self.game.lightnings.append(bolt)
        self.game._update_lightnings(1000)
        self.assertLess(self.boss.split_hp[0], self.boss.head_max_hp)
        self.assertTrue(self.boss.hit_flashes)

    def test_all_campaign_bosses_draw_hit_sparks_and_play_throttled_damage_sound(self):
        for chapter in range(1, 12):
            with self.subTest(chapter=chapter), patch('game_core.entities.play_sound') as sound:
                self.game._start_level(chapter)
                if self.game.boss is None:
                    self.game._trigger_boss()
                boss = self.game.boss
                boss.y, boss.entered = 60, True
                rect = boss.hitboxes()[0]
                boss.hit_by('pistol', 1, hit_rect=rect)
                sound.assert_called_once_with('boss_hit')
                self.assertEqual(boss.hit_flashes, [(*rect.center, config.game_ticks())])
                canvas = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
                boss._draw_hit_flashes(canvas, config.game_ticks())
                self.assertNotEqual(canvas.get_at(rect.center)[:3], (0, 0, 0))
                boss.hit_by('pistol', 1, hit_rect=rect)
                self.assertEqual(sound.call_count, 1)
                with patch.object(config, 'campaign_time_ms', 1100):
                    boss.hit_by('pistol', 1, hit_rect=rect)
                self.assertEqual(sound.call_count, 2)

    def test_orochi_head_sound_requires_damage_and_shares_body_cooldown(self):
        with patch('game_core.entities.play_sound') as sound:
            self.start('storm')
            self.boss.hit_by('pistol', 0, hit_rect=self.boss.head_rect(0))
            self.assertFalse(sound.called)
            self.boss.skill = None
            self.boss.hit_by('pistol', 1, hit_rect=self.boss.rect())
            self.start('storm')
            self.boss.hit_by('pistol', 1, hit_rect=self.boss.head_rect(0))
            sound.assert_called_once_with('boss_hit')
            with patch.object(config, 'campaign_time_ms', 1100):
                self.boss.hit_by('pistol', 1, hit_rect=self.boss.head_rect(1))
            with patch.object(config, 'campaign_time_ms', 1200):
                self.boss.invincible_until = 1300
                self.boss.hit_by('pistol', 1, hit_rect=self.boss.head_rect(0))
            self.assertEqual(sound.call_count, 2)

    def test_hit_sparks_fade_on_normal_and_high_resolution_surfaces(self):
        from game_core.render import RenderSurface

        for scale in (1, 3):
            surface = pygame.Surface((64 * scale, 64 * scale))
            target = surface if scale == 1 else RenderSurface(surface, (64, 64), surface.get_size(), (0, 0))
            brightness = []
            for elapsed in (0, 110, 150):
                surface.fill((0, 0, 0))
                self.boss.hit_flashes = [(32, 32, 1000)]
                self.boss._draw_hit_flashes(target, 1000 + elapsed)
                brightness.append(sum(pygame.image.tobytes(surface, 'RGB')))
            self.assertGreater(brightness[0], brightness[1])
            self.assertGreater(brightness[1], 0)
            self.assertEqual(brightness[2], 0)
            self.assertFalse(self.boss.hit_flashes)

    def test_laser_has_three_moving_heads_and_three_seconds_of_damage(self):
        self.start('laser')
        heads = self.boss._laser_head_rects(900)
        self.assertEqual(len(heads), 3)
        self.assertNotEqual(heads, self.boss._laser_head_rects(1200))
        self.assertEqual(len(self.boss.hitboxes()), 3)
        self.assertEqual(self.boss.LASER_END - self.boss.LASER_WARNING, 3000)
        for path in self.boss.laser_paths(900):
            self.assertEqual(path[-1][1], config.SCREEN_HEIGHT)
            x, y = path[len(path) // 2]
            self.assertTrue(self.boss.hazard_hits(pygame.Rect(x - 2, y - 2, 4, 4), 900))
        self.assertFalse(self.boss.hazard_hits(pygame.Rect(self.boss.x, 350, 5, 5), 500))
        for i, path in enumerate(self.boss.laser_paths(900)):
            point = pygame.Rect(path[0][0] + 14, 350, 1, 1)
            self.assertEqual(self.boss.hazard_hits(point, 900), i == 1)

    def test_storm_bubbles_are_damage_targets_and_pop_individually(self):
        self.start('storm')
        self.assertEqual(len(self.boss.bubble_art), 8)
        for art in self.boss.bubble_art:
            self.assertIsNotNone(art)
            self.assertGreater(art.get_at(art.get_rect().center).a, 75)
        self.boss.hp = self.boss.max_hp / 2
        positions = [self.boss.head_rect(i) for i in range(8)]
        self.assertEqual(list(self.boss.hitboxes()), positions)
        self.boss.hit_by('pistol', 1, hit_rect=positions[7])
        self.assertEqual(list(self.boss.hitboxes()), positions)
        self.assertFalse(self.boss.bubble_breaks)
        self.boss.hit_by('sniper', self.boss.max_hp * .05, hit_rect=positions[7])
        self.assertEqual(list(self.boss.hitboxes()), positions[:7])
        self.assertEqual([len(effect.particles) for effect in self.boss.bubble_breaks], [18, 5])
        self.assertEqual(self.boss.bubble_breaks[0].particles[0]['color'], self.boss.BUBBLE_COLORS[7])
        self.assertEqual([self.boss.head_rect(i) for i in range(8)], positions)
        for rect in reversed(positions[:7]):
            self.boss.hit_by('sniper', self.boss.max_hp * .05, hit_rect=rect)
        self.assertIsNone(self.boss.skill)
        self.tick(10000)
        self.assertEqual(self.boss.hp, self.boss.max_hp / 2)
        self.assertEqual(self.boss.invincible_until, 0)
        for _ in range(25):
            self.boss.update()
        self.assertFalse(self.boss.bubble_breaks)

    def test_split_snakes_use_distinct_looping_swim_frames(self):
        frames = self.boss.split_frames
        self.assertEqual(len(frames), 12)
        self.assertEqual(len({pygame.image.tobytes(frame, 'RGBA') for frame in frames}), 12)
        surface = pygame.Surface((100, 150))
        rect = self.boss._snake_rect(50, 130)
        with patch.object(self.boss, '_draw_skill_sprite') as draw:
            self.boss._draw_split_snake(surface, 0, 0, rect)
            draw.assert_called_with(surface, frames[0], rect)
            self.boss._draw_split_snake(surface, 1, self.boss.SPLIT_STEP, rect)
            draw.assert_called_with(surface, frames[4], rect)
            self.boss._draw_split_snake(surface, 0, len(frames) * self.boss.SPLIT_STEP, rect)
            draw.assert_called_with(surface, frames[0], rect)

    def test_slam_heads_fall_straight_and_land_before_disappearing(self):
        self.start('slam')
        begin = self.boss.SLAM_IMPACT - self.boss.SLAM_FALL_MS
        self.assertFalse(self.boss._slam_rects(begin - 1))
        in_flight = self.boss._slam_rects(begin + 150)
        landed = self.boss._slam_rects(self.boss.SLAM_IMPACT)
        self.assertEqual(len(landed), 2)
        for moving, stationary in zip(in_flight, landed):
            self.assertEqual(moving.centerx, stationary.centerx)
            self.assertTrue(self.boss.hazard_hits(moving, begin + 150))
            self.assertEqual(stationary.bottom, config.GAME_AREA_BOTTOM)
        self.assertFalse(self.boss._slam_rects(self.boss.SLAM_IMPACT + self.boss.SLAM_HOLD_MS))

    def test_storm_timeout_heals_and_grants_three_seconds_immunity(self):
        self.start('storm')
        self.boss.hp = self.boss.max_hp / 2
        self.tick(9999)
        self.assertEqual(self.boss.hp, self.boss.max_hp / 2)
        self.tick(10000)
        self.assertEqual(self.boss.hp, self.boss.max_hp * .90)
        self.tick(12999)
        self.boss.hit_by('pistol')
        self.assertEqual(self.boss.hp, self.boss.max_hp * .90)
        self.tick(13000)
        self.boss.hit_by('pistol')
        self.assertEqual(self.boss.hp, self.boss.max_hp * .90 - 1)

    def test_level_ten_transitions_directly_to_orochi(self):
        self.game._start_level(10)
        self.game._trigger_boss()
        self.game.boss.hp = 0
        self.game.update()
        self.assertEqual(self.game.state, GameState.LEVEL_TRANSITION)
        config.campaign_time_ms = self.game.level_transition_end
        self.game.update()
        self.assertEqual(self.game.current_level, 11)
        self.assertEqual(self.game.state, GameState.BOSS_FIGHT)
        self.assertIsInstance(self.game.boss, OrochiBoss)
        self.assertFalse(self.game.enemies)

    def test_shift_minus_opens_orochi_from_campaign(self):
        self.game._start_level(10)
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_MINUS, mod=pygame.KMOD_SHIFT)
        self.game.handle_events([event])
        self.assertEqual(self.game.current_level, 11)
        self.assertEqual(self.game.state, GameState.BOSS_FIGHT)
        self.assertIsInstance(self.game.boss, OrochiBoss)

    def test_hud_next_opens_orochi_from_level_ten(self):
        self.game._start_level(10)
        _, _, next_level = self.game._hud_controls()
        self.game._handle_hud_click(next_level.center)
        self.assertEqual(self.game.current_level, 11)
        self.assertEqual(self.game.state, GameState.BOSS_FIGHT)
        self.assertIsInstance(self.game.boss, OrochiBoss)

    def test_random_opening_at_three_seconds_then_regular_order(self):
        self.boss.entered = False
        self.boss.y = 59
        config.campaign_time_ms = 3000
        self.game.update()
        self.assertTrue(self.boss.entered)
        config.campaign_time_ms = 3999
        self.game.update()
        self.assertIsNone(self.boss.skill)
        with patch('game_core.orochi.random.choice', return_value='laser') as pick:
            config.campaign_time_ms = 4000
            self.game.update()
            pick.assert_called_once_with(self.boss.SKILLS)
        self.assertEqual(self.boss.skill, 'laser')
        for expected in self.boss.SKILLS:
            self.boss._finish_skill(10000)
            self.boss.attack(10000 + self.boss.attack_interval, self.boss.x)
            self.assertEqual(self.boss.skill, expected)

    def test_burst_damage_cannot_skip_thresholds_and_final_success_dissolves(self):
        for threshold in (.5, .01):
            self.boss.hit_by('sniper', self.boss.max_hp * 2)
            self.assertEqual(self.boss.hp, self.boss.max_hp * threshold)
            self.assertEqual(self.boss.skill, 'storm')
            config.campaign_time_ms += 2000
            for i in reversed(range(8)):
                self.boss.hit_by('sniper', self.boss.max_hp * .05, hit_rect=self.boss.head_rect(i))
        self.assertEqual(self.boss.hp, 0)
        self.assertIsNotNone(self.boss.death_at)
        self.assertTrue(self.boss.death_particles)
        self.assertFalse(self.game._settle_boss_if_killed())
        config.campaign_time_ms += self.boss.DEATH_DURATION
        self.assertTrue(self.game._settle_boss_if_killed())
        self.assertEqual(self.game.state, GameState.VICTORY)

    def test_final_timeout_heals_once_then_boss_can_be_killed_normally(self):
        self.boss.hit_by('sniper', self.boss.max_hp * 2)
        self.tick(10000)
        self.tick(13000)
        half_hp = self.boss.max_hp * .5
        final_hp = self.boss.max_hp * .01
        self.boss.hit_by('sniper', self.boss.hp - half_hp)
        self.assertAlmostEqual(self.boss.hp, half_hp)
        self.assertIsNone(self.boss.skill)
        self.boss.hit_by('sniper', self.boss.hp - final_hp)
        self.assertEqual(self.boss.skill, 'storm')
        self.assertTrue(self.boss.final_storm)
        self.tick(23000)
        self.assertAlmostEqual(self.boss.hp, self.boss.max_hp * .41)
        self.tick(26000)
        self.boss.hit_by('sniper', self.boss.hp - final_hp)
        self.assertAlmostEqual(self.boss.hp, final_hp)
        self.assertIsNone(self.boss.skill)
        self.boss.hit_by('sniper', final_hp + 1)
        self.assertIsNotNone(self.boss.death_at)

    def test_draws_all_skill_poses_on_regular_and_scaled_surfaces(self):
        from game_core.render import RenderSurface
        size = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        surface = pygame.Surface(size, pygame.SRCALPHA)
        view = (size[0] * 2, size[1] * 2)
        scaled = RenderSurface(pygame.Surface(view, pygame.SRCALPHA), size, view, (0, 0), track_damage=True)
        for skill, age in (('volley', 400), ('slam', 1120), ('split', 1400), ('laser', 1300), ('storm', 2010)):
            config.campaign_time_ms = 1000
            self.start(skill)
            if skill == 'storm':
                self.boss.update(240, 380)
            self.tick(age)
            if skill == 'storm':
                self.boss.draw_storm_lightning(surface, config.game_ticks())
                self.boss.draw_storm_lightning(scaled, config.game_ticks())
            self.boss.draw(surface)
            self.boss.draw(scaled)
        self.boss._start_death(config.game_ticks())
        self.boss.draw(surface)
        self.boss.draw(scaled)

    def test_infinite_level_ten_advances_to_orochi_before_wrapping(self):
        game = self.game
        game._begin_infinite_run(10)
        game._trigger_infinite_boss()
        game.boss.hp = 0
        game.update()
        self.assertEqual(game.chapter, 11)
        self.assertEqual(game.infinite_background_level, 11)
        self.assertTrue(game.level_enemy_defs)
        self.assertEqual(game.state, GameState.BOSS_FIGHT)
        self.assertGreater(game.level_title_until, config.game_ticks())
        self.assertIsInstance(game.boss, OrochiBoss)
        self.assertEqual(game.boss.bdef['campaign_level'], 11)
        game.boss._start_death(config.game_ticks())
        config.campaign_time_ms += game.boss.DEATH_DURATION
        game.update()
        self.assertEqual(game.chapter, 12)
        self.assertEqual(game.infinite_background_level, 1)
        game._trigger_infinite_boss()
        self.assertEqual(game.boss.bdef['key'], 'boss_lobster')

    def test_infinite_shift_shortcuts_select_chapters_nine_to_eleven(self):
        game = self.game
        game._start_infinite_game()
        for key, chapter, boss in ((pygame.K_0, 11, 'boss_orochi'),
                                   (pygame.K_9, 9, 'boss_mecha_lizard'),
                                   (pygame.K_MINUS, 10, 'boss_ancient_whale')):
            with self.subTest(chapter=chapter):
                event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_SHIFT)
                game.handle_events([event])
                self.assertTrue(game.infinite_mode)
                self.assertEqual(game.chapter, chapter)
                self.assertEqual(game.infinite_background_level, chapter)
                if chapter != 11:
                    game._trigger_infinite_boss()
                self.assertEqual(game.boss.bdef['key'], boss)

    def test_idle_heads_animate_and_the_loop_returns_to_its_first_pose(self):
        first = self.boss._idle_frame(1000)
        middle = self.boss._idle_frame(1600)
        self.assertIsNotNone(first)
        self.assertIsNot(first, middle)
        self.assertIs(first, self.boss._idle_frame(1000 + self.boss.IDLE_PERIOD))
        bottom = pygame.Rect(0, first.get_height() * 4 // 5, first.get_width(), first.get_height() // 5)
        self.assertEqual(pygame.image.tobytes(first.subsurface(bottom), 'RGBA'),
                         pygame.image.tobytes(middle.subsurface(bottom), 'RGBA'))

    def test_fireballs_start_at_the_current_animated_mouth(self):
        self.start('volley')
        for i in range(8):
            self.tick(i * 200)
            shot = self.boss.shots[-1]
            self.assertEqual((shot.x, shot.y), self.boss._mouth(i, config.game_ticks()))
        self.assertNotEqual(self.boss._mouth(3, 1000), self.boss._mouth(3, 1600))

    def test_storm_head_hp_and_healing_scale_with_max_hp_and_remaining_head_hp(self):
        self.boss.max_hp = 230
        self.boss.hp = 115
        self.start('storm')
        self.assertEqual(len(self.boss.head_hp), 8)
        for hp in self.boss.head_hp:
            self.assertAlmostEqual(hp, 11.5)
        for i in range(5):
            self.boss.hit_by('sniper', 11.5, hit_rect=self.boss.head_rect(i))
        self.boss.hit_by('pistol', 1, hit_rect=self.boss.head_rect(5))
        self.assertEqual(len(self.boss.hitboxes()), 3)
        self.tick(9999)
        self.assertEqual(self.boss.hp, 115)
        self.tick(10000)
        self.assertAlmostEqual(self.boss.hp, 115 + 230 * .15 - 1)
        self.assertEqual(self.boss.invincible_until, 14000)

    def test_storm_locks_warning_and_strikes_after_one_second(self):
        self.start('storm')
        player = self.game.player
        self.boss.update(player.x, player.y)
        self.assertFalse(self.boss.hazard_hits(player.rect(), 999))
        self.assertTrue(self.boss.hazard_hits(player.rect(), 1000))
        corner = pygame.Rect(round(player.x + 49), round(player.y - 34), 1, 1)
        self.assertFalse(self.boss.hazard_hits(corner, 1000))
        self.assertFalse(self.boss.hazard_hits(player.rect().move(-150, 0), 1000))
        self.game.player_invincible_until = 0
        self.game.player_hp = 5
        config.campaign_time_ms = 2000
        self.boss.update(player.x - 150, player.y)
        self.game._update_special_boss_hazards(2000)
        self.game._update_special_boss_hazards(2000)
        self.assertEqual(self.game.player_hp, 3)
        self.assertFalse(self.boss.hazard_hits(player.rect(), self.boss.THUNDER_INTERVAL))
