"""The same attack objects run on desktop, browser and online authority."""
import os
import math
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame

from game_core import config
from game_core.abyss_bosses import (AbyssProjectile, AncientWhaleBoss,
                                    MechaLizardBoss, ABYSS_PROJECTILE_FIELDS,
                                    RAIL_EXTEND_MS, RAIL_GAP_MS, RAIL_LASH_MS)
from game_core.render import RenderSurface


class AbyssBossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def boss(self, cls):
        key = 'boss_mecha_lizard' if cls is MechaLizardBoss else 'boss_ancient_whale'
        definition = dict(key=key, name=key, enemy_key='lobster', base_hp=100,
                          speed=.6, attack_interval=4000, projectile_count=3,
                          campaign_level=9 if cls is MechaLizardBoss else 10,
                          campaign_tier=1, size=(290, 215))
        boss = cls(definition, config.DIFFICULTY_PRESETS['medium'])
        boss.entered, boss.y = True, 60
        return boss

    def test_opening_starts_at_three_seconds_before_regular_cooldown(self):
        for cls in (MechaLizardBoss, AncientWhaleBoss):
            with self.subTest(boss=cls.__name__):
                boss = self.boss(cls)
                boss.fight_start_time = 100
                self.assertFalse(boss.should_attack(3099))
                with patch('game_core.entities.random.choice', side_effect=lambda skills: skills[0]), \
                        patch.object(boss, '_choose_attack_skill', wraps=boss._choose_attack_skill) as choose:
                    self.assertTrue(boss.should_attack(3100))
                    boss.attack(3100, boss.x)
                    choose.assert_called_once()
                self.assertIn(boss.current_skill, boss.SKILLS)
                self.assertFalse(boss.should_attack(7100))
                if cls is AncientWhaleBoss:
                    self.assertNotEqual(boss.current_skill, 'whale_suction')
                    boss.x, boss.y = boss._center_x(), 18
                self.assertTrue(boss.should_attack(8100))

    def test_whale_keeps_selected_suction_while_swimming_to_center(self):
        boss = self.boss(AncientWhaleBoss)
        with patch('game_core.entities.random.choice', side_effect=lambda skills: skills[-1]):
            boss.attack(3100, boss.x)
        boss.x, boss.y = boss._center_x() + 12, 24
        now = boss.last_attack_time + boss.attack_interval
        with patch.object(config, 'game_ticks', return_value=now), \
                patch('game_core.entities.random.choice', side_effect=lambda skills: skills[-1]) as choose:
            boss.update()
            self.assertFalse(boss.should_attack(now))
            boss.update()
            self.assertTrue(boss.should_attack(now))
            boss.attack(now, boss.x)
            choose.assert_called_once()
        self.assertEqual(boss.current_skill, 'whale_suction')

    def test_all_eight_skills_start_and_expire(self):
        for cls in (MechaLizardBoss, AncientWhaleBoss):
            boss = self.boss(cls)
            seen = []
            skills = cls.CAST_SKILLS if cls is AncientWhaleBoss else cls.SKILLS
            for index in range(len(skills)):
                now = 10000 + index * 10000
                with patch.object(config, 'game_ticks', return_value=now):
                    shots = boss.attack(now, config.SCREEN_WIDTH * .6)
                    seen.append(boss.current_skill)
                    self.assertEqual(bool(shots), boss.current_skill != 'whale_suction')
                    for shot in shots:
                        if shot.warning_ms:
                            self.assertEqual(shot.rect().size, (0, 0))
                            self.assertFalse(shot.hits_rect(pygame.Rect(0, 0, 3000, 3000)))
                            self.assertEqual(shot.block_rect().size, (0, 0))
                for shot in shots:
                    with patch.object(config, 'game_ticks', return_value=now + shot.warning_ms):
                        shot.update(config.SCREEN_WIDTH * .6, config.GAME_AREA_BOTTOM)
                        self.assertTrue(shot.is_active())
                        self.assertGreater(shot.rect().width, 0)
                    with patch.object(config, 'game_ticks', return_value=now + shot.max_lifetime):
                        shot.update()
                        self.assertFalse(shot.alive)
                        self.assertFalse(shot.hits_rect(pygame.Rect(0, 0, 3000, 3000)))
            self.assertCountEqual(seen, skills)
            with patch.object(config, 'game_ticks', return_value=60000):
                boss.attack(60000, 480)
                self.assertNotEqual(boss.current_skill, seen[-1])

    def test_whale_draws_all_eight_frames_for_each_motion(self):
        boss = self.boss(AncientWhaleBoss)
        boss.breath_start_time = boss.skill_started_at = 1000
        surface = pygame.Surface((1, 1))
        for skill, (_, period) in boss.ANIMATION.items():
            with self.subTest(skill=skill), patch.object(boss, '_draw_suction'), \
                    patch('game_core.abyss_bosses._blit') as blit:
                boss.current_skill = skill
                frames = set()
                for frame in range(8):
                    now = 1000 + math.ceil(frame * period / 8)
                    with patch.object(config, 'game_ticks', return_value=now):
                        boss.draw(surface)
                    frames.add(pygame.image.tobytes(blit.call_args.args[1], 'RGBA'))
                self.assertEqual(len(frames), 8)
                last_frame = blit.call_args.args[1]
                with patch.object(config, 'game_ticks', return_value=1000 + period):
                    boss.draw(surface)
                if skill == 'whale_swallow':
                    self.assertEqual(pygame.image.tobytes(blit.call_args.args[1], 'RGBA'),
                                     pygame.image.tobytes(last_frame, 'RGBA'))

    def test_whale_rain_has_a_moving_center_gap(self):
        boss = self.boss(AncientWhaleBoss)
        boss._pending_attack_skill = 'tidal_crescent'
        shots = boss.attack(1000, 480)
        self.assertEqual([shot.warning_ms for shot in shots[:3]], [0, 110, 220])
        self.assertLess(shots[-1].warning_ms, 5000)
        first_row = sorted(shot.x for shot in shots[:3])
        next_row = sorted(shot.x for shot in shots[9:12])
        self.assertNotEqual(first_row, next_row)
        self.assertEqual(first_row[0], next_row[0])
        self.assertEqual(first_row[-1], next_row[-1])
        for start in range(0, len(shots), 3):
            row = sorted(shots[start:start + 3], key=lambda shot: shot.x)
            for left, right in zip(row, row[1:]):
                self.assertGreater(right.x - left.x, (left.width + right.width) / 2)

    def test_whale_takes_half_damage_only_during_crescent_cast(self):
        boss = self.boss(AncientWhaleBoss)
        boss._pending_attack_skill = 'tidal_crescent'
        boss.attack(1000, 480)
        hp = boss.hp
        for now, source in ((1000, 'bullet'), (5999, 'skill'), (6000, 'skill')):
            with patch.object(config, 'game_ticks', return_value=now):
                boss.hit_by('pistol', 10, source=source)
        self.assertAlmostEqual(hp - boss.hp, 20)

    def test_geyser_launch_lifts_player_and_locks_fire_temporarily(self):
        from game_core.entities import Player

        player = Player()
        player.y = 500
        player.start_geyser_lift(1000)
        player.update_geyser_lift(1200)
        self.assertLess(player.y, 500)
        self.assertFalse(player.can_shoot(1449))
        player.update_geyser_lift(1450)
        self.assertAlmostEqual(player.y, 365)
        self.assertTrue(player.can_shoot(1450))

    def test_whale_geysers_rise_in_three_distinct_pairs_then_shatter(self):
        boss = self.boss(AncientWhaleBoss)
        boss._pending_attack_skill = 'rune_geyser'
        shots = boss.attack(1000, 480)
        self.assertEqual(len({shot.x for shot in shots}), 6)
        self.assertEqual([shot.warning_ms for shot in shots], [800, 800, 1900, 1900, 3000, 3000])
        shot = shots[0]
        self.assertAlmostEqual(shot.y + shot.height, config.SCREEN_HEIGHT)
        rect = pygame.Rect(round(shot.x) - 4, round(shot.y) + 30, 8, 8)
        with patch.object(config, 'game_ticks', return_value=1600):
            shot.update()
            self.assertGreater(shot.bounds().height, 0)
            self.assertGreater(shot.bounds().top, config.SCREEN_HEIGHT - 100)
            self.assertFalse(shot.hits_rect(rect))
        with patch.object(config, 'game_ticks', return_value=2170):
            shot.update()
            self.assertTrue(shot.hits_rect(rect))
        with patch.object(config, 'game_ticks', return_value=2230):
            shot.update()
            self.assertFalse(shot.hits_rect(rect))

    def test_whale_suction_pulls_and_requires_twenty_percent_max_hp_in_five_seconds(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from game_core.game import Game

        game = Game.__new__(Game)
        game.boss = boss = self.boss(AncientWhaleBoss)
        boss._pending_attack_skill = 'whale_suction'
        boss.hp = boss.max_hp * .75
        game.player = SimpleNamespace(x=boss.x + 100, y=500, move=Mock())
        enemy = SimpleNamespace(x=boss.x + 100, y=300, h=50, temple_kind='')
        game.enemies = [enemy]
        boss.attack(1000, 480)
        self.assertEqual(game._player_fire_interval_multiplier(1000), 2)
        self.assertFalse(game._update_whale_suction(2000))
        self.assertLess(game.player.move.call_args.args[1], 0)
        self.assertLess(enemy.y, 300)
        boss.hp = boss.suction_start_hp - boss.max_hp * .20
        self.assertFalse(game._update_whale_suction(5999))
        self.assertEqual(boss.current_skill, '')
        self.assertEqual(game._player_fire_interval_multiplier(5999), 1)
        boss._pending_attack_skill = 'whale_suction'
        boss.attack(10000, 480)
        with patch.object(game, '_defeat_players_by_suction') as defeat:
            boss.hp -= boss.max_hp * .19
            self.assertFalse(game._update_whale_suction(14999))
            self.assertTrue(game._update_whale_suction(15000))
            defeat.assert_not_called()
            self.assertTrue(boss.swallowing)
            before_y = game.player.y
            self.assertTrue(game._update_whale_suction(15350))
            self.assertLess(game.player.y, before_y)
            defeat.assert_not_called()
            self.assertTrue(game._update_whale_suction(15700))
            self.assertAlmostEqual(game.player.y, boss.y + boss.h * .81)
            defeat.assert_called_once_with(15700)
            self.assertFalse(game._update_whale_suction(15701))

    def test_pearl_volley_spawns_only_three_and_accelerates(self):
        boss = self.boss(AncientWhaleBoss)
        boss._pending_attack_skill = 'ancient_pearl'
        shots = boss.attack(1000, boss.x)
        self.assertEqual(len(shots), 3)
        self.assertEqual([shot.angle for shot in shots], [-48, 0, 48])
        shot = shots[1]
        distances = []
        for now in (1900, 2000, 2100):
            before = shot.y
            with patch.object(config, 'game_ticks', return_value=now):
                shot.update()
            distances.append(shot.y - before)
        self.assertGreater(distances[0], 0)
        self.assertLess(distances[0], distances[1])
        self.assertLess(distances[1], distances[2])

    def test_pearl_arms_after_six_bounces_and_bursts_three_seconds_later(self):
        with patch.object(config, 'game_ticks', return_value=1000):
            shot = AbyssProjectile('ancient_pearl', config.SCREEN_WIDTH / 2, 180,
                                   angle=90, speed=12, warning_ms=0, active_ms=20000)
        now = 1000
        while now < 12000 and not shot.pearl_burst_at:
            now += 16
            with patch.object(config, 'game_ticks', return_value=now):
                shot.update()
        self.assertEqual(shot.pearl_bounces, 6)
        self.assertEqual(shot.pearl_burst_at, now + 3000)
        with patch.object(config, 'game_ticks', return_value=now + 2999):
            shot.update()
            self.assertTrue(shot.alive)
        with patch.object(config, 'game_ticks', return_value=now + 3000):
            shot.update()
            self.assertFalse(shot.alive)
            self.assertEqual(len(shot.pearl_fragments()), 6)

    def test_whip_is_held_by_the_moving_boss(self):
        boss = self.boss(MechaLizardBoss)
        boss._pending_attack_skill = 'plasma_rail'
        with patch.object(config, 'game_ticks', return_value=1000):
            rail = boss.attack(1000, 300)[0]
        start = rail.x, rail.y
        boss.x += 80
        now = 1000 + rail.warning_ms + RAIL_EXTEND_MS
        with patch.object(config, 'game_ticks', return_value=now):
            boss.sync_weapon_mount(rail, now)
            rail.update(700, 600)
            self.assertEqual(rail._rail_points()[0], (start[0] + 80, start[1]))
            self.assertTrue(rail.hits_rect(pygame.Rect(round(rail.x) - 5, 400, 10, 10)))
            self.assertFalse(rail.hits_rect(pygame.Rect(300, 400, 10, 10)))
            self.assertEqual(rail.damage, 2)

    def test_boss_missiles_launch_one_at_a_time(self):
        boss = self.boss(MechaLizardBoss)
        with patch.object(config, 'game_ticks', return_value=1000):
            shots = boss._skill_shots('guided_missile', 480, 600)
        for index, shot in enumerate(shots):
            now = shot.spawn_time + shot.warning_ms
            self.assertEqual(sum(m.is_active(now) for m in shots), index + 1)
            if index:
                self.assertGreaterEqual(shot.warning_ms - shots[index - 1].warning_ms, 650)
        first, second, _ = shots
        now = first.spawn_time + first.warning_ms + 20
        with patch.object(config, 'game_ticks', return_value=now):
            first.update(480, 600)
        first_x, second_x = first.x, second.x
        boss.x += 70
        for shot in shots:
            boss.sync_weapon_mount(shot, now)
        self.assertEqual(first.x, first_x)
        self.assertAlmostEqual(second.x, second_x + 70)

    def test_factory_missiles_leave_trails_and_take_separate_paths(self):
        boss = self.boss(MechaLizardBoss)
        target_x = boss.x
        with patch.object(config, 'game_ticks', return_value=1000):
            shots = boss._skill_shots('guided_missile', target_x, 600)
        crossings = {}
        for now in range(1000, 6500, 20):
            with patch.object(config, 'game_ticks', return_value=now):
                for shot in shots:
                    shot.update(target_x, 600)
                    if shot.is_active() and shot.y >= 550 and shot.missile_pass == 0:
                        crossings.setdefault(shot, shot.x)
        xs = [crossings[shot] for shot in shots]
        self.assertGreater(xs[1] - xs[0], 45)
        self.assertGreater(xs[2] - xs[1], 45)
        for shot in shots:
            self.assertEqual(len(shot.missile_trail), 23)
            self.assertNotEqual(shot.missile_trail[0], shot.missile_trail[-1])

    def test_factory_charge_does_not_draw_position_guides(self):
        surface = pygame.Surface((960, 720), pygame.SRCALPHA)
        boss = self.boss(MechaLizardBoss)
        with patch.object(config, 'game_ticks', return_value=1000), \
                patch('game_core.abyss_bosses.Draw.line') as line, \
                patch('game_core.abyss_bosses.Draw.lines') as lines, \
                patch('game_core.abyss_bosses.Draw.rect') as rect:
            for skill in boss.SKILLS:
                for shot in boss._skill_shots(skill, 480, 600):
                    shot.draw(surface)
            line.assert_not_called()
            lines.assert_not_called()
            rect.assert_not_called()

    def test_missile_tracks_on_both_descents_and_returns_from_below(self):
        with patch.object(config, 'game_ticks', return_value=1000):
            shot = AbyssProjectile('guided_missile', 400, 150, speed=4,
                                   warning_ms=1000, active_ms=16000)
        self.assertTrue(shot.unblockable)
        first_angles, second_angles = [], []
        lowest = 0
        returned_y = config.SCREEN_HEIGHT
        for now in range(2000, 17000, 20):
            with patch.object(config, 'game_ticks', return_value=now):
                shot.update(800 if now < 3300 else 120, 600)
            lowest = max(lowest, shot.y)
            if shot.missile_pass == 0:
                first_angles.append(shot.angle)
            if shot.missile_pass == 2:
                returned_y = min(returned_y, shot.y)
                second_angles.append(shot.angle)
            if not shot.alive:
                break
        self.assertGreater(max(first_angles), 10)
        self.assertGreater(lowest, config.SCREEN_HEIGHT)
        self.assertLess(returned_y, 180)
        self.assertTrue(any(math.sin(math.radians(angle)) < -.2 for angle in second_angles))
        self.assertFalse(shot.alive)
        self.assertGreater(shot.y, config.SCREEN_HEIGHT)

    def test_rail_extends_before_three_lashes_and_hits_along_the_curve(self):
        with patch.object(config, 'game_ticks', return_value=1000):
            rail, = self.boss(MechaLizardBoss)._skill_shots('plasma_rail', 400, 0)
        rail.whip_directions = 0b101
        for index, direction in enumerate((0, 1, -1, 1)):
            elapsed = (RAIL_EXTEND_MS // 2 if not index else
                       RAIL_EXTEND_MS + (index - 1) * (RAIL_LASH_MS + RAIL_GAP_MS) + RAIL_LASH_MS // 2)
            with patch.object(config, 'game_ticks', return_value=1000 + rail.warning_ms + elapsed):
                rail.update()
                points = rail._rail_points()
                x, y = points[-1]
                self.assertEqual(rail.hits_rect(pygame.Rect(round(x) - 4, round(y) - 4, 8, 8)), bool(index))
                if direction == 0:
                    self.assertEqual(x, rail.x)
                    self.assertLess(y, config.GAME_AREA_BOTTOM)
                else:
                    self.assertEqual(y, config.GAME_AREA_BOTTOM)
                    self.assertGreater(direction * (x - rail.x), 100)
                    self.assertTrue(any(direction * (px - rail.x) < -50 for px, _ in points))
                    self.assertFalse(rail.hits_rect(pygame.Rect(round(rail.x) - 4, round(y) - 4, 8, 8)))

    def test_whip_drifts_harmlessly_between_strikes_and_can_hit_again(self):
        boss = self.boss(MechaLizardBoss)
        boss._pending_attack_skill = 'plasma_rail'
        with patch.object(config, 'game_ticks', return_value=1000):
            rail, = boss.attack(1000, 400)
        first_strike = 1000 + rail.warning_ms + RAIL_EXTEND_MS
        target = object()
        poses = []
        for delay in (RAIL_GAP_MS // 3, RAIL_GAP_MS * 2 // 3):
            with patch.object(config, 'game_ticks', return_value=first_strike + RAIL_LASH_MS + delay):
                rail.update()
                self.assertTrue(rail.is_active())
                self.assertFalse(rail.hits_rect(rail.bounds()))
                poses.append(rail._rail_points())
        self.assertNotEqual(*poses)
        rail._hit_players.add(target)
        with patch.object(config, 'game_ticks', return_value=first_strike + RAIL_LASH_MS + RAIL_GAP_MS):
            rail.update()
            self.assertTrue(rail.hits_rect(rail.bounds()))
            self.assertNotIn(target, rail._hit_players)

    def test_emp_iron_balls_launch_then_burst_as_the_circle_closes(self):
        boss = self.boss(MechaLizardBoss)
        with patch.object(config, 'game_ticks', return_value=1000):
            ring, = boss._skill_shots('emp_ring', 0, 0)
        self.assertEqual((ring.x, ring.y), (config.SCREEN_WIDTH / 2, config.SCREEN_HEIGHT / 2))
        start = 1000 + ring.warning_ms
        for age in (0, 340, 3000, 3750, 4499, 4500, 4700):
            now = start + age
            with patch.object(config, 'game_ticks', return_value=now):
                ring.update()
                points = list(ring._emp_orbs())
                if age == 0:
                    self.assertLess(ring.ring_radius, 10)
                    self.assertFalse(points)
                elif age == 340:
                    point, = points
                    self.assertLess(math.dist((ring.x, ring.y), point), ring.ring_radius)
                    self.assertFalse(ring._emp_link_points())
                elif age == 3000:
                    span = min(config.GAME_AREA_RIGHT - config.GAME_AREA_LEFT, config.SCREEN_HEIGHT)
                    self.assertAlmostEqual(ring.ring_radius, (5 * ring.visual_scale + span * .192) * .8)
                    self.assertAlmostEqual(ring._emp_orb_radius(), 69 * ring.visual_scale)
                    self.assertEqual(len(points), 8)
                    full_radius = ring.ring_radius
                elif age < 4500:
                    self.assertEqual(ring.ring_radius, full_radius)
                    self.assertEqual(len(points), 8)
                    for x, y in points:
                        self.assertAlmostEqual(math.hypot(x - ring.x, y - ring.y), full_radius)
                    if age == 3750:
                        half_circle = len(ring._emp_link_points())
                        self.assertGreater(half_circle, 1)
                    else:
                        self.assertGreater(len(ring._emp_link_points()), half_circle)
                else:
                    self.assertEqual(len(points), 16)
                    self.assertAlmostEqual(ring._emp_orb_radius(), 3 * .6 * ring.r)
                    self.assertFalse(ring._emp_link_points())
                    if age > 4500:
                        self.assertTrue(all(math.dist((ring.x, ring.y), p) > full_radius for p in points))

    def test_emp_dash_reaches_center_and_hits_along_its_route(self):
        boss = self.boss(MechaLizardBoss)
        boss.x = config.SCREEN_WIDTH / 2 - 200
        boss._pending_attack_skill = 'emp_ring'
        before = boss.rect()
        with patch.object(config, 'game_ticks', return_value=1000):
            shot, = boss.attack(1000, 0)
        self.assertFalse(shot.is_active(1000))
        now = 1000 + shot.warning_ms
        with patch.object(config, 'game_ticks', return_value=now):
            boss.update()
            after = boss.rect()
            self.assertAlmostEqual(boss.x, shot.x)
            self.assertAlmostEqual(boss.y + boss.h / 2, shot.y)
            target = pygame.Rect(before.centerx, before.centery, 6, 6)
            self.assertFalse(after.colliderect(target))
            self.assertTrue(any(rect.colliderect(target) for rect in boss.hitboxes()))
            self.assertTrue(shot.is_active(now))

    def test_simulation_time_not_update_count_controls_straight_shots(self):
        with patch.object(config, 'game_ticks', return_value=1000):
            a = AbyssProjectile('ancient_pearl', 300, 100, speed=3, warning_ms=1000)
            b = AbyssProjectile('ancient_pearl', 300, 100, speed=3, warning_ms=1000)
        for now in range(2000, 2501, 10):
            with patch.object(config, 'game_ticks', return_value=now):
                a.update()
        with patch.object(config, 'game_ticks', return_value=2500):
            b.update()
        self.assertAlmostEqual(a.y, b.y)
        self.assertAlmostEqual(b.y, 129.25)

    def test_render_without_png_and_snapshot_fields_are_scalar(self):
        plain = pygame.Surface((960, 720), pygame.SRCALPHA)
        scaled = RenderSurface(pygame.Surface((480, 360), pygame.SRCALPHA),
                               (960, 720), (480, 360), (0, 0))
        with patch.dict(os.environ, {'TTGAMES_DISABLE_IMAGE_ASSETS': '1'}):
            for cls in (MechaLizardBoss, AncientWhaleBoss):
                boss = self.boss(cls)
                for i in range(4):
                    with patch.object(config, 'game_ticks', return_value=1000):
                        shots = boss.attack(1000, 480)
                        boss.draw(plain)
                        boss.draw(scaled)
                        for shot in shots:
                            for field in ABYSS_PROJECTILE_FIELDS:
                                self.assertIsInstance(getattr(shot, field), (int, float, str, bool))
                            shot.draw(plain)
                            shot.draw(scaled)
                    for shot in shots:
                        with patch.object(config, 'game_ticks', return_value=1000 + shot.warning_ms + 200):
                            shot.update(480, 650)
                            shot.draw(plain)
                            shot.draw(scaled)

    def test_death_clears_warning_and_active_projectiles(self):
        from game_core.game import Game
        for cls in (MechaLizardBoss, AncientWhaleBoss):
            game = Game.__new__(Game)
            game.boss = self.boss(cls)
            game.chapter = 0
            game.particles, game.explosions = [], []
            game.infinite_mode = False
            with patch.object(config, 'game_ticks', return_value=1000):
                game.boss_projectiles = game.boss.attack(1000, 480)
            game.boss.hp = 0
            with patch.object(game, '_heal_player'), patch.object(game, '_campaign_tier', return_value=1), \
                    patch.object(game, '_level_complete'), patch('game_core.game.play_sound'):
                self.assertTrue(game._settle_boss_if_killed())
            self.assertIsNone(game.boss)
            self.assertEqual(game.boss_projectiles, [])

    def test_each_skill_draws_and_leaves_escape_space_in_responsive_arenas(self):
        geometries = ((480, 720, 0, 480, 590, False),
                      (960, 540, 240, 720, 443, True),
                      (960, 720, 240, 720, 590, True))
        for width, height, left, right, bottom, landscape in geometries:
            with patch.multiple(config, SCREEN_WIDTH=width, SCREEN_HEIGHT=height,
                                GAME_AREA_LEFT=left, GAME_AREA_RIGHT=right,
                                GAME_AREA_BOTTOM=bottom, MOBILE_LANDSCAPE_VIEW=landscape):
                surface = pygame.Surface((width, height), pygame.SRCALPHA)
                scaled = RenderSurface(pygame.Surface((width // 2, height // 2), pygame.SRCALPHA),
                                       (width, height), (width // 2, height // 2), (0, 0))
                for cls in (MechaLizardBoss, AncientWhaleBoss):
                    boss = self.boss(cls)
                    for i in range(4):
                        with patch.object(config, 'game_ticks', return_value=1000):
                            shots = boss.attack(1000, (left + right) / 2)
                            for shot in shots:
                                self.assertGreaterEqual(shot.x, left)
                                self.assertLessEqual(shot.x, right)
                                shot.draw(surface)
                                shot.draw(scaled)
                        for now in range(1200, 7000, 200):
                            with patch.object(config, 'game_ticks', return_value=now):
                                for shot in shots:
                                    shot.update((left + right) / 2, bottom - 30)
                                    shot.draw(surface)
                                    shot.draw(scaled)
                                choices = [pygame.Rect(x, bottom - 55, 28, 28)
                                           for x in range(left + 25, right - 52, 8)]
                                self.assertTrue(any(not any(shot.hits_rect(rect) for shot in shots)
                                                    for rect in choices),
                                                (width, height, cls.__name__, boss.current_skill, now))

    def test_persistent_hazard_selects_each_player_only_once(self):
        from game_core.game import Game
        class TwoPlayerGame(Game):
            @property
            def players(self):
                return self.test_players
        class Target:
            def rect(self):
                return pygame.Rect(395, 300, 10, 20)
        game = TwoPlayerGame.__new__(TwoPlayerGame)
        first, second = Target(), Target()
        game.test_players = (first, second)
        with patch.object(config, 'game_ticks', return_value=1000):
            shot = AbyssProjectile('plasma_rail', 400, 200, warning_ms=1000)
            shot.height = 400
        with patch.object(config, 'game_ticks', return_value=2000 + RAIL_EXTEND_MS):
            shot.update()
            self.assertIs(game._hit_by_projectile(shot), first)
            shot._hit_players.add(first)
            self.assertIs(game._hit_by_projectile(shot), second)
            shot._hit_players.add(second)
            self.assertIsNone(game._hit_by_projectile(shot))
            self.assertTrue(shot.alive)

    def test_missile_png_preserves_aspect_and_nose_anchor(self):
        from game_core.asset_loader import image_asset
        from game_core.abyss_bosses import EFFECT_ASSETS
        image = image_asset(EFFECT_ASSETS['guided_missile'])
        if image is None:
            self.skipTest('Final PNG assets unavailable in this checkout')
        shot = AbyssProjectile('guided_missile', 200, 200, scale=.8)
        art, size, center = shot._missile_art(image)
        self.assertAlmostEqual(size[0] / size[1], image.get_width() / image.get_height())
        self.assertAlmostEqual(center[1] + size[1] * .4, shot.y)
        self.assertEqual(center[0], shot.x)

    def test_dead_boss_cannot_attack(self):
        for cls in (MechaLizardBoss, AncientWhaleBoss):
            boss = self.boss(cls)
            boss.hp = 0
            self.assertFalse(boss.should_attack(99999))
            self.assertEqual(boss.attack(99999, 480), [])


if __name__ == '__main__':
    unittest.main()
