"""Setup-state regression tests, not an end-to-end human campaign playthrough."""
import random
import unittest
from unittest.mock import patch
import pygame
from game_core import config
from game_core import game as core
from game_core.entities import BossProjectile
from online.adapters.core_adapter import OnlineGame, SharedReturningAxe


class CampaignAdapterTests(unittest.TestCase):
    def boss_game(self, level, difficulty='medium'):
        game = OnlineGame(difficulty)
        game._start_level(level)
        if not game.boss:
            game._trigger_boss()
        game.boss.entered = True
        game.boss.y = 60
        game.boss.fight_start_time = -6000
        return game

    def stack(self, game, x, y):
        for p in game.all_players:
            p.x, p.y = x, y
            p.invincible_until = 0

    def test_all_eleven_shared_boss_classes_and_short_ai_runs(self):
        rng = random.getstate()
        try:
            random.seed(47)
            for level in range(1, len(config.LEVEL_CONFIGS) + 1):
                with self.subTest(level=level):
                    game = self.boss_game(level)
                    expected = config.BOSS_DEFS[config.LEVEL_CONFIGS[level-1]['boss_idx']]['key']
                    self.assertEqual(game.boss.bdef['key'], expected)
                    self.assertFalse(game.infinite_mode)
                    for p in game.all_players:
                        p.hp = p.max_hp = 10000
                    for _ in range(1200):
                        # Abyss bite is intentionally lethal regardless of HP.
                        for p in game.all_players:
                            if not p.alive:
                                game.lives += 1
                                game.action(p.slot, 'revive')
                                p.hp = p.max_hp = 10000
                        game.step()
                    self.assertEqual(game.tick, 1200)
                    self.assertEqual(game.phase, 'playing')
        finally:
            random.setstate(rng)

    def test_signatures_preserve_original_geometry_and_per_player_hits(self):
        for level in (1, 3, 4, 6):
            with self.subTest(level=level):
                game = self.boss_game(level)
                game.boss.laser_warning_start = game.boss.laser_active_until = 0
                self.assertTrue(game._try_boss_signature(0, opening=True))
                sig = game.boss.signature
                now = 300
                sig.move(game.boss, now, game.player)
                if level == 1:
                    x, y, _ = sig._claws(now)[0]
                elif level == 3:
                    x, y, _ = list(sig._tentacles(game.boss, now))[0][12]
                elif level == 4:
                    _, x, y = sig._tridents(now)[0]
                else:
                    x, y = game.boss.x, game.boss.y + game.boss.h * .80
                self.stack(game, x, y)
                game._update_boss_signature(now)
                p1, p2 = game.all_players
                self.assertLess(p1.hp, 5)
                self.assertEqual(p1.hp, p2.hp)
                if level == 6:
                    self.assertFalse(p1.alive or p2.alive)
                    self.assertTrue(game.paused)

    def test_crab_bubbles_release_two_summons_once_and_chase_living_player(self):
        game = self.boss_game(2)
        game._try_boss_signature(0, opening=True)
        game._update_boss_signature(900)
        self.assertEqual(len(game.enemies), 2)
        game._update_boss_signature(910)
        self.assertEqual(len(game.enemies), 2)
        a, b = game.enemies
        self.assertIs(a.chase_partner, b)
        game.all_players[0].alive = False
        self.assertIs(game._nearest_player(a.x, a.y), game.all_players[1])

    def test_dragon_signature_emits_original_fireballs_once_per_tick(self):
        game = self.boss_game(5)
        game._try_boss_signature(0, opening=True)
        game._update_boss_signature(0)
        self.assertEqual(len(game.boss_projectiles), 1)
        self.assertIsInstance(game.boss_projectiles[0], core.DragonFireball)
        game._update_boss_signature(0)
        self.assertEqual(len(game.boss_projectiles), 1)
        game._update_boss_signature(400)
        self.assertEqual(len(game.boss_projectiles), 2)

    def test_abyss_restores_origin_and_delays_next_signature(self):
        game = self.boss_game(6)
        game.boss.laser_warning_start = game.boss.laser_active_until = 0
        game._try_boss_signature(0, opening=True)
        sig = game.boss.signature
        origin = game.boss.x, game.boss.y
        game._update_boss_signature(100)
        game._update_boss_signature(sig.end_at)
        self.assertIsNone(game.boss.signature)
        self.assertEqual((game.boss.x, game.boss.y), origin)
        self.assertEqual(game.boss.next_signature_time, sig.end_at + 10000)

    def test_all_boss_direct_projectiles_hit_actual_player_two(self):
        for level in range(1, len(config.LEVEL_CONFIGS) + 1):
            with self.subTest(level=level):
                game = self.boss_game(level)
                p1, p2 = game.all_players
                p1.alive = False
                shot = BossProjectile(p2.x, p2.y, 0, 0, damage=1)
                game._add_boss_projectiles([shot])
                game.step()
                self.assertEqual(p2.hp, 4)
                self.assertEqual(p1.hp, 5)

    def test_niu_and_zong_bomb_areas_damage_both_and_skip_dead(self):
        for level in (7, 8):
            game = self.boss_game(level)
            self.stack(game, 480, 600)
            shot = (core.ReturningAxe(game.boss, 1, 480, False) if level == 7 else
                    core.ZongBomb(480, 600, 0, 0, damage=2))
            shot.x, shot.y = 480, 600
            game._explode_enemy_bomb(shot, 100)
            self.assertEqual(game.all_players[0].hp, game.all_players[1].hp)
            self.assertLess(game.all_players[1].hp, 5)
            self.assertEqual(len(game.explosions), 1)
            if level == 7:
                self.assertEqual(game.all_players[1].niu_freeze_until, 400)
                self.assertEqual(game.all_players[0].niu_slow_until, 1600)
            game.all_players[0].alive = False
            game.all_players[1].invincible_until = 0
            old_hp = game.all_players[0].hp
            game._explode_enemy_bomb(shot, 200)
            self.assertEqual(game.all_players[0].hp, old_hp)

    def test_returning_axe_body_cooldown_is_per_victim_and_core_class_unchanged(self):
        game = self.boss_game(7)
        original = core.ReturningAxe(game.boss, 1, 480, True)
        game._add_boss_projectiles([original])
        axe = game.boss_projectiles[-1]
        self.assertIs(type(original), core.ReturningAxe)
        self.assertIsInstance(axe, SharedReturningAxe)
        for p in game.all_players:
            game._damage_target = p
            self.assertEqual(axe.last_player_hit, -9999)
            axe.last_player_hit = p.slot * 100
        for p in game.all_players:
            game._damage_target = p
            self.assertEqual(axe.last_player_hit, p.slot * 100)
        game._damage_target = None
        self.assertEqual(axe.last_player_hit, -9999)

    def test_niu_ground_slam_hits_both_once_per_strike(self):
        game = self.boss_game(7)
        game.boss.axe_slam_start = 0
        self.stack(game, game.boss.x, 600)
        game._update_special_boss_hazards(1100)
        self.assertEqual([p.hp for p in game.all_players], [4, 4])
        for p in game.all_players:
            p.invincible_until = 0
        game._update_special_boss_hazards(1200)
        self.assertEqual([p.hp for p in game.all_players], [4, 4])

    def test_niu_lightning_hits_both_on_original_tick_cadence(self):
        game = self.boss_game(7)
        boss = game.boss
        boss.lightning_xs = (480,)
        boss.lightning_until = 2000
        boss.lightning_warning_until = boss.lightning_next_tick = 100
        self.stack(game, 480, 600)
        game._update_special_boss_hazards(100)
        self.assertEqual([p.hp for p in game.all_players], [3, 3])
        self.assertEqual(boss.lightning_next_tick, 750)
        for p in game.all_players:
            p.invincible_until = 0
        game._update_special_boss_hazards(101)
        self.assertEqual([p.hp for p in game.all_players], [3, 3])

    def test_death_laser_hits_each_player_once_per_activation(self):
        for level in (6, 7):
            game = self.boss_game(level)
            game.boss.laser_active_until = 2000
            now = 100
            if level == 7:
                x, _ = game.boss.laser_paths(now)[0][-3]
            else:
                x = game.boss.death_laser_rects(now)[0].centerx
            self.stack(game, x, 600)
            game._damage_player_on_contacts(now)
            self.assertEqual([p.hp for p in game.all_players], [4, 4])
            for p in game.all_players:
                p.invincible_until = 0
            game._damage_player_on_contacts(now + 10)
            self.assertEqual([p.hp for p in game.all_players], [4, 4])

    def test_orochi_slam_split_and_laser_geometry_hits_both(self):
        for skill in ('slam', 'split', 'laser'):
            with self.subTest(skill=skill):
                game = self.boss_game(11)
                boss = game.boss
                boss._start_skill(skill, 0)
                now = boss.SLAM_IMPACT if skill == 'slam' else boss.LASER_WARNING if skill == 'laser' else 100
                if skill == 'slam':
                    x, y = boss._lane_x(boss._slam_pair(0)[0]), config.GAME_AREA_BOTTOM - 20
                elif skill == 'split':
                    x, y = boss.split_positions()[0]
                    y -= 40
                else:
                    x, _ = boss.laser_paths(now)[0][-1]
                    y = 600
                self.stack(game, x, y)
                self.assertTrue(boss.hazard_hits(game.player.rect(), now))
                game._update_special_boss_hazards(now)
                self.assertEqual([p.hp for p in game.all_players], [3, 3])
                for p in game.all_players:
                    p.invincible_until = 0
                game._update_special_boss_hazards(now)
                self.assertEqual([p.hp for p in game.all_players], [3, 3])

    def test_orochi_special_contact_exclusions(self):
        for skill in ('split', 'storm', 'laser'):
            game = self.boss_game(11)
            game.boss._start_skill(skill, 0)
            body = game.boss.hitboxes()[0]
            self.stack(game, body.centerx, body.centery)
            game._damage_player_on_contacts(0)
            self.assertEqual([p.hp for p in game.all_players], [5, 5])

    def test_original_niu_shield_and_zong_fusion_remain_authoritative(self):
        game = self.boss_game(7)
        boss = game.boss
        boss.hit_by('pistol', boss.max_hp * .4)
        self.assertGreater(boss.shield_until, 0)
        self.assertTrue(boss.shield_triggered)
        game = self.boss_game(8)
        boss = game.boss
        boss.fusion_mode = 'shield'
        before = boss.hp
        boss.hit_by('pistol', 100)
        self.assertEqual(boss.hp, before)
        boss.fusion_mode = 'rage'
        bodies = list(boss.body_hp)
        boss.hit_by('pistol', 10)
        self.assertTrue(all(a < b for a, b in zip(boss.body_hp, bodies)))

    def test_orochi_threshold_and_death_animation_precede_victory(self):
        game = self.boss_game(11)
        boss = game.boss
        boss.hit_by('pistol', boss.max_hp)
        self.assertEqual(boss.skill, 'storm')
        self.assertEqual(boss.hp, boss.max_hp * .5)
        boss._start_death(0)
        game._settle_boss_if_killed()
        self.assertEqual(game.phase, 'playing')
        config.campaign_time_ms = boss.DEATH_DURATION
        game._settle_boss_if_killed()
        self.assertEqual(game.phase, 'won')
        tick = game.tick
        game.step()
        self.assertEqual(game.tick, tick)

    def test_boss_clear_heals_each_survivor_but_never_revives(self):
        game = self.boss_game(1)
        p1, p2 = game.all_players
        p1.hp, p2.hp = 1, 2
        game._kill_boss()
        self.assertEqual((p1.hp, p2.hp), (3, 4))
        game = self.boss_game(1)
        p1, p2 = game.all_players
        p1.hp, p2.hp, p2.alive = 1, 0, False
        game._kill_boss()
        self.assertEqual((p1.hp, p2.hp), (3, 0))
        self.assertFalse(p2.alive)

    def test_world_primary_context_does_not_override_water_or_wounded_healing(self):
        game = self.boss_game(1)
        p1, p2 = game.all_players
        p2.character = 'water'
        p1.hp, p2.hp = 1, 2
        with game._for_player(p1, focus=False):
            game._heal_player(1)
        self.assertEqual((p1.hp, p2.hp), (1, 3))
        p2.character = None
        p1.hp, p2.hp = 4, 1
        with game._for_player(p1, focus=False):
            game._heal_player(1)
        self.assertEqual((p1.hp, p2.hp), (4, 2))

    def test_orochi_sound_capture_restores_both_bindings_even_on_error(self):
        from game_core import orochi
        game = self.boss_game(11)
        original = core.play_sound, orochi.play_sound
        with self.assertRaises(RuntimeError):
            with game._capture_sounds():
                orochi.play_sound('thunder')
                core.play_sound('hit')
                raise RuntimeError('test unwind')
        self.assertEqual((core.play_sound, orochi.play_sound), original)
        self.assertEqual([e['key'] for e in list(game._events)[-2:]], ['thunder', 'hit'])

    def test_crab_summon_original_contact_grace_applies_to_both(self):
        game = self.boss_game(2)
        game._try_boss_signature(0, opening=True)
        game._update_boss_signature(900)
        crab = game.enemies[0]
        self.stack(game, crab.x, crab.y + 10)
        game._damage_player_on_contacts(901)
        self.assertEqual([p.hp for p in game.all_players], [5, 5])
        game._damage_player_on_contacts(1350)
        self.assertEqual([p.hp for p in game.all_players], [4, 4])

    def test_special_projectile_types_hit_living_player_two(self):
        from game_core.special_bosses import NiuFanBullet, ZongFireball, ZongReflectBullet
        from game_core.orochi import OrochiFireball
        cases = (
            (5, lambda x, y: core.DragonFireball(x, y, 1)),
            (7, lambda x, y: NiuFanBullet(x, y, 0, True)),
            (7, lambda x, y: NiuFanBullet(x, y, 0, False)),
            (8, lambda x, y: core.CrescentWave(x, y)),
            (8, lambda x, y: ZongFireball(x, y, 0, 0, damage=1)),
            (8, lambda x, y: ZongReflectBullet(x, y)),
            (11, lambda x, y: OrochiFireball(x, y, (255, 58, 43), None)),
        )
        for level, factory in cases:
            game = self.boss_game(level)
            p1, p2 = game.all_players
            p1.alive = False
            shot = factory(p2.x, p2.y)
            game._add_boss_projectiles([shot])
            game.step()
            self.assertLess(p2.hp, 5, type(shot).__name__)
            self.assertEqual(p1.hp, 5)

    def test_persistent_axe_hits_both_bodies_on_successive_core_frames(self):
        game = self.boss_game(7)
        game.boss.fight_start_time = 0  # isolate the axe from randomized opening attacks
        game.last_spawn_time = 10**9
        shot = core.ReturningAxe(game.boss, 1, 480, True)
        game._add_boss_projectiles([shot])
        axe = game.boss_projectiles[-1]
        config.campaign_time_ms = 600
        axe.update()
        self.stack(game, axe.x, axe.y)
        game.tick = 35
        game.step()
        game.step()
        self.assertEqual([p.hp for p in game.all_players], [3, 3])
        self.assertEqual(set(axe._player_hits), {1, 2})

    def test_zong_snow_only_slows_living_players(self):
        game = self.boss_game(8)
        p1, p2 = game.all_players
        p1.alive = False
        game.boss.snow_until = 2000
        game.step()
        self.assertEqual(p1.snow_slow_until, 0)
        self.assertGreaterEqual(p2.snow_slow_until, 2000)

    def test_transition_preserves_shared_resources_equipment_and_death(self):
        game = self.boss_game(1)
        p1, p2 = game.all_players
        p1.gold = 123
        p1.owned_weapons.append('rifle')
        p1.current_weapon = 'rifle'
        p2.hp = 0
        p2.alive = False
        game._level_complete()
        game.set_input(1, 1, 0, True)
        x = p1.x
        for _ in range(120):
            game.step()
        self.assertEqual(game.current_level, 2)
        self.assertEqual(game.gold, 123 + config.CAMPAIGN_REWARDS[0])
        self.assertEqual(game.lives, 5)
        self.assertEqual(p1.current_weapon, 'rifle')
        self.assertFalse(p2.alive)
        self.assertEqual(p1.x, x)
        self.assertIs(p1.owned_weapons, p2.owned_weapons)


if __name__ == '__main__':
    unittest.main()
