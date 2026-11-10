import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame

from game_core import animation, config, entities, special_bosses


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

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

    def test_boss_animation_matches_special_state(self):
        niu = SimpleNamespace(bdef={'key': 'boss_niu'}, last_pattern='vortex', animation_attack_at=1000)
        with patch.object(animation, 'frame', wraps=animation.frame) as pick:
            self.assertIsNotNone(animation.boss_frame(niu, 1300))
            pick.assert_called_with('boss_niu_vortex', 4)
        zong = SimpleNamespace(bdef={'key': 'boss_zongzong'}, fusion_mode='rage', fusion_started_at=1000)
        with patch.object(animation, 'frame', wraps=animation.frame) as pick:
            self.assertIsNotNone(animation.boss_frame(zong, 1300))
            pick.assert_called_with('boss_zongzong_rage', 2)

    def test_niu_uses_eight_frames_for_attacks_and_laser(self):
        niu = SimpleNamespace(bdef={'key': 'boss_niu'}, last_pattern='axes', animation_attack_at=1000)
        with patch.object(animation, 'frame', wraps=animation.frame) as pick:
            for index in range(8):
                self.assertIsNotNone(animation.boss_frame(niu, 1000 + 75 * index))
                pick.assert_called_with('boss_niu_attack', index)
            niu.laser_warning_start = 1000
            niu.laser_active_until = 0
            animation.boss_frame(niu, 1350)
            pick.assert_called_with('boss_niu_laser', 7)
            niu.laser_warning_start = 0
            niu.laser_active_until = 4000
            animation.boss_frame(niu, 2150)
            pick.assert_called_with('boss_niu_laser', 2)

    def test_niu_action_sheets_have_eight_frames(self):
        for action in ('attack', 'vortex', 'lightning', 'laser'):
            with self.subTest(action=action):
                frames = [animation.frame('boss_niu_' + action, i) for i in range(8)]
                self.assertGreaterEqual(len({pygame.image.tostring(frame, 'RGBA') for frame in frames}), 7)
                self.assertIs(animation.frame('boss_niu_' + action, 8), frames[0])

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

    def test_niu_shield_break_uses_large_shield_fragments(self):
        shield = special_bosses.image_asset('effects/boss_niu_shield.png', (450, 150))
        fragments = special_bosses._niu_shield_fragments(shield)
        self.assertEqual(len(fragments), 5)
        self.assertTrue(all(fragment.get_bounding_rect().width >= 70 for fragment in fragments))
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.y = 60
        boss.shield_break_at = 1000
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        with patch.object(special_bosses, '_niu_shield_fragments', wraps=special_bosses._niu_shield_fragments) as split:
            boss._draw_shield_break(canvas, 1300)
            split.assert_called_once()
        self.assertGreater(canvas.get_bounding_rect().width, boss.w * 2)

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
        self.assertGreater(tinted.r, tinted.g * 2)

    def test_niu_axe_slam_windup_has_no_warning_lines(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.axe_slam_start = 1000
        canvas = pygame.Surface((1200, 1000), pygame.SRCALPHA)
        for elapsed in (400, 1900, 3400):
            with self.subTest(elapsed=elapsed), patch.object(special_bosses.Draw, 'line') as line:
                boss._draw_axe_slam(canvas, 1000 + elapsed)
                line.assert_not_called()

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

    def test_niu_running_reverses_direction_and_laser_takes_priority(self):
        boss = special_bosses.NiuBoss(config.BOSS_DEFS[6], config.DIFFICULTY_PRESETS['easy'])
        boss.entered = True
        right = boss._body_frame(1000)
        self.assertIsNotNone(right)
        boss.movement_timer = 16
        self.assertIsNot(boss._body_frame(1000), right)
        boss.movement_timer = 0
        boss.running_left = True
        left = boss._body_frame(1000)
        self.assertEqual(pygame.image.tostring(left, 'RGBA'),
                         pygame.image.tostring(pygame.transform.flip(right, True, False), 'RGBA'))
        boss.laser_active_until = 2000
        self.assertIs(boss._body_frame(1000), special_bosses.image_asset('bosses/boss_niu_laser.png'))

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
                     'boss_niu_attack', 'boss_zongzong_attack'):
            self.assertIsNotNone(animation.frame(name, 0), name)


if __name__ == '__main__':
    unittest.main()
