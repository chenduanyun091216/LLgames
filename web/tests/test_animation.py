import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame

from game_core import animation, config, entities, orochi, special_bosses
from game_core.render import RenderSurface


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_orochi_fireball_rotates_at_output_size_and_reuses_the_pose(self):
        art = pygame.Surface((100, 200), pygame.SRCALPHA)
        shot = orochi.OrochiFireball(120, 90, (255, 80, 40), art)
        shot.angle = 30
        for output, expected in (((2560, 1440), (67, 131)), ((1920, 1080), (50, 98))):
            with self.subTest(output=output):
                pixels = pygame.Surface(output, pygame.SRCALPHA)
                view = RenderSurface(pixels, (960, 540), output, (0, 0))
                with patch.object(pygame.transform, 'rotate', wraps=pygame.transform.rotate) as rotate:
                    shot.draw(view)
                    shot.draw(view)
                rotate.assert_called_once()
                self.assertEqual(rotate.call_args.args[0].get_size(), expected)
                self.assertEqual(rotate.call_args.args[1], 30)

    def test_player_motion_only_when_position_changes(self):
        player = entities.Player()
        player.move(0, 0)
        self.assertFalse(player.animation_moving)
        player.move(3, 0)
        self.assertTrue(player.animation_moving)
        player.move(0, 0)
        self.assertFalse(player.animation_moving)

    def test_action_frame_finishes(self):
        self.assertEqual(animation.action_frame(1000, 1000), 0)
        self.assertEqual(animation.action_frame(1000, 1300), 2)
        self.assertIsNone(animation.action_frame(1000, 1700))

    def test_q_style_player_animation_priority_and_recovery(self):
        player = entities.Player()
        player.character = 'fire'
        player.animation_move_at = 1000
        player.shoot(1000)
        player.animation_skill = 'fireball'
        player.animation_skill_at = 1000
        player.animation_hit_at = 1000
        with patch.object(animation, 'frame', side_effect=lambda name, index: name):
            self.assertEqual(animation.player_frame(player, 'player_fire', 1000, 0), 'player_fire_down')
            self.assertEqual(animation.player_frame(player, 'player_fire', 1000), 'player_fire_hurt')
            self.assertEqual(animation.player_frame(player, 'player_fire', 1300), 'player_fire_fireball')
            player.animation_skill_at = None
            player.shoot(1400)
            self.assertEqual(animation.player_frame(player, 'player_fire', 1450), 'player_fire_attack')
            player.animation_move_at = 1630
            self.assertEqual(animation.player_frame(player, 'player_fire', 1640), 'player_fire_run')
            self.assertEqual(animation.player_frame(player, 'player_fire', 1800), 'player_fire_idle')

    def test_fisher_animation_switches_between_grenade_shoot_walk_and_idle(self):
        player = entities.Player()
        player.animation_move_at = 1000
        player.shoot(1000)
        player.animation_skill = 'fisher_grenade'
        player.animation_skill_at = 1000
        with patch.object(animation, 'frame', side_effect=lambda name, index: (name, index)):
            self.assertEqual(animation.player_frame(player, 'player1', 1150), ('player1_fisher_grenade', 1))
            player.animation_skill_at = None
            self.assertEqual(animation.player_frame(player, 'player1', 1045), ('player1_attack', 1))
            player.animation_move_at = 1190
            self.assertEqual(animation.player_frame(player, 'player1', 1200), ('player1_run', 2))
            self.assertEqual(animation.player_frame(player, 'player1', 1440), ('player1_idle', 2))

    def test_zongzong_expressions_follow_hits_without_changing_damage(self):
        enemy = entities.Enemy(next(e for e in config.ENEMY_DEFS if e.get('zongzong')))
        enemy.y = enemy.ENTRY_DAMAGE_Y
        enemy.hit_by('pistol', 0.1)
        self.assertEqual(enemy.zong_expression, 0)
        enemy.hit_by('pistol', 0.1)
        self.assertGreaterEqual(enemy.zong_expression, 1)
        enemy.hit_by('pistol', 1000)
        self.assertEqual(enemy.zong_expression, 3)
        self.assertTrue(enemy.is_killed('pistol'))

    def test_zongzong_draws_progressive_expressions(self):
        enemy = entities.Enemy(next(e for e in config.ENEMY_DEFS if e.get('zongzong')))
        enemy.y = enemy.ENTRY_DAMAGE_Y
        clock = (config, 'game_ticks')
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(*clock, return_value=1000), patch.object(entities.animation, 'frame', wraps=entities.animation.frame) as pick:
            enemy.hit_by('pistol', 0.1)
            enemy.draw(canvas)
            pick.assert_called_with('zongzong_hurt', 0)
        with patch.object(*clock, return_value=2000):
            enemy.hit_by('pistol', 0.1)
        with patch.object(*clock, return_value=2300), patch.object(entities.animation, 'frame', wraps=entities.animation.frame) as pick:
            enemy.draw(canvas)
            pick.assert_called_with('zongzong_hurt', 1)
        with patch.object(*clock, return_value=3000):
            enemy.hit_by('pistol', 1000)
        with patch.object(*clock, return_value=3500), patch.object(entities.animation, 'frame', wraps=entities.animation.frame) as pick:
            enemy.draw(canvas)
            pick.assert_called_with('zongzong_hurt', 3)

    def test_zongzong_rotates_both_idle_bodies_at_output_resolution(self):
        definition = next(boss for boss in config.BOSS_DEFS if boss['key'] == 'boss_zongzong')
        boss = special_bosses.ZongBoss(definition, config.DIFFICULTY_PRESETS['easy'])
        logical = pygame.Surface((960, 540), pygame.SRCALPHA)
        pixels = pygame.Surface((2560, 1440), pygame.SRCALPHA)
        view = RenderSurface(pixels, (960, 540), pixels.get_size(), (0, 0))
        with patch.object(config, 'game_ticks', return_value=400), \
                patch.object(pygame.transform, 'rotate', wraps=pygame.transform.rotate) as rotate:
            boss.draw(logical)
            original_sizes = [call.args[0].get_size() for call in rotate.call_args_list]
            rotate.reset_mock()
            boss.draw(view)
        self.assertEqual(len(original_sizes), 2)
        self.assertEqual([call.args[0].get_size() for call in rotate.call_args_list],
                         [tuple(view.length(side) for side in size) for size in original_sizes])

    def test_zongzong_animation_matches_rage_state(self):
        zong = SimpleNamespace(bdef={'key': 'boss_zongzong'}, fusion_mode='rage', fusion_started_at=1000)
        with patch.object(animation, 'frame', wraps=animation.frame) as pick:
            self.assertIsNotNone(animation.boss_frame(zong, 1300))
            pick.assert_called_with('boss_zongzong_rage', 2)

    def test_niu_shield_image_is_drawn_only_while_active(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.shield_until = 2000
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(config, 'game_ticks', return_value=1000), \
                patch('game_core.special_bosses.image_asset', wraps=special_bosses.image_asset) as load:
            boss.draw(canvas)
            self.assertEqual(load.call_args.args[0], 'effects/boss_niu_shield.png')
            self.assertIsNotNone(special_bosses.image_asset(*load.call_args.args))
        with patch.object(config, 'game_ticks', return_value=2000), \
                patch('game_core.special_bosses.image_asset') as load:
            boss.draw(canvas)
            load.assert_not_called()

    def test_niu_shield_is_sized_for_output_before_it_breaks(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        pixels = pygame.Surface((2560, 1440), pygame.SRCALPHA)
        view = RenderSurface(pixels, (960, 540), pixels.get_size(), (0, 0))
        boss.shield_break_at = 1000
        width = round(boss.w * 2.5)
        with patch.object(special_bosses, '_niu_shield_fragments',
                          wraps=special_bosses._niu_shield_fragments) as split:
            special_bosses.NiuShieldShard(300, 200, 2, width).draw(view)
        self.assertEqual(split.call_args.args[0].get_size(),
                         (view.length(width), view.length(round(width / 3))))

    def test_niu_shield_break_effect_follows_damage_and_expiry(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.shield_thresholds = ()
        boss.shield_until = 2000
        with patch.object(config, 'game_ticks', return_value=1000):
            boss.hit_by('pistol', boss.max_hp * .16)
        self.assertEqual(boss.shield_until, 0)

        self.assertEqual(boss.shield_break_at, 1000)
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(boss, '_draw_shield_break') as draw, patch.object(config, 'game_ticks', return_value=1200):
            boss.draw(canvas)
            draw.assert_called_once()
        with patch.object(boss, '_draw_shield_break') as draw, patch.object(config, 'game_ticks', return_value=1900):
            boss.draw(canvas)
            draw.assert_not_called()
        boss.shield_break_at = None
        boss.shield_until = 2000
        with patch.object(config, 'game_ticks', return_value=2100):
            boss.update()
        self.assertEqual(boss.shield_break_at, 2000)
        self.assertEqual(boss.shield_until, 0)

    def test_niu_shield_hits_flash_and_play_metal_sound(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.shield_until = 2000
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(config, 'game_ticks', return_value=1000), \
                patch.object(special_bosses, 'play_sound') as sound, \
                patch('game_core.entities.play_sound') as body_sound:
            boss.hit_by('pistol', 1)
            boss.hit_by('pistol', 1)
            sound.assert_called_once_with('niu_shield_hit')
            body_sound.assert_not_called()
            self.assertFalse(boss.hit_flashes)
            self.assertEqual(boss.shield_hit_at, 1000)
            with patch.object(boss, '_draw_shield_hit', wraps=boss._draw_shield_hit) as flash:
                boss.draw(canvas)
                flash.assert_called_once()

    def test_niu_shield_break_uses_large_shield_fragments(self):
        shield = special_bosses.image_asset('effects/boss_niu_shield.png', (450, 150))
        fragments = special_bosses._niu_shield_fragments(shield)
        self.assertEqual(len(fragments), 5)
        self.assertTrue(all(fragment.get_bounding_rect().width >= 70 for fragment in fragments))
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        shard = special_bosses.NiuShieldShard(300, 200, 2, 450)
        shard.draw(canvas)
        self.assertGreaterEqual(canvas.get_bounding_rect().width, 70)

    def test_niu_axe_slam_scales_and_tints_boss_sprite(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.axe_slam_start = 1000
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(config, 'game_ticks', return_value=1500), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            boss.draw(canvas)
        self.assertGreater(draw.call_args.args[1].get_width(), boss.surface.get_width())
        self.assertEqual(draw.call_args.args[1].get_at((0, 0)).a, 0)
        original = pygame.Surface((1, 1), pygame.SRCALPHA)
        original.fill((200, 200, 200, 255))
        tinted = entities._niu_slam_sprite(original).get_at((0, 0))
        self.assertGreater(tinted.r, tinted.g)
        self.assertGreater(tinted.g, tinted.b)

    def test_niu_axe_slam_windup_has_no_warning_lines(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.axe_slam_start = 1000
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        for elapsed in (400, 1900, 3400):
            with self.subTest(elapsed=elapsed), patch.object(special_bosses.Draw, 'line') as line:
                boss._draw_axe_slam(canvas, 1000 + elapsed)
                line.assert_not_called()

    def test_niu_axe_slam_draws_sprite_below_boss(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.x, boss.y = 240, 60
        boss.axe_slam_start = 1000
        size = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        for scale in (1, 2):
            with self.subTest(scale=scale):
                output = tuple(value * scale for value in size)
                canvas = pygame.Surface(output, pygame.SRCALPHA)
                target = RenderSurface(canvas, size, output, (0, 0)) if scale > 1 else canvas
                boss._draw_axe_slam(target, 2000)
                bounds = canvas.get_bounding_rect()
                hitbox = boss.axe_slam_rect(2000)
                self.assertGreater(bounds.width, hitbox.width * scale)
                self.assertGreaterEqual(bounds.top, hitbox.top * scale)
                self.assertGreaterEqual(bounds.bottom, hitbox.bottom * scale)

    def test_niu_axe_slam_preserves_blade_and_tassel_when_handle_extends(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.x, boss.y = 240, 60
        boss.axe_slam_start = 1000
        art = special_bosses.image_asset('effects/boss_niu_slam_axe.png')
        for size, output in (((480, 960), (480, 960)), ((960, 540), (1920, 1080)),
                             ((960, 540), (2560, 1440))):
            with self.subTest(output=output), \
                    patch.object(config, 'SCREEN_WIDTH', size[0]), \
                    patch.object(config, 'SCREEN_HEIGHT', size[1]):
                canvas = pygame.Surface(output, pygame.SRCALPHA)
                target = RenderSurface(canvas, size, output, (0, 0))
                boss._draw_axe_slam(target, 2100)
                logical_width = max(70, round(boss.w * 1.65))
                width = target.length(logical_width)
                height = max(1, round(width * art.get_height() / art.get_width()))
                original = pygame.transform.flip(
                    special_bosses.scale_surface_cached(art, (width, height)), False, True)
                hitbox = boss.axe_slam_rect(2100)
                bottom = min(size[1], hitbox.bottom + round(logical_width * .12))
                x, bottom = target.point((boss.x, bottom))
                preserved = height * 3 // 4
                actual = canvas.subsurface((x - width // 2, bottom - preserved, width, preserved))
                expected = original.subsurface((0, height - preserved, width, preserved))
                self.assertEqual(pygame.image.tobytes(actual, 'RGBA'),
                                 pygame.image.tobytes(expected, 'RGBA'))

    def test_boss_laser_and_zong_attack_select_their_own_frames(self):
        crab = SimpleNamespace(bdef={'key': 'boss_crab'}, laser_warning_start=1000, laser_active_until=0)
        with patch.object(animation, 'frame', wraps=animation.frame) as pick:
            self.assertIsNotNone(animation.boss_frame(crab, 1300))
            pick.assert_called_with('boss_crab_laser', 1)
        crab.laser_warning_start = 0
        crab.laser_active_until = 2000
        with patch.object(animation, 'frame', wraps=animation.frame) as pick:
            self.assertIsNotNone(animation.boss_frame(crab, 1500))
            pick.assert_called_with('boss_crab_laser', 1)
        for phase, action in ((1, 'bomb'), (2, 'wave')):
            boss = SimpleNamespace(bdef={'key': 'boss_zongzong'}, fusion_mode=None,
                                   attack_phase=phase, animation_attack_at=1000)
            with patch.object(animation, 'frame', wraps=animation.frame) as pick:
                self.assertIsNotNone(animation.boss_frame(boss, 1300))
                pick.assert_called_with('boss_zongzong_' + action, 2)

    def test_sprite_sheet_bosses_draw_attack_frames(self):
        clock = (config, 'game_ticks')
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        for definition in config.BOSS_DEFS:
            if definition['key'] in ('boss_niu', 'boss_orochi', 'boss_mecha_lizard', 'boss_ancient_whale'):
                continue
            with self.subTest(boss=definition['key']):
                cls = special_bosses.ZongBoss if definition['key'] == 'boss_zongzong' else entities.Boss
                boss = cls(definition, config.DIFFICULTY_PRESETS['easy'])
                boss.y = 60
                boss.entered = True
                boss.animation_attack_at = 1000
                with patch.object(*clock, return_value=1300), patch.object(entities.animation, 'boss_frame', wraps=entities.animation.boss_frame) as pick:
                    boss.draw(canvas)
                    self.assertTrue(pick.called)
                    self.assertIsNotNone(pick(boss, 1300))

    def test_niu_scooter_reverses_direction_without_laser(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.entered = True
        right = boss._body_frame(1000)
        self.assertIsNotNone(special_bosses.image_asset('bosses/boss_niu_scooter.png'))
        self.assertIsNot(boss._body_frame(1200), right)
        boss.running_left = True
        left = boss._body_frame(1000)
        self.assertEqual(pygame.image.tostring(left, 'RGBA'),
                         pygame.image.tostring(pygame.transform.flip(right, True, False), 'RGBA'))
        self.assertFalse(boss.can_laser())
        with patch.object(special_bosses.random, 'choice', return_value='axes') as choose:
            boss.attack(1000, 400, opening=True)
        self.assertNotIn('laser', choose.call_args.args[0])

    def test_niu_stops_patrol_and_dismounts_until_attack_ends(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.entered = True
        boss.last_pattern = 'bullets'
        boss.animation_attack_at = 1000
        x = boss.x
        with patch.object(config, 'game_ticks', return_value=1599):
            boss.update()
        self.assertEqual(boss.x, x)
        self.assertIs(boss._body_frame(1599).get_parent(),
                      special_bosses.image_asset('bosses/boss_niu_actions.png'))
        with patch.object(config, 'game_ticks', return_value=1600):
            boss.update()
        self.assertNotEqual(boss.x, x)
        self.assertIsNot(boss._body_frame(1600), boss._body_frame(1599))

    def test_niu_axe_attack_cycles_through_four_poses(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.entered = True
        boss.last_pattern = 'axes'
        boss.animation_attack_at = 1000
        sheet = special_bosses.image_asset('bosses/boss_niu_axe_sequence.png')
        frames = [boss._body_frame(1000 + 150 * index) for index in range(4)]
        self.assertTrue(all(frame.get_parent() is sheet for frame in frames))
        self.assertEqual(len({frame.get_offset() for frame in frames}), 4)

    def test_niu_shield_shards_launch_separately_and_aim_at_launch(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.shield_break_at = 1000
        with patch.object(config, 'game_ticks', return_value=1000):
            shards = boss.launch_shield_shards()
            self.assertEqual(len(shards), 5)
            self.assertFalse(boss.launch_shield_shards())
        first, second, *waiting = shards
        self.assertGreater(second.x - first.x, first.width / 5)
        starting_position = first.origin
        boss.x += 20
        boss.y += 12
        first.follow_shield(boss)
        self.assertEqual(first.origin, (starting_position[0] + 20, starting_position[1] + 12))
        left, right = boss.x - 220, boss.x + 220
        target_y = boss.y + boss.h + 400
        with patch.object(config, 'game_ticks', return_value=2499):
            for shard in shards:
                shard.update(left, target_y)
                self.assertEqual((shard.x, shard.y), shard.origin)
        with patch.object(config, 'game_ticks', return_value=2550):
            for shard in shards:
                shard.update(left, target_y)
            self.assertLess(first.x, first.prev_x)
            self.assertAlmostEqual(((first.x - first.prev_x) ** 2 + (first.y - first.prev_y) ** 2) ** .5, 70)
            self.assertEqual((second.x, second.y), second.origin)
            self.assertFalse(second.hits_rect(pygame.Rect(*second.origin, 2, 2)))
        with patch.object(config, 'game_ticks', return_value=2850):
            for shard in shards:
                shard.update(right, target_y)
        self.assertLess(first.x, first.prev_x)
        self.assertGreater(second.x, second.prev_x)
        self.assertTrue(second.hits_rect(pygame.Rect(*second.origin, 2, 2)))
        self.assertTrue(all((shard.x, shard.y) == shard.origin for shard in waiting))
        with patch.object(config, 'game_ticks', return_value=3750):
            for shard in shards:
                shard.update(right, target_y)
        self.assertTrue(all((shard.x, shard.y) != shard.origin for shard in shards))
        launched_origin = first.origin
        boss.x += 20
        first.follow_shield(boss)
        self.assertEqual(first.origin, launched_origin)

    def test_first_six_bosses_play_distinct_idle_and_attack_poses(self):
        for definition in config.BOSS_DEFS[:6]:
            with self.subTest(boss=definition['key']):
                boss = entities.Boss(definition, config.DIFFICULTY_PRESETS['easy'])
                boss.animation_attack_at = 1000
                idle = [animation.boss_idle_frame(definition['key'], boss.surface, i * 135)
                        for i in range(6)]
                attack = [animation.boss_frame(boss, 1000 + i * 75) for i in range(8)]
                for frames in (idle, attack):
                    self.assertEqual(len({pygame.image.tobytes(frame, 'RGBA') for frame in frames}),
                                     len(frames))
                self.assertIsNone(animation.boss_frame(boss, 1600))
                if boss.can_laser():
                    boss.bdef = {**definition, 'campaign_level': 2}
                    boss.laser_active_until = 3000
                    self.assertIs(animation.boss_frame(boss, 1000), animation.boss_frame(boss, 2000))

    def test_boss_action_size_compensates_for_transparent_padding(self):
        boss = entities.Boss(config.BOSS_DEFS[1], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        idle = pygame.Surface((100, 100), pygame.SRCALPHA)
        action = idle.copy()
        idle.fill('white', (10, 10, 80, 80))
        action.fill('white', (20, 20, 60, 60))
        boss.surface = idle
        boss.breath_base = pygame.transform.scale(idle, (130, 130))
        boss._breath_src = idle
        with patch.object(config, 'game_ticks', return_value=boss.breath_start_time), \
                patch.object(animation, 'boss_frame', return_value=action), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            boss.draw(canvas)
        visible = draw.call_args.args[1].get_bounding_rect(min_alpha=33)
        self.assertGreaterEqual(visible.height, 72)
        self.assertLessEqual(visible.height, 82)

    def test_abyss_idle_sprite_is_smaller_without_changing_hitbox(self):
        boss = entities.Boss(config.BOSS_DEFS[5], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        hitbox = boss.rect().copy()
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(config, 'game_ticks', return_value=boss.breath_start_time), \
                patch.object(entities.animation, 'boss_frame', return_value=None), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            boss.draw(canvas)
        sprite = draw.call_args.args[1]
        self.assertLess(sprite.get_width(), boss.surface.get_width())
        self.assertEqual(boss.rect(), hitbox)

    def test_boss_flashes_during_laser_preparation(self):
        boss = entities.Boss(config.BOSS_DEFS[1], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.laser_warning_start = 1000
        frame = pygame.Surface((20, 20), pygame.SRCALPHA)
        frame.fill((50, 60, 70, 255))
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(entities.animation, 'boss_frame', return_value=frame), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            with patch.object(config, 'game_ticks', return_value=1000):
                boss.draw(canvas)
                bright = draw.call_args.args[1].get_at((0, 0))
            with patch.object(config, 'game_ticks', return_value=1150):
                boss.draw(canvas)
                normal = draw.call_args.args[1].get_at((0, 0))
        self.assertGreater(bright.r, normal.r)
        self.assertEqual(bright.a, normal.a)

    def test_2k_boss_flash_keeps_full_animation_source(self):
        boss = entities.Boss(config.BOSS_DEFS[1], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.laser_warning_start = 1000
        frame = pygame.Surface((512, 512), pygame.SRCALPHA)
        frame.fill((50, 60, 70, 255))
        canvas = pygame.Surface((2560, 1440), pygame.SRCALPHA)
        view = RenderSurface(canvas, (960, 540), canvas.get_size(), (0, 0))
        with patch.object(config, 'game_ticks', return_value=1000), \
                patch.object(entities.animation, 'boss_frame', return_value=frame), \
                patch.object(entities, 'blit_lit_sprite') as draw:
            boss.draw(view)
        source = draw.call_args.kwargs['source']
        self.assertEqual(source.get_size(), (512, 512))
        self.assertGreater(source.get_at((0, 0)).r, frame.get_at((0, 0)).r)

    def test_every_skill_has_a_dedicated_sheet(self):
        skills = {
            'fire': ('fire_wall', 'fireball'),
            'ice': ('ice_floor', 'ice_balls'),
            'water': ('water_heal', 'water_boost'),
            'radiation': ('lightning', 'magnetic_storm', 'radiation_laser', 'dart_shield'),
        }
        for character, names in skills.items():
            for name in names:
                self.assertIsNotNone(animation.frame('player_' + character + '_' + name, 2), name)

    def test_assets_cover_all_characters_and_bosses(self):
        for name in ('player1_back', 'player_fire_run',
                     'player_ice_run', 'player_water_run', 'player_radiation_run',
                     'boss_lobster_attack', 'boss_crab_attack', 'boss_octopus_attack',
                     'boss_shark_attack', 'boss_dragon_attack', 'boss_attack',
                     'boss_zongzong_attack'):
            self.assertIsNotNone(animation.frame(name, 0), name)


if __name__ == '__main__':
    unittest.main()
