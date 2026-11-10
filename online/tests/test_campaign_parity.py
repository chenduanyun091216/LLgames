"""Shared-core numerical parity at the same logical geometry, not browser QA."""
import json
import random
import unittest
from unittest.mock import patch
import pygame
from game_core import config
from game_core.game import Game, GameState
from online.adapters.core_adapter import OnlineGame, fixed_world
from online.adapters.presentation import Presentation
from online.shared.world import WORLD_SIZES


class CampaignParityTests(unittest.TestCase):
    def test_all_levels_and_difficulties_share_spawn_and_boss_numbers(self):
        for orientation, size in WORLD_SIZES.items():
            for difficulty in ('easy', 'medium', 'hard'):
                for level in range(1, len(config.LEVEL_CONFIGS) + 1):
                    with self.subTest(orientation=orientation, difficulty=difficulty, level=level):
                        online = OnlineGame(difficulty, orientation=orientation)
                        online_geometry = (config.GAME_AREA_LEFT, config.GAME_AREA_RIGHT,
                                           config.GAME_AREA_BOTTOM, config.MOBILE_LANDSCAPE_VIEW)
                        # Actual PC/Web entrypoint layout, NOT an online helper.
                        config.update_mobile_view(size)
                        self.assertEqual(online_geometry, (config.GAME_AREA_LEFT,
                            config.GAME_AREA_RIGHT, config.GAME_AREA_BOTTOM, config.MOBILE_LANDSCAPE_VIEW))
                        single = Game(desktop_controls=False)
                        single._start_game(difficulty)
                        self.assertEqual(single.player.rect().size, online.player.rect().size)
                        random.seed(842)
                        single._start_level(level, checkpoint=False)
                        random.seed(842)
                        online._start_level(level)
                        self.assertEqual(single.spawn_interval, online.spawn_interval)
                        self.assertEqual(single.level_enemy_defs, online.level_enemy_defs)
                        self.assertEqual(single.large_enemy_slots, online.large_enemy_slots)
                        self.assertEqual(single._campaign_value(config.CAMPAIGN_KILLS),
                                         online._campaign_value(config.CAMPAIGN_KILLS))
                        if level != 11:
                            for game in (single, online):
                                random.seed(334)
                                game._spawn_campaign_enemy()
                            for attr in ('w', 'h', 'max_hp', 'speed', 'attack_interval', 'x', 'y'):
                                self.assertEqual(getattr(single.enemies[-1], attr),
                                                 getattr(online.enemies[-1], attr))
                        for game in (single, online):
                            random.seed(23)
                            if not game.boss:
                                game._trigger_boss()
                        self.assertIs(type(single.boss), type(online.boss))
                        self.assertEqual(single.boss.bdef, online.boss.bdef)
                        for attr in ('hp', 'max_hp', 'speed', 'attack_interval', 'projectile_count', 'w', 'h', 'size_scale'):
                            self.assertEqual(getattr(single.boss, attr), getattr(online.boss, attr))
                        raw = json.dumps(online.snapshot(), allow_nan=False)
                        for slot in (1, 2):
                            view = Presentation(pygame.Surface(size))
                            view.apply(json.loads(raw), slot)
                            self.assertEqual(view.view.boss.bdef, json.loads(json.dumps(online.boss.bdef)))
                            self.assertEqual(view.view.boss.hp, online.boss.hp)
                            self.assertEqual(view.view.player.rect().size, single.player.rect().size)

    def test_final_stage_is_boss_immediately_and_new_stages_have_waves(self):
        game = OnlineGame()
        self.assertEqual(len(config.LEVEL_CONFIGS), 11)
        for level in (9, 10):
            game._start_level(level)
            self.assertIsNone(game.boss)
            self.assertEqual(game.state, GameState.PLAYING)
            self.assertEqual(len(game.level_enemy_defs), 3)
        game._start_level(11)
        self.assertEqual(game.state, GameState.BOSS_FIGHT)
        self.assertEqual(game.boss.bdef['key'], 'boss_orochi')
        self.assertEqual(game.snapshot()['total_levels'], 11)

    def test_clients_never_run_combat(self):
        for level in (9, 10):
            game = OnlineGame()
            game._start_level(level)
            game._trigger_boss()
            raw = json.dumps(game.snapshot())
            with patch.object(Game, 'update', side_effect=AssertionError('client physics')):
                for slot in (1, 2):
                    view = Presentation(pygame.Surface((960, 720)))
                    view.apply(json.loads(raw), slot)
                    view.draw()

    def test_factory_link_and_merged_boss_are_visible_to_both_clients(self):
        game = OnlineGame()
        game._start_level(9)
        for index in range(3):
            game._spawn_campaign_enemy()
            game.enemies[-1].x, game.enemies[-1].y = 300 + index * 140, 120
        with patch('game_core.game.random.random', return_value=.25):
            game._start_factory_link(1000)
        views = [Presentation(pygame.Surface((960, 720))) for _ in range(2)]
        linked_snapshot = json.loads(json.dumps(game.snapshot()))
        for slot, view in enumerate(views, 1):
            view.apply(linked_snapshot, slot)
            self.assertEqual([e.factory_link_until for e in view.view.enemies], [3000] * 3)
            view.draw()

        game._settle_factory_link(3000)
        mini, = game.enemies
        game.enemy_projectiles.extend(game._enemy_shots(mini, 4000))
        merged_snapshot = json.loads(json.dumps(game.snapshot()))
        for slot, view in enumerate(views, 1):
            view.apply(merged_snapshot, slot)
            restored, = view.view.enemies
            self.assertEqual(restored.factory_kind, 'mini_boss')
            self.assertEqual(restored.sprite_asset, 'bosses/boss_mecha_lizard.png')
            self.assertEqual(restored.max_hp, mini.max_hp)
            self.assertEqual([p.missile_pass for p in view.view.enemy_projectiles], [2] * 3)
            view.draw()

    def test_each_new_skill_matches_shared_attack_and_json_render(self):
        from game_core.abyss_bosses import AbyssProjectile
        for orientation, size in WORLD_SIZES.items():
            for difficulty in ('easy', 'medium', 'hard'):
                for level in (9, 10):
                    game = OnlineGame(difficulty, orientation=orientation)
                    game._start_level(level)
                    game._trigger_boss()
                    boss = game.boss
                    boss.entered, boss.y, boss.fight_start_time = True, 60, 0
                    config.update_mobile_view(size)
                    single = Game(desktop_controls=False)
                    single._start_game(difficulty)
                    single._start_level(level, checkpoint=False)
                    single._trigger_boss()
                    shared = single.boss
                    shared.entered, shared.x, shared.y = True, boss.x, boss.y
                    for skill_index, skill in enumerate(boss.SKILLS):
                        config.campaign_time_ms = 10000 + skill_index * 10000
                        random.seed(57)
                        shots = boss.attack(config.game_ticks(), 480, 600)
                        random.seed(57)
                        expected = shared.attack(config.game_ticks(), 480, 600)
                        self.assertTrue(shots, skill)
                        self.assertEqual(len(shots), len(expected))
                        for a, b in zip(shots, expected):
                            self.assertIs(type(a), AbyssProjectile)
                            self.assertEqual(a.__dict__, b.__dict__)
                        game.boss_projectiles = shots
                        times = (0, 1300, 3600, 4200, 5100) if skill == 'emp_ring' else (0, 1300, 2300)
                        for elapsed in times:
                            config.campaign_time_ms = 10000 + skill_index * 10000 + elapsed
                            for shot in shots:
                                shot.update(480, 600)
                            raw = json.dumps(game.snapshot(), allow_nan=False)
                            self.assertNotIn('_hit_players', raw)
                            for slot in (1, 2):
                                view = Presentation(pygame.Surface(size))
                                view.apply(json.loads(raw), slot)
                                for source, restored in zip(shots, view.view.boss_projectiles):
                                    self.assertEqual(source.damage, restored.damage)
                                    self.assertEqual(source.skill, restored.skill)
                                    a = pygame.Surface((960, 720), pygame.SRCALPHA)
                                    b = a.copy()
                                    source.draw(a)
                                    restored.draw(b)
                                    self.assertEqual(pygame.image.tostring(a, 'RGBA'),
                                                     pygame.image.tostring(b, 'RGBA'))
                                view.draw()

    def test_new_projectile_damage_matches_single_and_hits_each_player_once(self):
        from game_core.abyss_bosses import AbyssProjectile, EFFECT_ASSETS, RAIL_EXTEND_MS, RINGS, LANES
        for difficulty in ('easy', 'medium', 'hard'):
            for skill in EFFECT_ASSETS:
                with self.subTest(difficulty=difficulty, skill=skill):
                    game = OnlineGame(difficulty)
                    game._start_level(9)
                    game._trigger_boss()
                    game.boss.entered, game.boss.y = True, 60
                    game.boss.fight_start_time = 0
                    game.last_spawn_time = 10**9
                    game.tick = 60
                    config.campaign_time_ms = 1000
                    damage = game.boss.bdef['damage_cap']
                    shot = AbyssProjectile(skill, 480, 550, warning_ms=0,
                                           active_ms=10000, damage=damage)
                    if skill in LANES:
                        shot.height = 110
                    if skill == 'rune_geyser':
                        shot.spawn_time -= 200
                    for p in game.all_players:
                        p.x, p.y = 480, 575 if skill in RINGS else 550
                    if skill == 'plasma_rail':
                        shot.spawn_time -= RAIL_EXTEND_MS
                        game.boss.sync_weapon_mount(shot, config.game_ticks())
                        for p in game.all_players:
                            p.x, p.y = shot.x, shot.y + 75
                    if skill == 'sonar_ring':
                        shot.gap_angle = 180  # keep both bodies outside safe sector
                    if skill == 'emp_ring':
                        shot.spawn_time -= 400
                        for p in game.all_players:
                            p.x, p.y = shot.x, shot.y
                    game._add_boss_projectiles([shot])
                    initial = game.player.hp
                    game.step()
                    self.assertEqual(game.all_players[0].hp, initial - damage)
                    game.step()
                    expected_second = initial - damage if shot.persistent else initial
                    self.assertEqual(game.all_players[1].hp, expected_second)
                    for p in game.all_players:
                        p.invincible_until = 0
                    game.step()
                    self.assertEqual([p.hp for p in game.all_players],
                                     [initial - damage, expected_second])
                    # The unmodified single-player damage function takes exactly
                    # the same damage and invincibility duration as the server.
                    single = Game(desktop_controls=False)
                    single._start_game(difficulty)
                    single._damage_player(1000, damage, 'fixture')
                    self.assertEqual(single.player_hp, initial - damage)
                    self.assertEqual(single.player_invincible_until - 1000,
                                     (850, 650, 550)[game._campaign_tier()])

    def test_precise_projectile_selection_excludes_dead_hit_and_invincible_teammate(self):
        from game_core.abyss_bosses import AbyssProjectile, RAIL_EXTEND_MS
        game = OnlineGame()
        config.campaign_time_ms = 1000
        p1, p2 = game.all_players
        p1.x = p2.x = 480
        p1.y = p2.y = 550
        shot = AbyssProjectile('plasma_rail', 480, 500, warning_ms=0)
        shot.height = 160
        config.campaign_time_ms = 1000 + RAIL_EXTEND_MS
        shot.update()
        p1.invincible_until = 2000
        self.assertIs(game._hit_by_projectile(shot), p2)
        shot._hit_players.add(p2)
        self.assertIs(game._hit_by_projectile(shot), p1)
        p1.alive = False
        self.assertIsNone(game._hit_by_projectile(shot))


if __name__ == '__main__':
    unittest.main()
