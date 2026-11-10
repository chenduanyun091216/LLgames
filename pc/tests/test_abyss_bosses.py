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
                                    MechaLizardBoss, ABYSS_PROJECTILE_FIELDS)
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

    def test_all_eight_skills_warn_before_damage_and_expire(self):
        for cls in (MechaLizardBoss, AncientWhaleBoss):
            boss = self.boss(cls)
            seen = []
            for index in range(4):
                now = 10000 + index * 10000
                with patch.object(config, 'game_ticks', return_value=now):
                    shots = boss.attack(now, config.SCREEN_WIDTH * .6)
                    seen.append(boss.current_skill)
                    self.assertTrue(shots)
                    for shot in shots:
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
            self.assertEqual(tuple(seen), cls.SKILLS)
            with patch.object(config, 'game_ticks', return_value=60000):
                boss.attack(60000, 480)
                self.assertEqual(boss.current_skill, cls.SKILLS[0])

    def test_ring_center_and_gap_safe_but_annulus_damages(self):
        with patch.object(config, 'game_ticks', return_value=1000):
            shot = AbyssProjectile('sonar_ring', 400, 200, warning_ms=1000)
        with patch.object(config, 'game_ticks', return_value=3000):
            shot.update()
            radius = round(shot.ring_radius)
            self.assertFalse(shot.hits_rect(pygame.Rect(395, 195, 10, 10)))
            self.assertFalse(shot.hits_rect(pygame.Rect(395, 200 + radius - 5, 10, 10)))
            self.assertTrue(shot.hits_rect(pygame.Rect(400 + radius - 5, 195, 10, 10)))
            self.assertTrue(shot.persistent)
            self.assertTrue(shot.unblockable)

    def test_lane_warning_does_not_retarget(self):
        boss = self.boss(MechaLizardBoss)
        with patch.object(config, 'game_ticks', return_value=1000):
            rail = boss.attack(1000, 300)[0]
        with patch.object(config, 'game_ticks', return_value=2600):
            rail.update(700, 600)
            self.assertEqual(rail.x, 300)
            self.assertTrue(rail.hits_rect(pygame.Rect(295, 400, 10, 10)))
            self.assertFalse(rail.hits_rect(pygame.Rect(600, 400, 10, 10)))
            self.assertEqual(rail.damage, 2)

    def test_missile_turn_is_limited_and_stops(self):
        with patch.object(config, 'game_ticks', return_value=1000):
            shot = AbyssProjectile('guided_missile', 400, 150, speed=3, warning_ms=1000)
        for now in range(2000, 2701, 20):
            previous = shot.angle
            with patch.object(config, 'game_ticks', return_value=now):
                shot.update(800, 600)
            self.assertLessEqual(abs(shot.angle - previous), .761)
        angle = shot.angle
        with patch.object(config, 'game_ticks', return_value=2800):
            shot.update(0, 600)
        self.assertEqual(shot.angle, angle)
        self.assertFalse(shot.unblockable)
        self.assertFalse(shot.persistent)

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
        self.assertAlmostEqual(b.y, 190)

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
        with patch.object(config, 'game_ticks', return_value=2200):
            shot.update()
            self.assertIs(game._hit_by_projectile(shot), first)
            shot._hit_players.add(first)
            self.assertIs(game._hit_by_projectile(shot), second)
            shot._hit_players.add(second)
            self.assertIsNone(game._hit_by_projectile(shot))
            self.assertTrue(shot.alive)

    def test_final_png_ring_collision_is_inside_visible_band(self):
        from game_core.asset_loader import image_asset
        from game_core.abyss_bosses import EFFECT_ASSETS
        for skill in ('emp_ring', 'sonar_ring'):
            if image_asset(EFFECT_ASSETS[skill]) is None:
                self.skipTest('Final PNG assets unavailable in this checkout')
            for radius in (24, 100, 250, 400, 600):
                with patch.object(config, 'game_ticks', return_value=1000):
                    shot = AbyssProjectile(skill, 800, 800, scale=.8,
                                           warning_ms=1000, active_ms=10000)
                now = 2000 + (radius - 24 * .8) / shot.ring_speed * 1000
                with patch.object(config, 'game_ticks', return_value=now):
                    shot.update()
                    surface = pygame.Surface((1600, 1600), pygame.SRCALPHA)
                    shot.draw(surface)
                    for angle in range(0, 360, 10):
                        if skill == 'sonar_ring' and abs((angle + 180) % 360 - 180) < 45:
                            continue
                        for offset in (-.30, 0, .30):
                            r = shot.ring_radius + shot.ring_thickness * offset
                            x = round(800 + math.sin(math.radians(angle)) * r)
                            y = round(800 + math.cos(math.radians(angle)) * r)
                            self.assertGreaterEqual(surface.get_at((x, y)).a, 24,
                                                    (skill, radius, angle, offset))

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
